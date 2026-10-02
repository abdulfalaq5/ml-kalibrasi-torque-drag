from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import ActualReading, PlanResult, Prediction, Survey, Well
from app.db.session import get_db
from app.services.export import export_well
from app.services.operations import OPERATIONS, WELL_TYPES
from app.services.predict import predict_well
from app.services.profile import well_profile
from app.services.training import active_model

router = APIRouter(prefix="/api/wells", tags=["wells"])


def _counts(db: Session, model, well_id: int) -> int:
    return db.scalar(select(func.count(model.id)).where(model.well_id == well_id)) or 0


def well_out(db: Session, w: Well) -> dict:
    model = active_model(db)
    pred_kinds = []
    if model is not None:
        pred_kinds = list(
            db.scalars(
                select(Prediction.kind).where(
                    Prediction.well_id == w.id, Prediction.model_id == model.id
                )
            )
        )
    return {
        "id": w.id,
        "name": w.name,
        "section_in": w.section_in,
        "well_type": w.well_type,
        "section_source": w.section_source,
        "type_source": w.type_source,
        "status": w.status,
        "meta": w.meta,
        "survey_points": _counts(db, Survey, w.id),
        "plan_points": _counts(db, PlanResult, w.id),
        "actual_points": _counts(db, ActualReading, w.id),
        "ff_scenarios": sorted(
            f
            for f in db.scalars(select(PlanResult.ff).where(PlanResult.well_id == w.id).distinct())
            if f is not None
        ),
        "prediction": "oof" if "oof" in pred_kinds else ("full" if pred_kinds else None),
        "files": [{"id": f.id, "filename": f.filename, "status": f.status} for f in w.files],
    }


@router.get("")
def list_wells(db: Session = Depends(get_db)):
    wells = db.scalars(select(Well).order_by(Well.name, Well.section_in)).all()
    return [well_out(db, w) for w in wells]


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
def predict(well_id: int, db: Session = Depends(get_db)):
    w = _get(db, well_id)
    try:
        p = predict_well(db, w)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"prediction_id": p.id, "warnings": p.warnings}


@router.get("/{well_id}/profile")
def profile(
    well_id: int,
    units: str = Query("imperial", pattern="^(imperial|si)$"),
    db: Session = Depends(get_db),
):
    return well_profile(db, _get(db, well_id), units)


@router.get("/{well_id}/export.xlsx")
def export(
    well_id: int,
    units: str = Query("imperial", pattern="^(imperial|si)$"),
    target: str = Query("pick_up"),
    db: Session = Depends(get_db),
):
    if target not in OPERATIONS:
        raise HTTPException(400, "Target tidak dikenal")
    w = _get(db, well_id)
    data = export_well(db, w, units, target)
    fname = f"{w.name}_{(w.section_in or 0):g}in_perbandingan.xlsx".replace(" ", "_")
    return Response(
        data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
