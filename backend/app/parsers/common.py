"""Alat bantu baca Excel bersama: mencari baris header, klasifikasi kolom, angka.

Semua pola nama kolom/sheet dikumpulkan di `column_map.py` supaya mudah
disesuaikan setelah audit data tanpa mengubah logika parser.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import openpyxl

from app.parsers import column_map as cm
from app.services import units


@dataclass
class Issue:
    level: str  # "error" | "warning"
    message: str
    location: str | None = None


@dataclass
class Row:
    """Satu titik data dalam format panjang (long format)."""

    operation: str
    depth: float
    depth_unit: str
    value: float
    unit: str
    sheet: str
    ff: float | None = None


@dataclass
class SurveyRow:
    md: float
    inc: float
    azi: float | None
    tvd: float | None
    dls: float | None


@dataclass
class SheetInfo:
    name: str
    role: str | None  # peran sheet yang dikenali, None = diabaikan
    rows: int
    header_row: int | None = None
    columns: list[str] = field(default_factory=list)
    units: list[str] = field(default_factory=list)


@dataclass
class ParsedWorkbook:
    filename: str
    kinds: set[str] = field(default_factory=set)
    meta: dict[str, Any] = field(default_factory=dict)
    survey: list[SurveyRow] = field(default_factory=list)
    survey_units: dict[str, str] = field(default_factory=dict)
    plan: list[Row] = field(default_factory=list)
    actual: list[Row] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    sheets: list[SheetInfo] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(i.level == "error" for i in self.issues)

    def error(self, msg: str, loc: str | None = None) -> None:
        self.issues.append(Issue("error", msg, loc))

    def warn(self, msg: str, loc: str | None = None) -> None:
        self.issues.append(Issue("warning", msg, loc))


def open_workbook(path: Path):
    # read_only + data_only: nilai hasil hitung, macro tidak pernah dijalankan.
    return openpyxl.load_workbook(path, read_only=True, data_only=True, keep_vba=False)


def norm(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def to_float(v: Any) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, int | float):
        return float(v)
    s = str(v).strip().replace(" ", "")
    if not s or s in {"-", "--", "n/a", "na", "#n/a", "#value!", "#div/0!"}:
        return None
    if "," in s and "." not in s:
        s = s.replace(",", ".")  # desimal koma
    else:
        s = s.replace(",", "")  # pemisah ribuan
    try:
        return float(s)
    except ValueError:
        return None


def sheet_role(sheet_name: str) -> str | None:
    n = norm(sheet_name)
    for role, patterns in cm.SHEET_ROLES.items():
        if any(re.search(p, n) for p in patterns):
            return role
    return None


def read_rows(ws, max_rows: int = 200_000) -> list[tuple]:
    rows = []
    for i, r in enumerate(ws.iter_rows(values_only=True)):
        if i >= max_rows:
            break
        rows.append(r)
    return rows


def find_header(rows: list[tuple], scan: int = 40) -> int | None:
    """Baris header = baris pertama (dalam `scan` baris) yang memuat kolom kedalaman
    dan minimal satu kolom lain yang tidak kosong."""
    for i, r in enumerate(rows[:scan]):
        cells = [norm(c) for c in r]
        if any(is_depth_header(c) for c in cells) and sum(1 for c in cells if c) >= 2:
            return i
    return None


def merge_header(rows: list[tuple], idx: int) -> list[str]:
    """Gabungkan header dua baris (mis. label di baris idx, satuan di baris idx+1)."""
    head = [str(c).strip() if c is not None else "" for c in rows[idx]]
    if idx + 1 < len(rows):
        nxt = rows[idx + 1]
        # baris berikutnya dianggap baris satuan bila isinya teks satuan semua
        texts = [str(c).strip() for c in nxt if c is not None and str(c).strip()]
        if texts and all(units.normalize_unit(t.strip("()[]")) for t in texts):
            for j, c in enumerate(nxt):
                if j < len(head) and c is not None and str(c).strip():
                    head[j] = f"{head[j]} ({str(c).strip().strip('()[]')})"
    return head


def header_has_unit_row(rows: list[tuple], idx: int) -> bool:
    if idx + 1 >= len(rows):
        return False
    texts = [str(c).strip() for c in rows[idx + 1] if c is not None and str(c).strip()]
    return bool(texts) and all(units.normalize_unit(t.strip("()[]")) for t in texts)


def is_depth_header(h: str) -> bool:
    return any(re.search(p, h) for p in cm.DEPTH_PATTERNS)


def parse_ff(h: str) -> float | None:
    for p in cm.FF_PATTERNS:
        m = re.search(p, h)
        if m:
            val = to_float(m.group(1))
            if val is not None and 0 <= val <= 1:
                return round(val, 3)
    return None


def classify_operation(h: str, dim: str | None, sheet_default: str | None) -> str | None:
    """Tentukan operasi dari teks header + dimensi satuan (beban vs torsi)."""
    if dim == "torque" or (dim is None and "torque" in h):
        for op, patterns in cm.TORQUE_OP_PATTERNS.items():
            if any(re.search(p, h) for p in patterns):
                return op
        if "torque" in h or dim == "torque":
            return (
                sheet_default
                if sheet_default in ("torque_off_bottom", "torque_on_bottom")
                else None
            )
        return None
    for op, patterns in cm.HOOKLOAD_OP_PATTERNS.items():
        if any(re.search(p, h) for p in patterns):
            return op
    return None
