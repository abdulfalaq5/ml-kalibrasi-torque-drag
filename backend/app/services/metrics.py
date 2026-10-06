import numpy as np


def rmse(y, p) -> float:
    y, p = np.asarray(y, float), np.asarray(p, float)
    return float(np.sqrt(np.mean((y - p) ** 2))) if len(y) else float("nan")


def mape(y, p, floor_frac: float = 0.05) -> float:
    """MAPE (%) dengan penyebut minimal `floor_frac` x median |y|, supaya nilai dekat
    nol (mis. slack off saat buckling) tidak membuat MAPE meledak. Lihat K-09."""
    y, p = np.asarray(y, float), np.asarray(p, float)
    if not len(y):
        return float("nan")
    floor = max(floor_frac * float(np.median(np.abs(y))), 1e-9)
    return float(np.mean(np.abs(y - p) / np.maximum(np.abs(y), floor)) * 100)


def r2(y, p) -> float:
    y, p = np.asarray(y, float), np.asarray(p, float)
    if len(y) < 2:
        return float("nan")
    ss_tot = np.sum((y - y.mean()) ** 2)
    if ss_tot == 0:
        return float("nan")
    return float(1 - np.sum((y - p) ** 2) / ss_tot)


def all_metrics(y, p) -> dict:
    return {"rmse": rmse(y, p), "mape": mape(y, p), "r2": r2(y, p), "n": int(len(y))}


# Toleransi client: |ML - aktual| < 8 klbf (hookload) dan < 0.8 kft-lbf (torsi). Lihat K-43, K-44.
TOL_HOOKLOAD_KLBF, TOL_TORQUE_KFTLBF = 8.0, 0.8
TOLERANCE_LABEL = {"force": "8 klbf", "torque": "0.8 kft-lbf"}


def tolerance_si(op: str) -> float:
    from app.services import units
    from app.services.operations import OP_DIMENSION

    if OP_DIMENSION[op] == "force":
        return units.to_si(TOL_HOOKLOAD_KLBF, "klbf")
    return units.to_si(TOL_TORQUE_KFTLBF, "kft-lbf")


def within_frac(y, p, tol: float) -> float:
    """Bagian titik dengan |p - y| < tol."""
    y, p = np.asarray(y, float), np.asarray(p, float)
    ok = np.isfinite(y) & np.isfinite(p)
    return float(np.mean(np.abs(p[ok] - y[ok]) < tol)) if ok.any() else float("nan")


def bias_correction(y_hist, p_hist, min_points: int = 3) -> float | None:
    """Median (aktual - prediksi) dari titik aktual terakhir; None bila titik < min_points."""
    y, p = np.asarray(y_hist, float), np.asarray(p_hist, float)
    ok = np.isfinite(y) & np.isfinite(p)
    return float(np.median(y[ok] - p[ok])) if ok.sum() >= min_points else None


def band_coverage(y, p, band: list[float] | tuple[float, float] | None) -> float:
    """Bagian titik aktual di dalam pita P10–P90 (p + band[0] .. p + band[1]); target desain 80%."""
    if not band:
        return float("nan")
    y, p = np.asarray(y, float), np.asarray(p, float)
    ok = np.isfinite(y) & np.isfinite(p)
    if not ok.any():
        return float("nan")
    return float(np.mean((y[ok] >= p[ok] + band[0]) & (y[ok] <= p[ok] + band[1])))
