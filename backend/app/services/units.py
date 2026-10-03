"""Konversi satuan. Satu-satunya tempat faktor konversi didefinisikan.

Satuan baku internal (SI):
  kedalaman  -> m
  beban      -> kN      (hookload: pick up, slack off, rotating weight)
  torsi      -> kN.m
  sudut      -> deg
  dogleg     -> deg/30m
Satuan asli selalu disimpan di samping nilai baku.
"""

import re

FT_TO_M = 0.3048
LBF_TO_KN = 4.4482216152605e-3
FTLBF_TO_KNM = 1.3558179483314e-3

# satuan (dinormalisasi) -> (dimensi, faktor ke SI)
_UNITS: dict[str, tuple[str, float]] = {
    "ft": ("length", FT_TO_M),
    "m": ("length", 1.0),
    "lbf": ("force", LBF_TO_KN),
    "klbf": ("force", 1000 * LBF_TO_KN),
    "kn": ("force", 1.0),
    "n": ("force", 1e-3),
    "ton": ("force", 9.80665),  # metric ton-force
    "ft-lbf": ("torque", FTLBF_TO_KNM),
    "kft-lbf": ("torque", 1000 * FTLBF_TO_KNM),
    "kn-m": ("torque", 1.0),
    "n-m": ("torque", 1e-3),
    "deg": ("angle", 1.0),
    "deg/100ft": ("dogleg", 30.0 / (100 * FT_TO_M)),
    "deg/30m": ("dogleg", 1.0),
    "in": ("diameter", 1.0),  # diameter lubang dibiarkan dalam inci (konvensi industri)
    "ppg": ("density", 1.0),  # berat lumpur dibiarkan dalam ppg (lbm/gal)
    "lbm/ft": ("linweight", 1.0),
}

_ALIASES = {
    "feet": "ft",
    "foot": "ft",
    "usft": "ft",
    "meter": "m",
    "meters": "m",
    "kip": "klbf",
    "kips": "klbf",
    "kilopound": "klbf",
    "1000lbf": "klbf",
    "klb": "klbf",
    "lb": "lbf",
    "lbs": "lbf",
    "ftlbf": "ft-lbf",
    "ft.lbf": "ft-lbf",
    "lbf-ft": "ft-lbf",
    "lbf.ft": "ft-lbf",
    "ft-lb": "ft-lbf",
    "ftlb": "ft-lbf",
    "lb-ft": "ft-lbf",
    "kftlbf": "kft-lbf",
    "kft.lbf": "kft-lbf",
    "kft-lb": "kft-lbf",
    "klbf-ft": "kft-lbf",
    "kip-ft": "kft-lbf",
    "knm": "kn-m",
    "kn.m": "kn-m",
    "nm": "n-m",
    "n.m": "n-m",
    "°": "deg",
    "degree": "deg",
    "degrees": "deg",
    "°/100ft": "deg/100ft",
    "deg/100'": "deg/100ft",
    "°/30m": "deg/30m",
    "inch": "in",
    "inches": "in",
    '"': "in",
    "tonf": "ton",
    "mt": "ton",
    # varian dari file WellPlan / roadmap client
    "klbs": "klbf",
    "1000ft.lbf": "kft-lbf",
    "1000ft-lbf": "kft-lbf",
    "1000ftlbf": "kft-lbf",
    "ft-kip": "kft-lbf",
    "ftkip": "kft-lbf",
    "lbs-ft": "ft-lbf",
    "lbsft": "ft-lbf",
    "lbs.ft": "ft-lbf",
    "lbm/gal": "ppg",
    "ppg": "ppg",
    "lb/gal": "ppg",
    "lbm/ft": "lbm/ft",
    "ft": "ft",
}

UNIT_PATTERN = re.compile(r"[\(\[]\s*([^\)\]]+?)\s*[\)\]]")


def normalize_unit(raw: str | None) -> str | None:
    if raw is None:
        return None
    u = raw.strip().lower().replace(" ", "").replace("·", "-").replace("×", "")
    u = u.replace("deg/100ft", "deg/100ft")
    u = _ALIASES.get(u, u)
    return u if u in _UNITS else None


def unit_from_header(header: str) -> str | None:
    """Ambil satuan dari teks header, misal 'Pick Up FF 0.30 (kip)' -> 'klbf'."""
    m = UNIT_PATTERN.search(header or "")
    return normalize_unit(m.group(1)) if m else None


def dimension(unit: str) -> str:
    return _UNITS[unit][0]


def to_si(value: float, unit: str) -> float:
    return value * _UNITS[unit][1]


def from_si(value: float, unit: str) -> float:
    return value / _UNITS[unit][1]


def is_known(unit: str | None) -> bool:
    return unit is not None and unit in _UNITS


# Satuan tampilan per sistem satuan untuk dashboard dan ekspor
DISPLAY_UNITS = {
    "imperial": {"length": "ft", "force": "klbf", "torque": "ft-lbf"},
    "si": {"length": "m", "force": "kn", "torque": "kn-m"},
}
UNIT_LABELS = {
    "ft": "ft",
    "m": "m",
    "klbf": "klbf",
    "kn": "kN",
    "ft-lbf": "ft-lbf",
    "kn-m": "kN·m",
}
