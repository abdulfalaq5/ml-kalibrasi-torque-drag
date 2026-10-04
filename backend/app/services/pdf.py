"""Ringkasan PDF (teks Inggris): per sumur (metrik, grafik per operasi, status kualitas,
versi model & dataset, operating limits) dan per model (metrik validasi & blind test, kurva belajar, pentingnya fitur)."""

import io
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_LEFT  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import cm  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy.orm import Session  # noqa: E402

from app.db.models import Dataset, MLModel, Well  # noqa: E402
from app.services.export import ohff_color  # noqa: E402
from app.services.operations import OP_LABELS, OPERATIONS, SERIES_PREFIX  # noqa: E402
from app.services.profile import well_profile  # noqa: E402

C_WP, C_ML, C_ACT, C_MLWP, C_LIM = "#2a78d6", "#eb6834", "#1baf7a", "#4a3aa7", "#e34948"
STATUS_LABEL = {
    "A": "Accepted",
    "B": "Accepted with warnings",
    "C": "On hold",
    "X": "Excluded",
}

_FONT = "Helvetica"


def _font() -> str:
    global _FONT
    if _FONT != "Helvetica":
        return _FONT
    try:
        ttf = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
        pdfmetrics.registerFont(TTFont("DejaVu", str(ttf / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(ttf / "DejaVuSans-Bold.ttf")))
        _FONT = "DejaVu"
    except Exception:
        _FONT = "Helvetica"
    return _FONT


def _styles():
    f = _font()
    ss = getSampleStyleSheet()
    bold = f + "-Bold" if f == "DejaVu" else "Helvetica-Bold"
    return {
        "h1": ParagraphStyle("h1", parent=ss["Heading1"], fontName=bold, fontSize=15, spaceAfter=6),
        "h2": ParagraphStyle(
            "h2", parent=ss["Heading2"], fontName=bold, fontSize=11.5, spaceBefore=8, spaceAfter=4
        ),
        "p": ParagraphStyle(
            "p", parent=ss["BodyText"], fontName=f, fontSize=8.5, leading=11, alignment=TA_LEFT
        ),
        "small": ParagraphStyle("s", parent=ss["BodyText"], fontName=f, fontSize=7.5, leading=9.5),
        "bold": bold,
        "font": f,
    }


def _table(data, st, col_widths=None, zebra=True):
    t = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ("FONTNAME", (0, 0), (-1, -1), st["font"]),
        ("FONTNAME", (0, 0), (-1, 0), st["bold"]),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eaeef2")),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c9c8c2")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
    ]
    if zebra:
        for r in range(2, len(data), 2):
            style.append(("BACKGROUND", (0, r), (-1, r), colors.HexColor("#f7f7f5")))
    t.setStyle(TableStyle(style))
    return t


def _n(v, d=2):
    if v is None:
        return "–"
    try:
        return f"{v:,.{d}f}"
    except (TypeError, ValueError):
        return str(v)


def _fig_png(fig) -> io.BytesIO:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def _op_panel(ax, prof: dict, op: str) -> None:
    o = prof["operations"][op]
    for sr in o["wellplan"]:
        ax.plot(sr["value"], sr["depth"], "-", color=ohff_color(sr["ff"]), lw=1.3, label=sr["name"])
    if o["ml"]["depth"]:
        ax.plot(
            o["ml"]["value"],
            o["ml"]["depth"],
            "-",
            color=C_ML,
            lw=1.8,
            label=f"{SERIES_PREFIX[op]} - ML",
        )
        if o["ml"]["lo"]:
            ax.plot(
                o["ml"]["lo"],
                o["ml"]["depth"],
                "--",
                color=C_ML,
                lw=0.9,
                label=f"{SERIES_PREFIX[op]} - ML P10 / P90",
            )
            ax.plot(o["ml"]["hi"], o["ml"]["depth"], "--", color=C_ML, lw=0.9)
    if o["actual"]["depth"]:
        ax.plot(
            o["actual"]["value"],
            o["actual"]["depth"],
            "o",
            color=C_ACT,
            ms=3.5,
            mec="white",
            mew=0.5,
            ls="none",
            label=f"{SERIES_PREFIX[op]} Actual",
        )
    for i, lim in enumerate(o["limits"]):
        ax.axvline(
            lim["value"], color=C_LIM, lw=1.1, ls=":", label="Operating limit" if i == 0 else None
        )
    ax.set_title(OP_LABELS[op], fontsize=9)
    ax.set_xlabel(f"{OP_LABELS[op]} ({o['unit']})", fontsize=7.5)
    ax.legend(fontsize=6, frameon=False, loc="best")


def _diff_panel(ax, prof: dict, target: str) -> None:
    o = prof["operations"][target]
    labels = {
        "wp_minus_actual": "T&D Model - Actual",
        "ml_minus_actual": "ML - Actual",
        "ml_minus_wp": "ML - T&D Model",
    }
    for key, color, line in (
        ("wp_minus_actual", C_WP, False),
        ("ml_minus_actual", C_ML, False),
        ("ml_minus_wp", C_MLWP, True),
    ):
        d = o["diff"][key]
        if not d["depth"]:
            continue
        if line:
            ax.plot(d["abs"], d["depth"], "-", color=color, lw=1.4, label=labels[key])
        else:
            ax.plot(
                d["abs"],
                d["depth"],
                "o" if key == "wp_minus_actual" else "D",
                color=color,
                ms=3.2,
                ls="none",
                mec="white",
                mew=0.5,
                label=labels[key],
            )
    ax.axvline(0, color="black", lw=1.4)
    lim = max([abs(v) for k in labels for v in o["diff"][k]["abs"]] or [1]) * 1.15
    ax.set_xlim(-lim, lim)
    ax.set_title(f"Difference Δ {OP_LABELS[target]}", fontsize=9)
    ax.set_xlabel(f"<- lower   Δ ({o['unit']})   higher ->", fontsize=7.5)
    ax.legend(fontsize=6, frameon=False, loc="best")


def _profile_charts(prof: dict, target: str) -> io.BytesIO:
    """Enam panel bertumpuk 2 x 3: PU, SO, ROT / Torque off, Torque on, Difference."""
    du = prof["depth_unit"]
    fig, axes = plt.subplots(2, 3, figsize=(11, 12), sharey=True)
    flat = axes.ravel()
    for ax, op in zip(flat[:5], OPERATIONS, strict=True):
        _op_panel(ax, prof, op)
    _diff_panel(flat[5], prof, target)
    for ax in flat:
        ax.grid(color="#e7e6e2", lw=0.6)
        ax.tick_params(labelsize=7)
    for row in axes:
        row[0].set_ylabel(f"Depth ({du})", fontsize=8)
    axes[0][0].invert_yaxis()
    fig.text(
        0.01,
        0.005,
        "One colour per OHFF in every chart (lighter = lower OHFF). ML band = P10–P90 (dashed). "
        "Operating limits dotted. Difference = A - B: right (+) = higher.",
        fontsize=6.5,
    )
    fig.subplots_adjust(bottom=0.06, hspace=0.25, wspace=0.08)
    return _fig_png(fig)


def well_pdf(
    db: Session,
    well: Well,
    unit_system: str = "imperial",
    target: str = "pick_up",
    model: MLModel | None = None,
    calibration: str | None = None,
) -> bytes:
    prof = well_profile(db, well, unit_system, model, calibration)
    st = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=1.4 * cm,
        rightMargin=1.4 * cm,
        topMargin=1.3 * cm,
        bottomMargin=1.3 * cm,
        title=f"Summary {well.name}",
        author="T&D ML Calibration",
    )
    m = prof["model"] or {}
    q = prof["quality"]
    els = [
        Paragraph(
            f'T&amp;D calibration summary: {well.name} · {(well.section_in or 0):g}"', st["h1"]
        ),
        Paragraph(
            f"Created {datetime.now():%Y-%m-%d %H:%M} · well type {well.well_type or '-'} · "
            f"data group {well.purpose} · plan format {(well.meta or {}).get('plan_format') or '-'}",
            st["p"],
        ),
    ]
    info = [
        ["Item", "Value"],
        [
            "Data quality",
            f"{q['status']} – {STATUS_LABEL.get(q['status'], '')} (score {q['score']})",
        ],
        ["Model", "-" if not m else f"#{m['id']} · dataset v{m.get('dataset_version')}"],
        [
            "Forecast",
            "-"
            if prof["prediction"] is None
            else (
                "out-of-fold (the model never saw this well)"
                if prof["prediction"]["kind"] == "oof"
                else "full model"
            ),
        ],
        [
            "WellPlan curves",
            "WellPlan + DD Calibrate offsets"
            if (prof.get("calibration") or {}).get("mode") == "calibrated"
            else "WellPlan as modelled",
        ],
        ["Units", f"{unit_system} (depth {prof['depth_unit']})"],
    ]
    els += [
        Spacer(1, 4),
        _table(
            [[Paragraph(str(c), st["small"]) for c in r] for r in info], st, [5 * cm, 12.6 * cm]
        ),
    ]
    if q["issues"]:
        els.append(Paragraph("Data quality notes", st["h2"]))
        els += [Paragraph(f"• [{c['level']}] {c['message']}", st["small"]) for c in q["issues"]]
    els.append(Paragraph("Metrics for this well (actual points)", st["h2"]))
    rows = [
        [
            "Operation",
            "Unit",
            "RMSE WP",
            "RMSE ML",
            "MAPE WP",
            "MAPE ML",
            "R² WP",
            "R² ML",
            "Points",
        ]
    ]
    for op, o in prof["operations"].items():
        mm = o["metrics"] or {}
        wp, ml = mm.get("wellplan") or {}, mm.get("ml") or {}
        rows.append(
            [
                OP_LABELS[op],
                o["unit"],
                _n(wp.get("rmse")),
                _n(ml.get("rmse")),
                _n(wp.get("mape"), 1) + "%",
                _n(ml.get("mape"), 1) + "%",
                _n(wp.get("r2")),
                _n(ml.get("r2")),
                str((ml or wp).get("n", "–")),
            ]
        )
    els.append(_table(rows, st))
    lims = [(op, lim) for op, o in prof["operations"].items() for lim in o["limits"]]
    els.append(Paragraph("Operating limits", st["h2"]))
    if lims:
        rows = [
            [
                "Operation",
                "Limit",
                "Applies to",
                "ML reaches",
                "ML band reaches",
                "WellPlan reaches",
                "ML margin",
            ]
        ]
        for op, lim in lims:
            u = prof["operations"][op]["unit"]
            rows.append(
                [
                    OP_LABELS[op],
                    f"{lim['kind']} {_n(lim['value'])} {u}",
                    lim["scope"],
                    _n(lim["cross_ml"], 0) if lim["cross_ml"] is not None else "no",
                    _n(lim["cross_ml_band"], 0) if lim["cross_ml_band"] is not None else "no",
                    _n(lim["cross_wellplan"], 0) if lim["cross_wellplan"] is not None else "no",
                    _n(lim["margin_ml"]),
                ]
            )
        els.append(_table(rows, st))
        els.append(
            Paragraph(
                f"Depth in {prof['depth_unit']}. 'no' = the curve does not reach the limit.",
                st["small"],
            )
        )
    else:
        els.append(Paragraph("No operating limits for this well/section yet.", st["small"]))
    if prof["warnings"]:
        els.append(Paragraph("Warnings", st["h2"]))
        els += [Paragraph(f"• {w}", st["small"]) for w in prof["warnings"]]
    els += [
        PageBreak(),
        Paragraph("Profiles: Hookload, Torque, Difference", st["h2"]),
        Image(_profile_charts(prof, target), width=18.2 * cm, height=19.8 * cm),
        Paragraph(prof["sign_convention"], st["small"]),
    ]
    doc.build(els)
    return buf.getvalue()


def model_pdf(db: Session, model: MLModel) -> bytes:
    st = _styles()
    m = model.metrics or {}
    ops = m.get("operations", {})
    ds = m.get("dataset", {})
    dataset = db.get(Dataset, model.dataset_id) if model.dataset_id else None
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=1.4 * cm,
        rightMargin=1.4 * cm,
        topMargin=1.3 * cm,
        bottomMargin=1.3 * cm,
        title=f"Model #{model.id}",
        author="T&D ML Calibration",
    )
    els = [
        Paragraph(f"Calibration model summary #{model.id}", st["h1"]),
        Paragraph(
            f"Status {model.status}{' · ACTIVE' if model.active else ''} · created "
            f"{model.created_at:%Y-%m-%d %H:%M} · dataset v{ds.get('version')} "
            f"(hash {str(ds.get('hash', ''))[:12]}) · {ds.get('wells_train')} training wells, "
            f"{ds.get('wells_blind')} blind test wells",
            st["p"],
        ),
        Paragraph((model.comparison or {}).get("decision", ""), st["small"]),
    ]
    els.append(Paragraph("Cross-validation grouped by well (GroupKFold 5)", st["h2"]))
    rows = [
        ["Operation", "Model", "Wells", "RMSE WP", "RMSE ML", "Improvement", "ML closer", "R² ML"]
    ]
    for op, d in ops.items():
        wp, ml = d["overall"]["wellplan"], d["overall"]["ml"]
        imp = (wp["rmse"] - ml["rmse"]) / wp["rmse"] * 100 if wp["rmse"] else None
        rows.append(
            [
                OP_LABELS.get(op, op),
                d.get("chosen_label", d["chosen"]),
                str(d["overall"]["n_wells"]),
                _n(wp["rmse"]),
                _n(ml["rmse"]),
                _n(imp, 1) + "%",
                _n((d["overall"].get("ml_better_frac") or 0) * 100, 0) + "%",
                _n(ml["r2"]),
            ]
        )
    els.append(_table(rows, st))
    els.append(
        Paragraph(
            "RMSE in SI (kN for hookload, kN·m for torque). 'ML closer' = share of points "
            "where the ML forecast is closer to actual than WellPlan.",
            st["small"],
        )
    )
    els.append(Paragraph("Blind test (run once, wells locked from the start)", st["h2"]))
    if model.blind_result:
        rows = [["Operation", "Points", "RMSE WP", "RMSE ML", "ML closer"]]
        for op, d in model.blind_result["operations"].items():
            rows.append(
                [
                    OP_LABELS.get(op, op),
                    str(d["ml"]["n"]),
                    _n(d["wellplan"]["rmse"]),
                    _n(d["ml"]["rmse"]),
                    _n((d.get("ml_better_frac") or 0) * 100, 0) + "%",
                ]
            )
        els.append(_table(rows, st))
        els.append(
            Paragraph(
                "Blind test wells: " + ", ".join(model.blind_result.get("wells", [])), st["small"]
            )
        )
    else:
        els.append(Paragraph("Not run yet.", st["small"]))
    els.append(Paragraph("Feature group tests", st["h2"]))
    rows = [["Group", "Score (RMSE ML/WP)", "Used", "Note"]]
    for r in m.get("feature_selection", []):
        rows.append([r["group"], _n(r["score"], 3), "yes" if r["used"] else "no", r["note"]])
    els.append(_table(rows, st))

    if ops:
        fig, axes = plt.subplots(1, len(ops), figsize=(11, 2.6))
        axes = axes if len(ops) > 1 else [axes]
        for ax, (op, d) in zip(axes, ops.items(), strict=True):
            lc = d.get("learning_curve", [])
            x = range(len(lc))
            ax.plot(x, [p["rmse_ml"] for p in lc], "o-", color=C_ML, lw=1.5, ms=3, label="ML")
            ax.plot(x, [p["rmse_wp"] for p in lc], "--", color=C_WP, lw=1.2, label="WellPlan")
            ax.set_xticks(list(x), [p["label"] for p in lc], fontsize=7)
            ax.set_title(OP_LABELS.get(op, op), fontsize=8)
            ax.tick_params(labelsize=7)
            ax.grid(color="#e7e6e2", lw=0.6)
        axes[0].set_ylabel("RMSE", fontsize=7)
        axes[0].legend(fontsize=7, frameon=False)
        fig.suptitle("Learning curve (number of training wells)", fontsize=9)
        els += [
            Paragraph("Learning curve", st["h2"]),
            Image(_fig_png(fig), width=18.2 * cm, height=4.6 * cm),
            Paragraph(
                "A curve still falling at the right end = more wells still help. "
                "Flat = the limit is in the data or the features.",
                st["small"],
            ),
        ]

        fig, axes = plt.subplots(1, len(ops), figsize=(11, 3.2))
        axes = axes if len(ops) > 1 else [axes]
        for ax, (op, d) in zip(axes, ops.items(), strict=True):
            feats = d.get("explain", {}).get("features", [])[:6][::-1]
            ax.barh([f["feature"] for f in feats], [f["importance"] for f in feats], color=C_WP)
            ax.set_title(OP_LABELS.get(op, op), fontsize=8)
            ax.tick_params(labelsize=6.5)
        fig.suptitle("Feature importance (mean |SHAP|)", fontsize=9)
        fig.tight_layout()
        els += [
            Paragraph("Model explanation (SHAP)", st["h2"]),
            Image(_fig_png(fig), width=18.2 * cm, height=5.4 * cm),
        ]
        els += [
            Paragraph(
                f"• {OP_LABELS.get(op, op)}: {d.get('explain', {}).get('note', '')}", st["small"]
            )
            for op, d in ops.items()
        ]
    els.append(Paragraph("Limitations", st["h2"]))
    lims = [
        "Accuracy is measured on wells the model did not see; there is no guarantee for wells "
        "outside the section/type/depth range of the training data.",
        "Section × type combinations with < 3 wells are flagged 'limited data'.",
        "Field recording errors that are not visible in the data cannot be detected by the system.",
    ]
    if dataset is not None and dataset.excluded:
        lims.append(
            f"{len(dataset.excluded)} well sections were excluded by the data quality gate "
            "(see the data quality report)."
        )
    els += [Paragraph(f"• {t}", st["small"]) for t in lims]
    doc.build(els)
    return buf.getvalue()
