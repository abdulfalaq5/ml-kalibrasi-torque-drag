"""Batas aman dari client dan kedalaman saat prediksi menyentuh batas.

Batas berlaku per sumur-section (well_id) atau per section (section_in, semua sumur).
Batas sumur menimpa batas section untuk operasi + jenis (max/min) yang sama.
"""

import numpy as np
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import Limit, Well

LIMIT_OPS = {
    "pick_up": "max",  # hookload maksimum (mis. kapasitas rig / overpull)
    "slack_off": "min",  # slack off minimum (mis. batas buckling / tidak bisa turun)
    "rotating_weight": "max",
    "torque_off_bottom": "max",  # make-up torque / batas top drive
    "torque_on_bottom": "max",
}


def applicable_limits(db: Session, well: Well) -> list[Limit]:
    rows = db.scalars(
        select(Limit)
        .where(
            or_(
                Limit.well_id == well.id,
                (Limit.well_id.is_(None)) & (Limit.section_in == well.section_in),
            )
        )
        .order_by(Limit.well_id.is_(None))  # batas sumur dulu
    ).all()
    seen, out = set(), []
    for lim in rows:
        key = (lim.operation, lim.kind)
        if key in seen:
            continue
        seen.add(key)
        out.append(lim)
    return out


def first_crossing(depth: np.ndarray, value: np.ndarray, limit: float, kind: str) -> float | None:
    """Kedalaman pertama (interpolasi linear) ketika kurva melewati batas."""
    if not len(depth):
        return None
    order = np.argsort(depth)
    d, v = np.asarray(depth)[order], np.asarray(value)[order]
    over = v > limit if kind == "max" else v < limit
    if not over.any():
        return None
    i = int(np.argmax(over))
    if i == 0:
        return float(d[0])
    v0, v1 = v[i - 1], v[i]
    t = (limit - v0) / (v1 - v0) if v1 != v0 else 0.0
    return float(d[i - 1] + t * (d[i] - d[i - 1]))


def margin(value: np.ndarray, limit: float, kind: str) -> float | None:
    if not len(value):
        return None
    return float(np.min(limit - value) if kind == "max" else np.min(value - limit))
