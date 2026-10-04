"""Parser satu file Excel client: deteksi format (A roadmap / B laporan WellPlan),
lalu tambahkan section (dari nama file), tipe sumur (dari folder), dan validasi umum."""

import re
from pathlib import Path, PurePath

from app.parsers import column_map as cm
from app.parsers.common import ParsedWorkbook, norm, open_workbook
from app.parsers.roadmap import parse_roadmap
from app.parsers.wellplan_report import parse_wellplan
from app.services import units

# Rentang wajar dalam satuan SI, di luar ini -> peringatan dan titik dibuang
RANGES_SI = {
    "length": (0.0, 12_000.0),  # m
    "force": (-500.0, 10_000.0),  # kN
    "torque": (-1.0, 300.0),  # kN.m
}

# "8.5in", "8.50in", "8.50_in", "12.25inHS", "12.25 HS", "22inHS", "17.5 in"
_SECTION_RE = re.compile(
    r"(?<![\d.])(\d{1,2}(?:[.,]\d{1,3})?)\s*_?(?:in(?:ch)?(?=\b|_|hs|\s|\))|\"|\s*hs\b)"
)


def section_from_filename(name: str) -> float | None:
    m = _SECTION_RE.search(PurePath(name).stem.lower())
    if not m:
        return None
    v = float(m.group(1).replace(",", "."))
    return v if 3 <= v <= 36 else None


def well_type_from_path(rel_path: str | None) -> str | None:
    if not rel_path:
        return None
    for part in PurePath(rel_path).parts[:-1]:
        t = cm.TYPE_FOLDERS.get(part.strip().lower())
        if t and part.strip().lower() in ("j", "s", "horizontal"):
            return t
    return None


def well_folder_from_path(rel_path: str | None) -> str | None:
    """Folder sumur = folder tepat di atas file (bukan folder tipe J/S/Horizontal)."""
    if not rel_path:
        return None
    parts = PurePath(rel_path).parts[:-1]
    if not parts:
        return None
    last = parts[-1].strip()
    return None if last.lower() in ("j", "s", "horizontal") else last


def parse_workbook(
    path: Path, filename: str | None = None, rel_path: str | None = None
) -> ParsedWorkbook:
    pw = ParsedWorkbook(filename=filename or path.name)
    try:
        wb = open_workbook(path)
    except Exception as exc:  # file rusak, bukan Excel, terenkripsi
        pw.error(f"The file cannot be opened as Excel: {exc.__class__.__name__}: {exc}")
        return pw
    try:
        names = {norm(ws.title) for ws in wb.worksheets}
        if cm.ROADMAP_SHEETS <= names:
            parse_roadmap(wb, pw)
        elif cm.WELLPLAN_SHEETS <= names:
            parse_wellplan(wb, pw)
        else:
            pw.error(
                "Unknown format (not a Drag/Torque roadmap or a WellPlan report). "
                "Sheets found: " + ", ".join(ws.title for ws in wb.worksheets)
            )
    finally:
        wb.close()

    pw.meta["section_from_filename"] = section_from_filename(pw.filename)
    wt = well_type_from_path(rel_path)
    if wt:
        pw.meta["well_type_folder"] = wt
    folder = well_folder_from_path(rel_path)
    if folder:
        pw.meta["well_folder"] = folder
    if pw.fmt and not pw.plan:
        pw.error("No WellPlan T&D model data could be read")
    _check_rows(pw, pw.plan, "WellPlan")
    _check_rows(pw, pw.actual, "actual")
    if pw.plan:
        d = [units.to_si(r.depth, r.depth_unit) for r in pw.plan]
        pw.meta["plan_depth_m"] = [min(d), max(d)]
    if pw.actual:
        d = [units.to_si(r.depth, r.depth_unit) for r in pw.actual]
        pw.meta["actual_depth_m"] = [min(d), max(d)]
    return pw


def _check_rows(pw: ParsedWorkbook, rows: list, label: str) -> None:
    bad = []
    for r in rows:
        d_si = units.to_si(r.depth, r.depth_unit)
        v_si = units.to_si(r.value, r.unit)
        lo, hi = RANGES_SI[units.dimension(r.unit)]
        dlo, dhi = RANGES_SI["length"]
        if not (dlo <= d_si <= dhi) or not (lo <= v_si <= hi):
            bad.append(r)
    if bad:
        sheets = sorted({r.sheet for r in bad})
        pw.warn(
            f"{len(bad)} {label} points outside the plausible range removed "
            f"(e.g. depth {bad[0].depth} {bad[0].depth_unit}, "
            f"value {bad[0].value} {bad[0].unit})",
            ", ".join(sheets),
        )
        bad_ids = {id(r) for r in bad}
        rows[:] = [r for r in rows if id(r) not in bad_ids]
