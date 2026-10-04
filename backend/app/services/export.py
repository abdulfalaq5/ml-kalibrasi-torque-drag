"""Ekspor Excel (.xlsx, XlsxWriter, tanpa macro). Semua teks keluaran dalam bahasa Inggris.

export_well         : per sumur, struktur sheet mengikuti file contoh client
                      (Drag, Torque, T&D Actual Reading) + kolom ML, selisih, band P10-P90,
                      grafik per operasi (warna tetap per OHFF), Difference, operating limits.
export_quality_report : laporan kualitas data semua sumur (status A/B/C, skor, alasan, tinjauan).
export_model_report : laporan evaluasi model (validasi silang, blind test, kurva belajar, SHAP).
"""

import io
import math

import numpy as np
import xlsxwriter
from sqlalchemy.orm import Session

from app.db.models import Dataset, MLModel, Well
from app.services.operations import HOOKLOAD_OPS, OP_LABELS, OPERATIONS, SERIES_PREFIX, TORQUE_OPS
from app.services.profile import well_profile

# warna sama dengan dashboard (web/src/components/chartTheme.ts)
COLORS = {"ml": "#eb6834", "actual": "#1baf7a", "limit": "#e34948"}
# satu warna tetap per nilai OHFF di semua grafik (ramp biru ordinal, tervalidasi)
OHFF_COLORS = {0.1: "#86b6ef", 0.2: "#5598e7", 0.3: "#2a78d6", 0.4: "#1c5cab", 0.5: "#104281"}
DIFF_COLORS = {"wp_minus_actual": "#2a78d6", "ml_minus_actual": "#eb6834", "ml_minus_wp": "#4a3aa7"}
DIFF_LABELS = {
    "wp_minus_actual": "T&D Model - Actual",
    "ml_minus_actual": "ML - Actual",
    "ml_minus_wp": "ML - T&D Model",
}
STATUS_LABEL = {
    "A": "Accepted",
    "B": "Accepted with warnings",
    "C": "On hold",
    "X": "Excluded",
}


def ohff_color(ff: float | None) -> str:
    if ff is None:
        return OHFF_COLORS[0.3]
    return OHFF_COLORS[min(OHFF_COLORS, key=lambda k: abs(k - ff))]


class _Fmt:
    def __init__(self, wb):
        self.bold = wb.add_format({"bold": True})
        self.title = wb.add_format({"bold": True, "font_size": 13})
        self.head = wb.add_format(
            {"bold": True, "bg_color": "#eaeef2", "border": 1, "text_wrap": True, "valign": "top"}
        )
        self.num = wb.add_format({"num_format": "#,##0.00"})
        self.num3 = wb.add_format({"num_format": "#,##0.000"})
        self.pct = wb.add_format({"num_format": "0%"})
        self.warn = wb.add_format({"bg_color": "#fff4d6"})
        self.bad = wb.add_format({"bg_color": "#fde7e7"})
        self.ok = wb.add_format({"bg_color": "#e3f4ea"})
        self.wrap = wb.add_format({"text_wrap": True, "valign": "top"})


def _write_row(ws, r: int, values: list, fmt=None, numfmt=None) -> None:
    for j, v in enumerate(values):
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            ws.write_blank(r, j, None, fmt)
        elif isinstance(v, str):
            ws.write_string(r, j, v, fmt)
        elif isinstance(v, bool):
            ws.write_string(r, j, "yes" if v else "", fmt)
        else:
            ws.write_number(r, j, float(v), fmt or numfmt)


def _interp(depth, value, grid):
    pairs = [(d, v) for d, v in zip(depth, value, strict=True) if d is not None and v is not None]
    if len(pairs) < 2:
        return [None] * len(grid)
    d = np.array([p[0] for p in pairs], float)
    v = np.array([p[1] for p in pairs], float)
    order = np.argsort(d)
    d, v = d[order], v[order]
    out = np.interp(grid, d, v)
    return [
        None if (g < d[0] - 1e-6 or g > d[-1] + 1e-6) else float(x)
        for g, x in zip(grid, out, strict=True)
    ]


def _nearest(depth, value, grid, tol):
    out = []
    for g in grid:
        best, bd = None, tol
        for d, v in zip(depth, value, strict=True):
            if abs(d - g) <= bd:
                best, bd = v, abs(d - g)
        out.append(best)
    return out


def _wp_mode_label(prof: dict) -> str:
    cal = prof.get("calibration") or {}
    if cal.get("mode") == "calibrated":
        return "WellPlan + DD Calibrate offsets (as Excel 'Graph reference')"
    return "WellPlan as modelled (no DD Calibrate offsets)"


# ---------------------------------------------------------------- per sumur


def export_well(
    db: Session,
    well: Well,
    unit_system: str = "imperial",
    diff_target: str = "pick_up",
    model: MLModel | None = None,
    calibration: str | None = None,
) -> bytes:
    prof = well_profile(db, well, unit_system, model, calibration)
    du = prof["depth_unit"]
    ops = prof["operations"]
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True, "nan_inf_to_errors": True})
    f = _Fmt(wb)

    # ---------- Info
    ws = wb.add_worksheet("Info")
    ws.set_column(0, 0, 30)
    ws.set_column(1, 1, 90)
    q = prof["quality"]
    m = prof["model"] or {}
    info = [
        ("Well", well.name),
        ("Well section (in)", well.section_in),
        ("Well type", well.well_type),
        ("Data group", "Training (ML reference)" if well.purpose == "training" else "Monitoring"),
        ("Plan file format", (well.meta or {}).get("plan_format")),
        (
            "Data quality",
            f"{q['status']} - {STATUS_LABEL.get(q['status'], '')} (score {q['score']})",
        ),
        ("Model", "-" if not m else f"#{m['id']} (dataset v{m.get('dataset_version')})"),
        (
            "Forecast",
            "-"
            if prof["prediction"] is None
            else (
                "out-of-fold (the model never saw this well)"
                if prof["prediction"]["kind"] == "oof"
                else "full model"
            ),
        ),
        ("WellPlan curves", _wp_mode_label(prof)),
        ("Unit system", unit_system),
        ("Sign convention", prof["sign_convention"]),
        ("Uncertainty band (P10–P90)", "10%–90% quantiles of cross-validation residuals"),
    ]
    ws.write(0, 0, "Prediction Output Torque & Drag ML", f.title)
    for i, (k, v) in enumerate(info, start=2):
        ws.write(i, 0, k, f.bold)
        ws.write(i, 1, "" if v is None else v)
    r = len(info) + 3
    ws.write(r, 0, "DD Calibrate offsets", f.bold)
    for j, op in enumerate(OPERATIONS):
        off = ops[op].get("calibration_offset")
        ws.write(
            r + j,
            1,
            f"{SERIES_PREFIX[op]}: {'-' if off is None else f'{off:g} ' + ops[op]['unit']}",
        )
    r += len(OPERATIONS) + 1
    ws.write(r, 0, "Warnings", f.bold)
    for j, w in enumerate(prof["warnings"] or ["-"]):
        ws.write(r + j, 1, w)
    r += max(len(prof["warnings"]), 1) + 1
    ws.write(r, 0, "Data quality notes", f.bold)
    for j, c in enumerate(q["issues"] or [{"message": "-"}]):
        ws.write(r + j, 1, c["message"])

    # ---------- Drag / Torque (grid prediksi, struktur seperti file roadmap)
    chart_cols: dict[tuple, tuple[str, int, int]] = {}  # kunci -> (sheet, kolom, n baris)
    for sheet, group in (("Drag", HOOKLOAD_OPS), ("Torque", TORQUE_OPS)):
        ws = wb.add_worksheet(sheet)
        ws.write(
            0,
            0,
            f"WellPlan T&D model + ML forecast. WellPlan curves: {_wp_mode_label(prof)}",
            f.bold,
        )
        grid = sorted(
            {d for op in group for d in ops[op]["ml"]["depth"]}
            | {d for op in group for s in ops[op]["wellplan"] for d in s["depth"]}
        )
        cols = [f"Depth ({du})"]
        series = []
        for op in group:
            o = ops[op]
            for s in o["wellplan"]:
                cols.append(f"{s['name']} ({o['unit']})")
                series.append((("wp", op, s["ff"]), _interp(s["depth"], s["value"], grid)))
        for op in group:
            o = ops[op]
            p = SERIES_PREFIX[op]
            cols += [
                f"{p} - ML ({o['unit']})",
                f"{p} - ML P10",
                f"{p} - ML P90",
                f"ML - T&D Model {p} ({o['unit']})",
            ]
            ml = _interp(o["ml"]["depth"], o["ml"]["value"], grid)
            lo = (
                _interp(o["ml"]["depth"], o["ml"]["lo"], grid)
                if o["ml"]["lo"]
                else [None] * len(grid)
            )
            hi = (
                _interp(o["ml"]["depth"], o["ml"]["hi"], grid)
                if o["ml"]["hi"]
                else [None] * len(grid)
            )
            d = o["diff"]["ml_minus_wp"]
            series += [
                (("ml", op), ml),
                (("lo", op), lo),
                (("hi", op), hi),
                (("diff", op), _interp(d["depth"], d["abs"], grid)),
            ]
        for j, h in enumerate(cols):
            ws.write(2, j, h, f.head)
        for i, dep in enumerate(grid):
            _write_row(ws, i + 3, [dep] + [s[1][i] for s in series], numfmt=f.num)
        ws.set_row(2, 60)
        ws.set_column(0, len(cols), 14)
        ws.freeze_panes(3, 1)
        for j, (key, vals) in enumerate(series, start=1):
            if any(v is not None for v in vals):
                chart_cols[key] = (sheet, j, len(grid))

    # ---------- T&D Actual Reading (titik aktual + ML + WellPlan + selisih)
    ws = wb.add_worksheet("T&D Actual Reading")
    ws.write(0, 0, f"Well: {well.name}", f.bold)
    ws.write(1, 0, f'Section: {well.section_in:g}"' if well.section_in else "Section: -", f.bold)
    tol = 30 if du == "ft" else 10
    act_grid = sorted({d for op in OPERATIONS for d in ops[op]["actual"]["depth"]})
    cols = [f"Depth ({du})"]
    rows_cols = []
    for op in OPERATIONS:
        o = ops[op]
        p = SERIES_PREFIX[op]
        a = _nearest(o["actual"]["depth"], o["actual"]["value"], act_grid, tol)
        ml = _interp(o["ml"]["depth"], o["ml"]["value"], act_grid)
        base = next(
            (s for s in o["wellplan"] if s["ff"] == o["wellplan_baseline_ff"]),
            o["wellplan"][0] if o["wellplan"] else None,
        )
        wp = _interp(base["depth"], base["value"], act_grid) if base else [None] * len(act_grid)
        cols += [
            f"{p} Actual ({o['unit']})",
            f"WellPlan {base['name'] if base else p}",
            f"{p} - ML",
            f"T&D Model - Actual {p}",
            f"ML - Actual {p}",
        ]
        rows_cols += [
            a,
            wp,
            ml,
            [None if x is None or y is None else x - y for x, y in zip(wp, a, strict=True)],
            [None if x is None or y is None else x - y for x, y in zip(ml, a, strict=True)],
        ]
        if any(v is not None for v in a):
            chart_cols[("act", op)] = (
                "T&D Actual Reading",
                1 + 5 * OPERATIONS.index(op),
                len(act_grid),
            )
    for j, h in enumerate(cols):
        ws.write(3, j, h, f.head)
    for i, dep in enumerate(act_grid):
        _write_row(ws, i + 4, [dep] + [c[i] for c in rows_cols], numfmt=f.num)
    ws.set_row(3, 45)
    ws.set_column(0, len(cols), 13)
    ws.freeze_panes(4, 1)

    # ---------- Difference (target terpilih)
    wsd = wb.add_worksheet("Difference")
    o = ops[diff_target]
    diff_ranges, col = {}, 0
    for key, label in DIFF_LABELS.items():
        dd = o["diff"][key]
        wsd.write(0, col, f"{label} depth ({du})", f.head)
        wsd.write(0, col + 1, f"{label} ({o['unit']})", f.head)
        wsd.write(0, col + 2, f"{label} (%)", f.head)
        for i, (d, a, p) in enumerate(zip(dd["depth"], dd["abs"], dd["pct"], strict=True)):
            _write_row(wsd, i + 1, [d, a, p])
        diff_ranges[key] = (col, len(dd["depth"]))
        col += 4
    all_d = [d for k in DIFF_LABELS for d in o["diff"][k]["depth"]]
    max_abs = max((abs(v) for k in DIFF_LABELS for v in o["diff"][k]["abs"]), default=1.0) or 1.0
    wsd.write(0, col, "Zero line", f.head)
    if all_d:
        wsd.write_row(1, col, [0, min(all_d)])
        wsd.write_row(2, col, [0, max(all_d)])
    zero_col = col
    wsd.set_column(0, col + 1, 16)

    # ---------- Operating limits: data garis vertikal untuk grafik
    wsl = wb.add_worksheet("Operating limits")
    hdr = [
        "Operation",
        "Kind",
        "Limit",
        "Unit",
        "Applies to",
        "Depth where ML reaches the limit",
        "Depth where the ML band (P10–P90) reaches the limit",
        "Depth where the T&D Model reaches the limit",
        "Minimum ML margin",
        "Note",
    ]
    for j, h in enumerate(hdr):
        wsl.write(0, j, h, f.head)
    r = 1
    lim_lines: dict[str, list[tuple[float, str]]] = {}
    for op in OPERATIONS:
        for lim_ in ops[op]["limits"]:
            _write_row(
                wsl,
                r,
                [
                    OP_LABELS[op],
                    lim_["kind"],
                    lim_["value"],
                    ops[op]["unit"],
                    lim_["scope"],
                    lim_["cross_ml"],
                    lim_["cross_ml_band"],
                    lim_["cross_wellplan"],
                    lim_["margin_ml"],
                    lim_["note"] or "",
                ],
                f.bad if lim_["cross_ml"] is not None else None,
                f.num,
            )
            lim_lines.setdefault(op, []).append(
                (lim_["value"], f"Limit {lim_['kind']} {lim_['value']:g}")
            )
            r += 1
    if r == 1:
        wsl.write(
            1, 0, "No operating limits for this well/section yet (set them on the dashboard)."
        )
    wsl.set_column(0, 9, 18)
    # garis batas: (nilai, kedalaman min) dan (nilai, kedalaman maks) di kolom L:M
    all_depths = [d for op in OPERATIONS for s in ops[op]["wellplan"] for d in s["depth"]]
    dmin, dmax = (min(all_depths), max(all_depths)) if all_depths else (0, 1)
    wsl.write(0, 11, "Chart helper: limit value", f.head)
    wsl.write(0, 12, f"Chart helper: depth ({du})", f.head)
    lim_rows: dict[str, list[tuple[int, str]]] = {}
    hr = 1
    for op, lines in lim_lines.items():
        for v, name in lines:
            wsl.write_row(hr, 11, [v, dmin])
            wsl.write_row(hr + 1, 11, [v, dmax])
            lim_rows.setdefault(op, []).append((hr, name))
            hr += 2

    # ---------- Charts: satu grafik per operasi + Difference
    wsg = wb.add_worksheet("Charts")
    wsg.set_landscape()
    wsg.write(
        0,
        0,
        f'{well.name} {(well.section_in or 0):g}" - WellPlan per OHFF (blue shades, one colour per '
        "OHFF), ML forecast (orange), P10/P90 band (orange dashed), Actual (green points), "
        "operating limits (red dotted).",
        f.bold,
    )
    for k, op in enumerate(OPERATIONS):
        o = ops[op]
        ch = wb.add_chart({"type": "scatter", "subtype": "straight"})
        for s in o["wellplan"]:
            loc = chart_cols.get(("wp", op, s["ff"]))
            if loc:
                _add_line(ch, s["name"], loc, ohff_color(s["ff"]), "solid", 1.5)
        for key, name, dash, width in (
            ("ml", f"{SERIES_PREFIX[op]} - ML", "solid", 2.25),
            ("lo", f"{SERIES_PREFIX[op]} - ML P10", "dash", 1.0),
            ("hi", f"{SERIES_PREFIX[op]} - ML P90", "dash", 1.0),
        ):
            loc = chart_cols.get((key, op))
            if loc:
                _add_line(ch, name, loc, COLORS["ml"], dash, width)
        loc = chart_cols.get(("act", op))
        if loc:
            sheet, c, n = loc
            ch.add_series(
                {
                    "name": f"{SERIES_PREFIX[op]} Actual",
                    "categories": [sheet, 4, c, n + 3, c],
                    "values": [sheet, 4, 0, n + 3, 0],
                    "line": {"none": True},
                    "marker": {
                        "type": "circle",
                        "size": 5,
                        "fill": {"color": COLORS["actual"]},
                        "border": {"color": "#fcfcfb"},
                    },
                }
            )
        for hr_, name in lim_rows.get(op, []):
            ch.add_series(
                {
                    "name": name,
                    "categories": ["Operating limits", hr_, 11, hr_ + 1, 11],
                    "values": ["Operating limits", hr_, 12, hr_ + 1, 12],
                    "line": {"color": COLORS["limit"], "width": 1.5, "dash_type": "round_dot"},
                    "marker": {"type": "none"},
                }
            )
        _style_depth_chart(ch, OP_LABELS[op], f"{OP_LABELS[op]} ({o['unit']})", du)
        wsg.insert_chart(2 + (k // 3) * 32, (k % 3) * 9, ch, {"x_scale": 1.1, "y_scale": 2.0})

    ch = wb.add_chart({"type": "scatter"})
    for key, label in DIFF_LABELS.items():
        c0, n = diff_ranges[key]
        if not n:
            continue
        line = key == "ml_minus_wp"
        ch.add_series(
            {
                "name": label,
                "categories": ["Difference", 1, c0 + 1, n, c0 + 1],
                "values": ["Difference", 1, c0, n, c0],
                "line": {"color": DIFF_COLORS[key], "width": 1.5} if line else {"none": True},
                "marker": {"type": "none"}
                if line
                else {
                    "type": "circle",
                    "size": 4,
                    "fill": {"color": DIFF_COLORS[key]},
                    "border": {"color": DIFF_COLORS[key]},
                },
            }
        )
    if all_d:
        ch.add_series(
            {
                "name": "Zero",
                "categories": ["Difference", 1, zero_col, 2, zero_col],
                "values": ["Difference", 1, zero_col + 1, 2, zero_col + 1],
                "line": {"color": "#000000", "width": 1.75},
                "marker": {"type": "none"},
            }
        )
    x_title = f"<- lower (-)   Difference Δ ({o['unit']})   higher (+) ->"
    _style_depth_chart(ch, f"Difference Δ {OP_LABELS[diff_target]} (right = higher)", x_title, du)
    step = _nice_step(max_abs * 1.15 / 3)
    lim = math.ceil(max_abs * 1.15 / step) * step
    ch.set_x_axis(
        {
            "name": x_title,
            "min": -lim,
            "max": lim,
            "major_unit": step,
            "crossing": "min",
            "major_gridlines": {"visible": True, "line": {"color": "#e5e5e5"}},
        }
    )
    wsg.insert_chart(34, 18, ch, {"x_scale": 1.1, "y_scale": 2.0})

    # ---------- Metrics
    ws = wb.add_worksheet("Metrics")
    hdr = [
        "Operation",
        "Unit",
        "RMSE T&D Model",
        "MAPE T&D Model (%)",
        "R² T&D Model",
        "RMSE ML",
        "MAPE ML (%)",
        "R² ML",
        "Points",
    ]
    for j, h in enumerate(hdr):
        ws.write(0, j, h, f.head)
    for i, op in enumerate(OPERATIONS, start=1):
        mm = ops[op]["metrics"] or {}
        wp, ml = mm.get("wellplan") or {}, mm.get("ml") or {}
        _write_row(
            ws,
            i,
            [
                OP_LABELS[op],
                ops[op]["unit"],
                wp.get("rmse"),
                wp.get("mape"),
                wp.get("r2"),
                ml.get("rmse"),
                ml.get("mape"),
                ml.get("r2"),
                (ml or wp).get("n"),
            ],
            numfmt=f.num,
        )
    ws.write(len(OPERATIONS) + 2, 0, f"WellPlan = {_wp_mode_label(prof)}, OHFF baseline curve.")
    ws.set_column(0, 8, 16)
    wb.close()
    return buf.getvalue()


def _add_line(
    ch, name: str, loc: tuple[str, int, int], color: str, dash: str, width: float
) -> None:
    sheet, c, n = loc
    if not n:
        return
    ch.add_series(
        {
            "name": name,
            "categories": [sheet, 3, c, n + 2, c],
            "values": [sheet, 3, 0, n + 2, 0],
            "line": {"color": color, "width": width, "dash_type": dash},
            "marker": {"type": "none"},
        }
    )


def _nice_step(raw: float) -> float:
    if raw <= 0:
        return 1.0
    mag = 10 ** math.floor(math.log10(raw))
    return next(m * mag for m in (1, 2, 5, 10) if m * mag >= raw)


def _style_depth_chart(ch, title: str, x_title: str, du: str) -> None:
    ch.set_title({"name": title, "name_font": {"size": 11}})
    ch.set_x_axis(
        {"name": x_title, "major_gridlines": {"visible": True, "line": {"color": "#e5e5e5"}}}
    )
    ch.set_y_axis(
        {
            "name": f"Kedalaman ({du})",
            "reverse": True,
            "major_gridlines": {"visible": True, "line": {"color": "#e5e5e5"}},
        }
    )
    ch.set_legend({"position": "bottom"})


# ---------------------------------------------------------------- kualitas data


def export_quality_report(rows: list[dict]) -> bytes:
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})
    f = _Fmt(wb)
    ws = wb.add_worksheet("Data quality")
    hdr = [
        "Well",
        "Well section (in)",
        "Well type",
        "Data group",
        "Status",
        "Meaning",
        "Automatic status",
        "Score",
        "Used for training",
        "Reasons (critical)",
        "Warnings",
        "Actual points",
        "Actual/WellPlan pick up ratio",
        "Review decision",
        "Review reason",
        "Reviewer",
        "Review date",
    ]
    for j, h in enumerate(hdr):
        ws.write(0, j, h, f.head)
    fm = {"A": f.ok, "B": f.warn, "C": f.bad, "X": f.bad}
    for i, r in enumerate(rows, start=1):
        crit = "; ".join(c["message"] for c in r["checks"] if c["level"] == "critical")
        warn = "; ".join(c["message"] for c in r["checks"] if c["level"] == "warning")
        rev = r["reviews"][0] if r["reviews"] else {}
        ws.write(i, 0, r["well"])
        _write_row(
            ws,
            i,
            [
                r["well"],
                r["section_in"],
                r["well_type"] or "",
                r.get("purpose", "training"),
                r["status"],
                STATUS_LABEL.get(r["status"], ""),
                r["auto_status"] or "",
                r["score"],
                "yes"
                if r["status"] in ("A", "B") and r.get("purpose", "training") == "training"
                else "no",
                crit,
                warn,
                r["stats"].get("n_actual_depths"),
                r["stats"].get("ratio_pick_up"),
                rev.get("decision", ""),
                rev.get("reason", ""),
                rev.get("reviewer", ""),
                str(rev.get("created_at", ""))[:19],
            ],
        )
        ws.write(i, 4, r["status"], fm.get(r["status"]))
    ws.set_column(0, 0, 34)
    ws.set_column(1, 8, 11)
    ws.set_column(9, 10, 60, f.wrap)
    ws.set_column(11, 16, 16)
    ws.autofilter(0, 0, len(rows), len(hdr) - 1)
    ws.freeze_panes(1, 1)

    ws = wb.add_worksheet("Summary")
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    ws.write(0, 0, "Status", f.head)
    ws.write(0, 1, "Meaning", f.head)
    ws.write(0, 2, "Well sections", f.head)
    for i, s in enumerate(("A", "B", "C", "X"), start=1):
        _write_row(ws, i, [s, STATUS_LABEL[s], counts.get(s, 0)])
    ws.write(6, 0, "Checks", f.bold)
    ws.write(
        7,
        0,
        "Critical (fail -> C): format & columns, units, increasing depth, physical values, order "
        "SO <= ROT <= PU, WellPlan-actual depth overlap, >= 8 actual points, section & type, "
        "not a duplicate.",
    )
    ws.write(
        8,
        0,
        "Statistical (fail -> warning B): actual/WellPlan ratio vs similar wells (MAD), "
        "jumps between points, repeated values, far fewer points, torque ratio.",
    )
    ws.set_column(0, 0, 14)
    ws.set_column(1, 1, 26)
    ws.set_column(2, 2, 20)
    wb.close()
    return buf.getvalue()


# ---------------------------------------------------------------- model


def export_model_report(model: MLModel, dataset: Dataset | None = None) -> bytes:
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})
    f = _Fmt(wb)
    m = model.metrics or {}
    ops = m.get("operations", {})

    ws = wb.add_worksheet("Summary")
    ws.set_column(0, 0, 22)
    ws.set_column(1, 12, 15)
    ws.write(0, 0, f"Model evaluation report #{model.id}", f.title)
    ds = m.get("dataset", {})
    ws.write(
        1,
        0,
        f"Dataset v{ds.get('version')} (hash {str(ds.get('hash', ''))[:12]}), "
        f"{ds.get('wells_train')} training wells, {ds.get('wells_blind')} blind test wells. "
        "Cross-validation grouped by well (GroupKFold 5). RMSE in SI (kN, kN·m).",
    )
    ws.write(
        2,
        0,
        f"Mean RMSE ML / RMSE WellPlan ratio: {m.get('skill') or 0:.3f} "
        f"(< 1 = ML is better). {(model.comparison or {}).get('decision', '')}",
    )
    hdr = [
        "Operation",
        "Selected model",
        "Wells",
        "RMSE T&D Model",
        "RMSE ML",
        "RMSE improvement",
        "ML closer (points)",
        "MAPE T&D Model (%)",
        "MAPE ML (%)",
        "R² T&D Model",
        "R² ML",
        "Blind RMSE WP",
        "Blind RMSE ML",
    ]
    for j, h in enumerate(hdr):
        ws.write(4, j, h, f.head)
    blind = (model.blind_result or {}).get("operations", {})
    for i, (op, d) in enumerate(ops.items(), start=5):
        wp, ml = d["overall"]["wellplan"], d["overall"]["ml"]
        imp = (wp["rmse"] - ml["rmse"]) / wp["rmse"] if wp["rmse"] else None
        b = blind.get(op, {})
        _write_row(
            ws,
            i,
            [
                OP_LABELS.get(op, op),
                d.get("chosen_label", d["chosen"]),
                d["overall"]["n_wells"],
                wp["rmse"],
                ml["rmse"],
                imp,
                d["overall"].get("ml_better_frac"),
                wp["mape"],
                ml["mape"],
                wp["r2"],
                ml["r2"],
                (b.get("wellplan") or {}).get("rmse"),
                (b.get("ml") or {}).get("rmse"),
            ],
            numfmt=f.num3,
        )
        ws.write(i, 5, imp if imp is not None else "", f.pct)
        ws.write(i, 6, d["overall"].get("ml_better_frac") or "", f.pct)
    r = 6 + len(ops)
    ws.write(r, 0, "Dataset notes", f.bold)
    for j, n in enumerate(m.get("notes", [])[:200]):
        ws.write(r + 1 + j, 0, n)

    ws = wb.add_worksheet("Feature tests")
    for j, h in enumerate(["Feature group", "Score (RMSE ML/WP)", "Used", "Note"]):
        ws.write(0, j, h, f.head)
    for i, row in enumerate(m.get("feature_selection", []), start=1):
        _write_row(
            ws,
            i,
            [row["group"], row["score"], bool(row["used"]), row["note"]],
            numfmt=f.num3,
        )
    ws.set_column(0, 3, 22)

    ws = wb.add_worksheet("Candidates")
    for j, h in enumerate(["Operation", "Candidate", "RMSE", "MAPE (%)", "R²", "Selected"]):
        ws.write(0, j, h, f.head)
    i = 1
    for op, d in ops.items():
        for name, s in d["candidates"].items():
            _write_row(
                ws,
                i,
                [OP_LABELS.get(op, op), name, s["rmse"], s["mape"], s["r2"], name == d["chosen"]],
                numfmt=f.num3,
            )
            i += 1
    ws.set_column(0, 5, 20)

    ws = wb.add_worksheet("Combination strategy")
    for j, h in enumerate(
        [
            "Operation",
            "Section|Type",
            "Wells",
            "RMSE single model",
            "RMSE combination model",
            "Used",
        ]
    ):
        ws.write(0, j, h, f.head)
    i = 1
    for op, d in ops.items():
        for s in d.get("strategy", []):
            _write_row(
                ws,
                i,
                [
                    OP_LABELS.get(op, op),
                    s["combo"],
                    s["n_wells"],
                    s["rmse_single"],
                    s.get("rmse_combo"),
                    s["used"],
                ],
                numfmt=f.num3,
            )
            i += 1
    ws.set_column(0, 5, 20)

    for key, title, _cols in (
        ("by_section", "By section", ["section"]),
        ("by_type", "By well type", ["well_type"]),
        ("by_section_type", "Section x type", ["section", "well_type"]),
    ):
        ws = wb.add_worksheet(title)
        hdr = [
            "Operation",
            "Section",
            "Type",
            "Wells",
            "Points",
            "RMSE T&D Model",
            "RMSE ML",
            "MAPE T&D Model (%)",
            "MAPE ML (%)",
            "R² T&D Model",
            "R² ML",
            "ML closer",
            "Warning",
        ]
        for j, h in enumerate(hdr):
            ws.write(0, j, h, f.head)
        i = 1
        for op, d in ops.items():
            for g in d[key]:
                wp, ml = g["wellplan"], g["ml"]
                _write_row(
                    ws,
                    i,
                    [
                        OP_LABELS.get(op, op),
                        g.get("section", ""),
                        g.get("well_type", ""),
                        g["n_wells"],
                        ml["n"],
                        wp["rmse"],
                        ml["rmse"],
                        wp["mape"],
                        ml["mape"],
                        wp["r2"],
                        ml["r2"],
                        g.get("ml_better_frac"),
                        "limited data" if g["warning"] else "",
                    ],
                    f.warn if g["warning"] else None,
                    f.num3,
                )
                i += 1
        ws.set_column(0, 12, 14)

    ws = wb.add_worksheet("By depth")
    for j, h in enumerate(
        ["Operation", "From (m)", "To (m)", "Points", "RMSE T&D Model", "RMSE ML", "ML closer"]
    ):
        ws.write(0, j, h, f.head)
    i = 1
    for op, d in ops.items():
        for g in d.get("by_depth", []):
            _write_row(
                ws,
                i,
                [
                    OP_LABELS.get(op, op),
                    g["depth_from_m"],
                    g["depth_to_m"],
                    g["ml"]["n"],
                    g["wellplan"]["rmse"],
                    g["ml"]["rmse"],
                    g["ml_better_frac"],
                ],
                numfmt=f.num3,
            )
            i += 1
    ws.set_column(0, 6, 15)

    ws = wb.add_worksheet("By well")
    for j, h in enumerate(
        [
            "Operation",
            "Well",
            "Section",
            "Type",
            "Points",
            "RMSE T&D Model",
            "RMSE ML",
            "MAPE T&D Model (%)",
            "MAPE ML (%)",
        ]
    ):
        ws.write(0, j, h, f.head)
    i = 1
    for op, d in ops.items():
        for g in d["per_well"]:
            wp, ml = g["wellplan"], g["ml"]
            worse = ml["rmse"] is not None and wp["rmse"] is not None and ml["rmse"] > wp["rmse"]
            _write_row(
                ws,
                i,
                [
                    OP_LABELS.get(op, op),
                    g["well_name"],
                    g["section"],
                    g["well_type"],
                    ml["n"],
                    wp["rmse"],
                    ml["rmse"],
                    wp["mape"],
                    ml["mape"],
                ],
                f.warn if worse else None,
                f.num3,
            )
            i += 1
    ws.set_column(0, 0, 18)
    ws.set_column(1, 1, 34)
    ws.set_column(2, 8, 13)

    ws = wb.add_worksheet("Worst points")
    for j, h in enumerate(
        ["Operation", "Well", "Section", "Depth (m)", "Actual", "WellPlan", "ML"]
    ):
        ws.write(0, j, h, f.head)
    i = 1
    for op, d in ops.items():
        for p in d.get("worst_points", []):
            _write_row(
                ws,
                i,
                [
                    OP_LABELS.get(op, op),
                    p["well_name"],
                    p["section"],
                    p["depth_m"],
                    p["actual"],
                    p["wellplan"],
                    p["ml"],
                ],
                numfmt=f.num,
            )
            i += 1
    ws.set_column(0, 6, 16)

    ws = wb.add_worksheet("Learning curve")
    for j, h in enumerate(["Operation", "Training wells", "RMSE ML", "RMSE T&D Model"]):
        ws.write(0, j, h, f.head)
    i = 1
    for op, d in ops.items():
        for p in d.get("learning_curve", []):
            _write_row(
                ws,
                i,
                [OP_LABELS.get(op, op), p["label"], p["rmse_ml"], p["rmse_wp"]],
                numfmt=f.num3,
            )
            i += 1
    ws.set_column(0, 3, 18)

    ws = wb.add_worksheet("Feature importance")
    for j, h in enumerate(["Operation", "Method", "Feature", "Importance", "Direction", "Note"]):
        ws.write(0, j, h, f.head)
    i = 1
    for op, d in ops.items():
        ex = d.get("explain", {})
        for p in ex.get("features", [])[:12]:
            _write_row(
                ws,
                i,
                [
                    OP_LABELS.get(op, op),
                    ex.get("method", ""),
                    p["feature"],
                    p["importance"],
                    "+" if p["direction"] > 0.1 else ("-" if p["direction"] < -0.1 else ""),
                    ex.get("note", ""),
                ],
                numfmt=f.num3,
            )
            i += 1
    ws.set_column(0, 4, 18)
    ws.set_column(5, 5, 80)

    if model.blind_result:
        ws = wb.add_worksheet("Blind test")
        ws.write(
            0,
            0,
            f"Blind test run once: {model.blind_result.get('run_at', '')[:19]}. "
            f"Wells: {', '.join(model.blind_result.get('wells', []))}",
        )
        for j, h in enumerate(
            ["Operation", "Well", "Section", "Points", "RMSE T&D Model", "RMSE ML"]
        ):
            ws.write(2, j, h, f.head)
        i = 3
        for op, d in blind.items():
            _write_row(
                ws,
                i,
                [
                    OP_LABELS.get(op, op),
                    "ALL",
                    "",
                    d["ml"]["n"],
                    d["wellplan"]["rmse"],
                    d["ml"]["rmse"],
                ],
                f.bold,
                f.num3,
            )
            i += 1
            for g in d["per_well"]:
                _write_row(
                    ws,
                    i,
                    [
                        OP_LABELS.get(op, op),
                        g["well_name"],
                        g["section"],
                        g["ml"]["n"],
                        g["wellplan"]["rmse"],
                        g["ml"]["rmse"],
                    ],
                    numfmt=f.num3,
                )
                i += 1
        ws.set_column(0, 5, 20)

    if dataset is not None:
        ws = wb.add_worksheet("Dataset")
        ws.write(
            0, 0, f"Dataset v{dataset.version}, hash {dataset.content_hash}, {dataset.n_rows} rows"
        )
        for j, h in enumerate(["Well", "Section", "Type", "Blind test", "Rows", "File SHA-256"]):
            ws.write(2, j, h, f.head)
        for i, w in enumerate(dataset.wells, start=3):
            _write_row(
                ws,
                i,
                [
                    w["name"],
                    w["section"],
                    w["type"],
                    bool(w["blind"]),
                    w["rows"],
                    w.get("file_sha256") or "",
                ],
            )
        r = len(dataset.wells) + 4
        ws.write(r, 0, "Excluded (data quality C / excluded)", f.bold)
        for i, w in enumerate(dataset.excluded, start=r + 1):
            _write_row(ws, i, [w["name"], w["section"], w["status"]])
        ws.set_column(0, 0, 34)
        ws.set_column(1, 5, 14)
    wb.close()
    return buf.getvalue()
