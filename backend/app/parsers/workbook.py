"""Parser satu file Excel: mengenali sheet WellPlan, roadmap, dan data aktual.

Satu file bisa berisi beberapa jenis (mis. laporan WellPlan + sheet data aktual).
Hasil: ParsedWorkbook dalam format panjang + daftar masalah per lokasi.
"""

import re
from pathlib import Path

from app.parsers import column_map as cm
from app.parsers.common import (
    ParsedWorkbook,
    Row,
    SheetInfo,
    SurveyRow,
    classify_operation,
    find_header,
    header_has_unit_row,
    is_depth_header,
    merge_header,
    norm,
    open_workbook,
    parse_ff,
    read_rows,
    sheet_role,
    to_float,
)
from app.services import units

# Rentang wajar dalam satuan SI, di luar ini -> peringatan dan titik dibuang
RANGES_SI = {
    "length": (0.0, 12_000.0),  # m
    "force": (-500.0, 10_000.0),  # kN
    "torque": (0.0, 300.0),  # kN.m
}


def parse_workbook(path: Path, filename: str | None = None) -> ParsedWorkbook:
    pw = ParsedWorkbook(filename=filename or path.name)
    try:
        wb = open_workbook(path)
    except Exception as exc:  # file rusak, bukan Excel, terenkripsi
        pw.error(f"File tidak bisa dibuka sebagai Excel: {exc.__class__.__name__}: {exc}")
        return pw

    try:
        for ws in wb.worksheets:
            role = sheet_role(ws.title)
            rows = read_rows(ws)
            info = SheetInfo(name=ws.title, role=role, rows=len(rows))
            pw.sheets.append(info)
            if role is None:
                continue
            if role in cm.WELLPLAN_ROLES:
                pw.kinds.add("wellplan")
            if role in cm.ROADMAP_ROLES:
                pw.kinds.add("roadmap")
            if role in cm.ACTUAL_ROLES:
                pw.kinds.add("actual")

            if role == "summary":
                _parse_summary(rows, pw)
            elif role == "bha":
                _parse_bha(rows, pw, ws.title)
            elif role == "survey":
                _parse_survey(rows, pw, ws.title, info)
            elif role in cm.PLAN_ROLES:
                _parse_series(rows, pw, ws.title, role, info, target=pw.plan, with_ff=True)
            elif role == "actual_tripping":
                _parse_tripping_actual(rows, pw, ws.title, role, info)
            elif role in cm.ACTUAL_ROLES:
                _parse_series(rows, pw, ws.title, role, info, target=pw.actual, with_ff=False)
    finally:
        wb.close()

    if not pw.kinds:
        pw.error(
            "Tidak ada sheet yang dikenali. Sheet yang ada: " + ", ".join(s.name for s in pw.sheets)
        )
    if "wellplan" in pw.kinds and not pw.plan and "roadmap" not in pw.kinds:
        pw.error("Laporan WellPlan tanpa data hookload/torque yang terbaca")
    if pw.plan and not any(r.ff is not None for r in pw.plan):
        pw.warn("Tidak ada kolom friction factor (FF) yang terbaca pada data WellPlan")
    _check_rows(pw, pw.plan, "WellPlan")
    _check_rows(pw, pw.actual, "aktual")
    return pw


# ---------------------------------------------------------------- Summary / BHA


def _parse_summary(rows: list[tuple], pw: ParsedWorkbook) -> None:
    for r in rows[:200]:
        cells = list(r)
        for j, c in enumerate(cells):
            label = norm(c)
            if not label:
                continue
            for key, patterns in cm.SUMMARY_KEYS.items():
                if key in pw.meta or not any(re.search(p, label) for p in patterns):
                    continue
                val = next((v for v in cells[j + 1 :] if v not in (None, "")), None)
                if val is None:
                    continue
                if key in ("hole_size", "bit_size", "section", "casing_shoe"):
                    num = _first_number(val)
                    if num is not None:
                        pw.meta[key] = num
                        unit = units.unit_from_header(str(c)) or _unit_after(cells, j)
                        if key == "casing_shoe" and unit:
                            pw.meta["casing_shoe_unit"] = unit
                else:
                    pw.meta[key] = str(val).strip()


def _unit_after(cells: list, j: int) -> str | None:
    for v in cells[j + 2 : j + 4]:
        u = units.normalize_unit(str(v)) if v is not None else None
        if u:
            return u
    return None


def _first_number(val) -> float | None:
    num = to_float(val)
    if num is not None:
        return num
    s = str(val)
    # "12 1/4" atau "8-1/2" -> pecahan
    m = re.search(r"(\d+)[\s-]+(\d+)\s*/\s*(\d+)", s)
    if m:
        return int(m.group(1)) + int(m.group(2)) / int(m.group(3))
    m = re.search(r"\d+(?:[.,]\d+)?", s)
    return to_float(m.group(0)) if m else None


def _parse_bha(rows: list[tuple], pw: ParsedWorkbook, sheet: str) -> None:
    idx = None
    for i, r in enumerate(rows[:40]):
        cells = [norm(c) for c in r]
        if any("od" == c or c.startswith("od ") or "outer diameter" in c for c in cells):
            idx = i
            break
    if idx is None:
        pw.warn("Header BHA (kolom OD) tidak ditemukan, sheet BHA dilewati", sheet)
        return
    head = [norm(c) for c in rows[idx]]
    od_col = next(j for j, c in enumerate(head) if c == "od" or c.startswith("od ") or "outer" in c)
    desc_col = next(
        (
            j
            for j, c in enumerate(head)
            if any(k in c for k in ("description", "component", "type"))
        ),
        0,
    )
    components = []
    for r in rows[idx + 1 :]:
        if not r or all(v in (None, "") for v in r):
            continue
        desc = str(r[desc_col] or "").strip() if desc_col < len(r) else ""
        od = to_float(r[od_col]) if od_col < len(r) else None
        components.append({"description": desc, "od_in": od})
        if "bit" in desc.lower() and od and "bit_size" not in pw.meta:
            pw.meta["bit_size"] = od
    pw.meta["bha_components"] = len(components)


# ---------------------------------------------------------------- Survey


def _parse_survey(rows: list[tuple], pw: ParsedWorkbook, sheet: str, info: SheetInfo) -> None:
    idx = find_header(rows)
    if idx is None:
        pw.error("Header survey (kolom MD) tidak ditemukan", sheet)
        return
    head = merge_header(rows, idx)
    start = idx + (2 if header_has_unit_row(rows, idx) else 1)
    info.header_row, info.columns = idx + 1, head
    cols: dict[str, int] = {}
    for j, h in enumerate(head):
        hn = norm(h)
        for key, patterns in cm.SURVEY_COLUMNS.items():
            if key not in cols and any(re.search(p, hn) for p in patterns):
                cols[key] = j
                break
    for req in ("md", "inc"):
        if req not in cols:
            pw.error(f"Kolom wajib survey '{req}' tidak ditemukan", sheet)
            return
    md_unit = units.unit_from_header(head[cols["md"]]) or "ft"
    if units.unit_from_header(head[cols["md"]]) is None:
        pw.warn("Satuan MD survey tidak tertulis, diasumsikan ft", sheet)
    dls_unit = units.unit_from_header(head[cols["dls"]]) if "dls" in cols else None
    tvd_unit = units.unit_from_header(head[cols["tvd"]]) if "tvd" in cols else None
    pw.survey_units = {"md": md_unit, "dls": dls_unit or "deg/100ft", "tvd": tvd_unit or md_unit}
    info.units = [u for u in pw.survey_units.values() if u]

    def get(r, key):
        j = cols.get(key)
        return to_float(r[j]) if j is not None and j < len(r) else None

    for i, r in enumerate(rows[start:], start=start + 1):
        md, inc = get(r, "md"), get(r, "inc")
        if md is None and inc is None:
            continue
        if md is None or inc is None:
            pw.warn(f"Baris survey tanpa MD/inklinasi dilewati (baris {i})", sheet)
            continue
        if not 0 <= inc <= 180:
            pw.warn(f"Inklinasi {inc} di luar 0-180 derajat dilewati (baris {i})", sheet)
            continue
        pw.survey.append(SurveyRow(md, inc, get(r, "azi"), get(r, "tvd"), get(r, "dls")))
    _check_monotonic([s.md for s in pw.survey], pw, sheet, "survey")


# ---------------------------------------------------------------- Seri hookload/torsi


def _parse_series(
    rows: list[tuple],
    pw: ParsedWorkbook,
    sheet: str,
    role: str,
    info: SheetInfo,
    target: list[Row],
    with_ff: bool,
) -> None:
    idx = find_header(rows)
    if idx is None:
        pw.error("Header (kolom kedalaman) tidak ditemukan", sheet)
        return
    head = merge_header(rows, idx)
    start = idx + (2 if header_has_unit_row(rows, idx) else 1)
    info.header_row, info.columns = idx + 1, head

    depth_col = next(j for j, h in enumerate(head) if is_depth_header(norm(h)))
    depth_unit = units.unit_from_header(head[depth_col])
    if depth_unit is None:
        depth_unit = "ft"
        pw.warn("Satuan kedalaman tidak tertulis, diasumsikan ft", sheet)
    elif units.dimension(depth_unit) != "length":
        pw.error(f"Satuan kedalaman '{depth_unit}' tidak valid", sheet)
        return

    columns: list[tuple[int, str, float | None, str]] = []
    for j, h in enumerate(head):
        if j == depth_col or not h:
            continue
        hn = norm(h)
        raw_unit = re.search(r"[\(\[]\s*([^\)\]]+?)\s*[\)\]]", h)
        unit = units.unit_from_header(h)
        if raw_unit and unit is None:
            pw.error(f"Satuan tidak dikenal '{raw_unit.group(1)}' pada kolom '{h}'", sheet)
            continue
        dim = units.dimension(unit) if unit else None
        if dim not in (None, "force", "torque"):
            continue  # mis. kolom inklinasi/TVD di sheet yang sama
        op = classify_operation(hn, dim, cm.SHEET_DEFAULT_TORQUE_OP.get(role))
        if op is None:
            continue
        if unit is None:
            unit = cm.SHEET_DEFAULT_UNIT.get(role) or (
                "ft-lbf" if op.startswith("torque") else "klbf"
            )
            pw.warn(f"Kolom '{h}' tanpa satuan, diasumsikan {unit}", sheet)
        ff = parse_ff(hn) if with_ff else None
        columns.append((j, op, ff, unit))

    if not columns:
        pw.error("Tidak ada kolom hookload/torque yang dikenali", sheet)
        return
    info.units = sorted({c[3] for c in columns} | {depth_unit})

    depths = []
    for i, r in enumerate(rows[start:], start=start + 1):
        d = to_float(r[depth_col]) if depth_col < len(r) else None
        if d is None:
            if any(to_float(r[j]) is not None for j, *_ in columns if j < len(r)):
                pw.warn(f"Baris tanpa kedalaman dilewati (baris {i})", sheet)
            continue
        depths.append(d)
        for j, op, ff, unit in columns:
            v = to_float(r[j]) if j < len(r) else None
            if v is None:
                continue
            target.append(Row(op, d, depth_unit, v, unit, sheet, ff))
    _check_monotonic(depths, pw, sheet, "kedalaman", allow_unsorted=role in cm.ACTUAL_ROLES)


def _parse_tripping_actual(
    rows: list[tuple], pw: ParsedWorkbook, sheet: str, role: str, info: SheetInfo
) -> None:
    """Tripping Data: bisa berupa kolom pick up/slack off terpisah, atau satu kolom
    hookload + kolom arah (POOH/RIH)."""
    idx = find_header(rows)
    if idx is None:
        pw.error("Header (kolom kedalaman) tidak ditemukan", sheet)
        return
    head = merge_header(rows, idx)
    hn = [norm(h) for h in head]
    dir_col = next(
        (j for j, h in enumerate(hn) if any(re.search(p, h) for p in cm.DIRECTION_PATTERNS)), None
    )
    if dir_col is None:
        _parse_series(rows, pw, sheet, role, info, target=pw.actual, with_ff=False)
        return
    hk_col = next(
        (j for j, h in enumerate(hn) if any(re.search(p, h) for p in cm.HOOKLOAD_GENERIC)), None
    )
    depth_col = next(j for j, h in enumerate(hn) if is_depth_header(h))
    if hk_col is None:
        pw.error("Kolom hookload tidak ditemukan pada Tripping Data", sheet)
        return
    depth_unit = units.unit_from_header(head[depth_col]) or "ft"
    unit = units.unit_from_header(head[hk_col]) or "klbf"
    info.header_row, info.columns, info.units = idx + 1, head, [depth_unit, unit]
    start = idx + (2 if header_has_unit_row(rows, idx) else 1)
    for i, r in enumerate(rows[start:], start=start + 1):
        d = to_float(r[depth_col]) if depth_col < len(r) else None
        v = to_float(r[hk_col]) if hk_col < len(r) else None
        if d is None or v is None:
            continue
        direction = norm(r[dir_col]) if dir_col < len(r) else ""
        op = next(
            (
                op
                for op, pats in cm.DIRECTION_VALUES.items()
                if any(re.search(p, direction) for p in pats)
            ),
            None,
        )
        if op is None:
            pw.warn(f"Arah '{direction}' tidak dikenal (baris {i})", sheet)
            continue
        pw.actual.append(Row(op, d, depth_unit, v, unit, sheet))


# ---------------------------------------------------------------- Validasi


def _check_monotonic(
    depths: list[float], pw: ParsedWorkbook, sheet: str, what: str, allow_unsorted: bool = False
) -> None:
    if len(depths) < 2:
        return
    dup = len(depths) - len(set(depths))
    if dup and not allow_unsorted:
        pw.warn(f"{dup} {what} duplikat (nilai terakhir dipakai)", sheet)
    if not allow_unsorted and any(b < a for a, b in zip(depths, depths[1:], strict=False)):
        pw.warn(f"Urutan {what} tidak naik, data diurutkan ulang", sheet)


def _check_rows(pw: ParsedWorkbook, rows: list[Row], label: str) -> None:
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
            f"{len(bad)} titik {label} di luar rentang wajar dibuang "
            f"(contoh: kedalaman {bad[0].depth} {bad[0].depth_unit}, "
            f"nilai {bad[0].value} {bad[0].unit})",
            ", ".join(sheets),
        )
        bad_ids = {id(r) for r in bad}
        rows[:] = [r for r in rows if id(r) not in bad_ids]
