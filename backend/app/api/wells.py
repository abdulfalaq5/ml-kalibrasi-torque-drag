from pathlib import Path

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
from app.services.forecast import export_forecast, forecast_well
from app.services.importer import OK_STATUSES, import_file
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
        "purpose": w.purpose,
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
            if f.status in OK_STATUSES
        ],
    }


@router.get("")
def list_wells(
    purpose: str | None = Query(None, pattern="^(training|monitoring)$"),
    db: Session = Depends(get_db),
):
    q = select(Well).options(selectinload(Well.files)).order_by(Well.name, Well.section_in)
    if purpose:
        q = q.where(Well.purpose == purpose)
    wells = db.scalars(q).all()
    ctx = _context(db)
    return [well_out(db, w, ctx) for w in wells]


@router.get("/matrix")
def matrix(db: Session = Depends(get_db)):
    """Matriks jumlah sumur TRAINING per section x tipe (untuk audit & peringatan data sedikit)."""
    rows = db.execute(
        select(Well.section_in, Well.well_type, func.count(Well.id))
        .where(Well.purpose == "training")
        .group_by(Well.section_in, Well.well_type)
    ).all()
    return [{"section_in": s, "well_type": t, "n_wells": n} for s, t, n in rows]


def _get(db: Session, well_id: int) -> Well:
    w = db.get(Well, well_id)
    if w is None:
        raise HTTPException(404, "Well not found")
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
            raise HTTPException(400, f"Well type must be one of {', '.join(WELL_TYPES)}")
        w.well_type = body.well_type
        w.type_source = "manual"
    if body.section_in is not None:
        if not 3 <= body.section_in <= 36:
            raise HTTPException(400, "Well section (in) is outside the valid range")
        clash = db.scalar(
            select(Well).where(
                Well.name == w.name,
                Well.section_in == body.section_in,
                Well.purpose == w.purpose,
                Well.id != w.id,
            )
        )
        if clash:
            raise HTTPException(409, "A well with this name and section already exists")
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
        f.status = "deleted"
        f.well_id = None
    db.delete(w)
    db.commit()
    return {"ok": True}


@router.post("/{well_id}/promote")
def promote(well_id: int, db: Session = Depends(get_db)):
    """Copy a monitoring well into the training data (re-imports its latest file as training).

    The monitoring well stays unchanged; the copy goes through the normal quality gate.
    """
    w = _get(db, well_id)
    if w.purpose != "monitoring":
        raise HTTPException(400, "Only monitoring wells can be promoted to training")
    files = sorted((f for f in w.files if f.status in OK_STATUSES), key=lambda f: f.version or 0)
    if not files:
        raise HTTPException(400, "This well has no valid file to promote")
    src = files[-1]
    uf = import_file(
        db,
        Path(src.path),
        src.filename,
        src.checksum,
        w.name,
        w.section_in,
        source="promote",
        well_type=w.well_type,
        purpose="training",
    )
    return {"file_id": uf.id, "well_id": uf.well_id, "status": uf.status}


class ForecastIn(BaseModel):
    distance_ft: float = 300.0
    start_depth_ft: float | None = None
    step_ft: float = 30.0
    bias_correction: bool | None = None  # None = otomatis (aktif bila ada data aktual)
    units: str = "imperial"
    model_id: int | None = None
    calibration: str | None = None


def _forecast(db: Session, well_id: int, body: ForecastIn) -> dict:
    if body.units not in ("imperial", "si"):
        raise HTTPException(400, "units must be imperial or si")
    if body.calibration not in (None, "calibrated", "raw"):
        raise HTTPException(400, "calibration must be calibrated or raw")
    try:
        return forecast_well(
            db,
            _get(db, well_id),
            body.distance_ft,
            body.start_depth_ft,
            body.step_ft,
            body.bias_correction,
            body.units,
            _model(db, body.model_id),
            body.calibration,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/{well_id}/forecast")
def forecast(well_id: int, body: ForecastIn, db: Session = Depends(get_db)):
    """Prediction N ft ahead of the last actual depth, with cause-and-effect explanation."""
    return _forecast(db, well_id, body)


@router.post("/{well_id}/forecast.xlsx")
def forecast_xlsx(well_id: int, body: ForecastIn, db: Session = Depends(get_db)):
    fc = _forecast(db, well_id, body)
    w = fc["well"]
    fname = (
        f"{w['name']}_{(w['section_in'] or 0):g}in_prediction_{body.distance_ft:g}ft.xlsx".replace(
            " ", "_"
        )
    )
    return Response(
        export_forecast(fc),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


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
        raise HTTPException(404, "Model not found")
    return m


@router.get("/{well_id}/profile")
def profile(
    well_id: int,
    units: str = Query("imperial", pattern="^(imperial|si)$"),
    model_id: int | None = None,
    calibration: str | None = Query(None, pattern="^(calibrated|raw)$"),
    db: Session = Depends(get_db),
):
    return well_profile(db, _get(db, well_id), units, _model(db, model_id), calibration)


@router.get("/{well_id}/report.pdf")
def report_pdf(
    well_id: int,
    units: str = Query("imperial", pattern="^(imperial|si)$"),
    target: str = Query("pick_up"),
    model_id: int | None = None,
    calibration: str | None = Query(None, pattern="^(calibrated|raw)$"),
    db: Session = Depends(get_db),
):
    if target not in OPERATIONS:
        raise HTTPException(400, "Unknown target")
    w = _get(db, well_id)
    data = well_pdf(db, w, units, target, _model(db, model_id), calibration)
    fname = f"summary_{w.name}_{(w.section_in or 0):g}in.pdf".replace(" ", "_")
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
    calibration: str | None = Query(None, pattern="^(calibrated|raw)$"),
    db: Session = Depends(get_db),
):
    if target not in OPERATIONS:
        raise HTTPException(400, "Unknown target")
    w = _get(db, well_id)
    data = export_well(db, w, units, target, _model(db, model_id), calibration)
    fname = f"OUTPUT {w.name} {(w.section_in or 0):g}in Multiple T&D Road Map.xlsx"
    return Response(
        data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
