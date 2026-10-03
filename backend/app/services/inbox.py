"""Impor massal dari folder inbox (tombol "Pindai folder", bukan pemantau otomatis).

Struktur yang diterima (kode sumur = nama folder):
    inbox/<sumur>/<file>.xlsx|.xlsm
    inbox/<J|S|Horizontal>/<sumur>/<file>   (tipe sumur dari folder induk)

- File yang diubah < INBOX_MIN_AGE_S detik terakhir dilewati (mungkin masih disalin).
- Idempoten: checksum sama -> tidak diimpor dua kali; file berubah -> versi baru.
- Setelah impor: file dipindah ke processed/ (diterima) atau rejected/ (+ file alasan).
"""

import logging
import shutil
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import ScanRun, UploadedFile
from app.services.importer import ALLOWED_EXT, find_by_checksum, import_file, sha256, store_upload
from app.services.quality import recompute_all

log = logging.getLogger(__name__)


def pending_files() -> list[Path]:
    s = get_settings()
    if not s.inbox_dir.exists():
        return []
    return sorted(
        p
        for p in s.inbox_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in ALLOWED_EXT and not p.name.startswith(("~$", "."))
    )


def inbox_status() -> dict:
    s = get_settings()
    files = pending_files()
    now = time.time()
    return {
        "inbox_dir": str(s.inbox_dir),
        "exists": s.inbox_dir.exists(),
        "pending": len(files),
        "too_new": sum(1 for f in files if now - f.stat().st_mtime < s.inbox_min_age_s),
        "wells": len({f.parent for f in files}),
        "move_after_import": s.inbox_move,
    }


def _move(src: Path, root: Path, rel: Path, reason: str | None = None) -> None:
    dest = root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest = dest.with_name(f"{dest.stem}_{int(time.time())}{dest.suffix}")
    shutil.move(str(src), dest)
    if reason:
        dest.with_name(dest.name + ".alasan.txt").write_text(reason, encoding="utf-8")


def scan(db: Session, run: ScanRun) -> ScanRun:
    s = get_settings()
    limit = s.max_upload_mb * 1024 * 1024
    now = time.time()
    results = []
    for path in pending_files():
        rel = path.relative_to(s.inbox_dir)
        item = {"file": str(rel), "well": None, "section": None, "status": None, "message": ""}
        try:
            if now - path.stat().st_mtime < s.inbox_min_age_s:
                item.update(
                    status="dilewati", message="Baru diubah < 1 menit, mungkin masih disalin"
                )
                results.append(item)
                continue
            if path.stat().st_size > limit:
                item.update(status="ditolak", message=f"Ukuran > {s.max_upload_mb} MB")
                if s.inbox_move:
                    _move(path, s.rejected_dir, rel, item["message"])
                results.append(item)
                continue
            checksum = sha256(path)
            dup = find_by_checksum(db, checksum)
            if dup is not None:
                item.update(
                    status="duplikat",
                    well=dup.well.name if dup.well else None,
                    message=f"Isi file sama dengan '{dup.filename}' yang sudah diimpor",
                )
                if s.inbox_move:
                    _move(path, s.processed_dir, rel)
                results.append(item)
                continue
            dest, checksum = store_upload(path, path.name)
            uf: UploadedFile = import_file(
                db, dest, path.name, checksum, rel_path=str(rel), source="folder"
            )
            item["well"] = uf.well.name if uf.well else None
            item["section"] = uf.well.section_in if uf.well else None
            item["version"] = uf.version
            errs = [i.message for i in uf.issues if i.level == "error"]
            warns = [i.message for i in uf.issues if i.level == "warning"]
            if uf.status == "gagal":
                item.update(status="ditolak", message="; ".join(errs))
                if s.inbox_move:
                    _move(path, s.rejected_dir, rel, "\n".join(errs))
            else:
                item.update(
                    status="diterima" if not warns else "diterima dengan peringatan",
                    message="; ".join(warns),
                )
                if s.inbox_move:
                    _move(path, s.processed_dir, rel)
        except Exception as exc:  # satu file rusak tidak menghentikan pemindaian
            db.rollback()
            log.error("Gagal memindai %s: %s\n%s", rel, exc, traceback.format_exc())
            item.update(status="ditolak", message=f"Galat: {exc}")
        results.append(item)

    counts = recompute_all(db)
    from app.db.models import Well, WellQuality

    wells = []
    for w in db.query(Well).order_by(Well.name, Well.section_in).all():
        wq = db.query(WellQuality).filter(WellQuality.well_id == w.id).first()
        if any(r.get("well") == w.name for r in results):
            wells.append(
                {
                    "well": w.name,
                    "section": w.section_in,
                    "type": w.well_type,
                    "quality": wq.status if wq else None,
                    "reasons": [
                        c["message"] for c in (wq.checks if wq else []) if c["level"] != "lolos"
                    ],
                }
            )
    by_status: dict[str, int] = {}
    for r in results:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    run.summary = {"files": results, "wells": wells, "counts": by_status, "quality": counts}
    run.status = "selesai"
    run.finished_at = datetime.now(UTC)
    db.commit()
    return run


def run_scan_job(run_id: int) -> None:
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        run = db.get(ScanRun, run_id)
        try:
            scan(db, run)
        except Exception as exc:
            db.rollback()
            run = db.get(ScanRun, run_id)
            run.status = "gagal"
            run.summary = {"error": str(exc)}
            run.finished_at = datetime.now(UTC)
            db.commit()
            log.error("Pemindaian %s gagal: %s\n%s", run_id, exc, traceback.format_exc())
    finally:
        db.close()
