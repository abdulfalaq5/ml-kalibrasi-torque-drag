"""Gerbang kualitas data per sumur-section: status A (layak), B (layak dengan peringatan),
C (ditahan). Hanya A/B yang dipakai melatih model. Lihat TODO_Lanjutan_6_Minggu.md.

Pemeriksaan kritis (gagal -> C) dan statistik (gagal -> peringatan, B) dihitung dari data
yang sudah tersimpan. Keputusan tinjauan engineer (terima / kecualikan / perbaiki) dicatat
terpisah dan menentukan status efektif.
"""

from datetime import UTC, datetime

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ActualReading, PlanResult, QualityReview, Well, WellQuality
from app.services.operations import BASELINE_FF, HOOKLOAD_OPS, OPERATIONS
from app.services.units import FT_TO_M

MIN_ACTUAL_POINTS = 8  # titik aktual minimum dalam rentang WellPlan (usul TODO, K-19)
ORDER_TOL_KN = 8.9  # toleransi urutan slack off <= rotating <= pick up (2 klbf)
ORDER_TOL_FRAC = 0.03
ORDER_FAIL_FRAC = 0.25  # > 25% titik melanggar urutan -> kritis
NONPHYS_FAIL_FRAC = 0.10
UNIT_RATIO_RANGE = (0.33, 3.0)  # hookload: median aktual/WellPlan di luar ini -> salah satuan/kolom
UNIT_RATIO_TORQUE_HARD = (0.01, 100.0)  # torsi: hanya faktor ~1000x yang pasti salah satuan
TORQUE_RATIO_WARN = (
    0.33,
    3.0,
)  # torsi: di luar ini -> peringatan (asumsi bit torque / torsi kecil)
PEER_Z = 3.5
JUMP_FRAC = 0.20
REPEAT_RUN = 4
FEW_POINTS_FRAC = 0.4
CORE_OPS = ["pick_up", "slack_off"]

PENALTY_CRIT, PENALTY_WARN = 25, 8

DECISIONS = {"terima", "kecualikan", "perbaiki"}


def _load(db: Session, well_ids: list[int]) -> tuple[pd.DataFrame, pd.DataFrame]:
    plan = pd.DataFrame(
        db.execute(
            select(
                PlanResult.id,
                PlanResult.well_id,
                PlanResult.operation,
                PlanResult.ff,
                PlanResult.source_sheet,
                PlanResult.depth_m,
                PlanResult.value_si,
            ).where(PlanResult.well_id.in_(well_ids))
        ).all(),
        columns=["id", "well_id", "operation", "ff", "sheet", "depth_m", "value_si"],
    )
    act = pd.DataFrame(
        db.execute(
            select(
                ActualReading.id,
                ActualReading.well_id,
                ActualReading.operation,
                ActualReading.source_sheet,
                ActualReading.depth_m,
                ActualReading.value_si,
            ).where(ActualReading.well_id.in_(well_ids))
        ).all(),
        columns=["id", "well_id", "operation", "sheet", "depth_m", "value_si"],
    )
    return plan, act


def _baseline_curve(plan: pd.DataFrame, op: str) -> tuple[np.ndarray, np.ndarray] | None:
    p = plan[plan.operation == op]
    if p.empty:
        return None
    ffs = p.ff.dropna().unique()
    if len(ffs):
        f = min(ffs, key=lambda x: abs(x - BASELINE_FF))
        p = p[p.ff == f]
    g = p.groupby("depth_m", as_index=False)["value_si"].mean().sort_values("depth_m")
    return g.depth_m.to_numpy(), g.value_si.to_numpy()


def well_stats(well: Well, plan: pd.DataFrame, act: pd.DataFrame) -> dict:
    """Statistik dasar per sumur, dipakai pemeriksaan dan pembanding sesama kelas."""
    st: dict = {"n_actual_depths": int(act.depth_m.nunique()) if not act.empty else 0}
    for op in OPERATIONS:
        curve = _baseline_curve(plan, op)
        a = act[act.operation == op].sort_values("depth_m")
        st[f"n_{op}"] = int(len(a))
        if curve is None or a.empty:
            continue
        d, v = curve
        inside = a[(a.depth_m >= d.min() - 1e-6) & (a.depth_m <= d.max() + 1e-6)]
        st[f"n_in_range_{op}"] = int(len(inside))
        if len(inside):
            wp = np.interp(inside.depth_m, d, v)
            ok = np.abs(wp) > 1e-6
            if ok.sum() >= 3:
                st[f"ratio_{op}"] = float(np.median(inside.value_si.to_numpy()[ok] / wp[ok]))
    return st


def evaluate_well(
    db: Session, well: Well, peers: dict | None = None, commit: bool = True
) -> WellQuality:
    plan, act = _load(db, [well.id])
    checks: list[dict] = []

    def crit(code, msg):
        checks.append({"code": code, "level": "kritis", "message": msg})

    def warn(code, msg):
        checks.append({"code": code, "level": "peringatan", "message": msg})

    def ok(code, msg):
        checks.append({"code": code, "level": "lolos", "message": msg})

    st = well_stats(well, plan, act)

    # K1 format dikenali & kolom wajib: rencana untuk operasi inti
    missing = (
        [op for op in OPERATIONS if plan[plan.operation == op].empty]
        if not plan.empty
        else OPERATIONS
    )
    core_missing = [op for op in CORE_OPS if op in missing]
    if plan.empty or core_missing:
        crit(
            "K1",
            f"Rencana WellPlan tidak lengkap: tidak ada {', '.join(core_missing or OPERATIONS)}",
        )
    elif missing:
        warn("K1", f"Rencana WellPlan tanpa operasi: {', '.join(missing)}")
    else:
        ok("K1", "Format dikenali, rencana kelima operasi ada")

    # K2 satuan: dicek saat impor (satuan tak dikenal -> file gagal). Cek kewajaran rasio.
    bad_unit, odd_torque = [], []
    for op in OPERATIONS:
        r = st.get(f"ratio_{op}")
        if r is None or st.get(f"n_in_range_{op}", 0) < 5:
            continue
        if op in HOOKLOAD_OPS:
            if not (UNIT_RATIO_RANGE[0] <= r <= UNIT_RATIO_RANGE[1]):
                bad_unit.append(f"{op} (aktual/WellPlan = {r:.2f})")
        elif not (UNIT_RATIO_TORQUE_HARD[0] <= r <= UNIT_RATIO_TORQUE_HARD[1]):
            bad_unit.append(f"{op} (aktual/WellPlan = {r:.3g}, faktor ~1000x)")
        elif not (TORQUE_RATIO_WARN[0] <= r <= TORQUE_RATIO_WARN[1]):
            odd_torque.append(f"{op} = {r:.2f}")
    if bad_unit:
        crit("K2", "Kemungkinan salah satuan atau salah kolom: " + "; ".join(bad_unit))
    else:
        ok("K2", "Satuan dikenali dan rasio aktual/WellPlan wajar")
    if odd_torque:
        warn(
            "S5",
            "Rasio torsi aktual/WellPlan jauh dari 1 (" + "; ".join(odd_torque) + "): torsi kecil "
            "di section dangkal atau asumsi bit torque WellPlan berbeda; periksa dengan engineer",
        )

    # K3 kedalaman naik, tanpa duplikat bertentangan
    dup_conflict, unsorted = 0, 0
    for (_, _, _), g in plan.groupby(["operation", "ff", "sheet"], dropna=False):
        g = g.sort_values("id")
        unsorted += int((np.diff(g.depth_m.to_numpy()) < -1e-6).sum())
        dd = g.groupby("depth_m").value_si.nunique()
        dup_conflict += int((dd > 1).sum())
    if not act.empty:
        # Tripping Data memang tercatat dari dalam ke dangkal (cabut pipa): tidak dihitung
        trip = act.sheet.str.lower().str.match(r"^tripping\s+data")
        for (_, _), g in act[~trip].groupby(["operation", "sheet"]):
            g = g.sort_values("id")
            unsorted += int((np.diff(g.depth_m.to_numpy()) < -1e-6).sum())
    if dup_conflict:
        crit("K3", f"{dup_conflict} kedalaman WellPlan duplikat dengan nilai berbeda")
    elif unsorted:
        warn("K3", f"{unsorted} kali urutan kedalaman turun di file (data diurutkan ulang)")
    else:
        ok("K3", "Kedalaman naik dan tanpa duplikat")

    # K4 nilai wajar fisik: hookload > 0, torsi >= 0
    if act.empty:
        crit("K4", "Tidak ada data aktual")
    else:
        hk = act[act.operation.isin(HOOKLOAD_OPS)]
        tq = act[~act.operation.isin(HOOKLOAD_OPS)]
        bad = int((hk.value_si <= 0).sum() + (tq.value_si < 0).sum())
        frac = bad / max(len(act), 1)
        if frac > NONPHYS_FAIL_FRAC:
            crit("K4", f"{bad} titik aktual tidak wajar (hookload <= 0 atau torsi < 0), {frac:.0%}")
        elif bad:
            warn("K4", f"{bad} titik aktual tidak wajar dibuang dari dataset")
        else:
            ok("K4", "Nilai aktual wajar secara fisik")

    # K5 urutan slack off <= rotating <= pick up (di kedalaman yang sama)
    if not act.empty:
        wide = act[act.operation.isin(HOOKLOAD_OPS)].pivot_table(
            index="depth_m", columns="operation", values="value_si", aggfunc="mean"
        )
        cols = [c for c in ("slack_off", "rotating_weight", "pick_up") if c in wide.columns]
        if len(cols) >= 2:
            w = wide[cols].dropna()
            viol = np.zeros(len(w), dtype=bool)
            for lo, hi in zip(cols, cols[1:], strict=False):
                tol = np.maximum(ORDER_TOL_KN, ORDER_TOL_FRAC * w[hi].abs())
                viol |= (w[lo] - w[hi]).to_numpy() > tol.to_numpy()
            frac = viol.mean() if len(w) else 0
            st["order_violation_frac"] = float(frac)
            if frac > ORDER_FAIL_FRAC:
                crit(
                    "K5",
                    f"Urutan slack off <= rotating <= pick up dilanggar di {frac:.0%} kedalaman",
                )
            elif viol.any():
                warn(
                    "K5",
                    f"Urutan slack off <= rotating <= pick up dilanggar di {int(viol.sum())} kedalaman",
                )
            else:
                ok("K5", "Urutan slack off <= rotating <= pick up wajar")

    # K6/K7 tumpang rentang & jumlah titik minimum
    n_in = st.get("n_in_range_pick_up", 0)
    if act.empty:
        pass
    elif n_in < MIN_ACTUAL_POINTS:
        crit(
            "K6",
            f"Hanya {n_in} titik aktual pick up di dalam rentang kedalaman WellPlan "
            f"(minimum {MIN_ACTUAL_POINTS})",
        )
    else:
        ok("K6", f"{n_in} titik aktual pick up di dalam rentang WellPlan")

    # K8 section & tipe
    if well.section_in is None or well.well_type is None:
        crit("K8", "Section atau tipe sumur belum teridentifikasi")
    else:
        ok("K8", f'Section {well.section_in:g}" tipe {well.well_type}')

    # K9 duplikat sumur lain (data aktual pick up identik)
    dup = _duplicate_of(db, well, act)
    if dup:
        crit("K9", f"Data aktual identik dengan sumur {dup}")
    elif not act.empty:
        ok("K9", "Bukan duplikat sumur lain")

    # ---- statistik
    if not act.empty:
        pu = act[act.operation == "pick_up"].groupby("depth_m").value_si.mean().sort_index()
        if len(pu) >= 5:
            diffs = np.abs(np.diff(pu.to_numpy()))
            mad = np.median(np.abs(diffs - np.median(diffs))) * 1.4826 or 1e-9
            jumps = int(
                (
                    (diffs > 5 * mad + np.median(diffs)) & (diffs > JUMP_FRAC * pu.to_numpy()[1:])
                ).sum()
            )
            if jumps:
                warn("S2", f"{jumps} lompatan tak wajar antar titik pick up berurutan")
        wide = act.pivot_table(
            index="depth_m", columns="operation", values="value_si", aggfunc="mean"
        ).sort_index()
        if len(wide) >= REPEAT_RUN:
            same = (wide.diff().abs().fillna(1).sum(axis=1) == 0).to_numpy()
            run, best = 0, 0
            for s_ in same:
                run = run + 1 if s_ else 0
                best = max(best, run)
            if best + 1 >= REPEAT_RUN:
                warn(
                    "S3",
                    f"{best + 1} baris aktual berurutan bernilai persis sama (kemungkinan salin tempel)",
                )
    if peers:
        _peer_checks(well, st, peers, warn)

    n_crit = sum(c["level"] == "kritis" for c in checks)
    n_warn = sum(c["level"] == "peringatan" for c in checks)
    status = "C" if n_crit else ("B" if n_warn else "A")
    score = max(0, 100 - PENALTY_CRIT * n_crit - PENALTY_WARN * n_warn)

    wq = db.scalar(select(WellQuality).where(WellQuality.well_id == well.id))
    if wq is None:
        wq = WellQuality(well_id=well.id, status=status, score=score)
        db.add(wq)
    wq.status, wq.score, wq.checks, wq.stats = status, score, checks, st
    wq.computed_at = datetime.now(UTC)
    if commit:
        db.commit()
    return wq


def _peer_checks(well: Well, st: dict, peers: dict, warn) -> None:
    key = f"{well.section_in}|{well.well_type}"
    group = [p for wid, p in peers.items() if wid != well.id and p["key"] == key]
    ratios = [p["stats"].get("ratio_pick_up") for p in group if p["stats"].get("ratio_pick_up")]
    r = st.get("ratio_pick_up")
    if r is not None and len(ratios) >= 4:
        med = float(np.median(ratios))
        mad = float(np.median(np.abs(np.array(ratios) - med))) * 1.4826 or 1e-6
        z = (r - med) / mad
        if abs(z) > PEER_Z:
            warn(
                "S1",
                f"Rasio aktual/WellPlan pick up ({r:.2f}) menyimpang dari sumur sekelas "
                f"(median {med:.2f}, z={z:+.1f})",
            )
    counts = [p["stats"].get("n_actual_depths", 0) for p in group]
    if len(counts) >= 4 and st.get("n_actual_depths", 0) < FEW_POINTS_FRAC * np.median(counts):
        warn(
            "S4",
            f"Titik aktual ({st.get('n_actual_depths', 0)}) jauh lebih sedikit dari sumur "
            f"sekelas (median {np.median(counts):.0f})",
        )


def _duplicate_of(db: Session, well: Well, act: pd.DataFrame) -> str | None:
    pu = act[act.operation == "pick_up"]
    if len(pu) < 5:
        return None
    sig = sorted(zip(pu.depth_m.round(1), pu.value_si.round(2), strict=True))
    others = db.execute(
        select(ActualReading.well_id, ActualReading.depth_m, ActualReading.value_si).where(
            ActualReading.operation == "pick_up", ActualReading.well_id != well.id
        )
    ).all()
    by: dict[int, list] = {}
    for wid, d, v in others:
        by.setdefault(wid, []).append((round(d, 1), round(v, 2)))
    for wid, rows in by.items():
        if len(rows) == len(sig) and sorted(rows) == sig:
            w = db.get(Well, wid)
            return f'{w.name} {w.section_in:g}"' if w else str(wid)
    return None


def recompute_all(db: Session) -> dict:
    """Hitung ulang semua sumur (dua lintasan: statistik dulu, lalu banding sesama kelas)."""
    wells = db.scalars(select(Well)).all()
    peers = {}
    for w in wells:
        plan, act = _load(db, [w.id])
        peers[w.id] = {"key": f"{w.section_in}|{w.well_type}", "stats": well_stats(w, plan, act)}
    counts = {"A": 0, "B": 0, "C": 0}
    for w in wells:
        wq = evaluate_well(db, w, peers=peers, commit=False)
        counts[wq.status] += 1
    db.commit()
    return counts


def latest_review(db: Session, well_id: int) -> QualityReview | None:
    return db.scalar(
        select(QualityReview)
        .where(QualityReview.well_id == well_id)
        .order_by(QualityReview.created_at.desc(), QualityReview.id.desc())
    )


def effective_status(wq: WellQuality | None, review: QualityReview | None) -> str:
    """A/B/C otomatis, dikoreksi keputusan tinjauan terakhir. X = dikecualikan."""
    if wq is None:
        return "C"
    if review is None:
        return wq.status
    if review.decision == "kecualikan":
        return "X"
    if review.decision == "terima" and wq.status == "C":
        return "B"
    if review.decision == "perbaiki":
        return "C"
    return wq.status


def eligible_well_ids(db: Session) -> tuple[list[int], dict[int, str]]:
    """Sumur yang boleh masuk training (status efektif A/B) + status semua sumur."""
    status = {}
    for w in db.scalars(select(Well)).all():
        wq = db.scalar(select(WellQuality).where(WellQuality.well_id == w.id))
        status[w.id] = effective_status(wq, latest_review(db, w.id))
    return [wid for wid, s in status.items() if s in ("A", "B")], status


def depth_ft(m: float) -> float:
    return m / FT_TO_M
