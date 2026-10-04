"""Dataset: selaraskan rencana WellPlan ke kedalaman titik aktual, bentuk fitur,
bekukan versi (hash + snapshot), dan kunci set blind test.

Keputusan terkait (docs/keputusan.md): K-05 sumber data, K-06 baseline & FF fitur,
K-07 data kosong & outlier, K-08 rentang kedalaman, K-20 fitur tambahan, K-21 versi data,
K-22 blind test.
"""

import gzip
import hashlib
import io
import re

import numpy as np
import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import ActualReading, BlindSet, Dataset, PlanResult, Survey, UploadedFile, Well
from app.services.calibration import CAL_FEATURE, offset_si
from app.services.operations import BASELINE_FF, HOOKLOAD_OPS, OPERATIONS
from app.services.units import FT_TO_M

FF_COLS = {0.3: "wp_ff03", 0.5: "wp_ff05"}
BASE_NUMERIC = ["depth_m", "wp_ff03", "wp_ff05", "wp_slope", "wp_rot"]
BASE_CATEGORICAL = ["section", "well_type", "plan_format"]
# Grup fitur tambahan: dipertahankan hanya bila terbukti membantu (uji manfaat di training)
FEATURE_GROUPS: dict[str, dict[str, list[str]]] = {
    "survey": {"num": ["inc_deg", "dls_deg_30m", "tortuosity"], "cat": []},
    "casing_shoe": {"num": ["open_hole_len_m", "open_hole_frac"], "cat": []},
    "bha_mud": {"num": ["mud_weight_ppg", "bha_weight_klbf", "bha_length_ft"], "cat": []},
    "kop_interval": {"num": ["depth_from_kop_m"], "cat": ["interval_type"]},
    "block_weight": {"num": ["block_weight_klbf"], "cat": []},
    # Koreksi "Calibrate" dari DD (file roadmap); grup tersendiri, dipakai hanya bila terbukti membantu
    "calibration": {"num": ["dd_calibration"], "cat": []},
}
OUTLIER_MAD = 5.0
VERTICAL_INC, HORIZONTAL_INC, BUILD_RATE = 3.0, 80.0, 1.0  # deg, deg, deg/100ft


def feature_columns(groups: list[str]) -> tuple[list[str], list[str]]:
    num, cat = list(BASE_NUMERIC), list(BASE_CATEGORICAL)
    for g in groups:
        num += FEATURE_GROUPS[g]["num"]
        cat += FEATURE_GROUPS[g]["cat"]
    return num, cat


# ---------------------------------------------------------------- pemuatan


def load_wells(db: Session, well_ids: list[int] | None = None) -> pd.DataFrame:
    q = select(Well)
    if well_ids is not None:
        q = q.where(Well.id.in_(well_ids))
    rows = []
    for w in db.scalars(q):
        m = w.meta or {}
        shoe = m.get("casing_shoe")
        if shoe is not None and m.get("casing_shoe_unit", "ft") == "ft":
            shoe = shoe * FT_TO_M
        rows.append(
            {
                "well_id": w.id,
                "well_name": w.name,
                "section": None if w.section_in is None else f"{w.section_in:g}",
                "well_type": w.well_type,
                "plan_format": m.get("plan_format") or "unknown",
                "casing_shoe_m": shoe,
                "block_weight_klbf": m.get("block_weight_klbf"),
                "mud_weight_ppg": m.get("mud_weight_ppg"),
                "bha_weight_klbf": m.get("bha_weight_klbf"),
                "bha_length_ft": m.get("bha_length_ft"),
                **{col: offset_si(m, op) for op, col in CAL_FEATURE.items()},
            }
        )
    cols = [
        "well_id",
        "well_name",
        "section",
        "well_type",
        "plan_format",
        "casing_shoe_m",
        "block_weight_klbf",
        "mud_weight_ppg",
        "bha_weight_klbf",
        "bha_length_ft",
        *CAL_FEATURE.values(),
    ]
    return pd.DataFrame(rows, columns=cols)


def load_plan(db: Session, well_ids: list[int]) -> pd.DataFrame:
    q = select(
        PlanResult.well_id,
        PlanResult.operation,
        PlanResult.ff,
        PlanResult.source_sheet,
        PlanResult.depth_m,
        PlanResult.value_si,
    ).where(PlanResult.well_id.in_(well_ids))
    return pd.DataFrame(
        db.execute(q).all(), columns=["well_id", "operation", "ff", "sheet", "depth_m", "value_si"]
    )


def load_actual(db: Session, well_ids: list[int]) -> pd.DataFrame:
    q = select(
        ActualReading.well_id,
        ActualReading.operation,
        ActualReading.source_sheet,
        ActualReading.depth_m,
        ActualReading.value_si,
    ).where(ActualReading.well_id.in_(well_ids))
    df = pd.DataFrame(
        db.execute(q).all(), columns=["well_id", "operation", "sheet", "depth_m", "actual_si"]
    )
    if df.empty:
        return df
    # nilai tidak wajar fisik dibuang (hookload <= 0, torsi < 0)
    hk = df.operation.isin(HOOKLOAD_OPS)
    df = df[(hk & (df.actual_si > 0)) | (~hk & (df.actual_si >= 0))]
    # Tripping Data hanya pengganti bila operasi itu tidak ada di sheet utama (K-05)
    df = df.assign(primary=~df.sheet.str.lower().str.match(r"^tripping\s+data"))
    has_primary = df[df.primary].groupby(["well_id", "operation"]).size()
    keep = df.apply(
        lambda r: r.primary or (r.well_id, r.operation) not in has_primary.index, axis=1
    )
    df = df[keep].drop(columns=["primary"])
    return df.groupby(["well_id", "operation", "depth_m"], as_index=False).agg(
        actual_si=("actual_si", "mean"), sheet=("sheet", "first")
    )


def load_survey(db: Session, well_ids: list[int]) -> pd.DataFrame:
    q = select(Survey.well_id, Survey.md_m, Survey.inc_deg, Survey.dls_deg_30m).where(
        Survey.well_id.in_(well_ids)
    )
    return pd.DataFrame(db.execute(q).all(), columns=["well_id", "md_m", "inc_deg", "dls_deg_30m"])


# ---------------------------------------------------------------- fitur


def plan_curves(plan: pd.DataFrame, well_id: int, op: str) -> dict[float | None, tuple]:
    """{ff: (depths, values)} terurut menurut kedalaman."""
    sub = plan[(plan.well_id == well_id) & (plan.operation == op)]
    out = {}
    for ff, g in sub.groupby(sub["ff"].fillna(-1)):
        g = g.groupby("depth_m", as_index=False)["value_si"].mean().sort_values("depth_m")
        out[None if ff == -1 else float(ff)] = (g.depth_m.to_numpy(), g.value_si.to_numpy())
    return out


def _interp(d, v, depths):
    res = np.interp(depths, d, v)
    res[(depths < d.min() - 1e-6) | (depths > d.max() + 1e-6)] = np.nan
    return res


def wp_at(curves: dict, depths: np.ndarray) -> dict[str, np.ndarray]:
    """Nilai WellPlan pada FF 0.3 dan 0.5 di kedalaman tertentu (tanpa ekstrapolasi kedalaman).

    Satu kurva saja (rotating weight / torque on bottom laporan WellPlan) -> nilai sama.
    FF lain -> interpolasi linear antar-FF.
    """
    nan = np.full(len(depths), np.nan)
    if not curves:
        return {c: nan for c in FF_COLS.values()}
    ffs = sorted(k for k in curves if k is not None)
    if len(ffs) <= 1:
        key = ffs[0] if ffs else None
        vals = _interp(*curves[key], depths)
        return {c: vals for c in FF_COLS.values()}
    at_ff = np.vstack([_interp(*curves[f], depths) for f in ffs])
    out = {}
    for target, col in FF_COLS.items():
        if target in ffs:
            out[col] = at_ff[ffs.index(target)]
        else:
            out[col] = np.array([np.interp(target, ffs, at_ff[:, k]) for k in range(len(depths))])
    return out


def survey_features(
    survey: pd.DataFrame, well_id: int, depths: np.ndarray
) -> dict[str, np.ndarray]:
    sub = survey[survey.well_id == well_id].sort_values("md_m")
    n = len(depths)
    nan = np.full(n, np.nan)
    if len(sub) < 2:
        return {
            "inc_deg": nan,
            "dls_deg_30m": nan,
            "tortuosity": nan,
            "depth_from_kop_m": nan,
            "interval_type": np.array(["unknown"] * n, dtype=object),
        }
    md = sub.md_m.to_numpy()
    inc = sub.inc_deg.to_numpy()
    dls = sub.dls_deg_30m.fillna(0.0).to_numpy()
    seg = np.diff(md, prepend=md[0])
    cum = np.cumsum(dls * seg / 30.0)  # derajat kumulatif
    tort = np.where(md > 0, cum / np.maximum(md, 1.0) * 30.0, 0.0)  # deg/30m rata-rata
    kop_idx = np.argmax(inc >= VERTICAL_INC) if (inc >= VERTICAL_INC).any() else None
    kop = md[kop_idx] if kop_idx is not None else np.nan
    inc_d = np.interp(depths, md, inc)
    # laju build lokal (deg/100ft) di jendela +-100 ft
    w = 100 * FT_TO_M
    rate = (
        (np.interp(depths + w, md, inc) - np.interp(depths - w, md, inc)) / (2 * w) * 100 * FT_TO_M
    )
    itype = np.where(
        inc_d < VERTICAL_INC,
        "vertical",
        np.where(
            inc_d >= HORIZONTAL_INC,
            "horizontal",
            np.where(rate > BUILD_RATE, "build", np.where(rate < -BUILD_RATE, "drop", "tangent")),
        ),
    ).astype(object)
    return {
        "inc_deg": inc_d,
        "dls_deg_30m": np.interp(depths, md, dls),
        "tortuosity": np.interp(depths, md, tort),
        "depth_from_kop_m": depths - kop,
        "interval_type": itype,
    }


def features_frame(
    well: pd.Series, op: str, depths: np.ndarray, plan: pd.DataFrame, survey: pd.DataFrame
) -> pd.DataFrame:
    depths = np.asarray(depths, dtype=float)
    wp = wp_at(plan_curves(plan, well.well_id, op), depths)
    rot = wp_at(plan_curves(plan, well.well_id, "rotating_weight"), depths)["wp_ff03"]
    sv = survey_features(survey, well.well_id, depths)
    shoe = well.casing_shoe_m
    oh = depths - shoe if shoe is not None and not pd.isna(shoe) else np.full(len(depths), np.nan)
    df = pd.DataFrame(
        {
            "well_id": well.well_id,
            "well_name": well.well_name,
            "section": well.section,
            "well_type": well.well_type,
            "plan_format": well.plan_format,
            "operation": op,
            "depth_m": depths,
            **wp,
            "wp_rot": rot,
            **sv,
            "open_hole_len_m": oh,
            "open_hole_frac": np.where(depths > 0, oh / np.maximum(depths, 1.0), np.nan),
            "mud_weight_ppg": well.mud_weight_ppg,
            "bha_weight_klbf": well.bha_weight_klbf,
            "bha_length_ft": well.bha_length_ft,
            "block_weight_klbf": well.block_weight_klbf,
            # offset Calibrate DD untuk operasi baris ini (kosong bila file tanpa Calibrate)
            "dd_calibration": getattr(well, CAL_FEATURE[op], None),
        }
    )
    df["wp_slope"] = (df.wp_ff05 - df.wp_ff03) / 0.2
    df["wp_base"] = df[FF_COLS[BASELINE_FF]]
    for c in (
        "mud_weight_ppg",
        "bha_weight_klbf",
        "bha_length_ft",
        "block_weight_klbf",
        "dd_calibration",
    ):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def build_dataset(db: Session, well_ids: list[int] | None = None) -> tuple[pd.DataFrame, list[str]]:
    """Satu baris per (sumur, operasi, kedalaman aktual). Kembalikan (dataset, catatan)."""
    wells = load_wells(db, well_ids)
    notes: list[str] = []
    if wells.empty:
        return pd.DataFrame(), ["No wells yet"]
    ids = wells.well_id.tolist()
    plan, actual, survey = load_plan(db, ids), load_actual(db, ids), load_survey(db, ids)
    if actual.empty or plan.empty:
        return pd.DataFrame(), ["No wells with both T&D model and actual data yet"]
    parts = []
    for _, w in wells.iterrows():
        label = f'{w.well_name} {w.section}"'
        for op in OPERATIONS:
            a = actual[(actual.well_id == w.well_id) & (actual.operation == op)]
            if a.empty:
                continue
            f = features_frame(w, op, a.depth_m.to_numpy(), plan, survey)
            f["target"] = a.actual_si.to_numpy()
            n0 = len(f)
            f = f[f.wp_base.notna()]
            if len(f) < n0:
                notes.append(
                    f"{label} {op}: {n0 - len(f)} actual points outside the T&D model depth range removed"
                )
            f = _drop_outliers(f, notes, label, op)
            parts.append(f)
    if not parts:
        return pd.DataFrame(), notes + ["No actual points match the T&D model"]
    ds = pd.concat(parts, ignore_index=True)
    for c in ("section", "well_type", "plan_format"):
        ds[c] = ds[c].fillna("unknown")
    return ds, notes


def _drop_outliers(f: pd.DataFrame, notes: list[str], label: str, op: str) -> pd.DataFrame:
    if len(f) < 8:
        return f
    resid = f.target - f.wp_base
    med = resid.median()
    mad = (resid - med).abs().median() * 1.4826
    if mad <= 0:
        return f
    mask = (resid - med).abs() <= OUTLIER_MAD * mad
    if (~mask).any():
        notes.append(
            f"{label} {op}: {(~mask).sum()} outlier points removed (> {OUTLIER_MAD:g} MAD)"
        )
    return f[mask]


def plan_grid(db: Session, well_id: int) -> np.ndarray:
    """Kedalaman prediksi: gabungan kedalaman WellPlan semua operasi, mulai dari casing shoe."""
    wells = load_wells(db, [well_id])
    plan = load_plan(db, [well_id])
    if plan.empty:
        return np.array([])
    depths = np.sort(plan.depth_m.unique())
    # rencana roadmap jarang (tiap ~1000 ft): rapatkan ke tiap ~30 m agar kurva halus
    if len(depths) >= 2 and np.median(np.diff(depths)) > 60:
        depths = np.unique(np.concatenate([depths, np.arange(depths.min(), depths.max(), 30.48)]))
    shoe = wells.casing_shoe_m.iloc[0] if not wells.empty else None
    if shoe is not None and not pd.isna(shoe):
        depths = depths[depths >= shoe - 1e-6]
    return depths


# ---------------------------------------------------------------- blind test & versi


def active_blind_set(db: Session) -> BlindSet | None:
    return db.scalar(select(BlindSet).where(BlindSet.active.is_(True)).order_by(BlindSet.id.desc()))


def ensure_blind_set(
    db: Session, wells: pd.DataFrame, frac: float = 0.2, seed: int = 42
) -> BlindSet:
    """Pilih ~20% SUMUR (semua section-nya) proporsional per tipe, sekali, lalu dikunci."""
    bs = active_blind_set(db)
    if bs is not None:
        return bs
    per_well = wells.drop_duplicates("well_name")[["well_name", "well_type"]]
    rng = np.random.default_rng(seed)
    chosen: list[str] = []
    for _, g in per_well.groupby("well_type"):
        names = sorted(g.well_name)
        n = int(round(frac * len(names)))
        if len(names) >= 3:
            n = max(n, 1)
        chosen += list(rng.choice(names, size=min(n, len(names)), replace=False))
    bs = BlindSet(
        wells=sorted(chosen),
        seed=seed,
        active=True,
        note=f"{len(chosen)} of {len(per_well)} wells, proportional per well type",
    )
    db.add(bs)
    db.flush()
    return bs


def freeze_dataset(db: Session) -> Dataset:
    """Bekukan dataset dari sumur berstatus kualitas A/B: snapshot CSV + hash + daftar sumur."""
    from app.services.quality import eligible_well_ids

    ok_ids, status = eligible_well_ids(db)
    ds, notes = build_dataset(db, ok_ids)
    if ds.empty:
        raise ValueError(
            "No training wells with data quality A/B and actual data. " + "; ".join(notes)
        )
    wells = load_wells(db, sorted(ds.well_id.unique().tolist()))
    bs = ensure_blind_set(db, wells)
    ds["is_blind"] = ds.well_name.isin(bs.wells)
    ds = ds.sort_values(["well_name", "section", "operation", "depth_m"]).reset_index(drop=True)
    csv = ds.to_csv(index=False, float_format="%.6g").encode()
    content_hash = hashlib.sha256(csv).hexdigest()
    version = (db.scalar(select(func.max(Dataset.version))) or 0) + 1
    out_dir = get_settings().model_dir / "datasets"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"dataset_v{version}.csv.gz"
    with gzip.open(path, "wb") as fh:
        fh.write(csv)
    files = {
        wid: chk
        for wid, chk in db.execute(
            select(UploadedFile.well_id, UploadedFile.checksum).where(
                UploadedFile.status.in_(["ok", "warning"])
            )
        ).all()
    }
    well_list = [
        {
            "well_id": int(r.well_id),
            "name": r.well_name,
            "section": r.section,
            "type": r.well_type,
            "file_sha256": files.get(int(r.well_id)),
            "blind": r.well_name in bs.wells,
            "rows": int((ds.well_id == r.well_id).sum()),
        }
        for r in wells.itertuples()
    ]
    excluded = []
    for wid, s in status.items():
        if s not in ("A", "B"):
            w = db.get(Well, wid)
            excluded.append({"well_id": wid, "name": w.name, "section": w.section_in, "status": s})
    d = Dataset(
        version=version,
        blind_set_id=bs.id,
        wells=well_list,
        excluded=excluded,
        content_hash=content_hash,
        n_rows=len(ds),
        path=str(path),
        notes=notes,
    )
    db.add(d)
    db.commit()
    return d


def load_frozen(dataset: Dataset) -> pd.DataFrame:
    with gzip.open(dataset.path, "rb") as fh:
        raw = fh.read()
    if hashlib.sha256(raw).hexdigest() != dataset.content_hash:
        raise ValueError(f"Dataset v{dataset.version} hash mismatch: the snapshot file has changed")
    df = pd.read_csv(io.BytesIO(raw), dtype={"section": str})
    for c in ("section", "well_type", "plan_format", "interval_type"):
        if c in df:
            df[c] = (
                df[c]
                .fillna("unknown")
                .astype(str)
                .replace({"tidak diketahui": "unknown", "vertikal": "vertical"})
            )
    df["section"] = df["section"].map(lambda s: re.sub(r"\.0$", "", s))
    return df
