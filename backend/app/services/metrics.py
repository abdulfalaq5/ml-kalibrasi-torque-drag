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


# Toleransi client: |ML - aktual| < 10 klbf (hookload) dan < 2 kft-lbf (torsi). Lihat K-43.
TOLERANCE_LABEL = {"force": "10 klbf", "torque": "2 kft-lbf"}


def tolerance_si(op: str) -> float:
    from app.services import units
    from app.services.operations import OP_DIMENSION

    return units.to_si(10, "klbf") if OP_DIMENSION[op] == "force" else units.to_si(2000, "ft-lbf")


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
