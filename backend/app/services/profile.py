"""Data grafik dashboard (Hookload, Torque, Difference) untuk satu sumur.

Konvensi selisih: A - B. Positif = A lebih tinggi = ke KANAN pada grafik Difference.
Selisih terhadap Aktual hanya dihitung pada kedalaman yang punya data aktual.

Kurva WellPlan "calibrated" = WellPlan + offset Calibrate DD (sama dengan kolom
"Graph reference" di Excel client); default bila file punya offset Calibrate.
ROT (rotating weight) ditampilkan satu kurva saja (OHFF baseline).
"""

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import MLModel, PredictionPoint, Well, WellQuality
from app.services import dataset as dsm
from app.services import units
from app.services.calibration import has_calibration, offsets_si
from app.services.limits import applicable_limits, first_crossing, margin
from app.services.metrics import TOLERANCE_LABEL, all_metrics, tolerance_si, within_frac
from app.services.operations import (
    BASELINE_FF,
    OP_DIMENSION,
    OP_LABELS,
    OPERATIONS,
    SINGLE_CURVE_OPS,
    series_name,
)
from app.services.predict import coverage_warnings, load_bundle, prediction_for_dashboard
from app.services.quality import effective_status, latest_review
from app.services.training import active_model

PCT_FLOOR_FRAC = 0.05  # penyebut persen minimal 5% x median |pembanding|


def _pct(diff: np.ndarray, ref: np.ndarray) -> np.ndarray:
    if not len(ref):
        return np.array([])
    floor = max(PCT_FLOOR_FRAC * float(np.median(np.abs(ref))), 1e-9)
    return diff / np.maximum(np.abs(ref), floor) * 100


def _r(a, nd=4) -> list:
    return [None if v is None or not np.isfinite(v) else round(float(v), nd) for v in a]


def _depth_or_none(d, conv_depth):
    return None if d is None else round(float(conv_depth(np.array([d]))[0]), 1)


def well_profile(
    db: Session,
    well: Well,
    unit_system: str = "imperial",
    model: MLModel | None = None,
    calibration: str | None = None,
) -> dict:
    """calibration: "calibrated" | "raw" | None (otomatis: calibrated bila ada offset Calibrate)."""
    disp = units.DISPLAY_UNITS[unit_system]
    cal_available = has_calibration(well)
    mode = calibration or ("calibrated" if cal_available else "raw")
    offsets = offsets_si(well) if mode == "calibrated" else {}
    len_u = disp["length"]

    def conv_depth(a):
        return np.array([units.from_si(v, len_u) for v in a])

    def conv(a, op):
        u = disp[OP_DIMENSION[op]]
        return np.array([units.from_si(v, u) for v in a])

    ids = [well.id]
    plan = dsm.load_plan(db, ids)
    actual = dsm.load_actual(db, ids)
    model = model or active_model(db)
    pred = prediction_for_dashboard(db, well, model)
    bundle = load_bundle(model.path) if model is not None and model.path else None
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
        warnings.append(
            "No active model yet: charts show only the WellPlan T&D model and actual data"
        )
    else:
        warnings.append(
            "This well has not been predicted with the active model yet: click 'Run prediction again' "
            "(top right) to draw the ML line."
        )

    has_actual = not actual.empty
    limits = applicable_limits(db, well)
    wq = db.scalar(select(WellQuality).where(WellQuality.well_id == well.id))
    review = latest_review(db, well.id)
    if not has_actual:
        warnings.append("No actual data yet: the Difference chart shows only ML - T&D Model")

    ops_out = {}
    for op in OPERATIONS:
        off = offsets.get(op, 0.0)
        curves = {ff: (d, v + off) for ff, (d, v) in dsm.plan_curves(plan, well.id, op).items()}
        # kurva baseline: OHFF 0.3, atau satu-satunya kurva (laporan WellPlan), atau kurva pertama
        base_key = next((k for k in (BASELINE_FF, None) if k in curves), next(iter(curves), None))
        base = curves.get(base_key)
        wp_series = []
        items = sorted(curves.items(), key=lambda kv: (kv[0] is None, kv[0] or 0))
        if op in SINGLE_CURVE_OPS and base is not None:
            items = [(base_key, base)]  # ROT: satu kurva
        for ff, (d, v) in items:
            wp_series.append(
                {
                    "ff": ff,
                    "name": series_name(op, ff),
                    "depth": _r(conv_depth(d), 2),
                    "value": _r(conv(v, op)),
                }
            )

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
            tol = tolerance_si(op)
            if metrics["wellplan"] is not None:
                metrics["wellplan"]["within"] = within_frac(act_v[mask_wp], wp_at_act[mask_wp], tol)
            if metrics["ml"] is not None:
                metrics["ml"]["within"] = within_frac(act_v[mask_ml], ml_at_act[mask_ml], tol)
            # konversi RMSE ke satuan tampilan
            for k in ("wellplan", "ml"):
                if metrics[k] is not None:
                    metrics[k]["rmse"] = float(conv(np.array([metrics[k]["rmse"]]), op)[0])

        band = (bundle or {}).get("operations", {}).get(op, {}).get("band")
        ml_lo = ml_v + band[0] if band and len(ml_v) else np.array([])
        ml_hi = ml_v + band[1] if band and len(ml_v) else np.array([])

        lims = []
        disp_u = disp[OP_DIMENSION[op]]
        for lim in limits:
            if lim.operation != op:
                continue
            wp_d, wp_v = base if base else (np.array([]), np.array([]))
            lims.append(
                {
                    "id": lim.id,
                    "kind": lim.kind,
                    "scope": "well" if lim.well_id else "section",
                    "value": round(units.from_si(lim.value_si, disp_u), 3),
                    "note": lim.note,
                    "cross_ml": _depth_or_none(
                        first_crossing(ml_d, ml_v, lim.value_si, lim.kind), conv_depth
                    ),
                    "cross_ml_band": _depth_or_none(
                        first_crossing(
                            ml_d, ml_hi if lim.kind == "max" else ml_lo, lim.value_si, lim.kind
                        )
                        if len(ml_lo)
                        else None,
                        conv_depth,
                    ),
                    "cross_wellplan": _depth_or_none(
                        first_crossing(wp_d, wp_v, lim.value_si, lim.kind), conv_depth
                    ),
                    "margin_ml": None
                    if not len(ml_v)
                    else round(units.from_si(margin(ml_v, lim.value_si, lim.kind), disp_u), 3),
                }
            )

        ops_out[op] = {
            "label": OP_LABELS[op],
            "unit": units.UNIT_LABELS[disp[OP_DIMENSION[op]]],
            "wellplan": wp_series,
            "wellplan_baseline_ff": BASELINE_FF if BASELINE_FF in curves else None,
            "calibration_offset": None
            if op not in offsets_si(well)
            else round(units.from_si(offsets_si(well)[op], disp[OP_DIMENSION[op]]), 3),
            "ml": {
                "depth": _r(conv_depth(ml_d), 2),
                "value": _r(conv(ml_v, op)),
                "lo": _r(conv(ml_lo, op)),
                "hi": _r(conv(ml_hi, op)),
            },
            "limits": lims,
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
            "tolerance": TOLERANCE_LABEL[OP_DIMENSION[op]],
        }

    return {
        "well": {
            "id": well.id,
            "name": well.name,
            "section_in": well.section_in,
            "well_type": well.well_type,
            "purpose": well.purpose,
        },
        "calibration": {"available": cal_available, "mode": mode},
        "unit_system": unit_system,
        "depth_unit": units.UNIT_LABELS[len_u],
        "has_actual": has_actual,
        "prediction": None
        if pred is None
        else {"id": pred.id, "kind": pred.kind, "model_id": pred.model_id},
        "model": None
        if model is None
        else {
            "id": model.id,
            "active": model.active,
            "dataset_version": (model.params or {}).get("dataset_version"),
            "band_quantiles": [10, 90],
        },
        "quality": {
            "status": effective_status(wq, review),
            "auto_status": wq.status if wq else None,
            "score": wq.score if wq else None,
            "issues": [c for c in (wq.checks if wq else []) if c["level"] != "pass"],
            "review": None
            if review is None
            else {"decision": review.decision, "reason": review.reason},
        },
        "warnings": warnings,
        "sign_convention": "Difference = A - B. Right (+) = A is higher, left (-) = A is lower.",
        "operations": ops_out,
    }
