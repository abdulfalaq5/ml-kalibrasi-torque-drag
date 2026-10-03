import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.db.models import UploadedFile
from app.db.session import get_db
from app.services.importer import ALLOWED_EXT, import_file, store_upload

router = APIRouter(prefix="/api/files", tags=["files"])

ZIP_MAGIC = b"PK\x03\x04"


def file_out(f: UploadedFile, db: Session | None = None) -> dict:
    quality = None
    if db is not None and f.well_id:
        from app.db.models import WellQuality
        from app.services.quality import effective_status, latest_review

        wq = db.scalar(select(WellQuality).where(WellQuality.well_id == f.well_id))
        quality = {
            "status": effective_status(wq, latest_review(db, f.well_id)),
            "score": wq.score if wq else None,
            "issues": [c["message"] for c in (wq.checks if wq else []) if c["level"] != "lolos"],
        }
    return {
        "quality": quality,
        "section_in": f.well.section_in if f.well else None,
        "well_type": f.well.well_type if f.well else None,
        "id": f.id,
        "filename": f.filename,
        "kind": f.kind,
        "status": f.status,
        "well_id": f.well_id,
        "well_name": f.well.name if f.well else None,
        "created_at": f.created_at,
        "summary": f.summary,
        "issues": [
            {"level": i.level, "message": i.message, "location": i.location} for i in f.issues
        ],
    }


@router.post("")
# sync def: impor berat dijalankan di threadpool, tidak memblokir event loop
def upload(
    file: UploadFile = File(...),
    well_name: str | None = Form(None),
    section_in: float | None = Form(None),
    well_type: str | None = Form(None),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    if well_type and well_type not in ("J", "S", "Horizontal"):
        raise HTTPException(400, "Tipe sumur harus J, S, atau Horizontal")
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"Hanya file {', '.join(sorted(ALLOWED_EXT))} yang diterima")
    limit = settings.max_upload_mb * 1024 * 1024
    size = 0
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp_path = Path(tmp.name)
        while chunk := file.file.read(1 << 20):
            size += len(chunk)
            if size > limit:
                tmp_path.unlink(missing_ok=True)
                raise HTTPException(413, f"File lebih besar dari {settings.max_upload_mb} MB")
            tmp.write(chunk)
    try:
        with tmp_path.open("rb") as fh:
            if fh.read(4) != ZIP_MAGIC:
                raise HTTPException(400, "Isi file bukan Excel .xlsx/.xlsm yang valid")
        dest, checksum = store_upload(tmp_path, file.filename or "file.xlsx")
    finally:
        tmp_path.unlink(missing_ok=True)
    uf = import_file(
        db,
        dest,
        file.filename or dest.name,
        checksum,
        well_name or None,
        section_in,
        well_type=well_type or None,
    )
    db.refresh(uf)
    return file_out(uf, db)


@router.get("")
def list_files(db: Session = Depends(get_db)):
    q = (
        select(UploadedFile)
        .options(selectinload(UploadedFile.issues), selectinload(UploadedFile.well))
        .order_by(UploadedFile.id.desc())
    )
    return [file_out(f) for f in db.scalars(q)]


@router.get("/{file_id}")
def get_file(file_id: int, db: Session = Depends(get_db)):
    f = db.get(UploadedFile, file_id)
    if f is None:
        raise HTTPException(404, "File tidak ditemukan")
    return file_out(f)


@router.get("/{file_id}/download")
def download(file_id: int, db: Session = Depends(get_db)):
    f = db.get(UploadedFile, file_id)
    if f is None:
        raise HTTPException(404, "File tidak ditemukan")
    path = Path(f.path).resolve()
    if not path.is_relative_to(get_settings().upload_dir.resolve()) or not path.exists():
        raise HTTPException(404, "File tidak tersedia")
    return FileResponse(path, filename=f.filename)
