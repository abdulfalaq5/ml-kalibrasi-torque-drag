from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import require_admin
from app.db.models import QualityReview, Well, WellQuality
from app.db.session import get_db
from app.services.export import export_quality_report
from app.services.quality import DECISIONS, effective_status, latest_review, recompute_all

router = APIRouter(prefix="/api/quality", tags=["quality"])

STATUS_LABEL = {"A": "Layak", "B": "Layak dengan peringatan", "C": "Ditahan", "X": "Dikecualikan"}


def quality_rows(db: Session) -> list[dict]:
    rows = []
    for w in db.scalars(select(Well).order_by(Well.name, Well.section_in)):
        wq = db.scalar(select(WellQuality).where(WellQuality.well_id == w.id))
        reviews = db.scalars(
            select(QualityReview)
            .where(QualityReview.well_id == w.id)
            .order_by(QualityReview.id.desc())
        ).all()
        eff = effective_status(wq, reviews[0] if reviews else None)
        rows.append(
            {
                "well_id": w.id,
                "well": w.name,
                "section_in": w.section_in,
                "well_type": w.well_type,
                "auto_status": wq.status if wq else None,
                "status": eff,
                "status_label": STATUS_LABEL.get(eff),
                "score": wq.score if wq else None,
                "checks": wq.checks if wq else [],
                "stats": wq.stats if wq else {},
                "computed_at": wq.computed_at if wq else None,
                "reviews": [
                    {
                        "decision": r.decision,
                        "reason": r.reason,
                        "reviewer": r.reviewer,
                        "created_at": r.created_at,
                    }
                    for r in reviews
                ],
            }
        )
    return rows


@router.get("")
def list_quality(db: Session = Depends(get_db)):
    return quality_rows(db)


@router.post("/recompute")
def recompute(db: Session = Depends(get_db)):
    return recompute_all(db)


class ReviewIn(BaseModel):
    decision: str
    reason: str


@router.post("/{well_id}/review")
def review(well_id: int, body: ReviewIn, request: Request, db: Session = Depends(get_db)):
    if body.decision not in DECISIONS:
        raise HTTPException(400, f"Keputusan harus salah satu dari {sorted(DECISIONS)}")
    if len(body.reason.strip()) < 5:
        raise HTTPException(400, "Alasan wajib diisi (minimal 5 karakter)")
    if db.get(Well, well_id) is None:
        raise HTTPException(404, "Sumur tidak ditemukan")
    db.add(
        QualityReview(
            well_id=well_id,
            decision=body.decision,
            reason=body.reason.strip(),
            reviewer=require_admin(request),
        )
    )
    db.commit()
    wq = db.scalar(select(WellQuality).where(WellQuality.well_id == well_id))
    return {"status": effective_status(wq, latest_review(db, well_id))}


@router.get("/report.xlsx")
def report(db: Session = Depends(get_db)):
    return Response(
        export_quality_report(quality_rows(db)),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="laporan_kualitas_data.xlsx"'},
    )
