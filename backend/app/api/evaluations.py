from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Prediction, PredictionEvaluation, Well
from app.db.session import get_db

router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])


@router.get("")
def list_evaluations(db: Session = Depends(get_db)):
    out = []
    for ev in db.scalars(select(PredictionEvaluation).order_by(PredictionEvaluation.id.desc())):
        w = db.get(Well, ev.well_id)
        p = db.get(Prediction, ev.prediction_id)
        out.append(
            {
                "id": ev.id,
                "well_id": ev.well_id,
                "well": w.name if w else None,
                "section_in": w.section_in if w else None,
                "model_id": p.model_id if p else None,
                "predicted_at": p.created_at if p else None,
                "evaluated_at": ev.created_at,
                "metrics": ev.metrics,
            }
        )
    return out
