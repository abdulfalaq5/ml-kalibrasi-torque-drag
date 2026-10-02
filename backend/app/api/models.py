import io

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import MLModel
from app.db.session import get_db
from app.services.dataset import build_dataset
from app.services.export import export_model_report
from app.services.training import run_training_job

router = APIRouter(prefix="/api/models", tags=["models"])


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
    }
    metrics = m.metrics or {}
    if full:
        out["metrics"] = metrics
    else:
        out["summary"] = {
            op: {
                "chosen": d["chosen"],
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
    algorithm: str = Query("terbaik", pattern="^(terbaik|xgboost|ridge)$"),
    db: Session = Depends(get_db),
):
    running = db.scalar(select(MLModel).where(MLModel.status.in_(["antri", "berjalan"])))
    if running:
        raise HTTPException(409, f"Model #{running.id} masih dilatih")
    m = MLModel(algorithm=algorithm, status="antri")
    db.add(m)
    db.commit()
    background.add_task(run_training_job, m.id, algorithm)
    return model_out(m)


def _get(db: Session, model_id: int) -> MLModel:
    m = db.get(MLModel, model_id)
    if m is None:
        raise HTTPException(404, "Model tidak ditemukan")
    return m


@router.get("/dataset.csv")
def dataset_csv(db: Session = Depends(get_db)):
    """Dataset latih untuk pemeriksaan manual (satuan SI)."""
    ds, notes = build_dataset(db)
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
    if m.status != "selesai":
        raise HTTPException(400, "Hanya model yang selesai dilatih yang bisa diaktifkan")
    db.execute(update(MLModel).values(active=False))
    m.active = True
    db.commit()
    return model_out(m)


@router.get("/{model_id}/report.xlsx")
def report(model_id: int, db: Session = Depends(get_db)):
    m = _get(db, model_id)
    if m.status != "selesai":
        raise HTTPException(400, "Model belum selesai dilatih")
    return Response(
        export_model_report(m),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="laporan_model_{m.id}.xlsx"'},
    )
