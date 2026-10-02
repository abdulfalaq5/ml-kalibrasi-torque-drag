"""Prediksi sumur memakai model aktif."""

from functools import lru_cache

import joblib
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import MLModel, Prediction, PredictionPoint, Well
from app.services import dataset as dsm
from app.services.training import MIN_WELLS_PER_GROUP, active_model


@lru_cache(maxsize=4)
def load_bundle(path: str) -> dict:
    return joblib.load(path)


def coverage_warnings(bundle: dict, section: str | None, well_type: str | None) -> list[str]:
    warns = []
    if section not in bundle["train_sections"]:
        warns.append(f'Section {section or "?"}" tidak ada di data latih; prediksi kurang andal')
    if well_type not in bundle["train_types"]:
        warns.append(
            f"Tipe sumur {well_type or '?'} tidak ada di data latih; prediksi kurang andal"
        )
    n = bundle["train_combos"].get(f"{section}|{well_type}", 0)
    if 0 < n < MIN_WELLS_PER_GROUP:
        warns.append(
            f'Kombinasi section {section}" x tipe {well_type} hanya punya {n} sumur latih '
            f"(< {MIN_WELLS_PER_GROUP}); data sedikit"
        )
    return warns


def predict_well(db: Session, well: Well, model: MLModel | None = None) -> Prediction:
    model = model or active_model(db)
    if model is None:
        raise ValueError("Belum ada model aktif. Latih model terlebih dahulu.")
    bundle = load_bundle(model.path)
    wells = dsm.load_wells(db, [well.id])
    w = wells.iloc[0]
    plan, survey = dsm.load_plan(db, [well.id]), dsm.load_survey(db, [well.id])
    grid = dsm.plan_grid(db, well.id)
    if not len(grid):
        raise ValueError("Sumur ini belum punya hasil WellPlan untuk diprediksi")

    section = w.section or "tidak diketahui"
    wtype = w.well_type or "tidak diketahui"
    warns = coverage_warnings(bundle, w.section, w.well_type)
    if survey.empty:
        warns.append("Tidak ada survey: inklinasi dan dogleg diisi nilai tengah data latih")
    lo, hi = bundle["depth_range_m"]
    if grid.max() > hi * 1.1 or grid.min() < lo * 0.9:
        warns.append(
            f"Rentang kedalaman sumur ({grid.min():.0f}-{grid.max():.0f} m) melewati rentang "
            f"data latih ({lo:.0f}-{hi:.0f} m)"
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
    for op, cm in bundle["operations"].items():
        f = dsm.features_frame(w, op, grid, plan, survey).dropna(subset=["wp_base"])
        if f.empty:
            warns.append(f"{op}: tidak ada hasil WellPlan, tidak diprediksi")
            continue
        f["section"], f["well_type"] = section, wtype
        yhat = cm.predict(f)
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


def prediction_for_dashboard(db: Session, well: Well) -> Prediction | None:
    """Sumur latih -> prediksi out-of-fold model aktif; selain itu prediksi penuh."""
    model = active_model(db)
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
