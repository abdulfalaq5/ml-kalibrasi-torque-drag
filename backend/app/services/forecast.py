"""Forecast N ft ke depan dari kedalaman aktual terakhir, dengan penjelasan sebab-akibat.

Per operasi: prediksi ML, band P10-P90, kurva WellPlan per OHFF (mentah / terkalibrasi DD),
koreksi bias lokal opsional (median aktual - ML di titik aktual terakhir), lalu penjelasan:
  - kontribusi lokal SHAP: perubahan kontribusi tiap fitur antara awal dan akhir jendela
    (fallback: tukar nilai fitur satu per satu untuk SVR/MLP),
  - perubahan rencana: inklinasi, DLS, tipe interval di jendela forecast,
  - batas operasi yang terlewati (ML dan band),
  - satu kalimat ringkas otomatis (bahasa Inggris).
Teks keluaran dalam bahasa Inggris.
"""

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.db.models import MLModel, Well
from app.services import dataset as dsm
from app.services import units
from app.services.calibration import has_calibration, offsets_si
from app.services.limits import applicable_limits, first_crossing
from app.services.metrics import TOLERANCE_LABEL, tolerance_si, within_frac
from app.services.operations import (
    BASELINE_FF,
    OP_DIMENSION,
    OP_LABELS,
    OPERATIONS,
    SINGLE_CURVE_OPS,
    series_name,
)
from app.services.predict import load_bundle, predict_frame
from app.services.training import active_model

FT = units.FT_TO_M
BIAS_POINTS = 10  # titik aktual terakhir untuk koreksi bias lokal
BIAS_WINDOW_FT = 1000.0  # ... dan hanya yang berada dalam jendela ini dari aktual terakhir

FEATURE_LABELS = {
    "depth_m": "Depth",
    "wp_ff03": "T&D Model OHFF 0.3",
    "wp_ff05": "T&D Model OHFF 0.5",
    "wp_slope": "T&D Model OHFF sensitivity",
    "wp_rot": "T&D Model ROT",
    "wp_base": "T&D Model",
    "inc_deg": "Inclination",
    "dls_deg_30m": "Dogleg severity",
    "tortuosity": "Tortuosity",
    "open_hole_len_m": "Open hole length",
    "open_hole_frac": "Open hole fraction",
    "depth_from_kop_m": "Depth below KOP",
    "interval_type": "Interval type",
    "mud_weight_ppg": "Mud weight",
    "bha_weight_klbf": "BHA weight",
    "bha_length_ft": "BHA length",
    "block_weight_klbf": "Block weight",
    "dd_calibration": "DD Calibrate offset",
    "section": "Well section",
    "well_type": "Well type",
    "plan_format": "Plan file format",
}


def _label(f: str) -> str:
    return FEATURE_LABELS.get(f, f)


def _model_for(entry_model, section: str | None, well_type: str | None):
    """RoutedModel -> CalibrationModel yang dipakai untuk sumur ini."""
    combos = getattr(entry_model, "combos", {}) or {}
    return combos.get(f"{section}|{well_type}") or getattr(entry_model, "single", entry_model)


def _base_feature(name: str, num: list[str], cat: list[str]) -> str:
    from app.services.training import _base_feature as bf

    return bf(name, num, cat)


def local_contributions(cm, start: pd.DataFrame, end: pd.DataFrame) -> tuple[str, dict[str, float]]:
    """Perubahan kontribusi per fitur (SI) dari baris `start` ke baris `end` (masing-masing 1 baris).

    Untuk model bentuk residual, perubahan WellPlan baseline (wp_base) dicatat sendiri karena
    prediksi = WellPlan + koreksi.
    """
    out: dict[str, float] = {}
    if cm.spec["form"] == "residual":
        out["wp_base"] = float(end.wp_base.iloc[0] - start.wp_base.iloc[0])
    prep = cm.pipeline.named_steps["prep"]
    est = cm.pipeline.named_steps["model"]
    try:
        import shap

        X = pd.concat([start, end])[cm.features]
        Xt = prep.transform(X)
        if cm.spec["algo"] in ("xgboost", "random_forest"):
            sv = shap.TreeExplainer(est).shap_values(Xt)
        elif cm.spec["algo"] == "ridge":
            sv = np.asarray(Xt) * np.asarray(est.coef_)  # kontribusi linear (selisih dua baris)
        else:
            raise TypeError
        names = list(prep.get_feature_names_out())
        delta = np.asarray(sv[1]) - np.asarray(sv[0])
        for n, v in zip(names, delta, strict=True):
            b = _base_feature(n, cm.num, cm.cat)
            out[b] = out.get(b, 0.0) + float(v)
        return "SHAP", out
    except Exception:
        # tukar satu fitur: prediksi akhir - prediksi akhir dengan fitur itu dikembalikan ke awal
        y_end = float(cm.predict(end)[0])
        for f in cm.features:
            alt = end.copy()
            alt[f] = start[f].to_numpy()
            out[f] = out.get(f, 0.0) + y_end - float(cm.predict(alt)[0])
        return "feature swap", out


def _plan_changes(f: pd.DataFrame, du: str) -> dict:
    """Perubahan geometri rencana di jendela forecast (dari survey)."""
    out: dict = {}
    if "inc_deg" in f and f.inc_deg.notna().any():
        out["inclination_deg"] = [
            round(float(f.inc_deg.iloc[0]), 1),
            round(float(f.inc_deg.iloc[-1]), 1),
        ]
    if "dls_deg_30m" in f and f.dls_deg_30m.notna().any():
        out["max_dls_deg_100ft"] = round(float(f.dls_deg_30m.max()) * 30.48 / 30.0, 2)
    if "interval_type" in f:
        seq, depths = [], []
        for d, t in zip(f.depth_m, f.interval_type, strict=True):
            if t != "unknown" and (not seq or seq[-1] != t):
                seq.append(str(t))
                depths.append(round(units.from_si(float(d), du), 0))
        out["intervals"] = [{"type": t, "from": d} for t, d in zip(seq, depths, strict=True)]
    return out


def forecast_well(
    db: Session,
    well: Well,
    distance_ft: float = 300.0,
    start_depth_ft: float | None = None,
    step_ft: float = 30.0,
    bias_correction: bool | None = None,
    unit_system: str = "imperial",
    model: MLModel | None = None,
    calibration: str | None = None,
) -> dict:
    if distance_ft <= 0 or distance_ft > 20000:
        raise ValueError("Forecast distance must be between 0 and 20,000 ft")
    step_ft = min(max(step_ft, 5.0), max(distance_ft / 2, 5.0))
    model = model or active_model(db)
    if model is None or not model.path:
        raise ValueError("No active model yet. Train a model first.")
    bundle = load_bundle(model.path)
    disp = units.DISPLAY_UNITS[unit_system]
    du = disp["length"]

    w = dsm.load_wells(db, [well.id]).iloc[0]
    plan = dsm.load_plan(db, [well.id])
    survey = dsm.load_survey(db, [well.id])
    actual = dsm.load_actual(db, [well.id])
    if plan.empty:
        raise ValueError("This well has no WellPlan T&D model results to forecast from")
    plan_lo, plan_hi = float(plan.depth_m.min()), float(plan.depth_m.max())

    warnings: list[str] = []
    last_actual = float(actual.depth_m.max()) if not actual.empty else None
    if bias_correction is None:  # bawaan: aktif bila sumur sudah punya pembacaan aktual (K-43)
        bias_correction = last_actual is not None
    if start_depth_ft is not None:
        start = start_depth_ft * FT
    elif last_actual is not None:
        start = last_actual
    else:
        start = plan_lo
        warnings.append(
            "No actual data yet: the forecast starts at the top of the WellPlan T&D model"
        )
    end = start + distance_ft * FT
    if end > plan_hi + 1e-6:
        warnings.append(
            f"The WellPlan T&D model ends at {units.from_si(plan_hi, du):,.0f} {du}; "
            "the forecast stops there (the ML needs the T&D model as input)"
        )
        end = plan_hi
    if end <= start:
        raise ValueError("The start depth is at or below the end of the WellPlan T&D model")
    grid = np.unique(np.append(np.arange(start, end, step_ft * FT), end))
    if last_actual is not None and start < last_actual - 1e-6:
        warnings.append(
            "The forecast starts before the last actual reading: readings after the start depth are not "
            "used by the forecast (nor by the bias correction); they are only used to check it (see "
            "'Check against actual')."
        )

    mode = calibration or ("calibrated" if has_calibration(well) else "raw")
    offsets = offsets_si(well) if mode == "calibrated" else {}
    section = None if w.section is None else str(w.section)
    limits = applicable_limits(db, well)

    def conv(a, op):
        return [
            None
            if not np.isfinite(v)
            else round(units.from_si(float(v), disp[OP_DIMENSION[op]]), 3)
            for v in a
        ]

    def conv_d(a):
        return [round(units.from_si(float(v), du), 1) for v in a]

    ops_out: dict[str, dict] = {}
    sentences: list[str] = []
    for op in OPERATIONS:
        entry = bundle["operations"].get(op)
        if entry is None:
            continue
        f = dsm.features_frame(w, op, grid, plan, survey).dropna(subset=["wp_base"])
        if f.empty:
            continue
        for c in ("section", "well_type", "plan_format", "interval_type"):
            f[c] = f[c].fillna("unknown").astype(str)
        y, lo, hi = predict_frame(bundle, op, f)
        u = disp[OP_DIMENSION[op]]

        # koreksi bias lokal: HANYA titik aktual sampai kedalaman awal (uji jujur bila start < aktual terakhir)
        bias = None
        a_all = (
            actual[actual.operation == op].sort_values("depth_m") if not actual.empty else actual
        )
        a = a_all[a_all.depth_m <= grid[0] + 1e-6] if len(a_all) else a_all
        if bias_correction and a is not None and len(a):
            a = a[a.depth_m >= a.depth_m.max() - BIAS_WINDOW_FT * FT].tail(BIAS_POINTS)
            fa = dsm.features_frame(w, op, a.depth_m.to_numpy(), plan, survey)
            ok = fa.wp_base.notna().to_numpy()
            if ok.sum() >= 3:
                fa = fa[ok]
                for c in ("section", "well_type", "plan_format", "interval_type"):
                    fa[c] = fa[c].fillna("unknown").astype(str)
                ya, _, _ = predict_frame(bundle, op, fa)
                bias = float(np.median(a.actual_si.to_numpy()[ok] - ya))
            else:
                warnings.append(
                    f"{OP_LABELS[op]}: fewer than 3 recent actual points; no bias correction"
                )
        y_corr = y + bias if bias is not None else None
        check = _actual_check(w, op, a_all, grid, plan, survey, bundle, bias)

        # kurva WellPlan per OHFF di jendela forecast
        curves = dsm.plan_curves(plan, well.id, op)
        off = offsets.get(op, 0.0)
        wp_series = []
        keys = sorted(curves, key=lambda k: (k is None, k or 0))
        if op in SINGLE_CURVE_OPS:
            keys = [
                next((k for k in (BASELINE_FF, None) if k in curves), keys[0] if keys else None)
            ]
        for k in keys:
            if k not in curves:
                continue
            d, v = curves[k]
            vals = np.interp(f.depth_m, d, v) + off
            wp_series.append({"ff": k, "name": series_name(op, k), "value": conv(vals, op)})

        # penjelasan: kontribusi lokal antara awal dan akhir jendela
        cm = _model_for(entry["model"], section, w.well_type)
        method, contrib = local_contributions(cm, f.iloc[[0]], f.iloc[[-1]])
        total = float(y[-1] - y[0])
        drivers = sorted(
            (
                {"feature": k, "label": _label(k), "delta": round(units.from_si(v, u), 3)}
                for k, v in contrib.items()
                if abs(v) > 1e-9
            ),
            key=lambda r: -abs(r["delta"]),
        )[:6]
        changes = _plan_changes(f, du)

        crossings = []
        for lim in limits:
            if lim.operation != op:
                continue
            band = hi if lim.kind == "max" else lo
            x_ml = first_crossing(
                f.depth_m.to_numpy(), y_corr if y_corr is not None else y, lim.value_si, lim.kind
            )
            x_band = first_crossing(f.depth_m.to_numpy(), band, lim.value_si, lim.kind)
            crossings.append(
                {
                    "kind": lim.kind,
                    "value": round(units.from_si(lim.value_si, u), 3),
                    "scope": "well" if lim.well_id else "section",
                    "cross_ml": None if x_ml is None else round(units.from_si(x_ml, du), 1),
                    "cross_band": None if x_band is None else round(units.from_si(x_band, du), 1),
                }
            )

        sentence = _sentence(
            op, f, y_corr if y_corr is not None else y, u, du, total, drivers, changes, crossings
        )
        sentences.append(sentence)
        acc = _backtest_accuracy(model, op, distance_ft, bias is not None, u)
        ops_out[op] = {
            "label": OP_LABELS[op],
            "unit": units.UNIT_LABELS[u],
            "depth": conv_d(f.depth_m),
            "ml": conv(y, op),
            "p10": conv(lo, op),
            "p90": conv(hi, op),
            "ml_corrected": None if y_corr is None else conv(y_corr, op),
            "bias": None if bias is None else round(units.from_si(bias, u), 3),
            "wellplan": wp_series,
            "change": round(units.from_si(total, u), 3),
            "tolerance": TOLERANCE_LABEL[OP_DIMENSION[op]],
            "backtest": acc,
            "actual_check": check,
            "explanation": {
                "method": method,
                "drivers": drivers,
                "plan_changes": changes,
                "limit_crossings": crossings,
                "sentence": sentence,
            },
        }

    if not ops_out:
        raise ValueError("No operation could be forecast in this depth window")
    return {
        "well": {
            "id": well.id,
            "name": well.name,
            "section_in": well.section_in,
            "well_type": well.well_type,
            "purpose": well.purpose,
        },
        "model_id": model.id,
        "unit_system": unit_system,
        "depth_unit": units.UNIT_LABELS[du],
        "start_depth": round(units.from_si(float(grid[0]), du), 1),
        "end_depth": round(units.from_si(float(grid[-1]), du), 1),
        "last_actual_depth": None
        if last_actual is None
        else round(units.from_si(last_actual, du), 1),
        "distance_ft": distance_ft,
        "bias_correction": bias_correction,
        "calibration": mode,
        "warnings": warnings,
        "summary": " ".join(sentences),
        "operations": ops_out,
    }


def _actual_check(w, op, a_all, grid, plan, survey, bundle, bias) -> dict | None:
    """Bila ada pembacaan aktual DI DALAM jendela forecast (forecast dimulai sebelum aktual terakhir),
    bandingkan forecast dengan aktual itu: % titik dalam toleransi client dan rata-rata selisih."""
    if a_all is None or not len(a_all):
        return None
    aw = a_all[(a_all.depth_m > grid[0] + 1e-6) & (a_all.depth_m <= grid[-1] + 1e-6)]
    if aw.empty:
        return None
    fa = dsm.features_frame(w, op, aw.depth_m.to_numpy(), plan, survey)
    ok = fa.wp_base.notna().to_numpy()
    if not ok.any():
        return None
    fa, yv = fa[ok], aw.actual_si.to_numpy()[ok]
    for c in ("section", "well_type", "plan_format", "interval_type"):
        fa[c] = fa[c].fillna("unknown").astype(str)
    p, _, _ = predict_frame(bundle, op, fa)
    tol = tolerance_si(op)
    u = "klbf" if OP_DIMENSION[op] == "force" else "kft-lbf"
    out = {
        "n": int(len(yv)),
        "td_within": within_frac(yv, fa.wp_base.to_numpy(), tol),
        "ml_within": within_frac(yv, p, tol),
        "ml_mean_abs": round(units.from_si(float(np.mean(np.abs(p - yv))), u), 2),
        "unit": "klbf" if u == "klbf" else "kft-lbf",
    }
    if bias is not None:
        out["ml_bias_within"] = within_frac(yv, p + bias, tol)
        out["ml_bias_mean_abs"] = round(units.from_si(float(np.mean(np.abs(p + bias - yv))), u), 2)
    return out


def _backtest_accuracy(model: MLModel, op: str, distance_ft: float, with_bias: bool, u: str):
    """Akurasi backtest model ini (sumur tidak dilihat) untuk horizon terdekat >= jarak forecast."""
    bt = ((model.metrics or {}).get("operations", {}).get(op) or {}).get("forecast_backtest")
    if not bt:
        return None
    hs = sorted(int(h) for h in bt["horizons"])
    h = next((x for x in hs if x >= distance_ft), hs[-1])
    rows = bt["horizons"][str(h)]
    key = "ML + bias" if with_bias and "ML + bias" in rows else "ML"
    r = rows.get(key)
    if not r:
        return None
    return {
        "horizon_ft": h,
        "method": key,
        "within": r["within"],
        "p90": round(units.from_si(r["p90_si"], u), 3),
        "td_within": (rows.get("T&D model") or {}).get("within"),
    }


def _sentence(op, f, y, u, du, total, drivers, changes, crossings) -> str:
    ul = units.UNIT_LABELS[u]
    d0, d1 = (
        units.from_si(float(f.depth_m.iloc[0]), du),
        units.from_si(float(f.depth_m.iloc[-1]), du),
    )
    v0, v1 = units.from_si(float(y[0]), u), units.from_si(float(y[-1]), u)
    dv = round(v1 - v0, 1)
    trend = "rise" if dv > 0 else "fall" if dv < 0 else "stay about flat"
    s = (
        f"{OP_LABELS[op]}: from {d0:,.0f} to {d1:,.0f} {du} the ML forecast is expected to {trend} "
        f"from {v0:,.1f} to {v1:,.1f} {ul} ({dv:+,.1f})."
    )
    main = [d for d in drivers if abs(d["delta"]) >= 0.1 * max(abs(units.from_si(total, u)), 1e-9)][
        :3
    ]
    if main:
        s += " Main drivers: " + ", ".join(f"{d['label']} ({d['delta']:+,.1f})" for d in main)
        inc = changes.get("inclination_deg")
        if inc and any(d["feature"] == "inc_deg" for d in main):
            s += f", inclination {inc[0]:g}° → {inc[1]:g}°"
        s += "."
    ivs = changes.get("intervals") or []
    if len(ivs) > 1:
        s += (
            " Interval change: "
            + " → ".join(f"{i['type']} (from {i['from']:,.0f} {du})" for i in ivs)
            + "."
        )
    hits = [c for c in crossings if c["cross_ml"] is not None or c["cross_band"] is not None]
    if hits:
        c = hits[0]
        where = c["cross_ml"] if c["cross_ml"] is not None else c["cross_band"]
        what = "the ML forecast" if c["cross_ml"] is not None else "the P10–P90 band"
        lim = f"The {c['kind']} operating limit ({c['value']:,.1f} {ul})"
        if abs(where - d0) < 1.0:
            s += f" {lim} is already exceeded by {what} at the start ({where:,.0f} {du})."
        else:
            s += f" {lim} is reached by {what} at {where:,.0f} {du}."
    elif crossings:
        s += " No operating limit is reached."
    return s


def export_forecast(fc: dict) -> bytes:
    """Excel hasil forecast: tabel per kedalaman + lembar penjelasan."""
    import io

    import xlsxwriter

    from app.services.export import COLORS, _Fmt, _write_row, ohff_color

    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True, "nan_inf_to_errors": True})
    f = _Fmt(wb)
    du = fc["depth_unit"]

    ws = wb.add_worksheet("Summary")
    ws.set_column(0, 0, 28)
    ws.set_column(1, 1, 120)
    w = fc["well"]
    rows = [
        ("Well", w["name"]),
        ("Well section (in)", w["section_in"]),
        ("Well type", w["well_type"]),
        ("Data group", w["purpose"]),
        ("Model", f"#{fc['model_id']}"),
        (
            "Forecast window",
            f"{fc['start_depth']:,.0f} – {fc['end_depth']:,.0f} {du} ({fc['distance_ft']:g} ft ahead)",
        ),
        (
            "Last actual depth",
            "-" if fc["last_actual_depth"] is None else f"{fc['last_actual_depth']:,.0f} {du}",
        ),
        ("Local bias correction", "on" if fc["bias_correction"] else "off"),
        (
            "WellPlan curves",
            "WellPlan + DD Calibrate offsets"
            if fc["calibration"] == "calibrated"
            else "WellPlan as modelled",
        ),
    ]
    ws.write(0, 0, "Prediction Output Torque & Drag ML - Forecast", f.title)
    for i, (k, v) in enumerate(rows, start=2):
        ws.write(i, 0, k, f.bold)
        ws.write(i, 1, "" if v is None else v)
    r = len(rows) + 3
    ws.write(r, 0, "Cause and effect", f.bold)
    for j, op in enumerate(fc["operations"].values()):
        bt = op.get("backtest")
        acc = (
            f" Expected accuracy (backtest {bt['horizon_ft']:,} ft, {bt['method']}, unseen wells): "
            f"{bt['within']:.0%} of points within {op['tolerance']}, P90 error {bt['p90']:,.1f} {op['unit']}."
            if bt
            else ""
        )
        ck = op.get("actual_check")
        chk = (
            f" Check against {ck['n']} actual readings in the window: T&D model {ck['td_within']:.0%}, "
            f"ML {ck['ml_within']:.0%}"
            + (
                f", ML + bias {ck['ml_bias_within']:.0%}"
                if ck.get("ml_bias_within") is not None
                else ""
            )
            + f" within {op['tolerance']}."
            if ck
            else ""
        )
        ws.write(r + j, 1, op["explanation"]["sentence"] + acc + chk, f.wrap)
        ws.set_row(r + j, 55)
    r += len(fc["operations"]) + 1
    ws.write(r, 0, "Warnings", f.bold)
    for j, t in enumerate(fc["warnings"] or ["-"]):
        ws.write(r + j, 1, t)

    for key, o in fc["operations"].items():
        name = {
            "pick_up": "PU",
            "slack_off": "SO",
            "rotating_weight": "ROT",
            "torque_on_bottom": "Torque On Bottom",
            "torque_off_bottom": "Torque Off Bottom",
        }[key]
        ws = wb.add_worksheet(name[:31])
        cols = [f"Depth ({du})", f"ML ({o['unit']})", "ML P10", "ML P90"]
        data = [o["depth"], o["ml"], o["p10"], o["p90"]]
        if o["ml_corrected"] is not None:
            cols.append(f"ML bias-corrected (bias {o['bias']:+g})")
            data.append(o["ml_corrected"])
        for s in o["wellplan"]:
            cols.append(f"{s['name']} ({o['unit']})")
            data.append(s["value"])
        for j, h in enumerate(cols):
            ws.write(0, j, h, f.head)
        n = len(o["depth"])
        for i in range(n):
            _write_row(ws, i + 1, [c[i] for c in data], numfmt=f.num)
        ws.set_row(0, 45)
        ws.set_column(0, len(cols), 16)
        ws.freeze_panes(1, 1)
        # grafik: kedalaman ke bawah
        ch = wb.add_chart({"type": "scatter", "subtype": "straight"})
        styles = [
            ("ML", COLORS["ml"], "solid", 2.25),
            ("ML P10", COLORS["ml"], "dash", 1.0),
            ("ML P90", COLORS["ml"], "dash", 1.0),
        ]
        if o["ml_corrected"] is not None:
            styles.append(("ML bias-corrected", "#4a3aa7", "solid", 1.75))
        styles += [(s["name"], ohff_color(s["ff"]), "solid", 1.25) for s in o["wellplan"]]
        for j, (lab, color, dash, width) in enumerate(styles, start=1):
            ch.add_series(
                {
                    "name": lab,
                    "categories": [ws.name, 1, j, n, j],
                    "values": [ws.name, 1, 0, n, 0],
                    "line": {"color": color, "width": width, "dash_type": dash},
                    "marker": {"type": "none"},
                }
            )
        ch.set_title({"name": f"{o['label']} forecast", "name_font": {"size": 11}})
        ch.set_x_axis(
            {
                "name": f"{o['label']} ({o['unit']})",
                "major_gridlines": {"visible": True, "line": {"color": "#e5e5e5"}},
            }
        )
        ch.set_y_axis(
            {
                "name": f"Depth ({du})",
                "reverse": True,
                "major_gridlines": {"visible": True, "line": {"color": "#e5e5e5"}},
            }
        )
        ch.set_legend({"position": "bottom"})
        ws.insert_chart(1, len(cols) + 1, ch, {"x_scale": 1.2, "y_scale": 1.8})

    ws = wb.add_worksheet("Explanation")
    for j, h in enumerate(["Operation", "Method", "Feature", "Contribution to the change", "Unit"]):
        ws.write(0, j, h, f.head)
    r = 1
    for o in fc["operations"].values():
        ex = o["explanation"]
        for d in ex["drivers"]:
            _write_row(
                ws, r, [o["label"], ex["method"], d["label"], d["delta"], o["unit"]], numfmt=f.num
            )
            r += 1
    r += 1
    ws.write(r, 0, "Plan changes in the window", f.bold)
    r += 1
    for o in fc["operations"].values():
        pc = o["explanation"]["plan_changes"]
        inc = pc.get("inclination_deg")
        ivs = " → ".join(f"{i['type']} (from {i['from']:,.0f})" for i in pc.get("intervals", []))
        ws.write(r, 0, o["label"])
        ws.write(
            r,
            1,
            (f"Inclination {inc[0]:g}° → {inc[1]:g}°; " if inc else "")
            + (
                f"max DLS {pc['max_dls_deg_100ft']:g} °/100ft; "
                if pc.get("max_dls_deg_100ft") is not None
                else ""
            )
            + (f"intervals: {ivs}" if ivs else ""),
        )
        r += 1
        break  # geometri sama untuk semua operasi
    r += 1
    ws.write(r, 0, "Operating limits", f.bold)
    r += 1
    for j, h in enumerate(
        [
            "Operation",
            "Kind",
            "Limit",
            "Applies to",
            f"ML reaches at ({du})",
            f"Band reaches at ({du})",
        ]
    ):
        ws.write(r, j, h, f.head)
    r += 1
    for o in fc["operations"].values():
        for c in o["explanation"]["limit_crossings"]:
            _write_row(
                ws,
                r,
                [o["label"], c["kind"], c["value"], c["scope"], c["cross_ml"], c["cross_band"]],
                numfmt=f.num,
            )
            r += 1
    ws.set_column(0, 0, 20)
    ws.set_column(1, 5, 22)
    wb.close()
    return buf.getvalue()
