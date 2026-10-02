"""Bentuk dataset: selaraskan hasil WellPlan ke kedalaman titik aktual, tambah fitur.

Keputusan terkait (docs/keputusan.md): K-05 sumber data, K-06 baseline,
K-07 data kosong & outlier, K-08 rentang kedalaman.
"""

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ActualReading, PlanResult, Survey, Well
from app.parsers import column_map as cm
from app.parsers.common import sheet_role
from app.services.operations import BASELINE_FF, FF_SCENARIOS, OPERATIONS
from app.services.units import FT_TO_M

NUMERIC_FEATURES = ["depth_m", "inc_deg", "dls_deg_30m", "wp_ff01", "wp_ff03", "wp_ff05"]
CATEGORICAL_FEATURES = ["section", "well_type"]
FF_COLS = {0.1: "wp_ff01", 0.3: "wp_ff03", 0.5: "wp_ff05"}
OUTLIER_MAD = 5.0  # titik dengan residu > 5 x MAD (per sumur & operasi) dibuang


def load_wells(db: Session, well_ids: list[int] | None = None) -> pd.DataFrame:
    q = select(Well)
    if well_ids is not None:
        q = q.where(Well.id.in_(well_ids))
    rows = [
        {
            "well_id": w.id,
            "well_name": w.name,
            "section": None if w.section_in is None else f"{w.section_in:g}",
            "well_type": w.well_type,
            "casing_shoe_m": _shoe_m(w.meta or {}),
        }
        for w in db.scalars(q)
    ]
    return pd.DataFrame(
        rows, columns=["well_id", "well_name", "section", "well_type", "casing_shoe_m"]
    )


def _shoe_m(meta: dict) -> float | None:
    shoe = meta.get("casing_shoe")
    if shoe is None:
        return None
    return shoe * (FT_TO_M if meta.get("casing_shoe_unit", "ft") == "ft" else 1.0)


def load_plan(db: Session, well_ids: list[int]) -> pd.DataFrame:
    q = select(
        PlanResult.well_id,
        PlanResult.operation,
        PlanResult.ff,
        PlanResult.source_sheet,
        PlanResult.depth_m,
        PlanResult.value_si,
    ).where(PlanResult.well_id.in_(well_ids))
    df = pd.DataFrame(
        db.execute(q).all(), columns=["well_id", "operation", "ff", "sheet", "depth_m", "value_si"]
    )
    if df.empty:
        return df
    # Laporan WellPlan didahulukan; roadmap hanya bila laporan tidak punya operasi itu
    df["is_roadmap"] = df["sheet"].map(lambda s: sheet_role(s) in cm.ROADMAP_ROLES)
    has_report = df[~df.is_roadmap].groupby(["well_id", "operation"]).size()
    keep = df.apply(
        lambda r: (not r.is_roadmap) or (r.well_id, r.operation) not in has_report.index, axis=1
    )
    return df[keep].drop(columns=["is_roadmap"])


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
    # T&D Actual Reading didahulukan; Drilling/Tripping Data hanya sebagai pengganti
    df["primary"] = df["sheet"].map(lambda s: sheet_role(s) == "actual_td")
    has_primary = df[df.primary].groupby(["well_id", "operation"]).size()
    keep = df.apply(
        lambda r: r.primary or (r.well_id, r.operation) not in has_primary.index, axis=1
    )
    df = df[keep].drop(columns=["primary"])
    # rata-rata bila ada beberapa pembacaan di kedalaman yang sama
    return df.groupby(["well_id", "operation", "depth_m"], as_index=False).agg(
        actual_si=("actual_si", "mean"), sheet=("sheet", "first")
    )


def load_survey(db: Session, well_ids: list[int]) -> pd.DataFrame:
    q = select(Survey.well_id, Survey.md_m, Survey.inc_deg, Survey.dls_deg_30m).where(
        Survey.well_id.in_(well_ids)
    )
    return pd.DataFrame(db.execute(q).all(), columns=["well_id", "md_m", "inc_deg", "dls_deg_30m"])


def plan_curves(plan: pd.DataFrame, well_id: int, op: str) -> dict[float | None, tuple]:
    """{ff: (depths, values)} terurut menurut kedalaman."""
    sub = plan[(plan.well_id == well_id) & (plan.operation == op)]
    out = {}
    for ff, g in sub.groupby(sub["ff"].fillna(-1)):
        g = g.groupby("depth_m", as_index=False)["value_si"].last().sort_values("depth_m")
        out[None if ff == -1 else float(ff)] = (g.depth_m.to_numpy(), g.value_si.to_numpy())
    return out


def wp_at(curves: dict, depths: np.ndarray) -> dict[str, np.ndarray]:
    """Nilai WellPlan pada kedalaman tertentu untuk FF 0.1/0.3/0.5.

    Di luar rentang kedalaman WellPlan -> NaN (tidak diekstrapolasi).
    Operasi tanpa FF (rotating weight) -> nilai yang sama untuk ketiga kolom.
    FF lain dari 0.1/0.3/0.5 -> interpolasi linear antar-FF.
    """
    if not curves:
        return {c: np.full(len(depths), np.nan) for c in FF_COLS.values()}

    def interp(d, v):
        res = np.interp(depths, d, v)
        res[(depths < d.min()) | (depths > d.max())] = np.nan
        return res

    if None in curves and len(curves) == 1:
        vals = interp(*curves[None])
        return {c: vals for c in FF_COLS.values()}
    ffs = sorted(k for k in curves if k is not None)
    at_ff = np.vstack([interp(*curves[f]) for f in ffs])  # (n_ff, n_depth)
    out = {}
    for target, col in FF_COLS.items():
        if target in ffs:
            out[col] = at_ff[ffs.index(target)]
        elif len(ffs) == 1:
            out[col] = at_ff[0]
        else:
            out[col] = np.array([np.interp(target, ffs, at_ff[:, k]) for k in range(len(depths))])
    return out


def survey_at(survey: pd.DataFrame, well_id: int, depths: np.ndarray) -> tuple:
    sub = survey[survey.well_id == well_id].sort_values("md_m")
    if sub.empty:
        nan = np.full(len(depths), np.nan)
        return nan, nan
    inc = np.interp(depths, sub.md_m, sub.inc_deg)
    dls_src = sub.dls_deg_30m.fillna(0.0)
    dls = np.interp(depths, sub.md_m, dls_src)
    return inc, dls


def features_frame(
    well: pd.Series,
    op: str,
    depths: np.ndarray,
    plan: pd.DataFrame,
    survey: pd.DataFrame,
) -> pd.DataFrame:
    curves = plan_curves(plan, well.well_id, op)
    wp = wp_at(curves, depths)
    inc, dls = survey_at(survey, well.well_id, depths)
    df = pd.DataFrame(
        {
            "well_id": well.well_id,
            "well_name": well.well_name,
            "section": well.section,
            "well_type": well.well_type,
            "operation": op,
            "depth_m": depths,
            "inc_deg": inc,
            "dls_deg_30m": dls,
            **wp,
        }
    )
    df["wp_base"] = df[FF_COLS[BASELINE_FF]]
    return df


def build_dataset(db: Session, well_ids: list[int] | None = None) -> tuple[pd.DataFrame, list[str]]:
    """Dataset latih: satu baris per (sumur, operasi, kedalaman aktual).

    Kembalikan (dataset, catatan) — catatan berisi titik yang dibuang dan alasannya.
    """
    wells = load_wells(db, well_ids)
    notes: list[str] = []
    if wells.empty:
        return pd.DataFrame(), ["Belum ada sumur"]
    ids = wells.well_id.tolist()
    plan, actual, survey = load_plan(db, ids), load_actual(db, ids), load_survey(db, ids)
    if actual.empty or plan.empty:
        return pd.DataFrame(), ["Belum ada pasangan data WellPlan dan aktual"]

    parts = []
    for _, w in wells.iterrows():
        for op in OPERATIONS:
            a = actual[(actual.well_id == w.well_id) & (actual.operation == op)]
            if a.empty:
                continue
            depths = a.depth_m.to_numpy()
            f = features_frame(w, op, depths, plan, survey)
            f["target"] = a.actual_si.to_numpy()
            f["actual_sheet"] = a.sheet.to_numpy()
            n0 = len(f)
            f = f[f.wp_base.notna()]
            if len(f) < n0:
                notes.append(
                    f"{w.well_name} {op}: {n0 - len(f)} titik aktual di luar rentang WellPlan dibuang"
                )
            f = _drop_outliers(f, notes, w.well_name, op)
            parts.append(f)
    if not parts:
        return pd.DataFrame(), notes + ["Tidak ada titik aktual yang cocok dengan WellPlan"]
    ds = pd.concat(parts, ignore_index=True)
    for c in ("section", "well_type"):
        missing = ds[ds[c].isna()].well_name.unique()
        if len(missing):
            notes.append(f"Sumur tanpa {c}: {', '.join(missing)} (diisi 'tidak diketahui')")
        ds[c] = ds[c].fillna("tidak diketahui")
    return ds, notes


def _drop_outliers(f: pd.DataFrame, notes: list[str], well: str, op: str) -> pd.DataFrame:
    if len(f) < 8:
        return f
    resid = f.target - f.wp_base
    med = resid.median()
    mad = (resid - med).abs().median() * 1.4826
    if mad <= 0:
        return f
    mask = (resid - med).abs() <= OUTLIER_MAD * mad
    if (~mask).any():
        notes.append(f"{well} {op}: {(~mask).sum()} titik outlier dibuang (> {OUTLIER_MAD:g} MAD)")
    return f[mask]


def plan_grid(db: Session, well_id: int) -> np.ndarray:
    """Kedalaman WellPlan untuk prediksi (mulai dari casing shoe bila diketahui)."""
    wells = load_wells(db, [well_id])
    plan = load_plan(db, [well_id])
    if plan.empty:
        return np.array([])
    depths = np.sort(plan.depth_m.unique())
    shoe = wells.casing_shoe_m.iloc[0] if not wells.empty else None
    if shoe is not None and not pd.isna(shoe):
        depths = depths[depths >= shoe - 1e-6]
    return depths


__all__ = [
    "NUMERIC_FEATURES",
    "CATEGORICAL_FEATURES",
    "FF_SCENARIOS",
    "build_dataset",
    "features_frame",
    "load_wells",
    "load_plan",
    "load_survey",
    "load_actual",
    "plan_grid",
]
