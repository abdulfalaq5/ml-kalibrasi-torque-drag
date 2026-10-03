"""Struktur hasil parse dan alat bantu baca Excel bersama."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import openpyxl

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
    fmt: str | None = None  # "roadmap" (format A) | "wellplan" (format B)
    kinds: set[str] = field(default_factory=set)  # "plan", "actual"
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
    """Angka dari sel; file client sering menyimpan angka sebagai teks ('141')."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, int | float):
        return float(v)
    s = str(v).strip().replace(" ", "")
    if not s or s.lower() in {"-", "--", "n/a", "na", "#n/a", "#value!", "#div/0!", "#ref!"}:
        return None
    if "," in s and "." not in s:
        s = s.replace(",", ".")  # desimal koma
    else:
        s = s.replace(",", "")  # pemisah ribuan
    try:
        return float(s)
    except ValueError:
        return None


def first_number(val: Any) -> float | None:
    """Angka pertama dalam teks: '21 (1000 lbf)' -> 21, '8-1/2"' -> 8.5, '12 1/4' -> 12.25."""
    num = to_float(val)
    if num is not None:
        return num
    s = str(val or "")
    m = re.search(r"(\d+)\s*[-\s]\s*(\d+)\s*/\s*(\d+)", s)
    if m:
        return int(m.group(1)) + int(m.group(2)) / int(m.group(3))
    m = re.search(r"\d+(?:[.,]\d+)?", s)
    return to_float(m.group(0)) if m else None


def read_rows(ws, max_rows: int = 100_000) -> list[tuple]:
    rows = []
    for i, r in enumerate(ws.iter_rows(values_only=True)):
        if i >= max_rows:
            break
        rows.append(r)
    return rows


def cell(r: tuple, j: int) -> Any:
    return r[j] if j < len(r) else None


def match_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(p, text) for p in patterns)


def unit_in(text: Any) -> str | None:
    """Satuan dari teks berkurung '(Klbs)' atau teks satuan polos '1000 lbf'."""
    t = str(text or "").strip()
    u = units.unit_from_header(t)
    if u:
        return u
    return units.normalize_unit(t.strip("()[] "))
