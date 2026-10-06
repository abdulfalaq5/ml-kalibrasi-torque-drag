"""Ekspor Excel per sumur dengan format yang diminta client
("OUTPUT xxx 8.5'' Multiple T&D Road Map.xls"). Semua teks keluaran dalam bahasa Inggris.

Sheet (urutan dan letak sel mengikuti template):
  Summary Outputs                 judul + info sumur (C3..D10), tabel "ACTUAL VS Machine Learning"
                                  (B16:O17 + data), tabel metrik Drag/Torque, dua gambar parity
  Tripping Load Analysis - Graph  grafik A1:N44; MODELLED HOOKLOADS Q2.., ACTUAL HOOKLOADS AB2..,
                                  TRIPPING DATA AG2..; tambahan: ML PREDICTION AK2..
  Torque Analysis Off Btm         grafik A1:K46; MODELLED TORQUE L3.., Actual Torque R3..;
  Torque Analysis On Bottom       tambahan: ML PREDICTION U3..
  ROT/SO/PU MW <mud weight>       format "Multipoint Torque and Drag Outputs" WellPlan (model mentah)

Perbedaan yang disengaja dari template (lihat docs/keputusan.md K-42):
  - warna kurva model mengikuti satu warna per OHFF (permintaan client #5), aktual = titik;
  - kolom/garis ML ditambahkan (template tidak punya seri ML);
  - nilai FF mengikuti file (template contoh punya 0,2–0,5);
  - satuan torsi ringkasan ditulis benar (Kft.lbf), template menulis "klbf";
  - file .xlsx (bukan .xls).
"""

import io
import math
import re
from datetime import date

import numpy as np
import xlsxwriter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ActualReading, MLModel, Survey, Well
from app.services import dataset as dsm
from app.services import units
from app.services.export import COLORS, MARKER_EDGE, ohff_color
from app.services.operations import (
    BASELINE_FF,
    HOOKLOAD_OPS,
    PICK_UP,
    ROTATING,
    SLACK_OFF,
    TORQUE_OFF,
    TORQUE_ON,
    TORQUE_OPS,
)
from app.services.profile import well_profile

TITLE = "ML PREDICTION ANALYSIS SUMMARY REPORT"
SUBTITLE = "Prediction Output Torque & Drag ML"
ACT_SYMBOL = {
    PICK_UP: "circle",
    SLACK_OFF: "triangle",
    ROTATING: "square",
    TORQUE_OFF: "circle",
    TORQUE_ON: "triangle",
}
OP_SHORT = {
    PICK_UP: "PU",
    SLACK_OFF: "SO",
    ROTATING: "ROT",
    TORQUE_OFF: "Torque Off Bottom",
    TORQUE_ON: "Torque On Bottom",
}


# ---------------------------------------------------------------- helper


def _num(v):
    return None if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))) else v


def _interp(depth, value, grid):
    pairs = [(d, v) for d, v in zip(depth, value, strict=True) if d is not None and v is not None]
    if len(pairs) < 2:
        return [None] * len(grid)
    d = np.array([p[0] for p in pairs], float)
    v = np.array([p[1] for p in pairs], float)
    o = np.argsort(d)
    d, v = d[o], v[o]
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


class _F:
    def __init__(self, wb):
        b = {"font_name": "Arial", "font_size": 10}
        self.title = wb.add_format({**b, "bold": True, "font_size": 16})
        self.sub = wb.add_format({**b, "italic": True, "font_color": "#52514e"})
        self.label = wb.add_format({**b, "bold": True, "italic": True})
        self.text = wb.add_format(b)
        self.h2 = wb.add_format({**b, "font_size": 14})
        self.head = wb.add_format({**b, "border": 1, "text_wrap": True, "valign": "vcenter"})
        self.unit = wb.add_format({**b, "border": 1, "align": "center"})
        self.cell = wb.add_format({**b, "border": 1, "num_format": "#,##0.00"})
        self.cell0 = wb.add_format({**b, "border": 1, "num_format": "#,##0"})
        self.group = wb.add_format(
            {**b, "bold": True, "align": "center", "border": 1, "bg_color": "#eaeef2"}
        )
        self.ghead = wb.add_format(
            {
                **b,
                "bold": True,
                "border": 1,
                "text_wrap": True,
                "valign": "top",
                "bg_color": "#f4f4f2",
            }
        )
        self.gunit = wb.add_format({**b, "border": 1, "align": "center", "bg_color": "#f4f4f2"})
        self.n2 = wb.add_format({**b, "num_format": "0.00"})
        self.n0 = wb.add_format({**b, "num_format": "0"})
        self.bold = wb.add_format({**b, "bold": True})
        self.note = wb.add_format({**b, "italic": True, "font_color": "#52514e", "font_size": 9})


def _write(ws, r, c, v, fmt=None):
    v = _num(v)
    if v is None:
        ws.write_blank(r, c, None, fmt)
    elif isinstance(v, str):
        ws.write_string(r, c, v, fmt)
    else:
        ws.write_number(r, c, float(v), fmt)


def _col(letters: str) -> int:
    return xlsxwriter.utility.xl_cell_to_rowcol(f"{letters}1")[1]


# ---------------------------------------------------------------- utama


def build_output_workbook(
    db: Session,
    well: Well,
    unit_system: str = "imperial",
    model: MLModel | None = None,
    calibration: str | None = None,
    guest: bool = False,
    forecast: dict | None = None,
) -> bytes:
    """guest=True: hanya aktual + ML (tanpa kurva WellPlan, metrik T&D, sheet multipoint; K-45)."""
    prof = well_profile(db, well, unit_system, model, calibration)
    if guest:
        from app.services.guest_view import profile_for_guest

        prof = profile_for_guest(prof)
    disp = units.DISPLAY_UNITS[unit_system]
    imperial = unit_system == "imperial"
    du = prof["depth_unit"]
    du_cap = "Ft" if imperial else "m"
    tq_u = "kft-lbf" if imperial else "kn-m"  # template memakai Kft.lbf
    tq_lab = "Kft.lbf" if imperial else "kN.m"
    hk_lab = "klbf" if imperial else "kN"
    ops = prof["operations"]

    def tq(vals):  # ft-lbf tampilan -> Kft.lbf
        if imperial:
            return [None if v is None else v / 1000.0 for v in vals]
        return list(vals)

    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True, "nan_inf_to_errors": True})
    f = _F(wb)
    sec = f"{(well.section_in or 0):g}"
    head_title = f'{well.name}  {sec}"_HOLE'

    _summary(wb, f, db, well, prof, unit_system, du, hk_lab, tq_lab, tq)
    _tripping(wb, f, db, well, prof, du, du_cap, hk_lab, head_title, forecast)
    for op, name, act_label in (
        (TORQUE_OFF, "Torque Analysis Off Btm", "RT Torque Off Bottom Max"),
        (TORQUE_ON, "Torque Analysis On Bottom", "RT Torque ON Bottom Max"),
    ):
        _torque(wb, f, well, ops[op], op, name, act_label, du_cap, tq_lab, tq, head_title, forecast)
    if not guest:
        _multipoint(wb, f, db, well, unit_system, disp, du, hk_lab, tq_lab, tq_u)
    wb.close()
    return buf.getvalue()


# ---------------------------------------------------------------- Summary Outputs


def _summary(wb, f, db, well, prof, unit_system, du, hk_lab, tq_lab, tq):
    ws = wb.add_worksheet("Summary Outputs")
    ws.hide_gridlines(2)
    ws.set_column("A:A", 3)
    ws.set_column("B:O", 12.5)
    ws.set_column("B:B", 20)
    ws.set_column("H:H", 20)
    meta = well.meta or {}
    ops = prof["operations"]
    ws.set_landscape()
    ws.fit_to_pages(1, 0)
    ws.write("C3", TITLE, f.title)
    ws.write("C4", SUBTITLE, f.sub)
    info = [
        ("Client :", meta.get("client") or ""),
        ("Field :", meta.get("field") or ""),
        ("Rig :", meta.get("rig") or ""),
        ("Well :", well.name),
        ("Engineer :", ""),
        ("Date :", date.today().strftime("%B %d, %Y")),
        ("Section :", f'{(well.section_in or 0):g}"'),
        ("Well type :", well.well_type or ""),
        (
            "ML model :",
            "-"
            if not prof["model"]
            else f"#{prof['model']['id']} (dataset v{prof['model'].get('dataset_version')})"
            + (
                " · unseen-well validation"
                if (prof["prediction"] or {}).get("kind") == "oof"
                else ""
            ),
        ),
    ]
    for i, (k, v) in enumerate(info):
        ws.write(4 + i, 2, k, f.label)
        ws.write(4 + i, 3, v, f.text)
    ws.write("C15", "ACTUAL VS Machine Learning", f.h2)
    head = [
        ("Bit Depth ", du),
        ("Actual PU", hk_lab),
        ("Actual SO", hk_lab),
        ("Actual ROT", hk_lab),
        ("ML PU", hk_lab),
        ("ML SO", hk_lab),
        ("ML ROT", hk_lab),
        ("PU-MLPU", hk_lab),
        ("SO-MLSO", hk_lab),
        ("ROT-MLROT", hk_lab),
        ("Actual TORQ OFF", tq_lab),
        ("ACTUAL TORQ ON", tq_lab),
        ("TQ-MLTQ Off", tq_lab),
        ("TQ-MLTQ On", tq_lab),
    ]
    for j, (h, u) in enumerate(head):
        ws.write(15, 1 + j, h, f.head)
        ws.write(16, 1 + j, u, f.unit)
    ws.set_row(15, 28)
    tol = 30 if du == "ft" else 10
    grid = sorted({d for op in ops for d in ops[op]["actual"]["depth"]})
    act = {
        op: _nearest(ops[op]["actual"]["depth"], ops[op]["actual"]["value"], grid, tol)
        for op in ops
    }
    ml = {op: _interp(ops[op]["ml"]["depth"], ops[op]["ml"]["value"], grid) for op in ops}
    for op in TORQUE_OPS:
        act[op], ml[op] = tq(act[op]), tq(ml[op])

    def d(a, b):
        return [None if x is None or y is None else x - y for x, y in zip(a, b, strict=True)]

    cols = [
        grid,
        act[PICK_UP],
        act[SLACK_OFF],
        act[ROTATING],
        ml[PICK_UP],
        ml[SLACK_OFF],
        ml[ROTATING],
        d(act[PICK_UP], ml[PICK_UP]),
        d(act[SLACK_OFF], ml[SLACK_OFF]),
        d(act[ROTATING], ml[ROTATING]),
        act[TORQUE_OFF],
        act[TORQUE_ON],
        d(act[TORQUE_OFF], ml[TORQUE_OFF]),
        d(act[TORQUE_ON], ml[TORQUE_ON]),
    ]
    n = max(len(grid), 10)  # template: minimal 10 baris tabel
    for i in range(n):
        for j, c in enumerate(cols):
            _write(
                ws, 17 + i, 1 + j, c[i] if i < len(grid) else None, f.cell0 if j == 0 else f.cell
            )
    r0 = 17 + n + 2
    if not grid:
        ws.write(17, 1, "No actual data for this well yet.", f.note)

    # metrik (SI, sesuai template: kN; torsi kN.m) untuk sumur ini
    rows_d, rows_t, par = _metrics(prof, well)
    ws.write(r0, 1, "Drag Prediction Performance Metric", f.text)
    ws.write(r0, 7, "Torque Prediciton Performance Metric", f.text)
    for j, h in enumerate(["Model", "R2", "RMSE (kN)", "MAE (kN)", "MAPE (%)"]):
        ws.write(r0 + 1, 1 + j, h, f.head)
    for j, h in enumerate(["Model", "R2", "RMSE (kN.m)", "MAE (kN.m)", "MAPE (%)"]):
        ws.write(r0 + 1, 7 + j, h, f.head)
    for i in range(max(4, len(rows_d), len(rows_t))):
        for c0, rows in ((1, rows_d), (7, rows_t)):
            row = rows[i] if i < len(rows) else [None] * 5
            for j, v in enumerate(row):
                _write(ws, r0 + 2 + i, c0 + j, v, f.cell if j else f.head)
    rn = r0 + 2 + max(4, len(rows_d), len(rows_t))
    ws.write(
        rn,
        1,
        "Metrics for this well on its actual readings (pooled over PU/SO/ROT and torque off/on bottom). "
        "Unseen-well validation for training wells.",
        f.note,
    )
    # gambar parity
    for c0, key, title, color in (
        (1, "drag", "Drag", "#1f9e2c"),
        (7, "torque", "Torque", "#2a78d6"),
    ):
        png = _parity_png(par[key], title, color)
        if png is not None:
            ws.insert_image(
                rn + 2, c0, f"{key}.png", {"image_data": png, "x_scale": 0.9, "y_scale": 0.9}
            )


def _to_si(xs, u):
    return [None if x is None else units.to_si(x, u) for x in xs]


def _metrics(prof, well):
    """Baris metrik T&D model, T&D + Calibrate, ML untuk sumur ini (SI)."""
    from app.services.calibration import offsets_si

    ops = prof["operations"]
    disp_u = units.DISPLAY_UNITS[prof["unit_system"]]
    offs = offsets_si(well)
    groups = {"drag": HOOKLOAD_OPS, "torque": TORQUE_OPS}
    acc = {g: {"wp": ([], []), "cal": ([], []), "ml": ([], [])} for g in groups}
    for g, gops in groups.items():
        for op in gops:
            o = ops[op]
            u = disp_u["force" if g == "drag" else "torque"]
            ad, av = o["actual"]["depth"], o["actual"]["value"]
            if not ad:
                continue
            base = next(
                (s for s in o["wellplan"] if s["ff"] == o["wellplan_baseline_ff"]),
                o["wellplan"][0] if o["wellplan"] else None,
            )
            y = _to_si(av, u)
            wp = _to_si(_interp(base["depth"], base["value"], ad), u) if base else [None] * len(ad)
            # profil sudah memuat offset bila mode calibrated: kurangi agar "T&D Model" = mentah
            off_disp = offs.get(op, 0.0) if prof["calibration"]["mode"] == "calibrated" else 0.0
            raw = [None if x is None else x - off_disp for x in wp]
            cal = (
                [None if x is None else x + offs[op] for x in raw]
                if op in offs
                else [None] * len(raw)
            )
            ml = _to_si(_interp(o["ml"]["depth"], o["ml"]["value"], ad), u)
            for k, p in (("wp", raw), ("cal", cal), ("ml", ml)):
                for yy, pp in zip(y, p, strict=True):
                    if yy is not None and pp is not None:
                        acc[g][k][0].append(yy)
                        acc[g][k][1].append(pp)
    model = prof["model"]
    names = {
        "wp": "T&D Model (OHFF 0.3)",
        "cal": "T&D Model + DD Calibrate",
        "ml": f"ML (model #{model['id']})" if model else "ML",
    }
    out = {}
    for g in groups:
        rows = []
        for k in ("wp", "cal", "ml"):
            y, p = (np.array(a, float) for a in acc[g][k])
            if len(y) < 2:
                continue
            e = p - y
            ss = float(np.sum((y - y.mean()) ** 2))
            r2 = 1 - float(np.sum(e**2)) / ss if ss > 0 else None
            floor = max(0.05 * float(np.median(np.abs(y))), 1e-9)
            mape = float(np.mean(np.abs(e) / np.maximum(np.abs(y), floor)) * 100)
            rows.append(
                [names[k], r2, float(np.sqrt(np.mean(e**2))), float(np.mean(np.abs(e))), mape]
            )
        out[g] = rows
    par = {g: (np.array(acc[g]["ml"][0]), np.array(acc[g]["ml"][1])) for g in groups}
    return out["drag"], out["torque"], par


def _parity_png(data, title, color):
    y, p = data
    if len(y) < 2:
        return None
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ss = float(np.sum((y - y.mean()) ** 2))
    r2 = 1 - float(np.sum((p - y) ** 2)) / ss if ss > 0 else float("nan")
    unit = "kN" if title == "Drag" else "kN.m"
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.scatter(y, p, s=14, alpha=0.6, color=color, edgecolors="none", label=f"ML {title}")
    lo, hi = float(min(y.min(), p.min())), float(max(y.max(), p.max()))
    ax.plot([lo, hi], [lo, hi], "--", color="#e34948", lw=1.5, label="Perfect Prediction")
    ax.set_title(f"ML {title} Prediction\nR² = {r2:.4f}", fontsize=11, fontweight="bold")
    ax.set_xlabel(f"Actual {title} ({unit})")
    ax.set_ylabel(f"Predicted {title} ({unit})")
    ax.grid(color="#e7e6e2", lw=0.6)
    ax.legend(loc="upper left", fontsize=8)
    fig.text(0.01, 0.005, f"Figure: {title} Prediction - Actual vs ML (R²)", fontsize=8)
    fig.tight_layout()
    out = io.BytesIO()
    fig.savefig(out, format="png", dpi=150)
    plt.close(fig)
    out.seek(0)
    return out


# ---------------------------------------------------------------- Tripping Load Analysis - Graph


def _fc_values(o: dict, conv=lambda v: v) -> tuple[list, list, list]:
    """Prediction ahead seperti di dashboard: nilai terkoreksi bias + pita P10–P90 yang digeser."""
    shift = o.get("bias") or 0.0
    main = o["ml_corrected"] if o.get("ml_corrected") is not None else o["ml"]
    lo = [None if v is None else v + shift for v in o["p10"]]
    hi = [None if v is None else v + shift for v in o["p90"]]
    return conv(main), conv(lo), conv(hi)


def _fc_block(ws, f, fc, op_list, r_group, c0, du_label, unit_label, conv=lambda v: v):
    """Tabel PREDICTION AHEAD (per operasi: kedalaman, prediction, P10, P90).

    Hasil: {op: (kolom kedalaman, kolom prediction, kolom P10, kolom P90, n, nilai prediction)}.
    """
    out = {}
    if not fc:
        return out
    c = c0
    for op in op_list:
        o = (fc.get("operations") or {}).get(op)
        if not o or len(o["depth"]) < 2:
            continue
        main, lo, hi = _fc_values(o, conv)
        p = OP_SHORT[op]
        cols = [
            ("Bit Depth", du_label, o["depth"]),
            (f"{p} - Prediction", unit_label, main),
            (f"{p} - Prediction P10", unit_label, lo),
            (f"{p} - Prediction P90", unit_label, hi),
        ]
        for j, (h, u, vals) in enumerate(cols):
            ws.write(r_group + 1, c + j, h, f.ghead)
            ws.write(r_group + 2, c + j, u, f.gunit)
            for i, v in enumerate(vals):
                _write(ws, r_group + 3 + i, c + j, v, f.n0 if j == 0 else f.n2)
        out[op] = (c, c + 1, c + 2, c + 3, len(o["depth"]), main)
        c += 4
    if out:
        ws.merge_range(
            r_group,
            c0,
            r_group,
            c - 1,
            f"PREDICTION AHEAD {fc['start_depth']:,.0f} → {fc['end_depth']:,.0f} {fc['depth_unit']}"
            + (" (bias-corrected)" if fc.get("bias_correction") else ""),
            f.group,
        )
    return out


def _fc_series(ch, name, fcpos, r_data, unit_label, distance_ft):
    """Garis prediction ungu tebal + pita P10–P90 putus-putus + label nilai di ujung."""
    for op, (cd, cm, clo, chi, n, main) in fcpos.items():
        p = OP_SHORT[op]
        last = next((v for v in reversed(main) if v is not None), None)
        labels = [{"delete": True}] * (n - 1) + [
            {"value": f"{p} {last:,.1f} {unit_label}" if last is not None else ""}
        ]
        ch.add_series(
            {
                "name": f"{p} - Prediction (next {distance_ft:g} ft)",
                "categories": [name, r_data, cm, r_data + n - 1, cm],
                "values": [name, r_data, cd, r_data + n - 1, cd],
                "line": {"color": COLORS["forecast"], "width": 3.5},
                "marker": {
                    "type": "circle",
                    "size": 5,
                    "fill": {"color": COLORS["forecast"]},
                    "border": {"color": COLORS["forecast"]},
                },
                "data_labels": {
                    "custom": labels,
                    "position": "right",
                    "font": {"color": COLORS["forecast"], "bold": True, "size": 12},
                },
            }
        )
        for col, k in ((clo, "P10"), (chi, "P90")):
            ch.add_series(
                {
                    "name": f"{p} - Prediction {k}",
                    "categories": [name, r_data, col, r_data + n - 1, col],
                    "values": [name, r_data, cd, r_data + n - 1, cd],
                    "line": {"color": COLORS["forecast"], "width": 1.25, "dash_type": "dash"},
                    "marker": {"type": "none"},
                }
            )


def _tripping(wb, f, db, well, prof, du, du_cap, hk_lab, head_title, fc=None):
    ws = wb.add_worksheet("Tripping Load Analysis - Graph")
    ws.set_column("Q:AT", 11)
    ops = prof["operations"]
    pu, so, rot = ops[PICK_UP], ops[SLACK_OFF], ops[ROTATING]
    ffs_pu = sorted(s["ff"] for s in pu["wellplan"] if s["ff"] is not None)
    ffs_so = sorted((s["ff"] for s in so["wellplan"] if s["ff"] is not None), reverse=True)
    grid = sorted({d for o in (pu, so, rot) for s in o["wellplan"] for d in s["depth"]})
    # MODELLED HOOKLOADS: Bit Depth | SO ff (turun) | PU ff (naik) | RT Hook Load Off Bottom
    cols = [("Bit Depth", du, grid, None)]
    for ff in ffs_so:
        s = next(s for s in so["wellplan"] if s["ff"] == ff)
        cols.append(
            (f"SO Hook Load ff={ff:g}", hk_lab, _interp(s["depth"], s["value"], grid), ("so", ff))
        )
    for ff in ffs_pu:
        s = next(s for s in pu["wellplan"] if s["ff"] == ff)
        cols.append(
            (f"PU Hook Load ff={ff:g}", hk_lab, _interp(s["depth"], s["value"], grid), ("pu", ff))
        )
    if rot["wellplan"]:
        s = rot["wellplan"][0]
        cols.append(
            (
                "RT Hook Load Off Bottom",
                hk_lab,
                _interp(s["depth"], s["value"], grid),
                ("rot", s["ff"]),
            )
        )
    c0 = _col("Q")
    pos = {}
    if len(cols) == 1:  # tanpa kurva WellPlan (ekspor guest)
        cols = []
    else:
        ws.merge_range(1, c0, 1, c0 + len(cols) - 1, "MODELLED HOOKLOADS", f.group)
    for j, (h, u, vals, key) in enumerate(cols):
        ws.write(2, c0 + j, h, f.ghead)
        ws.write(3, c0 + j, u, f.gunit)
        for i, v in enumerate(vals):
            _write(ws, 4 + i, c0 + j, v, f.n0 if j == 0 else f.n2)
        if key:
            pos[key] = c0 + j
    ws.set_row(2, 42)
    n_model = len(grid)

    # ACTUAL HOOKLOADS (AB..AE) dan TRIPPING DATA (AG..AI)
    a0 = max(_col("AB"), c0 + len(cols) + 1)
    tol = 30 if du == "ft" else 10
    agrid = sorted({d for o in (pu, so, rot) for d in o["actual"]["depth"]})
    acols = [
        ("Bit Depth", du, agrid),
        ("P/U Weight", hk_lab, _nearest(pu["actual"]["depth"], pu["actual"]["value"], agrid, tol)),
        (
            "Rotating Weight",
            hk_lab,
            _nearest(rot["actual"]["depth"], rot["actual"]["value"], agrid, tol),
        ),
        ("SO Weight", hk_lab, _nearest(so["actual"]["depth"], so["actual"]["value"], agrid, tol)),
    ]
    ws.merge_range(1, a0, 1, a0 + 3, "ACTUAL HOOKLOADS", f.group)
    for j, (h, u, vals) in enumerate(acols):
        ws.write(2, a0 + j, h, f.ghead)
        ws.write(3, a0 + j, u, f.gunit)
        for i, v in enumerate(vals):
            _write(ws, 4 + i, a0 + j, v, f.n0 if j == 0 else f.n2)
    t0 = a0 + 5
    trip = _trip_data(db, well, du, hk_lab)
    ws.merge_range(1, t0, 1, t0 + 2, "TRIPPING DATA", f.group)
    for j, (h, u) in enumerate(
        (("Trip Depth", du), ("TRIP#1 P/U", hk_lab), ("STRIP#1 S/O", hk_lab))
    ):
        ws.write(2, t0 + j, h, f.ghead)
        ws.write(3, t0 + j, u, f.gunit)
    for i, row in enumerate(trip):
        for j, v in enumerate(row):
            _write(ws, 4 + i, t0 + j, v, f.n0 if j == 0 else f.n2)

    # ML PREDICTION (tambahan)
    m0 = t0 + 4
    mgrid = sorted({d for o in (pu, so, rot) for d in o["ml"]["depth"]})
    mcols = [("Bit Depth", du, mgrid)]
    for op, o in ((PICK_UP, pu), (SLACK_OFF, so), (ROTATING, rot)):
        p = OP_SHORT[op]
        mcols += [
            (f"{p} - ML", hk_lab, _interp(o["ml"]["depth"], o["ml"]["value"], mgrid)),
            (
                f"{p} - ML P10",
                hk_lab,
                _interp(o["ml"]["depth"], o["ml"]["lo"], mgrid)
                if o["ml"]["lo"]
                else [None] * len(mgrid),
            ),
            (
                f"{p} - ML P90",
                hk_lab,
                _interp(o["ml"]["depth"], o["ml"]["hi"], mgrid)
                if o["ml"]["hi"]
                else [None] * len(mgrid),
            ),
        ]
    ws.merge_range(1, m0, 1, m0 + len(mcols) - 1, "ML PREDICTION", f.group)
    for j, (h, u, vals) in enumerate(mcols):
        ws.write(2, m0 + j, h, f.ghead)
        ws.write(3, m0 + j, u, f.gunit)
        for i, v in enumerate(vals):
            _write(ws, 4 + i, m0 + j, v, f.n0 if j == 0 else f.n2)
    # PREDICTION AHEAD (garis ungu di dashboard), bila sedang ditampilkan saat ekspor
    fcpos = _fc_block(ws, f, fc, (PICK_UP, SLACK_OFF, ROTATING), 1, m0 + len(mcols) + 1, du, hk_lab)
    ws.freeze_panes(4, 0)

    # grafik (A1:N44), urutan seri seperti template: PU ff, SO ff, RT, aktual; + ML
    name = ws.get_name()
    ch = wb.add_chart({"type": "scatter", "subtype": "straight"})

    def line(col, n, depth_col, label_col, color, width=1.5, dash="solid"):
        if n < 2:
            return
        ch.add_series(
            {
                "name": [name, 2, label_col],
                "categories": [name, 4, col, 3 + n, col],
                "values": [name, 4, depth_col, 3 + n, depth_col],
                "line": {"color": color, "width": width, "dash_type": dash},
                "marker": {"type": "none"},
            }
        )

    for ff in ffs_pu:
        line(pos[("pu", ff)], n_model, c0, pos[("pu", ff)], ohff_color(ff))
    for ff in ffs_so:
        line(pos[("so", ff)], n_model, c0, pos[("so", ff)], ohff_color(ff))
    rk = next((k for k in pos if k[0] == "rot"), None)
    if rk:
        line(pos[rk], n_model, c0, pos[rk], ohff_color(BASELINE_FF), dash="dash")
    na = len(agrid)
    for j, op in ((1, PICK_UP), (2, ROTATING), (3, SLACK_OFF)):
        if na and any(v is not None for v in acols[j][2]):
            ch.add_series(
                {
                    "name": [name, 2, a0 + j],
                    "categories": [name, 4, a0 + j, 3 + na, a0 + j],
                    "values": [name, 4, a0, 3 + na, a0],
                    "line": {"none": True},
                    "marker": {
                        "type": ACT_SYMBOL[op],
                        "size": 12,
                        "fill": {"color": COLORS["actual"]},
                        "border": {"color": MARKER_EDGE, "width": 1},
                    },
                }
            )
    nm = len(mgrid)
    for k in range(3):
        line(m0 + 1 + 3 * k, nm, m0, m0 + 1 + 3 * k, COLORS["ml"], width=2.25)
    if fcpos:
        _fc_series(ch, name, fcpos, 4, hk_lab, fc["distance_ft"])
    _depth_chart(
        ch,
        f"{head_title} DRAG Analysis",
        "Hookload (Klbs)" if hk_lab == "klbf" else "Hookload (kN)",
        f"Measured Depth ({du_cap})",
    )
    # grafik sangat besar (± 1.900 x 1.700 px) agar titik per kedalaman terlihat detail;
    # kolom A:P dilebarkan supaya grafik tidak menutupi tabel data mulai kolom Q
    ws.set_column("A:P", 17)
    ws.insert_chart("A1", ch, {"x_scale": 3.95, "y_scale": 5.9})
    ws.set_landscape()
    ws.print_area("A1:P88")
    ws.fit_to_pages(1, 1)
    ws.write(86, 0, _curve_note(prof), f.note)


def _trip_data(db, well, du, hk_lab):
    rows = db.execute(
        select(
            ActualReading.operation,
            ActualReading.depth_m,
            ActualReading.value_si,
            ActualReading.source_sheet,
        ).where(ActualReading.well_id == well.id)
    ).all()
    trip = [r for r in rows if re.match(r"^tripping\s+data", (r.source_sheet or "").lower())]
    u = "klbf" if hk_lab == "klbf" else "kn"
    by = {}
    for r in trip:
        if r.operation in (PICK_UP, SLACK_OFF):
            by.setdefault(round(r.depth_m, 2), {})[r.operation] = units.from_si(r.value_si, u)
    return [[units.from_si(d, du), v.get(PICK_UP), v.get(SLACK_OFF)] for d, v in sorted(by.items())]


def _curve_note(prof) -> str:
    if not any(o["wellplan"] for o in prof["operations"].values()):
        return "Actual = points; ML prediction = orange; prediction ahead = thick purple line (dashed = P10–P90)."
    mode = (prof.get("calibration") or {}).get("mode")
    return (
        "Modelled curves: WellPlan T&D model + DD Calibrate offsets (as the Excel 'Graph reference'). "
        if mode == "calibrated"
        else "Modelled curves: WellPlan T&D model as modelled. "
    ) + (
        "One colour per OHFF; actual = points; ML prediction = orange; "
        "prediction ahead = thick purple line (dashed = P10–P90)."
    )


def _depth_chart(ch, title, x_title, y_title):
    # huruf lebih besar, sebanding dengan ukuran grafik
    ch.set_title({"name": title, "name_font": {"size": 16, "bold": True}})
    ch.set_x_axis(
        {
            "name": x_title,
            "name_font": {"size": 13, "bold": True},
            "num_font": {"size": 12},
            "position_axis": "on_tick",
            "major_gridlines": {"visible": True, "line": {"color": "#d9d9d9"}},
            "label_position": "high",
        }
    )
    ch.set_y_axis(
        {
            "name": y_title,
            "name_font": {"size": 13, "bold": True},
            "num_font": {"size": 12},
            "reverse": True,
            "major_gridlines": {"visible": True, "line": {"color": "#d9d9d9"}},
        }
    )
    ch.set_legend({"position": "right", "font": {"size": 12}})


# ---------------------------------------------------------------- Torque Analysis


def _torque(wb, f, well, o, op, sheet, act_label, du_cap, tq_lab, tq, head_title, fc=None):
    ws = wb.add_worksheet(sheet)
    ws.set_column("L:X", 11)
    series = sorted(o["wellplan"], key=lambda s: (s["ff"] is None, s["ff"] or 0))
    base_ff = (well.meta or {}).get("base_ff", {}).get("oh_rot")
    grid = sorted({d for s in series for d in s["depth"]})
    cols = [("Bit Depth", du_cap, grid)]
    for s in series:
        ff = s["ff"] if s["ff"] is not None else base_ff
        label = f"Surface Torque ff={ff:g}" if ff is not None else "Surface Torque"
        cols.append((label, tq_lab, tq(_interp(s["depth"], s["value"], grid))))
    c0 = _col("L")
    if len(cols) == 1:  # tanpa kurva WellPlan (ekspor guest)
        cols = []
    else:
        ws.merge_range(2, c0, 2, c0 + len(cols) - 1, "MODELLED TORQUE", f.group)
    for j, (h, u, vals) in enumerate(cols):
        ws.write(3, c0 + j, h, f.ghead)
        ws.write(4, c0 + j, u, f.gunit)
        for i, v in enumerate(vals):
            _write(ws, 5 + i, c0 + j, v, f.n0 if j == 0 else f.n2)
    ws.set_row(3, 30)
    a0 = max(_col("R"), c0 + len(cols) + 1)
    ad, av = o["actual"]["depth"], tq(o["actual"]["value"])
    ws.merge_range(1, a0, 1, a0 + 1, "", f.text)
    ws.merge_range(2, a0, 2, a0 + 1, "Actual Torque", f.group)
    for j, (h, u) in enumerate((("Bit Depth", du_cap), (act_label, tq_lab))):
        ws.write(3, a0 + j, h, f.ghead)
        ws.write(4, a0 + j, u, f.gunit)
    for i, (d, v) in enumerate(zip(ad, av, strict=True)):
        _write(ws, 5 + i, a0, d, f.n0)
        _write(ws, 5 + i, a0 + 1, v, f.n2)
    m0 = a0 + 3
    md = o["ml"]["depth"]
    p = OP_SHORT[op]
    mcols = [
        ("Bit Depth", du_cap, md),
        (f"{p} - ML", tq_lab, tq(o["ml"]["value"])),
        (f"{p} - ML P10", tq_lab, tq(o["ml"]["lo"]) if o["ml"]["lo"] else [None] * len(md)),
        (f"{p} - ML P90", tq_lab, tq(o["ml"]["hi"]) if o["ml"]["hi"] else [None] * len(md)),
    ]
    ws.merge_range(2, m0, 2, m0 + 3, "ML PREDICTION", f.group)
    for j, (h, u, vals) in enumerate(mcols):
        ws.write(3, m0 + j, h, f.ghead)
        ws.write(4, m0 + j, u, f.gunit)
        for i, v in enumerate(vals):
            _write(ws, 5 + i, m0 + j, v, f.n0 if j == 0 else f.n2)
    fcpos = _fc_block(ws, f, fc, (op,), 2, m0 + 5, du_cap, tq_lab, tq)
    ws.freeze_panes(5, 0)

    name = ws.get_name()
    ch = wb.add_chart({"type": "scatter", "subtype": "straight"})
    n = len(grid)
    for j, s in enumerate(series, start=1):
        if n >= 2:
            ch.add_series(
                {
                    "name": [name, 3, c0 + j],
                    "categories": [name, 5, c0 + j, 4 + n, c0 + j],
                    "values": [name, 5, c0, 4 + n, c0],
                    "line": {
                        "color": ohff_color(s["ff"] if s["ff"] is not None else base_ff),
                        "width": 1.5,
                    },
                    "marker": {"type": "none"},
                }
            )
    if len(ad):
        ch.add_series(
            {
                "name": [name, 3, a0 + 1],
                "categories": [name, 5, a0 + 1, 4 + len(ad), a0 + 1],
                "values": [name, 5, a0, 4 + len(ad), a0],
                "line": {"none": True},
                "marker": {
                    "type": ACT_SYMBOL.get(op, "circle"),
                    "size": 12,
                    "fill": {"color": COLORS["actual"]},
                    "border": {"color": MARKER_EDGE, "width": 1},
                },
            }
        )
    if len(md) >= 2:
        ch.add_series(
            {
                "name": [name, 3, m0 + 1],
                "categories": [name, 5, m0 + 1, 4 + len(md), m0 + 1],
                "values": [name, 5, m0, 4 + len(md), m0],
                "line": {"color": COLORS["ml"], "width": 2.25},
                "marker": {"type": "none"},
            }
        )
    if fcpos:
        _fc_series(ch, name, fcpos, 5, tq_lab, fc["distance_ft"])
    _depth_chart(
        ch, f"{head_title} TQ Analysis", f"Torque ({tq_lab})", f"Measured Depth ({du_cap})"
    )
    # grafik sangat besar (± 1.450 x 1.700 px); kolom A:K dilebarkan, data mulai kolom L
    ws.set_column("A:K", 19)
    ws.insert_chart("A1", ch, {"x_scale": 3.0, "y_scale": 5.9})
    ws.print_area("A1:K88")
    ws.fit_to_pages(1, 1)


# ---------------------------------------------------------------- PU/SO/ROT MW


def _multipoint(wb, f, db, well, unit_system, disp, du, hk_lab, tq_lab, tq_u):
    meta = well.meta or {}
    imperial = unit_system == "imperial"
    mw = meta.get("mud_weight_ppg")
    mw_txt = "NA" if mw is None else (f"{mw:g}" if imperial else f"{mw * 119.826:.0f}")
    plan = dsm.load_plan(db, [well.id])  # model mentah (tanpa Calibrate)
    csg = meta.get("csg_ff") or {}
    hk_u = disp["force"]
    n_survey = len(db.scalars(select(Survey.id).where(Survey.well_id == well.id)).all())
    for op, mode, suffix in (
        (ROTATING, "ROTATING OFF BOTTOM ANALYSIS", "  "),
        (SLACK_OFF, "TRIPPING LOADS ANALYSIS", " Trip in"),
        (PICK_UP, "TRIPPING LOADS ANALYSIS", " Trip out"),
    ):
        ws = wb.add_worksheet(f"{OP_SHORT[op]} MW {mw_txt}"[:31])
        ws.set_column("A:A", 26)
        ws.set_column("B:K", 13)
        ws.fit_to_pages(1, 0)
        ws.write("D5", "Multipoint Torque and Drag Outputs", f.title)
        hdr = [
            ("Client:", meta.get("client") or ""),
            ("Field:", meta.get("field") or ""),
            ("Rig:", meta.get("rig") or ""),
            ("Well:", well.name),
            ("Bore Hole:", f'{(well.section_in or 0):g}" section'),
            ("Location:", ""),
            ("Engineer:", ""),
            ("Date:", date.today().strftime("%B %d, %Y")),
        ]
        for i, (k, v) in enumerate(hdr):
            ws.write(7 + i, 1, k, f.bold)
            ws.write(7 + i, 3, v, f.text)
        curves = dsm.plan_curves(plan, well.id, op)
        tq_curves = dsm.plan_curves(plan, well.id, TORQUE_OFF) if op == ROTATING else {}
        ffs = sorted({k for k in (*curves, *tq_curves) if k is not None}) or [None]
        all_d = sorted({d for c in (*curves.values(), *tq_curves.values()) for d in c[0]})
        grid = np.array(all_d)
        step = float(np.median(np.diff(grid))) if len(grid) > 1 else None
        L = lambda m: units.from_si(m, du)  # noqa: E731
        ws.write("A18", "BHA & WELLBORE DATA", f.bold)
        bha = meta.get("bha") or []
        bha_txt = (
            f"{meta.get('bha_components', len(bha))} components, {meta.get('bha_length_ft', 0):g} ft, "
            f"{meta.get('bha_weight_klbf', 0):g} klbf"
            if meta.get("bha_components")
            else "-"
        )
        rows = [
            ("BHA Data:", bha_txt),
            ("Survey Data:", f"{n_survey} survey stations" if n_survey else "-"),
            ("Wellbore Data:", f'{meta.get("hole_size_in", well.section_in or 0):g}" open hole'),
        ]
        for i, (k, v) in enumerate(rows):
            ws.write(18 + i, 0, k, f.text)
            ws.write(18 + i, 3, v, f.text)
        ws.write("A23", "DRILLING PARAMETERS", f.bold)
        bw = meta.get("block_weight_klbf")
        params = [
            ("Operation Mode:", mode),
            (
                f"Mud Weight ({'ppg' if imperial else 'kg/m3'}):",
                None if mw is None else (mw if imperial else mw * 119.826),
            ),
            (f"Downhole WoB ({hk_lab}):", None),
            (f"Downhole ToB ({tq_lab}):", None),
            (
                f"Block Weight ({hk_lab}):",
                None if bw is None else units.from_si(units.to_si(bw, "klbf"), hk_u),
            ),
            (f"Bit Measured Depth ({du}):", L(grid.max()) if len(grid) else None),
            (f"Start Bit Depth ({du}):", L(grid.min()) if len(grid) else None),
            (f"End Bit Depth ({du}):", L(grid.max()) if len(grid) else None),
            (f"Bit Depth Increment ({du}):", L(step) if step else None),
        ]
        for i, (k, v) in enumerate(params):
            ws.write(23 + i, 0, k, f.text)
            _write(ws, 23 + i, 3, v, f.n2 if isinstance(v, float) else f.text)
        r = 33
        ws.write(r, 0, "BHA DESCRIPTION", f.bold)
        bh = [
            "Component Name",
            "Steel Grade",
            "Length",
            "Cum Length",
            "ID",
            "OD",
            "Max OD",
            "Bend Angle",
            "Sub Comp To Bottom",
            "Sensor To Bit",
            "Lin Weight",
        ]
        bu = ["", "", du, du, "in", "in", "in", "deg", du, du, "ppf"]
        for j, (h, u) in enumerate(zip(bh, bu, strict=True)):
            ws.write(r + 1, j, h, f.head)
            ws.write(r + 2, j, u, f.unit)
        cum = 0.0
        for i, c in enumerate(bha):
            ln = c.get("length_ft")
            cum += ln or 0
            vals = [
                c.get("name"),
                None,
                ln,
                cum,
                None,
                c.get("od_in"),
                c.get("max_od_in"),
                None,
                None,
                None,
                c.get("lin_weight_ppf"),
            ]
            if not imperial:
                vals[2] = None if ln is None else ln * units.FT_TO_M
                vals[3] = cum * units.FT_TO_M
            for j, v in enumerate(vals):
                _write(ws, r + 3 + i, j, v, f.cell if j else f.head)
        r = r + 3 + max(len(bha), 1) + 1
        ws.write(r, 0, "WELLBORE DESCRIPTION", f.bold)
        wh = ["Section Name", "Length", "Cum Length", "Diameter", "           Friction Factor"]
        for j, h in enumerate(wh):
            ws.write(r + 1, j, h, f.head)
        for j, u in enumerate([None, du, du, "in"]):
            if u:
                ws.write(r + 2, j, u, f.unit)
        for k in range(len(ffs)):
            ws.write(r + 2, 4 + k, f"#{k + 1} {suffix.strip()}".strip(), f.unit)
        wbore = meta.get("wellbore") or []
        for i, sct in enumerate(wbore):
            conv = 1.0 if imperial else units.FT_TO_M
            vals = [
                sct.get("name"),
                None if sct.get("length_ft") is None else sct["length_ft"] * conv,
                None if sct.get("cum_length_ft") is None else sct["cum_length_ft"] * conv,
                sct.get("diameter_in"),
            ]
            for j, v in enumerate(vals):
                _write(ws, r + 3 + i, j, v, f.cell if j else f.head)
            for k, ff in enumerate(ffs):
                fv = (csg.get(f"{ff:g}") if ff is not None else None) if sct.get("cased") else ff
                _write(ws, r + 3 + i, 4 + k, fv, f.cell)
        r = r + 3 + max(len(wbore), 1) + 1
        # tabel data: Bit Depth | per FF: Surface Torque, Hook Load
        ws.write(r, 0, "Bit Depth", f.head)
        ws.write(r + 2, 0, du, f.unit)
        hook = {}
        for k, ff in enumerate(ffs):
            c = 1 + 2 * k
            cs = csg.get(f"{ff:g}") if ff is not None else None
            title = (
                (f"CSG {cs:.2f} " if cs is not None else "")
                + (f"OPH {ff:.2f}" if ff is not None else "Base")
                + suffix
            )
            ws.merge_range(r, c, r, c + 1, title.rstrip() if op != ROTATING else title, f.head)
            ws.write(r + 1, c, "Surface Torque", f.head)
            ws.write(r + 1, c + 1, "Hook Load", f.head)
            ws.write(r + 2, c, tq_lab, f.unit)
            ws.write(r + 2, c + 1, hk_lab, f.unit)
            hc = curves.get(ff) or curves.get(None)
            hook[k] = (
                None
                if hc is None
                else [units.from_si(v, hk_u) for v in np.interp(grid, *hc)]
                if len(grid)
                else []
            )
            if hc is not None and len(grid):
                lo, hi = hc[0].min(), hc[0].max()
                hook[k] = [
                    None if (g < lo - 1e-6 or g > hi + 1e-6) else x
                    for g, x in zip(grid, hook[k], strict=True)
                ]
            tc = tq_curves.get(ff)
            tq_vals = None
            if tc is not None and len(grid):
                lo, hi = tc[0].min(), tc[0].max()
                tq_vals = [
                    None if (g < lo - 1e-6 or g > hi + 1e-6) else units.from_si(x, tq_u)
                    for g, x in zip(grid, np.interp(grid, *tc), strict=True)
                ]
            for i, g in enumerate(grid):
                if k == 0:
                    _write(ws, r + 3 + i, 0, L(g), f.n0)
                _write(ws, r + 3 + i, c, tq_vals[i] if tq_vals else None, f.n2)
                _write(ws, r + 3 + i, c + 1, hook[k][i] if hook[k] else None, f.n2)
        ws.write(
            r + 4 + len(grid),
            0,
            "WellPlan T&D model as modelled (no DD Calibrate). Surface torque while tripping is not in the "
            "source files and is left empty.",
            f.note,
        )
