"""Format B, laporan WellPlan "TnD" (.xlsm, dibaca tanpa macro).

Summary            : Client/Field/Well, Block Weight, Mud Weight, tabel BHA, tabel
                     Wellbore (casing shoe + diameter lubang), tabel Friction Factors.
Tripping Load Analysis : Bit Depth + "CSG 0.3 OPH 0.3 Trip IN/Out" + "Rotate Off Bottom"
                     (baris satuan "1000 lbf").
Off Bottom Torque analysis : Bit Depth + "CSG x OPH x" (1000 ft.lbf).
Rotary Drill Buckling Outputs : Surface Torque per kedalaman bit saat rotary drilling
                     = rencana torque on bottom, hanya untuk Base FF set.
Survey Outputs     : Measured Depth, Inclination, Azimuth, Dog-Leg Severity.
Drilling Data      : data aktual harian (klbf, torsi kft-lbf, TANPA satuan di header).
Tripping  Data     : data aktual trip (blok Trip #1..#3: depth, slack off, pick up).
"""

import re

from app.parsers import column_map as cm
from app.parsers.common import (
    ParsedWorkbook,
    Row,
    SheetInfo,
    SurveyRow,
    cell,
    first_number,
    match_any,
    norm,
    read_rows,
    to_float,
    unit_in,
)


def parse_wellplan(wb, pw: ParsedWorkbook) -> None:
    pw.fmt = "wellplan"
    seen = set()
    for ws in wb.worksheets:
        n = norm(ws.title)
        rows = read_rows(ws)
        role = None
        if n == "summary":
            role = "summary"
            _parse_summary(rows, pw)
        elif re.match(cm.WP_TRIPPING, n):
            role = "tripping"
            _parse_tripping(rows, pw, ws.title)
        elif re.match(cm.WP_OFFBTM, n):
            role = "off_bottom_torque"
            _parse_offbottom(rows, pw, ws.title)
        elif re.match(cm.WP_ROTARY, n):
            role = "rotary_drill"
            _parse_rotary(rows, pw, ws.title)
        elif re.match(cm.WP_SURVEY, n):
            role = "survey"
            _parse_survey(rows, pw, ws.title)
        elif re.match(cm.WP_DRILLING, n):
            role = "actual_drilling"
            _parse_drilling(rows, pw, ws.title)
        elif re.match(cm.WP_TRIPDATA, n):
            role = "actual_tripping"
            _parse_tripdata(rows, pw, ws.title)
        seen.add(role)
        pw.sheets.append(SheetInfo(ws.title, role, len(rows)))
    for role, label in (
        ("summary", "Summary"),
        ("tripping", "Tripping Load Analysis"),
        ("off_bottom_torque", "Off Bottom Torque analysis"),
    ):
        if role not in seen:
            pw.error(f"Sheet '{label}' is missing")
    if "rotary_drill" not in seen:
        pw.warn("Sheet 'Rotary Drill Buckling Outputs' is missing: no modelled torque on bottom")
    if "survey" not in seen:
        pw.warn("Sheet 'Survey Outputs' is missing")
    if pw.plan:
        pw.kinds.add("plan")
    if pw.actual:
        pw.kinds.add("actual")
    pw.meta["ff_scenarios"] = sorted({r.ff for r in pw.plan if r.ff is not None})


# ---------------------------------------------------------------- Summary


def _parse_summary(rows, pw) -> None:
    for r in rows:
        for j, c in enumerate(r):
            t = norm(c)
            if not t.endswith(":"):
                continue
            for key, pat in cm.SUMMARY_KEYS.items():
                if key in pw.meta or not re.search(pat, t):
                    continue
                val = next((x for x in r[j + 1 :] if x not in (None, "")), None)
                if val is None:
                    continue
                if key in ("block_weight", "mud_weight"):
                    num = first_number(val)
                    if num is not None:
                        pw.meta[
                            "block_weight_klbf" if key == "block_weight" else "mud_weight_ppg"
                        ] = num
                elif key == "bit_depth_range":
                    nums = re.findall(r"\d+(?:\.\d+)?", str(val))
                    if len(nums) >= 2:
                        pw.meta["drilling_range_ft"] = [float(nums[0]), float(nums[1])]
                else:
                    pw.meta[key] = str(val).strip()
    _parse_bha(rows, pw)
    _parse_wellbore(rows, pw)
    _parse_ff_table(rows, pw)


def _find_row(rows, text: str, col_text_exact: bool = True) -> int | None:
    for i, r in enumerate(rows):
        for c in r:
            t = norm(c)
            if (t == text) if col_text_exact else t.startswith(text):
                return i
    return None


def _header_index(r, name: str) -> int | None:
    return next((j for j, c in enumerate(r) if norm(c).startswith(name)), None)


def _parse_bha(rows, pw) -> None:
    i = _find_row(rows, "component name")
    if i is None:
        return
    h = rows[i]
    cj = {
        k: _header_index(h, k) for k in ("component name", "length", "od", "max od", "lin weight")
    }
    comps = []
    for r in rows[i + 2 :]:
        name = cell(r, cj["component name"]) if cj["component name"] is not None else None
        if name in (None, "") or not str(name).strip():
            break
        length = to_float(cell(r, cj["length"])) if cj["length"] is not None else None
        lw = to_float(cell(r, cj["lin weight"])) if cj["lin weight"] is not None else None
        od = to_float(cell(r, cj["od"])) if cj["od"] is not None else None
        max_od = to_float(cell(r, cj["max od"])) if cj["max od"] is not None else None
        comps.append(
            {
                "name": str(name).strip(),
                "length_ft": length,
                "od_in": od,
                "max_od_in": max_od,
                "lin_weight_ppf": lw,
            }
        )
    if not comps:
        return
    # komponen "to surface" (drill pipe) bukan bagian BHA
    bha = [c for c in comps if "surface" not in c["name"].lower()]
    pw.meta["bha_components"] = len(bha)
    pw.meta["bha_length_ft"] = round(sum(c["length_ft"] or 0 for c in bha), 2)
    pw.meta["bha_weight_klbf"] = round(
        sum((c["length_ft"] or 0) * (c["lin_weight_ppf"] or 0) for c in bha) / 1000, 3
    )
    bit = comps[0]
    if "bit" in bit["name"].lower() and bit["max_od_in"]:
        pw.meta["bit_size_in"] = bit["max_od_in"]
    dp = next((c for c in comps if "surface" in c["name"].lower()), None)
    if dp:
        pw.meta["dp_od_in"] = dp["od_in"]
        pw.meta["dp_weight_ppf"] = dp["lin_weight_ppf"]


def _parse_wellbore(rows, pw) -> None:
    i = _find_row(rows, "section name")
    if i is None:
        return
    h = rows[i]
    jn, jc, jd = (
        _header_index(h, "section name"),
        _header_index(h, "cum length"),
        _header_index(h, "diameter"),
    )
    shoe = None
    hole = None
    for r in rows[i + 2 :]:
        name = norm(cell(r, jn))
        if not name:
            break
        cum = to_float(cell(r, jc)) if jc is not None else None
        dia = to_float(cell(r, jd)) if jd is not None else None
        if "casing" in name or "liner" in name:
            shoe = cum
        else:
            hole = dia
    if shoe is not None:
        pw.meta["casing_shoe"] = shoe
        pw.meta["casing_shoe_unit"] = "ft"
    if hole is not None:
        pw.meta["hole_size_in"] = hole


def _parse_ff_table(rows, pw) -> None:
    i = _find_row(rows, "friction factors")
    if i is None or i + 1 >= len(rows):
        return
    h = rows[i + 1]
    for r in rows[i + 2 : i + 10]:
        if norm(cell(r, 1)) == "base set":
            base = {}
            for j, c in enumerate(h):
                v = to_float(cell(r, j))
                t = norm(c)
                if v is None or not t:
                    continue
                if t.startswith("open hole rotational"):
                    base["oh_rot"] = v
                elif t.startswith("cased hole rotational"):
                    base["ch_rot"] = v
                elif t.startswith("open hole translational (sl"):
                    base["oh_slide"] = v
                elif t.startswith("cased hole translational (sl"):
                    base["ch_slide"] = v
            pw.meta["base_ff"] = base


# ---------------------------------------------------------------- Rencana WellPlan


def _bitdepth_table(rows, pw, sheet, first: str = "bit depth"):
    i = next(
        (k for k, r in enumerate(rows[:40]) if any(norm(c) == first for c in r)),
        None,
    )
    if i is None:
        pw.error(f"Header '{first.title()}' not found", sheet)
        return None
    head = rows[i]
    unitrow = rows[i + 1] if i + 1 < len(rows) else ()
    dcol = next(j for j, c in enumerate(head) if norm(c) == first)
    return i, head, unitrow, dcol


def _parse_tripping(rows, pw, sheet) -> None:
    t = _bitdepth_table(rows, pw, sheet)
    if t is None:
        return
    i, head, unitrow, dcol = t
    du = unit_in(cell(unitrow, dcol)) or "ft"
    cols = []
    for j, c in enumerate(head):
        h = norm(c)
        if j == dcol or not h:
            continue
        unit = unit_in(cell(unitrow, j)) or "klbf"
        m = re.search(cm.WP_FF_SET, h)
        if m and "trip in" in h:
            cols.append((j, "slack_off", to_float(m.group(2)), unit))
        elif m and "trip out" in h:
            cols.append((j, "pick_up", to_float(m.group(2)), unit))
        elif h.startswith("rotate off bottom"):
            cols.append((j, "rotating_weight", None, unit))
    _collect(rows[i + 2 :], dcol, du, cols, pw.plan, sheet)
    if not cols:
        pw.error("Columns Trip IN / Trip Out / Rotate Off Bottom not recognised", sheet)


def _parse_offbottom(rows, pw, sheet) -> None:
    t = _bitdepth_table(rows, pw, sheet)
    if t is None:
        return
    i, head, unitrow, dcol = t
    du = unit_in(cell(unitrow, dcol)) or "ft"
    cols = []
    for j, c in enumerate(head):
        m = re.search(cm.WP_FF_SET, norm(c))
        if m:
            cols.append(
                (
                    j,
                    "torque_off_bottom",
                    to_float(m.group(2)),
                    unit_in(cell(unitrow, j)) or "kft-lbf",
                )
            )
    _collect(rows[i + 2 :], dcol, du, cols, pw.plan, sheet)
    if not cols:
        pw.error("Columns 'CSG x OPH y' not recognised", sheet)


def _parse_rotary(rows, pw, sheet) -> None:
    t = _bitdepth_table(rows, pw, sheet, first="measured depth")
    if t is None:
        return
    i, head, unitrow, dcol = t
    du = unit_in(cell(unitrow, dcol)) or "ft"
    j = next((k for k, c in enumerate(head) if norm(c) == "surface torque"), None)
    if j is None:
        pw.warn("Column 'Surface Torque' not found", sheet)
        return
    ff = (pw.meta.get("base_ff") or {}).get("oh_rot")
    _collect(
        rows[i + 2 :],
        dcol,
        du,
        [(j, "torque_on_bottom", ff, unit_in(cell(unitrow, j)) or "kft-lbf")],
        pw.plan,
        sheet,
    )


def _collect(rows, dcol, du, cols, target, sheet) -> None:
    for r in rows:
        d = to_float(cell(r, dcol))
        if d is None:
            continue
        for j, op, ff, unit in cols:
            v = to_float(cell(r, j))
            if v is not None:
                target.append(Row(op, d, du, v, unit, sheet, ff))


# ---------------------------------------------------------------- Survey


def _parse_survey(rows, pw, sheet) -> None:
    i = next(
        (k for k, r in enumerate(rows[:60]) if any(norm(c) == "measured depth" for c in r)), None
    )
    if i is None:
        pw.warn("Survey table (Measured Depth) not found", sheet)
        return
    head = rows[i]
    unitrow = rows[i + 1] if i + 1 < len(rows) else ()
    col = {}
    for j, c in enumerate(head):
        h = norm(c)
        if h == "measured depth":
            col["md"] = j
        elif h.startswith("inclination"):
            col["inc"] = j
        elif h.startswith("azimuth"):
            col["azi"] = j
        elif h.startswith("dog-leg") or h.startswith("dogleg") or h.startswith("dls"):
            col["dls"] = j
        elif h.startswith("true vertical") or h == "tvd":
            col["tvd"] = j
    if "md" not in col or "inc" not in col:
        pw.warn("Survey MD/Inclination columns incomplete", sheet)
        return
    pw.survey_units = {
        "md": unit_in(cell(unitrow, col["md"])) or "ft",
        "dls": unit_in(cell(unitrow, col["dls"])) if "dls" in col else "deg/100ft",
        "tvd": "ft",
    }
    pw.survey_units["dls"] = pw.survey_units["dls"] or "deg/100ft"
    for r in rows[i + 2 :]:
        md, inc = to_float(cell(r, col["md"])), to_float(cell(r, col["inc"]))
        if md is None or inc is None:
            continue
        pw.survey.append(
            SurveyRow(
                md,
                inc,
                to_float(cell(r, col["azi"])) if "azi" in col else None,
                to_float(cell(r, col["tvd"])) if "tvd" in col else None,
                to_float(cell(r, col["dls"])) if "dls" in col else None,
            )
        )


# ---------------------------------------------------------------- Data aktual


def _parse_drilling(rows, pw, sheet) -> None:
    i = next((k for k, r in enumerate(rows[:15]) if norm(cell(r, 0)) == "depth"), None)
    if i is None:
        pw.warn("Header 'Depth' of Drilling Data not found", sheet)
        return
    head = rows[i]
    cols = []
    for j, c in enumerate(head):
        h = norm(c)
        op = next((o for o, pats in cm.DRILLING_COLS.items() if match_any(h, pats)), None)
        if op:
            cols.append((j, op))
    raw = []
    for r in rows[i + 1 :]:
        d = to_float(cell(r, 0))
        if d is None:
            continue
        raw.append((d, {op: to_float(cell(r, j)) for j, op in cols}))
    if not raw:
        return
    # Header tanpa satuan: beban klbf; torsi kft-lbf bila nilainya kecil (< 100)
    tq = [
        v[op]
        for _, v in raw
        for op in ("torque_off_bottom", "torque_on_bottom")
        if v.get(op) is not None
    ]
    tq_unit = "kft-lbf" if tq and max(tq) < 100 else "ft-lbf"
    pw.meta["drilling_torque_unit_assumed"] = tq_unit
    for d, vals in raw:
        for op, v in vals.items():
            if v is None:
                continue
            unit = tq_unit if op.startswith("torque") else "klbf"
            pw.actual.append(Row(op, d, "ft", v, unit, sheet))


def _parse_tripdata(rows, pw, sheet) -> None:
    i = next((k for k, r in enumerate(rows[:15]) if any(norm(c) == "trip depth" for c in r)), None)
    if i is None:
        return
    head = rows[i]
    starts = [j for j, c in enumerate(head) if norm(c) == "trip depth"]
    for s in starts:
        cols = []
        for j in range(s + 1, s + 3):
            h = norm(cell(head, j))
            if "slack" in h:
                cols.append((j, "slack_off"))
            elif "pick" in h:
                cols.append((j, "pick_up"))
        for r in rows[i + 1 :]:
            d = to_float(cell(r, s))
            if d is None:
                continue
            for j, op in cols:
                v = to_float(cell(r, j))
                if v is not None:
                    pw.actual.append(Row(op, d, "ft", v, "klbf", sheet))
