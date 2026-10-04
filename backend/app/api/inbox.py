from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ScanRun
from app.db.session import get_db
from app.services.inbox import inbox_status, run_scan_job

router = APIRouter(prefix="/api/inbox", tags=["inbox"])


def run_out(r: ScanRun, full: bool = False) -> dict:
    s = r.summary or {}
    out = {
        "id": r.id,
        "status": r.status,
        "started_at": r.started_at,
        "finished_at": r.finished_at,
        "counts": s.get("counts"),
        "quality": s.get("quality"),
        "error": s.get("error"),
    }
    if full:
        out["files"] = s.get("files", [])
        out["wells"] = s.get("wells", [])
    return out


@router.get("/status")
def status():
    return inbox_status()


@router.post("/scan")
def scan(background: BackgroundTasks, db: Session = Depends(get_db)):
    if db.scalar(select(ScanRun).where(ScanRun.status == "running")):
        raise HTTPException(409, "Another scan is still running")
    if inbox_status()["pending"] == 0:
        raise HTTPException(400, "The inbox folder is empty")
    run = ScanRun(status="running")
    db.add(run)
    db.commit()
    background.add_task(run_scan_job, run.id)
    return run_out(run)


@router.get("/runs")
def runs(db: Session = Depends(get_db)):
    return [run_out(r) for r in db.scalars(select(ScanRun).order_by(ScanRun.id.desc()).limit(20))]


@router.get("/runs/{run_id}")
def run_detail(run_id: int, db: Session = Depends(get_db)):
    r = db.get(ScanRun, run_id)
    if r is None:
        raise HTTPException(404, "Scan run not found")
    return run_out(r, full=True)
