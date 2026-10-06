"""Backtest prediction N ft ke depan pada prediksi out-of-fold (sumur tidak dilihat model).

Dari setiap kedalaman aktual (minimal 3 titik aktual sebelumnya), prediction H ft ke depan dinilai
terhadap pembacaan aktual di jendela (kedalaman, kedalaman + H]. Koreksi bias lokal sama dengan
fitur Prediction: median (aktual - prediksi) dari <= 10 titik aktual terakhir dalam 1.000 ft.
Hasil: % titik dalam toleransi client (10 klbf / 2 kft-lbf) dan error persentil 90.
"""

import numpy as np
import pandas as pd

from app.services.metrics import tolerance_si
from app.services.units import FT_TO_M

HORIZONS_FT = (300, 600, 1000)
BIAS_POINTS, BIAS_WINDOW_FT, MIN_HIST = 10, 1000.0, 3


def forecast_backtest(d: pd.DataFrame, op: str, pred_col: str = "ml_oof") -> dict:
    tol = tolerance_si(op)
    methods = {
        "T&D model": lambda g: g.wp_base.to_numpy(),
        "T&D model + bias": lambda g: g.wp_base.to_numpy(),
        "ML": lambda g: g[pred_col].to_numpy(),
        "ML + bias": lambda g: g[pred_col].to_numpy(),
    }
    has_cal = "dd_calibration" in d and d.dd_calibration.notna().any()
    out: dict = {"tolerance_si": tol, "horizons": {}}
    for h in HORIZONS_FT:
        errs = {k: [] for k in (*methods, *(["T&D + DD Calibrate"] if has_cal else []))}
        for _, g in d.groupby("well_id"):
            g = g.sort_values("depth_m")
            dep = g.depth_m.to_numpy()
            y = g.target.to_numpy()
            preds = {k: f(g) for k, f in methods.items()}
            cal = (g.wp_base + g.dd_calibration).to_numpy() if has_cal else None
            for i in range(MIN_HIST, len(g)):
                cut = dep[i - 1]
                win = (dep > cut) & (dep <= cut + h * FT_TO_M)
                if not win.any():
                    continue
                hist = np.where((dep <= cut) & (dep >= cut - BIAS_WINDOW_FT * FT_TO_M))[0][
                    -BIAS_POINTS:
                ]
                for k, p in preds.items():
                    pw = p[win]
                    if k.endswith("+ bias"):
                        if len(hist) < MIN_HIST:
                            continue
                        pw = pw + np.median(y[hist] - p[hist])
                    errs[k].extend(np.abs(pw - y[win]))
                if cal is not None and np.isfinite(cal[win]).all():
                    errs["T&D + DD Calibrate"].extend(np.abs(cal[win] - y[win]))
        out["horizons"][str(h)] = {
            k: {
                "within": float(np.mean(np.array(e) < tol)),
                "p90_si": float(np.percentile(e, 90)),
                "n": len(e),
            }
            for k, e in errs.items()
            if len(e)
        }
    return out
