"""Ekspor Excel (.xlsx, XlsxWriter, tanpa macro). Semua teks keluaran dalam bahasa Inggris.

export_well         : per sumur, struktur sheet mengikuti file contoh client
                      (Drag, Torque, T&D Actual Reading) + kolom ML, selisih, band P10-P90,
                      grafik per operasi (warna tetap per OHFF), Difference, operating limits.
export_quality_report : laporan kualitas data semua sumur (status A/B/C, skor, alasan, tinjauan).
export_model_report : laporan evaluasi model (validasi silang, blind test, kurva belajar, SHAP).
"""

import io
import math

import xlsxwriter
from sqlalchemy.orm import Session

from app.db.models import Dataset, MLModel, Well
from app.services.operations import OP_LABELS

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


def export_well(
    db: Session,
    well: Well,
    unit_system: str = "imperial",
    diff_target: str = "pick_up",
    model: MLModel | None = None,
    calibration: str | None = None,
) -> bytes:
    """Ekspor per sumur dengan format template client (lihat services/output_workbook.py)."""
    from app.services.output_workbook import build_output_workbook

    return build_output_workbook(db, well, unit_system, model, calibration)


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
        "Within tolerance T&D Model",
        "Within tolerance ML",
        "Blind within tolerance ML",
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
        wi = d["overall"].get("within") or {}
        for j, v in (
            (13, wi.get("wellplan")),
            (14, wi.get("ml")),
            (15, (b.get("within") or {}).get("ml")),
        ):
            if v is not None:
                ws.write(i, j, v, f.pct)
        ws.write(i, 5, imp if imp is not None else "", f.pct)
        ws.write(i, 6, d["overall"].get("ml_better_frac") or "", f.pct)
    r = 6 + len(ops)
    ws.write(
        r - 1,
        0,
        "Tolerance (client): |ML - actual| < 10 klbf for hookload, < 2 kft-lbf for torque. "
        "Share of actual points within tolerance; cross-validation on unseen wells.",
    )
    r += 1
    ws.write(r, 0, "Dataset notes", f.bold)
    for j, n in enumerate(m.get("notes", [])[:200]):
        ws.write(r + 1 + j, 0, n)

    ws = wb.add_worksheet("Forecast backtest")
    ws.write(
        0,
        0,
        "Forecast N ft ahead from every actual depth (unseen wells): share of actual points in the "
        "window within tolerance (10 klbf / 2 kft-lbf), and the 90th percentile error (SI). "
        "'+ bias' = local bias correction from the last <= 10 actual points within 1,000 ft.",
    )
    for j, h in enumerate(
        ["Operation", "Horizon (ft)", "Method", "Within tolerance", "P90 error (SI)", "Points"]
    ):
        ws.write(2, j, h, f.head)
    i = 3
    for op, d in ops.items():
        for h, rows in (d.get("forecast_backtest") or {}).get("horizons", {}).items():
            for meth, v in rows.items():
                _write_row(
                    ws,
                    i,
                    [OP_LABELS.get(op, op), int(h), meth, None, v["p90_si"], v["n"]],
                    numfmt=f.num3,
                )
                ws.write(i, 3, v["within"], f.pct)
                i += 1
    ws.set_column(0, 2, 20)
    ws.set_column(3, 5, 16)

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
