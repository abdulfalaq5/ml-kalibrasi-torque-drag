"""Ekspor Excel (.xlsx, XlsxWriter, tanpa macro).

export_well         : per sumur, struktur sheet mengikuti file contoh client
                      (Drag, Torque, T&D Actual Reading) + kolom prediksi ML, kolom selisih,
                      pita ketidakpastian, tiga grafik (Hookload, Torque, Selisih), batas aman.
export_quality_report : laporan kualitas data semua sumur (status A/B/C, skor, alasan, tinjauan).
export_model_report : laporan evaluasi model (validasi silang, blind test, kurva belajar, SHAP).
"""

import io
import math

import numpy as np
import xlsxwriter
from sqlalchemy.orm import Session

from app.db.models import Dataset, MLModel, Well
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
WP_LABEL = {
    "pick_up": "Tripping Out",
    "slack_off": "Tripping In",
    "rotating_weight": "Rotating Off Bottom",
    "torque_on_bottom": "Rotating On Bottom",
    "torque_off_bottom": "Rotating Off Bottom",
}
STATUS_LABEL = {"A": "Layak", "B": "Layak dengan peringatan", "C": "Ditahan", "X": "Dikecualikan"}


class _Fmt:
    def __init__(self, wb):
        self.bold = wb.add_format({"bold": True})
        self.title = wb.add_format({"bold": True, "font_size": 13})
        self.head = wb.add_format(
            {"bold": True, "bg_color": "#eaeef2", "border": 1, "text_wrap": True, "valign": "top"}
        )
        self.num = wb.add_format({"num_format": "0.00"})
        self.num3 = wb.add_format({"num_format": "0.000"})
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
            ws.write_string(r, j, "ya" if v else "", fmt)
        else:
            ws.write_number(r, j, float(v), fmt or numfmt)


def _interp(depth, value, grid):
    if len(depth) < 2:
        return [None] * len(grid)
    d, v = np.asarray(depth, float), np.asarray(value, float)
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


# ---------------------------------------------------------------- per sumur


def export_well(
    db: Session,
    well: Well,
    unit_system: str = "imperial",
    diff_target: str = "pick_up",
    model: MLModel | None = None,
) -> bytes:
    prof = well_profile(db, well, unit_system, model)
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
        ("Sumur", well.name),
        ("Section (in)", well.section_in),
        ("Tipe sumur", well.well_type),
        ("Format file rencana", (well.meta or {}).get("plan_format")),
        (
            "Status kualitas data",
            f"{q['status']} - {STATUS_LABEL.get(q['status'], '')} (skor {q['score']})",
        ),
        ("Model", "-" if not m else f"#{m['id']} (dataset v{m.get('dataset_version')})"),
        (
            "Prediksi",
            "-"
            if prof["prediction"] is None
            else (
                "out-of-fold (model tidak pernah melihat sumur ini)"
                if prof["prediction"]["kind"] == "oof"
                else "model penuh"
            ),
        ),
        ("Sistem satuan", unit_system),
        ("Konvensi selisih", prof["sign_convention"]),
        ("Pita ketidakpastian", "kuantil 10%-90% residu validasi silang (ML lo / ML hi)"),
    ]
    ws.write(0, 0, "Kalibrasi Torque & Drag ML - hasil per sumur", f.title)
    for i, (k, v) in enumerate(info, start=2):
        ws.write(i, 0, k, f.bold)
        ws.write(i, 1, "" if v is None else v)
    r = len(info) + 3
    ws.write(r, 0, "Peringatan", f.bold)
    for j, w in enumerate(prof["warnings"] or ["-"]):
        ws.write(r + j, 1, w)
    r += max(len(prof["warnings"]), 1) + 1
    ws.write(r, 0, "Catatan kualitas data", f.bold)
    for j, c in enumerate(q["issues"] or [{"message": "-"}]):
        ws.write(r + j, 1, c["message"])

    # ---------- Drag / Torque (grid prediksi, struktur seperti file roadmap)
    chart_ranges: dict[str, dict] = {}
    for sheet, group in (("Drag", HOOKLOAD_OPS), ("Torque", TORQUE_OPS)):
        ws = wb.add_worksheet(sheet)
        ws.write(0, 0, "WellPlan Result + Prediksi ML", f.title)
        grid = sorted(
            {d for op in group for d in ops[op]["ml"]["depth"]}
            | {d for op in group for s in ops[op]["wellplan"] for d in s["depth"]}
        )
        cols = [f"Run Measured Depth ({du})"]
        series = []
        for op in group:
            o = ops[op]
            for s in o["wellplan"]:
                lab = f"WellPlan {WP_LABEL[op]}" + (
                    f" FF {s['ff']:.2f}" if s["ff"] is not None else ""
                )
                cols.append(f"{lab} ({o['unit']})")
                series.append(("wp", op, s["ff"], _interp(s["depth"], s["value"], grid)))
        for op in group:
            o = ops[op]
            cols += [
                f"ML {OP_LABELS[op]} ({o['unit']})",
                f"ML {OP_LABELS[op]} lo",
                f"ML {OP_LABELS[op]} hi",
                f"ML - WellPlan {OP_LABELS[op]} ({o['unit']})",
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
            dd = _interp(d["depth"], d["abs"], grid)
            series += [
                ("ml", op, None, ml),
                ("lo", op, None, lo),
                ("hi", op, None, hi),
                ("diff", op, None, dd),
            ]
        for j, h in enumerate(cols):
            ws.write(2, j, h, f.head)
        for i, dep in enumerate(grid):
            _write_row(ws, i + 3, [dep] + [s[3][i] for s in series], numfmt=f.num)
        ws.set_row(2, 60)
        ws.set_column(0, len(cols), 14)
        ws.freeze_panes(3, 1)
        base_ff = {op: ops[op]["wellplan_baseline_ff"] for op in group}
        chart_ranges[sheet] = {"n": len(grid), "cols": {}}
        for j, s in enumerate(series, start=1):
            kind, op, ff, _ = s
            if kind == "wp" and (ff == base_ff[op] or ff is None):
                chart_ranges[sheet]["cols"][("wp", op)] = j
            elif kind == "ml":
                chart_ranges[sheet]["cols"][("ml", op)] = j

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
        a = _nearest(o["actual"]["depth"], o["actual"]["value"], act_grid, tol)
        ml = _interp(o["ml"]["depth"], o["ml"]["value"], act_grid)
        base = next(
            (s for s in o["wellplan"] if s["ff"] == o["wellplan_baseline_ff"]),
            o["wellplan"][0] if o["wellplan"] else None,
        )
        wp = _interp(base["depth"], base["value"], act_grid) if base else [None] * len(act_grid)
        cols += [
            f"Aktual {OP_LABELS[op]} ({o['unit']})",
            f"WellPlan {OP_LABELS[op]}",
            f"ML {OP_LABELS[op]}",
            f"WellPlan - Aktual {OP_LABELS[op]}",
            f"ML - Aktual {OP_LABELS[op]}",
        ]
        rows_cols += [
            a,
            wp,
            ml,
            [None if x is None or y is None else x - y for x, y in zip(wp, a, strict=True)],
            [None if x is None or y is None else x - y for x, y in zip(ml, a, strict=True)],
        ]
    for j, h in enumerate(cols):
        ws.write(3, j, h, f.head)
    for i, dep in enumerate(act_grid):
        _write_row(ws, i + 4, [dep] + [c[i] for c in rows_cols], numfmt=f.num)
    ws.set_row(3, 45)
    ws.set_column(0, len(cols), 13)
    ws.freeze_panes(4, 1)
    act_cols = {op: 1 + k * 5 for k, op in enumerate(OPERATIONS)}

    # ---------- Selisih (target terpilih)
    wsd = wb.add_worksheet("Selisih")
    o = ops[diff_target]
    diff_ranges, col = {}, 0
    for key, label in DIFF_LABELS.items():
        dd = o["diff"][key]
        wsd.write(0, col, f"{label} kedalaman ({du})", f.head)
        wsd.write(0, col + 1, f"{label} ({o['unit']})", f.head)
        wsd.write(0, col + 2, f"{label} (%)", f.head)
        for i, (d, a, p) in enumerate(zip(dd["depth"], dd["abs"], dd["pct"], strict=True)):
            _write_row(wsd, i + 1, [d, a, p])
        diff_ranges[key] = (col, len(dd["depth"]))
        col += 4
    all_d = [d for k in DIFF_LABELS for d in o["diff"][k]["depth"]]
    max_abs = max((abs(v) for k in DIFF_LABELS for v in o["diff"][k]["abs"]), default=1.0) or 1.0
    wsd.write(0, col, "Garis nol", f.head)
    if all_d:
        wsd.write_row(1, col, [0, min(all_d)])
        wsd.write_row(2, col, [0, max(all_d)])
    zero_col = col
    wsd.set_column(0, col + 1, 16)

    # ---------- Grafik
    wsg = wb.add_worksheet("Grafik")
    wsg.set_landscape()
    wsg.fit_to_pages(1, 1)
    wsg.write(
        0,
        0,
        f"{well.name} {well.section_in:g}\" - WellPlan (biru), ML (oranye), Aktual (hijau). "
        f"{prof['sign_convention']}",
        f.bold,
    )
    for k, (sheet, group) in enumerate((("Drag", HOOKLOAD_OPS), ("Torque", TORQUE_OPS))):
        ch = wb.add_chart({"type": "scatter", "subtype": "straight"})
        cr = chart_ranges[sheet]
        n = cr["n"]
        for op in group:
            for kind, color in (("wp", COLORS["wellplan"]), ("ml", COLORS["ml"])):
                c = cr["cols"].get((kind, op))
                if c is None or not n:
                    continue
                ch.add_series(
                    {
                        "name": f"{'WellPlan' if kind == 'wp' else 'ML'} {OP_LABELS[op]}",
                        "categories": [sheet, 3, c, n + 2, c],
                        "values": [sheet, 3, 0, n + 2, 0],
                        "line": {"color": color, "width": 1.5, "dash_type": DASH[op]},
                        "marker": {"type": "none"},
                    }
                )
            na = len(act_grid)
            if na:
                c = act_cols[op]
                ch.add_series(
                    {
                        "name": f"Aktual {OP_LABELS[op]}",
                        "categories": ["T&D Actual Reading", 4, c, na + 3, c],
                        "values": ["T&D Actual Reading", 4, 0, na + 3, 0],
                        "line": {"none": True},
                        "marker": {
                            "type": "circle",
                            "size": 4,
                            "fill": {"color": COLORS["actual"]},
                            "border": {"color": COLORS["actual"]},
                        },
                    }
                )
        title = "Hookload" if sheet == "Drag" else "Torque"
        _style_depth_chart(ch, title, f"{title} ({ops[group[0]]['unit']})", du)
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

    # ---------- Batas aman
    ws = wb.add_worksheet("Batas aman")
    hdr = [
        "Operasi",
        "Jenis",
        "Batas",
        "Satuan",
        "Berlaku untuk",
        "Kedalaman ML menyentuh batas",
        "Kedalaman ML (pita) menyentuh batas",
        "Kedalaman WellPlan menyentuh batas",
        "Margin minimum ML",
        "Catatan",
    ]
    for j, h in enumerate(hdr):
        ws.write(0, j, h, f.head)
    r = 1
    for op in OPERATIONS:
        for lim_ in ops[op]["limits"]:
            _write_row(
                ws,
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
            r += 1
    if r == 1:
        ws.write(1, 0, "Belum ada batas aman untuk sumur/section ini (atur di dashboard).")
    ws.set_column(0, 9, 18)

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
    ws.set_column(0, 8, 16)
    wb.close()
    return buf.getvalue()


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
    ws = wb.add_worksheet("Kualitas data")
    hdr = [
        "Sumur",
        "Section (in)",
        "Tipe",
        "Status",
        "Arti",
        "Status otomatis",
        "Skor",
        "Masuk training",
        "Alasan (kritis)",
        "Peringatan",
        "Titik aktual",
        "Rasio aktual/WellPlan pick up",
        "Keputusan tinjauan",
        "Alasan tinjauan",
        "Peninjau",
        "Tanggal tinjauan",
    ]
    for j, h in enumerate(hdr):
        ws.write(0, j, h, f.head)
    fm = {"A": f.ok, "B": f.warn, "C": f.bad, "X": f.bad}
    for i, r in enumerate(rows, start=1):
        crit = "; ".join(c["message"] for c in r["checks"] if c["level"] == "kritis")
        warn = "; ".join(c["message"] for c in r["checks"] if c["level"] == "peringatan")
        rev = r["reviews"][0] if r["reviews"] else {}
        ws.write(i, 0, r["well"])
        _write_row(
            ws,
            i,
            [
                r["well"],
                r["section_in"],
                r["well_type"] or "",
                r["status"],
                STATUS_LABEL.get(r["status"], ""),
                r["auto_status"] or "",
                r["score"],
                "ya" if r["status"] in ("A", "B") else "tidak",
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
        ws.write(i, 3, r["status"], fm.get(r["status"]))
    ws.set_column(0, 0, 34)
    ws.set_column(1, 7, 11)
    ws.set_column(8, 9, 60, f.wrap)
    ws.set_column(10, 15, 16)
    ws.autofilter(0, 0, len(rows), len(hdr) - 1)
    ws.freeze_panes(1, 1)

    ws = wb.add_worksheet("Ringkasan")
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    ws.write(0, 0, "Status", f.head)
    ws.write(0, 1, "Arti", f.head)
    ws.write(0, 2, "Jumlah sumur-section", f.head)
    for i, s in enumerate(("A", "B", "C", "X"), start=1):
        _write_row(ws, i, [s, STATUS_LABEL[s], counts.get(s, 0)])
    ws.write(6, 0, "Pemeriksaan", f.bold)
    ws.write(
        7,
        0,
        "Kritis (gagal -> C): format & kolom, satuan, kedalaman naik, nilai fisik, urutan "
        "SO <= ROT <= PU, tumpang rentang WellPlan-aktual, >= 8 titik aktual, section & tipe, "
        "bukan duplikat.",
    )
    ws.write(
        8,
        0,
        "Statistik (gagal -> peringatan B): rasio aktual/WellPlan vs sumur sekelas (MAD), "
        "lompatan antar titik, nilai berulang, titik jauh lebih sedikit, rasio torsi.",
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

    ws = wb.add_worksheet("Ringkasan")
    ws.set_column(0, 0, 22)
    ws.set_column(1, 12, 15)
    ws.write(0, 0, f"Laporan evaluasi model #{model.id}", f.title)
    ds = m.get("dataset", {})
    ws.write(
        1,
        0,
        f"Dataset v{ds.get('version')} (hash {str(ds.get('hash', ''))[:12]}), "
        f"{ds.get('wells_train')} sumur latih, {ds.get('wells_blind')} sumur blind test. "
        "Validasi silang per kelompok sumur (GroupKFold 5). RMSE dalam SI (kN, kN·m).",
    )
    ws.write(
        2,
        0,
        f"Rasio rata-rata RMSE ML / RMSE WellPlan: {m.get('skill') or 0:.3f} "
        f"(< 1 = ML lebih baik). {(model.comparison or {}).get('decision', '')}",
    )
    hdr = [
        "Operasi",
        "Model terpilih",
        "Sumur",
        "RMSE WellPlan",
        "RMSE ML",
        "Perbaikan RMSE",
        "ML lebih dekat (titik)",
        "MAPE WellPlan (%)",
        "MAPE ML (%)",
        "R² WellPlan",
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
    ws.write(r, 0, "Catatan dataset", f.bold)
    for j, n in enumerate(m.get("notes", [])[:200]):
        ws.write(r + 1 + j, 0, n)

    ws = wb.add_worksheet("Uji fitur")
    for j, h in enumerate(["Grup fitur", "Skor (RMSE ML/WP)", "Dipakai", "Keterangan"]):
        ws.write(0, j, h, f.head)
    for i, row in enumerate(m.get("feature_selection", []), start=1):
        _write_row(
            ws,
            i,
            [row["grup"], row["skor"], bool(row["dipakai"]), row["keterangan"]],
            numfmt=f.num3,
        )
    ws.set_column(0, 3, 22)

    ws = wb.add_worksheet("Kandidat")
    for j, h in enumerate(["Operasi", "Kandidat", "RMSE", "MAPE (%)", "R²", "Dipilih"]):
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

    ws = wb.add_worksheet("Strategi kombinasi")
    for j, h in enumerate(
        [
            "Operasi",
            "Section|Tipe",
            "Sumur",
            "RMSE model tunggal",
            "RMSE model kombinasi",
            "Dipakai",
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
                    s["dipakai"],
                ],
                numfmt=f.num3,
            )
            i += 1
    ws.set_column(0, 5, 20)

    for key, title, _cols in (
        ("by_section", "Per section", ["section"]),
        ("by_type", "Per tipe", ["well_type"]),
        ("by_section_type", "Section x tipe", ["section", "well_type"]),
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
            "ML lebih dekat",
            "Peringatan",
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
                        "data sedikit" if g["warning"] else "",
                    ],
                    f.warn if g["warning"] else None,
                    f.num3,
                )
                i += 1
        ws.set_column(0, 12, 14)

    ws = wb.add_worksheet("Per kedalaman")
    for j, h in enumerate(
        ["Operasi", "Dari (m)", "Sampai (m)", "Titik", "RMSE WellPlan", "RMSE ML", "ML lebih dekat"]
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

    ws = wb.add_worksheet("Per sumur")
    for j, h in enumerate(
        [
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

    ws = wb.add_worksheet("Titik terburuk")
    for j, h in enumerate(
        ["Operasi", "Sumur", "Section", "Kedalaman (m)", "Aktual", "WellPlan", "ML"]
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

    ws = wb.add_worksheet("Kurva belajar")
    for j, h in enumerate(["Operasi", "Sumur latih", "RMSE ML", "RMSE WellPlan"]):
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

    ws = wb.add_worksheet("Pentingnya fitur")
    for j, h in enumerate(["Operasi", "Metode", "Fitur", "Pentingnya", "Arah", "Catatan"]):
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
            f"Blind test dijalankan sekali: {model.blind_result.get('run_at', '')[:19]}. "
            f"Sumur: {', '.join(model.blind_result.get('wells', []))}",
        )
        for j, h in enumerate(["Operasi", "Sumur", "Section", "Titik", "RMSE WellPlan", "RMSE ML"]):
            ws.write(2, j, h, f.head)
        i = 3
        for op, d in blind.items():
            _write_row(
                ws,
                i,
                [
                    OP_LABELS.get(op, op),
                    "SEMUA",
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
            0, 0, f"Dataset v{dataset.version}, hash {dataset.content_hash}, {dataset.n_rows} baris"
        )
        for j, h in enumerate(["Sumur", "Section", "Tipe", "Blind test", "Baris", "SHA-256 file"]):
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
        ws.write(r, 0, "Dikecualikan (status kualitas C / dikecualikan)", f.bold)
        for i, w in enumerate(dataset.excluded, start=r + 1):
            _write_row(ws, i, [w["name"], w["section"], w["status"]])
        ws.set_column(0, 0, 34)
        ws.set_column(1, 5, 14)
    wb.close()
    return buf.getvalue()
