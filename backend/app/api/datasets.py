from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import BlindSet, Dataset
from app.db.session import get_db
from app.services.dataset import active_blind_set, freeze_dataset

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


def ds_out(d: Dataset, full: bool = False) -> dict:
    out = {
        "id": d.id,
        "version": d.version,
        "created_at": d.created_at,
        "hash": d.content_hash,
        "n_rows": d.n_rows,
        "n_wells": len(d.wells),
        "n_excluded": len(d.excluded),
        "n_blind": sum(1 for w in d.wells if w.get("blind")),
        "blind_set_id": d.blind_set_id,
    }
    if full:
        out.update({"wells": d.wells, "excluded": d.excluded, "notes": d.notes})
    return out


@router.get("")
def list_datasets(db: Session = Depends(get_db)):
    return [ds_out(d) for d in db.scalars(select(Dataset).order_by(Dataset.version.desc()))]


@router.post("/freeze")
def freeze(db: Session = Depends(get_db)):
    try:
        return ds_out(freeze_dataset(db), full=True)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/blind")
def blind(db: Session = Depends(get_db)):
    bs = active_blind_set(db)
    if bs is None:
        return None
    return {
        "id": bs.id,
        "wells": bs.wells,
        "note": bs.note,
        "created_at": bs.created_at,
        "seed": bs.seed,
    }


class ResetIn(BaseModel):
    confirm: str


@router.post("/blind/reset")
def reset_blind(body: ResetIn, db: Session = Depends(get_db)):
    """Buka kunci blind test (mis. data berubah total). Wajib konfirmasi tertulis."""
    if body.confirm != "BUKA KUNCI":
        raise HTTPException(400, "Ketik 'BUKA KUNCI' untuk mengonfirmasi")
    db.execute(update(BlindSet).values(active=False))
    db.commit()
    return {"ok": True}


@router.get("/{dataset_id}")
def get_dataset(dataset_id: int, db: Session = Depends(get_db)):
    d = db.get(Dataset, dataset_id)
    if d is None:
        raise HTTPException(404, "Dataset tidak ditemukan")
    return ds_out(d, full=True)


@router.get("/{dataset_id}/download.csv.gz")
def download(dataset_id: int, db: Session = Depends(get_db)):
    d = db.get(Dataset, dataset_id)
    if d is None:
        raise HTTPException(404, "Dataset tidak ditemukan")
    with open(d.path, "rb") as fh:
        data = fh.read()
    return Response(
        data,
        media_type="application/gzip",
        headers={"Content-Disposition": f'attachment; filename="dataset_v{d.version}.csv.gz"'},
    )
