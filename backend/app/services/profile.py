"""Data tiga grafik dashboard (Hookload, Torque, Selisih) untuk satu sumur.

Konvensi selisih: A - B. Positif = A lebih tinggi = ke KANAN pada grafik Selisih.
Selisih terhadap Aktual hanya dihitung pada kedalaman yang punya data aktual.
"""

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import PredictionPoint, Well
from app.services import dataset as dsm
from app.services import units
from app.services.metrics import all_metrics
from app.services.operations import BASELINE_FF, OP_DIMENSION, OP_LABELS, OPERATIONS
from app.services.predict import coverage_warnings, load_bundle, prediction_for_dashboard
from app.services.training import active_model

PCT_FLOOR_FRAC = 0.05  # penyebut persen minimal 5% x median |pembanding|


def _pct(diff: np.ndarray, ref: np.ndarray) -> np.ndarray:
    if not len(ref):
        return np.array([])
    floor = max(PCT_FLOOR_FRAC * float(np.median(np.abs(ref))), 1e-9)
    return diff / np.maximum(np.abs(ref), floor) * 100


def _r(a, nd=4) -> list:
    return [None if v is None or not np.isfinite(v) else round(float(v), nd) for v in a]


def well_profile(db: Session, well: Well, unit_system: str = "imperial") -> dict:
    disp = units.DISPLAY_UNITS[unit_system]
    len_u = disp["length"]

    def conv_depth(a):
        return np.array([units.from_si(v, len_u) for v in a])

    def conv(a, op):
        u = disp[OP_DIMENSION[op]]
        return np.array([units.from_si(v, u) for v in a])

    ids = [well.id]
    plan = dsm.load_plan(db, ids)
    actual = dsm.load_actual(db, ids)
    pred = prediction_for_dashboard(db, well)
    model = active_model(db)
    pts = []
    if pred is not None:
        pts = db.execute(
            select(
                PredictionPoint.operation,
                PredictionPoint.depth_m,
                PredictionPoint.ml_si,
            ).where(PredictionPoint.prediction_id == pred.id)
        ).all()

    warnings: list[str] = []
    if pred is not None:
        warnings += list(pred.warnings or [])
        # prediksi penuh sudah menyimpan peringatan cakupan saat dibuat
        if pred.kind == "oof" and model is not None and model.path:
            warnings += coverage_warnings(
                load_bundle(model.path),
                None if well.section_in is None else f"{well.section_in:g}",
                well.well_type,
            )
    elif model is None:
        warnings.append("Belum ada model aktif: grafik hanya menampilkan WellPlan dan aktual")
    else:
        warnings.append("Sumur belum diprediksi dengan model aktif. Klik 'Prediksi'.")

    has_actual = not actual.empty
    if not has_actual:
        warnings.append("Belum ada data aktual: grafik Selisih hanya menampilkan ML - WellPlan")

    ops_out = {}
    for op in OPERATIONS:
        curves = dsm.plan_curves(plan, well.id, op)
        wp_series = []
        for ff, (d, v) in sorted(curves.items(), key=lambda kv: (kv[0] is None, kv[0] or 0)):
            wp_series.append({"ff": ff, "depth": _r(conv_depth(d), 2), "value": _r(conv(v, op))})
        base = curves.get(BASELINE_FF) or curves.get(None)
        if base is None and curves:
            base = next(iter(curves.values()))

        ml = sorted((p.depth_m, p.ml_si) for p in pts if p.operation == op)
        ml_d = np.array([p[0] for p in ml])
        ml_v = np.array([p[1] for p in ml])

        a = actual[actual.operation == op].sort_values("depth_m") if has_actual else None
        act_d = a.depth_m.to_numpy() if a is not None else np.array([])
        act_v = a.actual_si.to_numpy() if a is not None else np.array([])

        def interp_at(xd, xv, depths):
            if not len(xd) or not len(depths):
                return np.full(len(depths), np.nan)
            res = np.interp(depths, xd, xv)
            res[(depths < xd.min()) | (depths > xd.max())] = np.nan
            return res

        wp_at_act = interp_at(*(base if base else (np.array([]), np.array([]))), act_d)
        ml_at_act = interp_at(ml_d, ml_v, act_d)
        wp_at_ml = interp_at(*(base if base else (np.array([]), np.array([]))), ml_d)

        d_wp_act = wp_at_act - act_v
        d_ml_act = ml_at_act - act_v
        d_ml_wp = ml_v - wp_at_ml

        mask_wp = np.isfinite(d_wp_act)
        mask_ml = np.isfinite(d_ml_act)
        metrics = None
        if has_actual and len(act_v):
            metrics = {
                "wellplan": all_metrics(act_v[mask_wp], wp_at_act[mask_wp])
                if mask_wp.any()
                else None,
                "ml": all_metrics(act_v[mask_ml], ml_at_act[mask_ml]) if mask_ml.any() else None,
            }
            # konversi RMSE ke satuan tampilan
            for k in ("wellplan", "ml"):
                if metrics[k] is not None:
                    metrics[k]["rmse"] = float(conv(np.array([metrics[k]["rmse"]]), op)[0])

        ops_out[op] = {
            "label": OP_LABELS[op],
            "unit": units.UNIT_LABELS[disp[OP_DIMENSION[op]]],
            "wellplan": wp_series,
            "wellplan_baseline_ff": BASELINE_FF if BASELINE_FF in curves else None,
            "ml": {"depth": _r(conv_depth(ml_d), 2), "value": _r(conv(ml_v, op))},
            "actual": {"depth": _r(conv_depth(act_d), 2), "value": _r(conv(act_v, op))},
            "diff": {
                "wp_minus_actual": {
                    "depth": _r(conv_depth(act_d[mask_wp]), 2),
                    "abs": _r(conv(d_wp_act[mask_wp], op)),
                    "pct": _r(_pct(d_wp_act[mask_wp], act_v[mask_wp]), 2),
                },
                "ml_minus_actual": {
                    "depth": _r(conv_depth(act_d[mask_ml]), 2),
                    "abs": _r(conv(d_ml_act[mask_ml], op)),
                    "pct": _r(_pct(d_ml_act[mask_ml], act_v[mask_ml]), 2),
                },
                "ml_minus_wp": {
                    "depth": _r(conv_depth(ml_d[np.isfinite(d_ml_wp)]), 2),
                    "abs": _r(conv(d_ml_wp[np.isfinite(d_ml_wp)], op)),
                    "pct": _r(
                        _pct(d_ml_wp[np.isfinite(d_ml_wp)], wp_at_ml[np.isfinite(d_ml_wp)]), 2
                    ),
                },
            },
            "metrics": metrics,
        }

    return {
        "well": {
            "id": well.id,
            "name": well.name,
            "section_in": well.section_in,
            "well_type": well.well_type,
        },
        "unit_system": unit_system,
        "depth_unit": units.UNIT_LABELS[len_u],
        "has_actual": has_actual,
        "prediction": None
        if pred is None
        else {"id": pred.id, "kind": pred.kind, "model_id": pred.model_id},
        "warnings": warnings,
        "sign_convention": "Selisih = A - B. Kanan (+) = A lebih tinggi, kiri (-) = A lebih rendah.",
        "operations": ops_out,
    }
