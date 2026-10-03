"""Evaluasi prediksi vs aktual: setelah data aktual sumur baru diunggah, prediksi yang
dibuat SEBELUMNYA (kind=full) dibandingkan otomatis dengan aktual dan WellPlan."""

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import Prediction, PredictionEvaluation, PredictionPoint, Well
from app.services import dataset as dsm
from app.services.metrics import all_metrics
from app.services.operations import OPERATIONS


def evaluate_prediction(db: Session, pred: Prediction) -> PredictionEvaluation | None:
    actual = dsm.load_actual(db, [pred.well_id])
    if actual.empty:
        return None
    pts = db.execute(
        select(
            PredictionPoint.operation,
            PredictionPoint.depth_m,
            PredictionPoint.wellplan_si,
            PredictionPoint.ml_si,
        ).where(PredictionPoint.prediction_id == pred.id)
    ).all()
    out = {"operations": {}}
    for op in OPERATIONS:
        p = sorted((d, wp, ml) for o, d, wp, ml in pts if o == op)
        a = actual[actual.operation == op]
        if len(p) < 2 or a.empty:
            continue
        d = np.array([x[0] for x in p])
        ml = np.array([x[2] for x in p])
        wp = np.array([np.nan if x[1] is None else x[1] for x in p])
        ad = a.depth_m.to_numpy()
        inside = (ad >= d.min()) & (ad <= d.max())
        if inside.sum() < 2:
            continue
        y = a.actual_si.to_numpy()[inside]
        ml_at = np.interp(ad[inside], d, ml)
        wp_at = (
            np.interp(ad[inside], d[~np.isnan(wp)], wp[~np.isnan(wp)])
            if (~np.isnan(wp)).sum() >= 2
            else None
        )
        better = None
        if wp_at is not None:
            better = float(np.mean(np.abs(ml_at - y) < np.abs(wp_at - y)))
        out["operations"][op] = {
            "ml": all_metrics(y, ml_at),
            "wellplan": all_metrics(y, wp_at) if wp_at is not None else None,
            "ml_better_frac": better,
        }
    if not out["operations"]:
        return None
    db.execute(delete(PredictionEvaluation).where(PredictionEvaluation.prediction_id == pred.id))
    ev = PredictionEvaluation(prediction_id=pred.id, well_id=pred.well_id, metrics=out)
    db.add(ev)
    db.commit()
    return ev


def evaluate_well_predictions(db: Session, well: Well) -> list[PredictionEvaluation]:
    preds = db.scalars(
        select(Prediction).where(Prediction.well_id == well.id, Prediction.kind == "full")
    ).all()
    return [ev for p in preds if (ev := evaluate_prediction(db, p)) is not None]
