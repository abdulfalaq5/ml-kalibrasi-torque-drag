"""Klasifikasi otomatis section (dari ukuran lubang) dan tipe sumur (dari survey).

Aturan tipe sumur (ASUMSI, konfirmasi ke narasumber; lihat docs/keputusan.md K-04):
  - Horizontal : inklinasi maksimum >= 80 derajat
  - S          : inklinasi maksimum >= 10 derajat dan inklinasi di dasar turun
                 >= 10 derajat dari maksimum (build-hold-drop)
  - J          : selain itu (termasuk sumur hampir vertikal, diberi peringatan)
"""

from app.services.operations import SECTIONS_IN

HORIZONTAL_MIN_INC = 80.0
S_MIN_DROP = 10.0
NEAR_VERTICAL_INC = 5.0


def classify_section(hole_in: float | None, tolerance: float = 0.4) -> float | None:
    if hole_in is None:
        return None
    best = min(SECTIONS_IN, key=lambda s: abs(s - hole_in))
    return best if abs(best - hole_in) <= tolerance else round(hole_in, 3)


def classify_well_type(md: list[float], inc: list[float]) -> tuple[str | None, str | None]:
    """Kembalikan (tipe, peringatan)."""
    if len(inc) < 3:
        return None, "Survey terlalu sedikit untuk menentukan tipe sumur"
    pairs = sorted(zip(md, inc, strict=True))
    incs = [i for _, i in pairs]
    max_inc = max(incs)
    final_inc = sum(incs[-3:]) / 3
    if max_inc >= HORIZONTAL_MIN_INC:
        return "Horizontal", None
    if max_inc >= 10 and max_inc - final_inc >= S_MIN_DROP:
        return "S", None
    if max_inc < NEAR_VERTICAL_INC:
        return "J", f"Sumur hampir vertikal (inklinasi maks {max_inc:.1f}°), dicatat sebagai J"
    return "J", None
