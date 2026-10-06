import io

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import Dataset, MLModel
from app.db.session import get_db
from app.services.dataset import build_dataset
from app.services.export import export_model_report
from app.services.pdf import model_pdf
from app.services.quality import eligible_well_ids
from app.services.training import run_blind_test, run_training_job

router = APIRouter(prefix="/api/models", tags=["models"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def model_out(m: MLModel, full: bool = False) -> dict:
    out = {
        "id": m.id,
        "algorithm": m.algorithm,
        "status": m.status,
        "active": m.active,
        "message": m.message,
        "created_at": m.created_at,
        "finished_at": m.finished_at,
        "params": m.params,
        "dataset_id": m.dataset_id,
        "dataset_version": (m.params or {}).get("dataset_version"),
        "comparison": m.comparison,
        "blind_done": bool(m.blind_result),
    }
    metrics = m.metrics or {}
    out["skill"] = metrics.get("skill")
    if full:
        out["metrics"] = metrics
        out["blind_result"] = m.blind_result
    else:
        out["summary"] = {
            op: {
                "chosen": d["chosen"],
                "chosen_label": d.get("chosen_label"),
                "wellplan_rmse": d["overall"]["wellplan"]["rmse"],
                "ml_rmse": d["overall"]["ml"]["rmse"],
                "n_wells": d["overall"]["n_wells"],
            }
            for op, d in metrics.get("operations", {}).items()
        }
    return out


@router.get("")
def list_models(db: Session = Depends(get_db)):
    return [model_out(m) for m in db.scalars(select(MLModel).order_by(MLModel.id.desc()))]


@router.post("/train")
def train(
    background: BackgroundTasks,
    algorithm: str = Query("all", pattern="^(all|ridge|xgboost|random_forest|svr|mlp)$"),
    include_mlp: bool = False,
    dataset_id: int | None = None,
    db: Session = Depends(get_db),
):
    running = db.scalar(select(MLModel).where(MLModel.status.in_(["queued", "running"])))
    if running:
        raise HTTPException(409, f"Model #{running.id} is still training")
    if dataset_id is not None and db.get(Dataset, dataset_id) is None:
        raise HTTPException(404, "Dataset not found")
    m = MLModel(algorithm=algorithm, status="queued", dataset_id=dataset_id)
    db.add(m)
    db.commit()
    background.add_task(run_training_job, m.id, algorithm, include_mlp, dataset_id)
    return model_out(m)


def _get(db: Session, model_id: int) -> MLModel:
    m = db.get(MLModel, model_id)
    if m is None:
        raise HTTPException(404, "Model not found")
    return m


@router.get("/dataset.csv")
def dataset_csv(db: Session = Depends(get_db)):
    """Dataset LIVE (belum beku) dari sumur berstatus A/B, untuk pemeriksaan manual (SI)."""
    ids, _ = eligible_well_ids(db)
    ds, notes = build_dataset(db, ids)
    buf = io.StringIO()
    for n in notes:
        buf.write(f"# {n}\n")
    ds.to_csv(buf, index=False)
    return Response(
        buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="dataset_si.csv"'},
    )


@router.get("/{model_id}")
def get_model(model_id: int, db: Session = Depends(get_db)):
    return model_out(_get(db, model_id), full=True)


@router.post("/{model_id}/activate")
def activate(model_id: int, db: Session = Depends(get_db)):
    m = _get(db, model_id)
    if m.status not in ("done", "held"):
        raise HTTPException(400, "Only a model that has finished training can be activated")
    db.execute(update(MLModel).values(active=False))
    if m.status == "held":
        cmp = dict(m.comparison or {})
        cmp["decision"] = (cmp.get("decision", "") + " | Activated manually by the admin.").strip(
            " |"
        )
        m.comparison = cmp
    m.status = "done"
    m.active = True
    db.commit()
    from app.services.predict import refresh_monitoring_predictions

    refresh_monitoring_predictions(db, m)  # garis ML sumur monitoring memakai model yang baru aktif
    return model_out(m)


@router.post("/{model_id}/blind-test")
def blind_test(model_id: int, db: Session = Depends(get_db)):
    try:
        return run_blind_test(db, _get(db, model_id))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/{model_id}/report.xlsx")
def report(model_id: int, db: Session = Depends(get_db)):
    m = _get(db, model_id)
    if m.status not in ("done", "held"):
        raise HTTPException(400, "The model has not finished training")
    return Response(
        export_model_report(m, db.get(Dataset, m.dataset_id) if m.dataset_id else None),
        media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="model_report_{m.id}.xlsx"'},
    )


@router.get("/{model_id}/report.pdf")
def report_pdf(model_id: int, db: Session = Depends(get_db)):
    m = _get(db, model_id)
    if m.status not in ("done", "held"):
        raise HTTPException(400, "The model has not finished training")
    return Response(
        model_pdf(db, m),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="model_summary_{m.id}.pdf"'},
    )
