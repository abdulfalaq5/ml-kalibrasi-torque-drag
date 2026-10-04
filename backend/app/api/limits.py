from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Limit, Well
from app.db.session import get_db
from app.services import units
from app.services.limits import LIMIT_OPS
from app.services.operations import OP_DIMENSION

router = APIRouter(prefix="/api/limits", tags=["limits"])


def lim_out(lim: Limit, unit_system: str = "imperial") -> dict:
    u = units.DISPLAY_UNITS[unit_system][OP_DIMENSION[lim.operation]]
    return {
        "id": lim.id,
        "well_id": lim.well_id,
        "section_in": lim.section_in,
        "operation": lim.operation,
        "kind": lim.kind,
        "value": round(units.from_si(lim.value_si, u), 3),
        "unit": units.UNIT_LABELS[u],
        "note": lim.note,
        "scope": "well" if lim.well_id else "section",
    }


@router.get("")
def list_limits(
    well_id: int | None = None,
    units_: str = Query("imperial", alias="units"),
    db: Session = Depends(get_db),
):
    q = select(Limit).order_by(Limit.section_in, Limit.well_id, Limit.operation)
    if well_id is not None:
        w = db.get(Well, well_id)
        q = q.where(
            (Limit.well_id == well_id)
            | ((Limit.well_id.is_(None)) & (Limit.section_in == w.section_in))
        )
    return [lim_out(x, units_) for x in db.scalars(q)]


class LimitIn(BaseModel):
    operation: str
    value: float
    unit_system: str = "imperial"
    kind: str | None = None
    well_id: int | None = None
    section_in: float | None = None
    note: str | None = None


@router.post("")
def create(body: LimitIn, db: Session = Depends(get_db)):
    if body.operation not in LIMIT_OPS:
        raise HTTPException(400, "Unknown operation")
    if (body.well_id is None) == (body.section_in is None):
        raise HTTPException(
            400, "Fill in exactly one: well_id (well limit) or section_in (section limit)"
        )
    kind = body.kind or LIMIT_OPS[body.operation]
    if kind not in ("max", "min"):
        raise HTTPException(400, "Limit kind must be max or min")
    u = units.DISPLAY_UNITS.get(body.unit_system, units.DISPLAY_UNITS["imperial"])[
        OP_DIMENSION[body.operation]
    ]
    lim = Limit(
        operation=body.operation,
        kind=kind,
        value_si=units.to_si(body.value, u),
        well_id=body.well_id,
        section_in=body.section_in,
        note=body.note,
    )
    db.add(lim)
    db.commit()
    return lim_out(lim, body.unit_system)


@router.delete("/{limit_id}")
def remove(limit_id: int, db: Session = Depends(get_db)):
    lim = db.get(Limit, limit_id)
    if lim is None:
        raise HTTPException(404, "Limit not found")
    db.delete(lim)
    db.commit()
    return {"ok": True}
