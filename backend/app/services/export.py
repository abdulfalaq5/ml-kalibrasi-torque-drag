"""Ekspor Excel (.xlsx) dengan XlsxWriter: perbandingan, prediksi ML, dan grafik.

Grafik di Excel sama dengan dashboard: Hookload, Torque, Selisih (sumbu kedalaman
terbalik). File tidak berisi macro.
"""

import io
import math

import xlsxwriter
from sqlalchemy.orm import Session

from app.db.models import MLModel, Well
from app.services.operations import HOOKLOAD_OPS, OP_LABELS, OPERATIONS, TORQUE_OPS
from app.services.profile import well_profile

# warna sama dengan dashboard (web/src/components/chartTheme.ts)
COLORS = {"wellplan": "#2a78d6", "ml": "#eb6834", "actual": "#1baf7a"}
DIFF_COLORS = {"wp_minus_actual": "#2a78d6", "ml_minus_actual": "#eb6834", "ml_minus_wp": "#4a3aa7"}
DIFF_LABELS = {
    "wp_minus_actual": "WellPlan - Aktual",
    "ml_minus_actual": "ML - Aktual",
    "ml_minus_wp": "ML - WellPlan",
}
DASH = {
    "pick_up": "solid",
    "slack_off": "dash",
    "rotating_weight": "round_dot",
    "torque_off_bottom": "solid",
    "torque_on_bottom": "dash",
}


def export_well(
    db: Session, well: Well, unit_system: str = "imperial", diff_target: str = "pick_up"
) -> bytes:
    prof = well_profile(db, well, unit_system)
    du = prof["depth_unit"]
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True, "nan_inf_to_errors": True})
    bold = wb.add_format({"bold": True})
    head = wb.add_format(
        {"bold": True, "bg_color": "#eaeef2", "border": 1, "text_wrap": True, "valign": "top"}
    )
    num = wb.add_format({"num_format": "0.00"})

    # ---------- Info
    ws = wb.add_worksheet("Info")
    ws.set_column(0, 0, 28)
    ws.set_column(1, 1, 70)
    info = [
        ("Sumur", well.name),
        ("Section (in)", well.section_in),
        ("Tipe sumur", well.well_type),
        ("Sistem satuan", unit_system),
        (
            "Prediksi",
            "-"
            if prof["prediction"] is None
            else f"model #{prof['prediction']['model_id']} ({'out-of-fold' if prof['prediction']['kind'] == 'oof' else 'model penuh'})",
        ),
        ("Konvensi selisih", prof["sign_convention"]),
    ]
    model = db.get(MLModel, prof["prediction"]["model_id"]) if prof["prediction"] else None
    if model is not None:
        info.append(
            (
                "Model per operasi",
                ", ".join(f"{k}: {v}" for k, v in (model.params or {}).get("chosen", {}).items()),
            )
        )
    for i, (k, v) in enumerate(info):
        ws.write(i, 0, k, bold)
        ws.write(i, 1, v)
    r = len(info) + 1
    ws.write(r, 0, "Peringatan", bold)
    for j, w in enumerate(prof["warnings"] or ["-"]):
        ws.write(r + j, 1, w)

    # ---------- Perbandingan (di kedalaman titik aktual)
    ws = wb.add_worksheet("Perbandingan")
    ws.freeze_panes(1, 0)
    col = 0
    for op in OPERATIONS:
        o = prof["operations"][op]
        u = o["unit"]
        act = dict(zip(o["actual"]["depth"], o["actual"]["value"], strict=True))
        d_wa = o["diff"]["wp_minus_actual"]
        d_ma = o["diff"]["ml_minus_actual"]
        wa = dict(zip(d_wa["depth"], zip(d_wa["abs"], d_wa["pct"], strict=True), strict=True))
        ma = dict(zip(d_ma["depth"], zip(d_ma["abs"], d_ma["pct"], strict=True), strict=True))
        headers = [
            f"{OP_LABELS[op]}\nKedalaman ({du})",
            f"Aktual ({u})",
            f"WellPlan ({u})",
            f"ML ({u})",
            f"WellPlan - Aktual ({u})",
            "WellPlan - Aktual (%)",
            f"ML - Aktual ({u})",
            "ML - Aktual (%)",
        ]
        for j, h in enumerate(headers):
            ws.write(0, col + j, h, head)
        for i, d in enumerate(sorted(act)):
            a = act[d]
            wav = wa.get(d, (None, None))
            mav = ma.get(d, (None, None))
            wp = None if wav[0] is None else a + wav[0]
            ml = None if mav[0] is None else a + mav[0]
            for j, v in enumerate([d, a, wp, ml, wav[0], wav[1], mav[0], mav[1]]):
                if v is None:
                    ws.write_blank(i + 1, col + j, None)
                else:
                    ws.write_number(i + 1, col + j, v, num)
        ws.set_column(col, col + 7, 13)
        col += 9
    ws.set_row(0, 45)

    # ---------- Prediksi ML (grid WellPlan)
    ws = wb.add_worksheet("Prediksi ML")
    ws.freeze_panes(1, 0)
    pred_ranges = {}
    col = 0
    for op in OPERATIONS:
        o = prof["operations"][op]
        u = o["unit"]
        mlw = o["diff"]["ml_minus_wp"]
        ml_map = dict(zip(o["ml"]["depth"], o["ml"]["value"], strict=True))
        diff_map = dict(zip(mlw["depth"], zip(mlw["abs"], mlw["pct"], strict=True), strict=True))
        base = _baseline_series(o)
        depths = sorted(set(ml_map) | set(base))
        headers = [
            f"{OP_LABELS[op]}\nKedalaman ({du})",
            f"WellPlan FF baseline ({u})",
            f"ML ({u})",
            f"ML - WellPlan ({u})",
            "ML - WellPlan (%)",
        ]
        for j, h in enumerate(headers):
            ws.write(0, col + j, h, head)
        for i, d in enumerate(depths):
            vals = [d, base.get(d), ml_map.get(d), *diff_map.get(d, (None, None))]
            for j, v in enumerate(vals):
                if v is None:
                    ws.write_blank(i + 1, col + j, None)
                else:
                    ws.write_number(i + 1, col + j, v, num)
        pred_ranges[op] = (col, len(depths))
        ws.set_column(col, col + 4, 14)
        col += 6
    ws.set_row(0, 45)

    # Sheet data actual untuk grafik (titik)
    ws_act = wb.add_worksheet("Data Aktual")
    col = 0
    act_ranges = {}
    for op in OPERATIONS:
        o = prof["operations"][op]
        ws_act.write(0, col, f"{OP_LABELS[op]} kedalaman ({du})", head)
        ws_act.write(0, col + 1, f"Aktual ({o['unit']})", head)
        for i, (d, v) in enumerate(zip(o["actual"]["depth"], o["actual"]["value"], strict=True)):
            ws_act.write_number(i + 1, col, d)
            ws_act.write_number(i + 1, col + 1, v)
        act_ranges[op] = (col, len(o["actual"]["depth"]))
        col += 3

    # Sheet selisih untuk grafik
    ws_diff = wb.add_worksheet("Selisih")
    o = prof["operations"][diff_target]
    diff_ranges = {}
    col = 0
    for key, label in DIFF_LABELS.items():
        dd = o["diff"][key]
        ws_diff.write(0, col, f"{label} kedalaman ({du})", head)
        ws_diff.write(0, col + 1, f"{label} ({o['unit']})", head)
        ws_diff.write(0, col + 2, f"{label} (%)", head)
        for i, (d, a, p) in enumerate(zip(dd["depth"], dd["abs"], dd["pct"], strict=True)):
            ws_diff.write_number(i + 1, col, d)
            ws_diff.write_number(i + 1, col + 1, a)
            ws_diff.write_number(i + 1, col + 2, p)
        diff_ranges[key] = (col, len(dd["depth"]))
        col += 4
    # garis nol eksplisit (dua titik) untuk grafik Selisih
    all_d = [d for k in DIFF_LABELS for d in o["diff"][k]["depth"]]
    max_abs = max((abs(v) for k in DIFF_LABELS for v in o["diff"][k]["abs"]), default=1.0) or 1.0
    ws_diff.write(0, col, "Garis nol", head)
    if all_d:
        ws_diff.write_row(1, col, [0, min(all_d)])
        ws_diff.write_row(2, col, [0, max(all_d)])
    zero_col = col
    ws_diff.set_column(0, col + 1, 16)

    # ---------- Grafik
    wsg = wb.add_worksheet("Grafik")
    wsg.set_landscape()
    wsg.fit_to_pages(1, 1)
    wsg.write(
        0,
        0,
        f"{well.name} — WellPlan (biru), ML (oranye), Aktual (hijau, titik). "
        f"{prof['sign_convention']}",
        bold,
    )
    charts = [
        ("Hookload", HOOKLOAD_OPS, prof["operations"][HOOKLOAD_OPS[0]]["unit"]),
        ("Torque", TORQUE_OPS, prof["operations"][TORQUE_OPS[0]]["unit"]),
    ]
    for k, (title, ops, unit) in enumerate(charts):
        ch = wb.add_chart({"type": "scatter", "subtype": "straight"})
        for op in ops:
            c0, n = pred_ranges[op]
            if n:
                for series_col, name, color in (
                    (c0 + 1, "WellPlan", COLORS["wellplan"]),
                    (c0 + 2, "ML", COLORS["ml"]),
                ):
                    ch.add_series(
                        {
                            "name": f"{name} {OP_LABELS[op]}",
                            "categories": ["Prediksi ML", 1, series_col, n, series_col],
                            "values": ["Prediksi ML", 1, c0, n, c0],
                            "line": {"color": color, "width": 1.5, "dash_type": DASH[op]},
                            "marker": {"type": "none"},
                        }
                    )
            a0, an = act_ranges[op]
            if an:
                ch.add_series(
                    {
                        "name": f"Aktual {OP_LABELS[op]}",
                        "categories": ["Data Aktual", 1, a0 + 1, an, a0 + 1],
                        "values": ["Data Aktual", 1, a0, an, a0],
                        "line": {"none": True},
                        "marker": {
                            "type": "circle",
                            "size": 4,
                            "fill": {"color": COLORS["actual"]},
                            "border": {"color": COLORS["actual"]},
                        },
                    }
                )
        _style_depth_chart(ch, title, f"{title} ({unit})", du)
        wsg.insert_chart(2, k * 9, ch, {"x_scale": 1.1, "y_scale": 2.0})

    ch = wb.add_chart({"type": "scatter"})
    for key, label in DIFF_LABELS.items():
        c0, n = diff_ranges[key]
        if not n:
            continue
        line = key == "ml_minus_wp"
        ch.add_series(
            {
                "name": label,
                "categories": ["Selisih", 1, c0 + 1, n, c0 + 1],
                "values": ["Selisih", 1, c0, n, c0],
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
                "name": "Nol",
                "categories": ["Selisih", 1, zero_col, 2, zero_col],
                "values": ["Selisih", 1, zero_col + 1, 2, zero_col + 1],
                "line": {"color": "#000000", "width": 1.75},
                "marker": {"type": "none"},
            }
        )
    x_title = f"<- lebih rendah (-)   Selisih ({o['unit']})   lebih tinggi (+) ->"
    _style_depth_chart(ch, f"Selisih {OP_LABELS[diff_target]} (kanan = lebih tinggi)", x_title, du)
    # rentang simetris di sekitar nol; sumbu kedalaman di tepi kiri agar tidak menutupi data
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
    wsg.insert_chart(2, 18, ch, {"x_scale": 1.1, "y_scale": 2.0})

    # ---------- Metrik
    ws = wb.add_worksheet("Metrik")
    hdr = [
        "Operasi",
        "Satuan",
        "RMSE WellPlan",
        "MAPE WellPlan (%)",
        "R² WellPlan",
        "RMSE ML",
        "MAPE ML (%)",
        "R² ML",
        "Titik",
    ]
    for j, h in enumerate(hdr):
        ws.write(0, j, h, head)
    for i, op in enumerate(OPERATIONS):
        o = prof["operations"][op]
        m = o["metrics"] or {}
        wp, ml = m.get("wellplan") or {}, m.get("ml") or {}
        row = [
            OP_LABELS[op],
            o["unit"],
            wp.get("rmse"),
            wp.get("mape"),
            wp.get("r2"),
            ml.get("rmse"),
            ml.get("mape"),
            ml.get("r2"),
            (ml or wp).get("n"),
        ]
        for j, v in enumerate(row):
            if v is None:
                ws.write_blank(i + 1, j, None)
            elif isinstance(v, str):
                ws.write_string(i + 1, j, v)
            else:
                ws.write_number(i + 1, j, v, num)
    ws.set_column(0, 8, 16)

    wb.close()
    return buf.getvalue()


def _baseline_series(o: dict) -> dict[float, float]:
    ff = o["wellplan_baseline_ff"]
    for s in o["wellplan"]:
        if s["ff"] == ff:
            return dict(zip(s["depth"], s["value"], strict=True))
    if o["wellplan"]:
        s = o["wellplan"][0]
        return dict(zip(s["depth"], s["value"], strict=True))
    return {}


def _nice_step(raw: float) -> float:
    """Langkah tick 1/2/5 x 10^n."""
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


def export_model_report(model: MLModel) -> bytes:
    """Laporan evaluasi model untuk client."""
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})
    head = wb.add_format({"bold": True, "bg_color": "#eaeef2", "border": 1, "text_wrap": True})
    warnf = wb.add_format({"bg_color": "#fff8c5"})
    num = wb.add_format({"num_format": "0.000"})
    m = model.metrics or {}

    ws = wb.add_worksheet("Ringkasan")
    ws.set_column(0, 0, 22)
    ws.set_column(1, 12, 14)
    hdr = [
        "Operasi",
        "Model terpilih",
        "Sumur",
        "RMSE WellPlan",
        "RMSE ML",
        "Perbaikan RMSE (%)",
        "MAPE WellPlan (%)",
        "MAPE ML (%)",
        "R² WellPlan",
        "R² ML",
    ]
    for j, h in enumerate(hdr):
        ws.write(0, j, h, head)
    for i, (op, d) in enumerate(m.get("operations", {}).items(), start=1):
        wp, ml = d["overall"]["wellplan"], d["overall"]["ml"]
        imp = None
        if wp["rmse"] and ml["rmse"] is not None:
            imp = (wp["rmse"] - ml["rmse"]) / wp["rmse"] * 100
        row = [
            OP_LABELS.get(op, op),
            d["chosen"],
            d["overall"]["n_wells"],
            wp["rmse"],
            ml["rmse"],
            imp,
            wp["mape"],
            ml["mape"],
            wp["r2"],
            ml["r2"],
        ]
        _write_row(ws, i, row, num)
    r = len(m.get("operations", {})) + 3
    ws.write(r, 0, "Catatan", head)
    ws.write(r + 1, 0, "Satuan RMSE: kN (hookload), kN·m (torsi). Validasi leave-one-well-out.")
    for j, note in enumerate(m.get("notes", [])):
        ws.write(r + 2 + j, 0, note)

    for key, title in (
        ("by_section", "Per section"),
        ("by_type", "Per tipe"),
        ("by_section_type", "Section x tipe"),
    ):
        ws = wb.add_worksheet(title)
        hdr = [
            "Operasi",
            "Section",
            "Tipe",
            "Sumur",
            "Titik",
            "RMSE WellPlan",
            "RMSE ML",
            "MAPE WellPlan (%)",
            "MAPE ML (%)",
            "R² WellPlan",
            "R² ML",
            "Peringatan",
        ]
        for j, h in enumerate(hdr):
            ws.write(0, j, h, head)
        ws.set_column(0, 11, 14)
        i = 1
        for op, d in m.get("operations", {}).items():
            for g in d[key]:
                wp, ml = g["wellplan"], g["ml"]
                row = [
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
                    "data sedikit" if g["warning"] else "",
                ]
                _write_row(ws, i, row, num, warnf if g["warning"] else None)
                i += 1

    ws = wb.add_worksheet("Per sumur")
    hdr = [
        "Operasi",
        "Sumur",
        "Section",
        "Tipe",
        "Titik",
        "RMSE WellPlan",
        "RMSE ML",
        "MAPE WellPlan (%)",
        "MAPE ML (%)",
    ]
    for j, h in enumerate(hdr):
        ws.write(0, j, h, head)
    ws.set_column(0, 8, 14)
    i = 1
    for op, d in m.get("operations", {}).items():
        for g in d["per_well"]:
            wp, ml = g["wellplan"], g["ml"]
            worse = ml["rmse"] is not None and wp["rmse"] is not None and ml["rmse"] > wp["rmse"]
            row = [
                OP_LABELS.get(op, op),
                g["well_name"],
                g["section"],
                g["well_type"],
                ml["n"],
                wp["rmse"],
                ml["rmse"],
                wp["mape"],
                ml["mape"],
            ]
            _write_row(ws, i, row, num, warnf if worse else None)
            i += 1

    ws = wb.add_worksheet("Kandidat")
    hdr = ["Operasi", "Kandidat", "RMSE", "MAPE (%)", "R²", "Dipilih"]
    for j, h in enumerate(hdr):
        ws.write(0, j, h, head)
    ws.set_column(0, 5, 18)
    i = 1
    for op, d in m.get("operations", {}).items():
        for name, s in d["candidates"].items():
            _write_row(
                ws,
                i,
                [
                    OP_LABELS.get(op, op),
                    name,
                    s["rmse"],
                    s["mape"],
                    s["r2"],
                    "ya" if name == d["chosen"] else "",
                ],
                num,
            )
            i += 1
    wb.close()
    return buf.getvalue()


def _write_row(ws, r: int, values: list, num, fmt=None) -> None:
    for j, v in enumerate(values):
        if v is None:
            ws.write_blank(r, j, None, fmt)
        elif isinstance(v, str):
            ws.write_string(r, j, v, fmt)
        else:
            ws.write_number(r, j, v, fmt or num)
