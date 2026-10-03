from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    ActualReading,
    MLModel,
    PlanResult,
    Prediction,
    QualityReview,
    Survey,
    Well,
    WellQuality,
)
from app.db.session import get_db
from app.services.evaluation import evaluate_well_predictions
from app.services.export import export_well
from app.services.operations import OPERATIONS, WELL_TYPES
from app.services.pdf import well_pdf
from app.services.predict import predict_well
from app.services.profile import well_profile
from app.services.quality import effective_status, evaluate_well
from app.services.training import active_model

router = APIRouter(prefix="/api/wells", tags=["wells"])


def _context(db: Session, ids: list[int] | None = None) -> dict:
    """Data pendukung daftar sumur dalam beberapa kueri agregat (bukan per sumur)."""

    def counts(model) -> dict[int, int]:
        q = select(model.well_id, func.count(model.id)).group_by(model.well_id)
        if ids is not None:
            q = q.where(model.well_id.in_(ids))
        return dict(db.execute(q).all())

    ffs: dict[int, set] = {}
    q = select(PlanResult.well_id, PlanResult.ff).distinct()
    if ids is not None:
        q = q.where(PlanResult.well_id.in_(ids))
    for wid, ff in db.execute(q).all():
        if ff is not None:
            ffs.setdefault(wid, set()).add(ff)
    model = active_model(db)
    kinds: dict[int, set] = {}
    if model is not None:
        for wid, kind in db.execute(
            select(Prediction.well_id, Prediction.kind).where(Prediction.model_id == model.id)
        ).all():
            kinds.setdefault(wid, set()).add(kind)
    quality = {q.well_id: q for q in db.scalars(select(WellQuality))}
    reviews = {}
    for r in db.scalars(select(QualityReview).order_by(QualityReview.created_at, QualityReview.id)):
        reviews[r.well_id] = r  # terakhir menang
    return {
        "survey": counts(Survey),
        "plan": counts(PlanResult),
        "actual": counts(ActualReading),
        "ffs": ffs,
        "kinds": kinds,
        "quality": quality,
        "reviews": reviews,
    }


def well_out(db: Session, w: Well, ctx: dict | None = None) -> dict:
    ctx = ctx or _context(db, [w.id])
    wq = ctx["quality"].get(w.id)
    kinds = ctx["kinds"].get(w.id, set())
    return {
        "id": w.id,
        "name": w.name,
        "quality": effective_status(wq, ctx["reviews"].get(w.id)),
        "quality_score": wq.score if wq else None,
        "plan_format": (w.meta or {}).get("plan_format"),
        "section_in": w.section_in,
        "well_type": w.well_type,
        "section_source": w.section_source,
        "type_source": w.type_source,
        "status": w.status,
        "meta": w.meta,
        "survey_points": ctx["survey"].get(w.id, 0),
        "plan_points": ctx["plan"].get(w.id, 0),
        "actual_points": ctx["actual"].get(w.id, 0),
        "ff_scenarios": sorted(ctx["ffs"].get(w.id, set())),
        "prediction": "oof" if "oof" in kinds else ("full" if kinds else None),
        "files": [
            {"id": f.id, "filename": f.filename, "status": f.status, "version": f.version}
            for f in w.files
            if f.status in ("ok", "peringatan")
        ],
    }


@router.get("")
def list_wells(db: Session = Depends(get_db)):
    wells = db.scalars(
        select(Well).options(selectinload(Well.files)).order_by(Well.name, Well.section_in)
    ).all()
    ctx = _context(db)
    return [well_out(db, w, ctx) for w in wells]


@router.get("/matrix")
def matrix(db: Session = Depends(get_db)):
    """Matriks jumlah sumur per section x tipe (untuk audit & peringatan data sedikit)."""
    rows = db.execute(
        select(Well.section_in, Well.well_type, func.count(Well.id)).group_by(
            Well.section_in, Well.well_type
        )
    ).all()
    return [{"section_in": s, "well_type": t, "n_wells": n} for s, t, n in rows]


def _get(db: Session, well_id: int) -> Well:
    w = db.get(Well, well_id)
    if w is None:
        raise HTTPException(404, "Sumur tidak ditemukan")
    return w


@router.get("/{well_id}")
def get_well(well_id: int, db: Session = Depends(get_db)):
    return well_out(db, _get(db, well_id))


class WellPatch(BaseModel):
    section_in: float | None = None
    well_type: str | None = None


@router.patch("/{well_id}")
def patch_well(well_id: int, body: WellPatch, db: Session = Depends(get_db)):
    """Koreksi manual section / tipe sumur."""
    w = _get(db, well_id)
    changed = body.well_type is not None or body.section_in is not None
    if body.well_type is not None:
        if body.well_type not in WELL_TYPES:
            raise HTTPException(400, f"Tipe sumur harus salah satu dari {WELL_TYPES}")
        w.well_type = body.well_type
        w.type_source = "manual"
    if body.section_in is not None:
        if not 3 <= body.section_in <= 36:
            raise HTTPException(400, "Section (inci) di luar rentang wajar")
        clash = db.scalar(
            select(Well).where(
                Well.name == w.name, Well.section_in == body.section_in, Well.id != w.id
            )
        )
        if clash:
            raise HTTPException(409, "Sumur dengan nama dan section ini sudah ada")
        w.section_in = body.section_in
        w.section_source = "manual"
    db.commit()
    if changed:
        evaluate_well(db, w)
    return well_out(db, w)


@router.delete("/{well_id}")
def delete_well(well_id: int, db: Session = Depends(get_db)):
    w = _get(db, well_id)
    for f in w.files:
        f.status = "dihapus"
        f.well_id = None
    db.delete(w)
    db.commit()
    return {"ok": True}


@router.post("/{well_id}/predict")
def predict(well_id: int, model_id: int | None = None, db: Session = Depends(get_db)):
    w = _get(db, well_id)
    try:
        p = predict_well(db, w, _model(db, model_id))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"prediction_id": p.id, "warnings": p.warnings}


def _model(db: Session, model_id: int | None) -> MLModel | None:
    if model_id is None:
        return None
    m = db.get(MLModel, model_id)
    if m is None or not m.path:
        raise HTTPException(404, "Model tidak ditemukan")
    return m


@router.get("/{well_id}/profile")
def profile(
    well_id: int,
    units: str = Query("imperial", pattern="^(imperial|si)$"),
    model_id: int | None = None,
    db: Session = Depends(get_db),
):
    return well_profile(db, _get(db, well_id), units, _model(db, model_id))


@router.get("/{well_id}/report.pdf")
def report_pdf(
    well_id: int,
    units: str = Query("imperial", pattern="^(imperial|si)$"),
    target: str = Query("pick_up"),
    model_id: int | None = None,
    db: Session = Depends(get_db),
):
    if target not in OPERATIONS:
        raise HTTPException(400, "Target tidak dikenal")
    w = _get(db, well_id)
    data = well_pdf(db, w, units, target, _model(db, model_id))
    fname = f"ringkasan_{w.name}_{(w.section_in or 0):g}in.pdf".replace(" ", "_")
    return Response(
        data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/{well_id}/evaluate")
def evaluate(well_id: int, db: Session = Depends(get_db)):
    evs = evaluate_well_predictions(db, _get(db, well_id))
    return {"evaluations": [e.metrics for e in evs]}


@router.get("/{well_id}/export.xlsx")
def export(
    well_id: int,
    units: str = Query("imperial", pattern="^(imperial|si)$"),
    target: str = Query("pick_up"),
    model_id: int | None = None,
    db: Session = Depends(get_db),
):
    if target not in OPERATIONS:
        raise HTTPException(400, "Target tidak dikenal")
    w = _get(db, well_id)
    data = export_well(db, w, units, target, _model(db, model_id))
    fname = f"{w.name}_{(w.section_in or 0):g}in_perbandingan.xlsx".replace(" ", "_")
    return Response(
        data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
