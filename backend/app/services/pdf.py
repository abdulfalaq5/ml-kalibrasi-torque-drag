"""Ringkasan PDF: per sumur (metrik, tiga grafik, status kualitas, versi model & dataset,
batas aman) dan per model (metrik validasi & blind test, kurva belajar, pentingnya fitur)."""

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
from app.services.operations import HOOKLOAD_OPS, OP_LABELS, TORQUE_OPS  # noqa: E402
from app.services.profile import well_profile  # noqa: E402

C_WP, C_ML, C_ACT, C_MLWP = "#2a78d6", "#eb6834", "#1baf7a", "#4a3aa7"
DASH = {
    "pick_up": "-",
    "slack_off": "--",
    "rotating_weight": ":",
    "torque_off_bottom": "-",
    "torque_on_bottom": "--",
}
MARK = {
    "pick_up": "o",
    "slack_off": "^",
    "rotating_weight": "s",
    "torque_off_bottom": "o",
    "torque_on_bottom": "^",
}
STATUS_LABEL = {"A": "Layak", "B": "Layak dengan peringatan", "C": "Ditahan", "X": "Dikecualikan"}

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
        return f"{v:,.{d}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    except (TypeError, ValueError):
        return str(v)


def _fig_png(fig) -> io.BytesIO:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def _three_charts(prof: dict, target: str) -> io.BytesIO:
    ops = prof["operations"]
    du = prof["depth_unit"]
    fig, axes = plt.subplots(1, 3, figsize=(11, 7.2), sharey=True)
    for ax, group, title in ((axes[0], HOOKLOAD_OPS, "Hookload"), (axes[1], TORQUE_OPS, "Torque")):
        for op in group:
            o = ops[op]
            base = next(
                (s for s in o["wellplan"] if s["ff"] == o["wellplan_baseline_ff"]),
                o["wellplan"][0] if o["wellplan"] else None,
            )
            if base:
                ax.plot(base["value"], base["depth"], DASH[op], color=C_WP, lw=1.3)
            if o["ml"]["depth"]:
                ax.plot(o["ml"]["value"], o["ml"]["depth"], DASH[op], color=C_ML, lw=1.5)
                if o["ml"]["lo"]:
                    ax.fill_betweenx(
                        o["ml"]["depth"], o["ml"]["lo"], o["ml"]["hi"], color=C_ML, alpha=0.12, lw=0
                    )
            if o["actual"]["depth"]:
                ax.plot(
                    o["actual"]["value"],
                    o["actual"]["depth"],
                    MARK[op],
                    color=C_ACT,
                    ms=3.5,
                    mec="white",
                    mew=0.5,
                    ls="none",
                )
            for lim in o["limits"]:
                ax.axvline(lim["value"], color="#e34948", lw=1, ls="-.")
        ax.set_title(title, fontsize=10)
        ax.set_xlabel(f"{title} ({ops[group[0]]['unit']})", fontsize=8)
    ax = axes[2]
    o = ops[target]
    for key, color, line in (
        ("wp_minus_actual", C_WP, False),
        ("ml_minus_actual", C_ML, False),
        ("ml_minus_wp", C_MLWP, True),
    ):
        d = o["diff"][key]
        if not d["depth"]:
            continue
        if line:
            ax.plot(d["abs"], d["depth"], "-", color=color, lw=1.4)
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
            )
    ax.axvline(0, color="black", lw=1.4)
    lim = (
        max(
            [
                abs(v)
                for k in ("wp_minus_actual", "ml_minus_actual", "ml_minus_wp")
                for v in o["diff"][k]["abs"]
            ]
            or [1]
        )
        * 1.15
    )
    ax.set_xlim(-lim, lim)
    ax.set_title(f"Selisih {OP_LABELS[target]}", fontsize=10)
    ax.set_xlabel(f"<- lebih rendah   ({o['unit']})   lebih tinggi ->", fontsize=8)
    axes[0].set_ylabel(f"Kedalaman ({du})", fontsize=8)
    axes[0].invert_yaxis()
    for a in axes:
        a.grid(color="#e7e6e2", lw=0.6)
        a.tick_params(labelsize=7)
    handles = [
        plt.Line2D([], [], color=C_WP, lw=1.5, label="WellPlan (FF 0,3)"),
        plt.Line2D([], [], color=C_ML, lw=1.5, label="Prediksi ML (+ pita 10-90%)"),
        plt.Line2D([], [], color=C_ACT, marker="o", ls="none", label="Aktual"),
        plt.Line2D([], [], color=C_MLWP, lw=1.5, label="ML - WellPlan"),
        plt.Line2D([], [], color="#e34948", ls="-.", label="Batas aman"),
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.045),
        ncol=5,
        fontsize=7.5,
        frameon=False,
    )
    fig.text(
        0.01,
        0.0,
        "Garis penuh = pick up / torque off bottom, putus-putus = slack off / torque on bottom, "
        "titik-titik = rotating. Selisih = A - B: kanan (+) = lebih tinggi.",
        fontsize=6.5,
    )
    fig.subplots_adjust(bottom=0.2, wspace=0.08)
    return _fig_png(fig)


def well_pdf(
    db: Session,
    well: Well,
    unit_system: str = "imperial",
    target: str = "pick_up",
    model: MLModel | None = None,
) -> bytes:
    prof = well_profile(db, well, unit_system, model)
    st = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=1.4 * cm,
        rightMargin=1.4 * cm,
        topMargin=1.3 * cm,
        bottomMargin=1.3 * cm,
        title=f"Ringkasan {well.name}",
        author="Kalibrasi T&D ML",
    )
    m = prof["model"] or {}
    q = prof["quality"]
    els = [
        Paragraph(f'Ringkasan kalibrasi T&amp;D: {well.name} · {well.section_in:g}"', st["h1"]),
        Paragraph(
            f"Dibuat {datetime.now():%d-%m-%Y %H:%M} · tipe {well.well_type or '-'} · "
            f"format rencana {(well.meta or {}).get('plan_format') or '-'}",
            st["p"],
        ),
    ]
    info = [
        ["Item", "Nilai"],
        [
            "Status kualitas data",
            f"{q['status']} – {STATUS_LABEL.get(q['status'], '')} (skor {q['score']})",
        ],
        ["Model", "-" if not m else f"#{m['id']} · dataset v{m.get('dataset_version')}"],
        [
            "Prediksi",
            "-"
            if prof["prediction"] is None
            else (
                "out-of-fold (model tidak melihat sumur ini)"
                if prof["prediction"]["kind"] == "oof"
                else "model penuh"
            ),
        ],
        ["Satuan", f"{unit_system} (kedalaman {prof['depth_unit']})"],
    ]
    els += [
        Spacer(1, 4),
        _table(
            [[Paragraph(str(c), st["small"]) for c in r] for r in info], st, [5 * cm, 12.6 * cm]
        ),
    ]
    if q["issues"]:
        els.append(Paragraph("Catatan kualitas data", st["h2"]))
        els += [Paragraph(f"• [{c['level']}] {c['message']}", st["small"]) for c in q["issues"]]
    els.append(Paragraph("Metrik sumur ini (titik aktual)", st["h2"]))
    rows = [
        ["Operasi", "Satuan", "RMSE WP", "RMSE ML", "MAPE WP", "MAPE ML", "R² WP", "R² ML", "Titik"]
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
    els.append(Paragraph("Batas aman", st["h2"]))
    if lims:
        rows = [
            [
                "Operasi",
                "Batas",
                "Berlaku",
                "ML menyentuh",
                "ML pita",
                "WellPlan menyentuh",
                "Margin ML",
            ]
        ]
        for op, lim in lims:
            u = prof["operations"][op]["unit"]
            rows.append(
                [
                    OP_LABELS[op],
                    f"{lim['kind']} {_n(lim['value'])} {u}",
                    lim["scope"],
                    _n(lim["cross_ml"], 0) if lim["cross_ml"] is not None else "tidak",
                    _n(lim["cross_ml_band"], 0) if lim["cross_ml_band"] is not None else "tidak",
                    _n(lim["cross_wellplan"], 0) if lim["cross_wellplan"] is not None else "tidak",
                    _n(lim["margin_ml"]),
                ]
            )
        els.append(_table(rows, st))
        els.append(
            Paragraph(
                f"Kedalaman dalam {prof['depth_unit']}. 'tidak' = kurva tidak melewati batas.",
                st["small"],
            )
        )
    else:
        els.append(Paragraph("Belum ada batas aman untuk sumur/section ini.", st["small"]))
    if prof["warnings"]:
        els.append(Paragraph("Peringatan", st["h2"]))
        els += [Paragraph(f"• {w}", st["small"]) for w in prof["warnings"]]
    els += [
        PageBreak(),
        Paragraph("Tiga profil: Hookload, Torque, Selisih", st["h2"]),
        Image(_three_charts(prof, target), width=18.2 * cm, height=12.4 * cm),
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
        author="Kalibrasi T&D ML",
    )
    els = [
        Paragraph(f"Ringkasan model kalibrasi #{model.id}", st["h1"]),
        Paragraph(
            f"Status {model.status}{' · AKTIF' if model.active else ''} · dibuat "
            f"{model.created_at:%d-%m-%Y %H:%M} · dataset v{ds.get('version')} "
            f"(hash {str(ds.get('hash', ''))[:12]}) · {ds.get('wells_train')} sumur latih, "
            f"{ds.get('wells_blind')} sumur blind test",
            st["p"],
        ),
        Paragraph((model.comparison or {}).get("decision", ""), st["small"]),
    ]
    els.append(Paragraph("Validasi silang per kelompok sumur (GroupKFold 5)", st["h2"]))
    rows = [
        ["Operasi", "Model", "Sumur", "RMSE WP", "RMSE ML", "Perbaikan", "ML lebih dekat", "R² ML"]
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
            "RMSE dalam SI (kN untuk hookload, kN·m untuk torsi). 'ML lebih dekat' = persen "
            "titik ketika prediksi ML lebih dekat ke aktual daripada WellPlan.",
            st["small"],
        )
    )
    els.append(Paragraph("Blind test (sekali, sumur yang dikunci sejak awal)", st["h2"]))
    if model.blind_result:
        rows = [["Operasi", "Titik", "RMSE WP", "RMSE ML", "ML lebih dekat"]]
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
                "Sumur blind test: " + ", ".join(model.blind_result.get("wells", [])), st["small"]
            )
        )
    else:
        els.append(Paragraph("Belum dijalankan.", st["small"]))
    els.append(Paragraph("Uji manfaat fitur", st["h2"]))
    rows = [["Grup", "Skor (RMSE ML/WP)", "Dipakai", "Keterangan"]]
    for r in m.get("feature_selection", []):
        rows.append(
            [r["grup"], _n(r["skor"], 3), "ya" if r["dipakai"] else "tidak", r["keterangan"]]
        )
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
        fig.suptitle("Kurva belajar (jumlah sumur latih)", fontsize=9)
        els += [
            Paragraph("Kurva belajar", st["h2"]),
            Image(_fig_png(fig), width=18.2 * cm, height=4.6 * cm),
            Paragraph(
                "Kurva yang masih turun di ujung kanan = menambah sumur masih membantu. "
                "Mendatar = keterbatasan ada di data atau fitur.",
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
        fig.suptitle("Pentingnya fitur (rata-rata |SHAP|)", fontsize=9)
        fig.tight_layout()
        els += [
            Paragraph("Penjelasan model (SHAP)", st["h2"]),
            Image(_fig_png(fig), width=18.2 * cm, height=5.4 * cm),
        ]
        els += [
            Paragraph(
                f"• {OP_LABELS.get(op, op)}: {d.get('explain', {}).get('note', '')}", st["small"]
            )
            for op, d in ops.items()
        ]
    els.append(Paragraph("Keterbatasan", st["h2"]))
    lims = [
        "Akurasi diukur pada sumur yang tidak dilihat model; tidak ada jaminan untuk sumur di luar "
        "rentang section/tipe/kedalaman data latih.",
        "Kombinasi section × tipe dengan < 3 sumur ditandai 'data sedikit'.",
        "Kesalahan pencatatan di lapangan yang tidak terlihat dari data tidak dapat dideteksi sistem.",
    ]
    if dataset is not None and dataset.excluded:
        lims.append(
            f"{len(dataset.excluded)} sumur-section dikecualikan oleh gerbang kualitas data "
            "(lihat laporan kualitas data)."
        )
    els += [Paragraph(f"• {t}", st["small"]) for t in lims]
    doc.build(els)
    return buf.getvalue()
