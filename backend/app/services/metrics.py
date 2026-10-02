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
