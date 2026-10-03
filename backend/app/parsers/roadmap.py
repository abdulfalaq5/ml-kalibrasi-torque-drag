"""Format A, "TnD Roadmap" (.xlsx): sheet Drag, Torque, T&D Actual Reading, Casing Shoe.

Drag / Torque: beberapa blok kolom, satu blok per skenario FF. Tiap blok diawali kolom
"Run Measured Depth using:", baris berikutnya "open hole friction factor: 0.30", lalu
(opsional) baris satuan "(ft)", "(kip)" / "(ft-lbf)". Blok "Graph reference" di sebelah
kanan = kurva WellPlan + offset kalibrasi (baris "Calibrate") -> diabaikan, labelnya
pun keliru ("(ft-kip)" padahal ft-lbf).

T&D Actual Reading: baris meta (Well, Actual Block Weight, Section, Run) lalu header
"Depth (ft) | Actual Pick Up Weight (Klbs) | ... | Actual torque on bottom Run (Lbs-ft)".

Casing Shoe: hanya data bantu grafik (garis vertikal di kedalaman tetap), diabaikan.
"""

import re

from app.parsers import column_map as cm
from app.parsers.common import (
    ParsedWorkbook,
    Row,
    SheetInfo,
    cell,
    first_number,
    match_any,
    norm,
    read_rows,
    to_float,
    unit_in,
)


def parse_roadmap(wb, pw: ParsedWorkbook) -> None:
    pw.fmt = "roadmap"
    names = {norm(ws.title): ws for ws in wb.worksheets}
    for ws in wb.worksheets:
        n = norm(ws.title)
        rows = read_rows(ws)
        if n == "drag":
            pw.sheets.append(SheetInfo(ws.title, "roadmap_drag", len(rows)))
            _parse_block_sheet(rows, pw, ws.title, cm.ROADMAP_DRAG_OPS, "klbf")
            _parse_drag_calibration(rows, pw)
        elif n == "torque":
            pw.sheets.append(SheetInfo(ws.title, "roadmap_torque", len(rows)))
            _parse_block_sheet(rows, pw, ws.title, cm.ROADMAP_TORQUE_OPS, "ft-lbf")
            _parse_torque_calibration(rows, pw)
        elif re.search(cm.ACTUAL_SHEET, n):
            pw.sheets.append(SheetInfo(ws.title, "actual_td", len(rows)))
            _parse_actual(rows, pw, ws.title)
        else:
            pw.sheets.append(SheetInfo(ws.title, None, len(rows)))
    if "drag" not in names:
        pw.error("Sheet 'Drag' tidak ada")
    if "torque" not in names:
        pw.error("Sheet 'Torque' tidak ada")
    if not any(re.search(cm.ACTUAL_SHEET, n) for n in names):
        pw.warn("Sheet 'T&D Actual Reading' tidak ada: file hanya berisi rencana WellPlan")
    if pw.plan:
        pw.kinds.add("plan")
    if pw.actual:
        pw.kinds.add("actual")
    ffs = sorted({r.ff for r in pw.plan if r.ff is not None})
    pw.meta["ff_scenarios"] = ffs


def _parse_block_sheet(rows, pw, sheet, op_patterns, default_unit) -> None:
    hdr = next(
        (
            i
            for i, r in enumerate(rows[:40])
            if any(re.search(cm.ROADMAP_DEPTH_HEADER, norm(c)) for c in r)
        ),
        None,
    )
    if hdr is None:
        pw.error("Header 'Run Measured Depth' tidak ditemukan", sheet)
        return
    head = rows[hdr]
    ffrow = rows[hdr + 1] if hdr + 1 < len(rows) else ()
    unitrow = rows[hdr + 2] if hdr + 2 < len(rows) else ()
    # kolom awal blok "Graph reference" (dicari di atas header, termasuk baris header)
    gcol = None
    for r in rows[: hdr + 1]:
        for j, c in enumerate(r):
            if re.search(cm.ROADMAP_GRAPH_REF, norm(c)):
                gcol = j if gcol is None else min(gcol, j)
    starts = [
        j
        for j, c in enumerate(head)
        if re.search(cm.ROADMAP_DEPTH_HEADER, norm(c)) and (gcol is None or j < gcol)
    ]
    if not starts:
        pw.error("Tidak ada blok WellPlan sebelum 'Graph reference'", sheet)
        return
    data_start = hdr + 2
    if all(to_float(c) is None for c in unitrow if c not in (None, "")):
        data_start = hdr + 3  # ada baris satuan
    ends = starts[1:] + [gcol if gcol is not None else len(head)]
    found = 0
    for c0, c1 in zip(starts, ends, strict=True):
        ff = _ff(cell(ffrow, c0))
        depth_unit = unit_in(cell(unitrow, c0)) or "ft"
        cols = []
        for j in range(c0 + 1, c1):
            h = norm(cell(head, j))
            op = next((o for o, pats in op_patterns.items() if match_any(h, pats)), None)
            if op is None:
                continue
            col_ff = _ff(cell(ffrow, j))
            if col_ff is None:
                col_ff = ff
            unit = unit_in(cell(unitrow, j)) or default_unit
            cols.append((j, op, col_ff, unit))
        if ff is None and cols:
            pw.warn(f"Nilai FF blok kolom {c0 + 1} tidak terbaca", sheet)
        for r in rows[data_start:]:
            d = to_float(cell(r, c0))
            if d is None:
                continue
            for j, op, col_ff, unit in cols:
                v = to_float(cell(r, j))
                if v is not None:
                    pw.plan.append(Row(op, d, depth_unit, v, unit, sheet, col_ff))
                    found += 1
    if not found:
        pw.error("Tidak ada nilai WellPlan yang terbaca", sheet)


def _ff(text) -> float | None:
    m = re.search(cm.FF_OPEN_HOLE, norm(text))
    if not m:
        return None
    v = to_float(m.group(1))
    return round(v, 3) if v is not None and 0 <= v <= 1 else None


def _parse_drag_calibration(rows, pw) -> None:
    # baris "Calibrate | | PICK UP | SLACK OFF | ROTATE" + baris nilai di bawahnya
    for i, r in enumerate(rows[:5]):
        if norm(cell(r, 0)) == "calibrate" and i + 1 < len(rows):
            cal = {}
            for j, c in enumerate(r):
                key = norm(c)
                if key in ("pick up", "slack off", "rotate"):
                    v = to_float(cell(rows[i + 1], j))
                    if v is not None:
                        cal[key.replace(" ", "_")] = v
            if cal:
                pw.meta["calibration_drag_klbf"] = cal


def _parse_torque_calibration(rows, pw) -> None:
    cal = {}
    for r in rows[:5]:
        label = norm(cell(r, 0))
        if label.startswith("calibrate"):
            v = next((to_float(c) for c in r[1:] if to_float(c) is not None), None)
            if v is not None:
                cal["on_bottom" if "on bot" in label else "off_bottom"] = v
    if cal:
        pw.meta["calibration_torque_ftlbf"] = cal


def _parse_actual(rows, pw, sheet) -> None:
    hdr = next(
        (i for i, r in enumerate(rows[:30]) if any(norm(c).startswith("depth") for c in r)), None
    )
    if hdr is None:
        pw.warn("Header 'Depth' data aktual tidak ditemukan", sheet)
        return
    # meta di atas header
    for r in rows[:hdr]:
        for j, c in enumerate(r):
            t = norm(c)
            if not t:
                continue
            nxt = next((x for x in r[j + 1 :] if x not in (None, "")), None)
            m = re.match(cm.ACTUAL_META["well_name"], t)
            if m and "well_name" not in pw.meta:
                inline = str(c).split(":", 1)[1].strip() if ":" in str(c) else ""
                name = inline or (
                    str(nxt).strip() if nxt is not None and ":" not in str(nxt) else ""
                )
                if name:
                    pw.meta["well_name"] = name
            elif re.search(cm.ACTUAL_META["block_weight"], t) and nxt is not None:
                bw = first_number(nxt)
                if bw is not None:
                    pw.meta["block_weight_klbf"] = bw
            elif re.match(cm.ACTUAL_META["section_meta"], t) and nxt is not None:
                pw.meta["section_meta"] = str(nxt).strip()
                pw.meta["section_meta_in"] = first_number(nxt)
            elif re.match(cm.ACTUAL_META["run"], t) and nxt is not None:
                pw.meta["run"] = str(nxt).strip()
    head = rows[hdr]
    depth_col = next(j for j, c in enumerate(head) if norm(c).startswith("depth"))
    depth_unit = unit_in(head[depth_col]) or "ft"
    cols = []
    for j, c in enumerate(head):
        h = norm(c)
        if j == depth_col or not h or match_any(h, cm.ACTUAL_IGNORE):
            continue
        op = next((o for o, pats in cm.ACTUAL_COLS.items() if match_any(h, pats)), None)
        if op is None:
            continue
        default = "ft-lbf" if op.startswith("torque") else "klbf"
        unit = unit_in(c) or default
        cols.append((j, op, unit))
    if not cols:
        pw.warn("Kolom data aktual tidak dikenali", sheet)
        return
    for r in rows[hdr + 1 :]:
        d = to_float(cell(r, depth_col))
        if d is None:
            continue
        for j, op, unit in cols:
            v = to_float(cell(r, j))
            if v is not None:
                pw.actual.append(Row(op, d, depth_unit, v, unit, sheet))
