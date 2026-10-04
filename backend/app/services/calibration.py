"""Offset "Calibrate" dari Directional Driller (DD) pada file roadmap (format A).

Excel client menggambar crossplot dari kolom "Graph reference" = kurva WellPlan + offset ini
(Drag: PICK UP / SLACK OFF / ROTATE di baris 2; Torque: On Bot di C2, Off Bot di C3).
Offset adalah koreksi DD, BUKAN data aktual: dipakai untuk tampilan kurva "terkalibrasi" dan
sebagai grup fitur tersendiri (dipertahankan hanya bila terbukti membantu, lihat K-05).
"""

from app.db.models import Well
from app.services import units
from app.services.operations import PICK_UP, ROTATING, SLACK_OFF, TORQUE_OFF, TORQUE_ON

# operasi -> (kunci meta, kunci offset, satuan di file)
CAL_SOURCE = {
    PICK_UP: ("calibration_drag_klbf", "pick_up", "klbf"),
    SLACK_OFF: ("calibration_drag_klbf", "slack_off", "klbf"),
    ROTATING: ("calibration_drag_klbf", "rotate", "klbf"),
    TORQUE_ON: ("calibration_torque_ftlbf", "on_bottom", "ft-lbf"),
    TORQUE_OFF: ("calibration_torque_ftlbf", "off_bottom", "ft-lbf"),
}
# nama kolom fitur dataset per operasi
CAL_FEATURE = {
    PICK_UP: "cal_pu",
    SLACK_OFF: "cal_so",
    ROTATING: "cal_rot",
    TORQUE_ON: "cal_ton",
    TORQUE_OFF: "cal_toff",
}


def offset_si(meta: dict | None, op: str) -> float | None:
    """Offset satu operasi dalam SI; None bila file tidak punya Calibrate untuk operasi itu."""
    key, sub, unit = CAL_SOURCE[op]
    v = ((meta or {}).get(key) or {}).get(sub)
    return None if v is None else units.to_si(float(v), unit)


def offsets_si(well: Well) -> dict[str, float]:
    """{operasi: offset SI} untuk operasi yang punya Calibrate."""
    out = {}
    for op in CAL_SOURCE:
        v = offset_si(well.meta, op)
        if v is not None:
            out[op] = v
    return out


def has_calibration(well: Well) -> bool:
    return any(abs(v) > 1e-12 for v in offsets_si(well).values())
