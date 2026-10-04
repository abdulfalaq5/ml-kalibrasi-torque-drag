"""Prediksi sumur memakai model aktif (atau model tertentu)."""

from functools import lru_cache

import joblib
import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import MLModel, Prediction, PredictionPoint, Well
from app.services import dataset as dsm
from app.services.operations import OP_LABELS
from app.services.training import MIN_WELLS_PER_GROUP, active_model


@lru_cache(maxsize=4)
def load_bundle(path: str) -> dict:
    return joblib.load(path)


def coverage_warnings(bundle: dict, section: str | None, well_type: str | None) -> list[str]:
    warns = []
    if section not in bundle["train_sections"]:
        warns.append(
            f'Well section {section or "?"}" is not in the training data; the forecast is less reliable'
        )
    if well_type not in bundle["train_types"]:
        warns.append(
            f"Well type {well_type or '?'} is not in the training data; the forecast is less reliable"
        )
    n = bundle["train_combos"].get(f"{section}|{well_type}", 0)
    if 0 < n < MIN_WELLS_PER_GROUP:
        warns.append(
            f'Section {section}" x type {well_type} has only {n} training wells '
            f"(< {MIN_WELLS_PER_GROUP}); limited data"
        )
    return warns


def predict_frame(bundle: dict, op: str, f) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    entry = bundle["operations"][op]
    y = entry["model"].predict(f)
    lo, hi = entry.get("band", [0.0, 0.0])
    return y, y + lo, y + hi


def predict_well(db: Session, well: Well, model: MLModel | None = None) -> Prediction:
    model = model or active_model(db)
    if model is None:
        raise ValueError("No active model yet. Train a model first.")
    bundle = load_bundle(model.path)
    w = dsm.load_wells(db, [well.id]).iloc[0]
    plan, survey = dsm.load_plan(db, [well.id]), dsm.load_survey(db, [well.id])
    grid = dsm.plan_grid(db, well.id)
    if not len(grid):
        raise ValueError("This well has no WellPlan T&D model results to forecast from")

    warns = coverage_warnings(bundle, w.section, w.well_type)
    if survey.empty and "survey" in bundle["features"]["groups"]:
        warns.append(
            "No survey: inclination/dogleg features use the training median (fill in the Survey sheet for a better forecast)"
        )
    lo, hi = bundle["depth_range_m"]
    if grid.max() > hi * 1.1 or grid.min() < lo * 0.9:
        warns.append(
            f"Well depth range ({grid.min():.0f}-{grid.max():.0f} m) is outside the training "
            f"depth range ({lo:.0f}-{hi:.0f} m)"
        )
    if w.well_name in bundle.get("trained_wells", []):
        warns.append(
            "This well is part of the model training data; see the out-of-fold forecast for a fair comparison"
        )

    db.execute(
        delete(Prediction).where(
            Prediction.well_id == well.id,
            Prediction.model_id == model.id,
            Prediction.kind == "full",
        )
    )
    pred = Prediction(well_id=well.id, model_id=model.id, kind="full", warnings=warns)
    db.add(pred)
    db.flush()
    for op in bundle["operations"]:
        f = dsm.features_frame(w, op, grid, plan, survey).dropna(subset=["wp_base"])
        if f.empty:
            warns.append(f"{OP_LABELS[op]}: no WellPlan T&D model result, not forecast")
            continue
        for c in ("section", "well_type", "plan_format", "interval_type"):
            f[c] = f[c].fillna("unknown").astype(str)
        yhat, _, _ = predict_frame(bundle, op, f)
        db.add_all(
            PredictionPoint(
                prediction_id=pred.id,
                operation=op,
                depth_m=float(d),
                wellplan_si=float(wp),
                ml_si=float(y),
            )
            for d, wp, y in zip(f.depth_m, f.wp_base, yhat, strict=True)
        )
    pred.warnings = list(warns)
    db.commit()
    return pred


def prediction_for_dashboard(
    db: Session, well: Well, model: MLModel | None = None
) -> Prediction | None:
    """Sumur latih -> prediksi out-of-fold; selain itu prediksi penuh model tersebut."""
    model = model or active_model(db)
    if model is None:
        return None
    for kind in ("oof", "full"):
        p = db.scalar(
            select(Prediction)
            .where(
                Prediction.well_id == well.id,
                Prediction.model_id == model.id,
                Prediction.kind == kind,
            )
            .order_by(Prediction.id.desc())
        )
        if p is not None:
            return p
    return None
