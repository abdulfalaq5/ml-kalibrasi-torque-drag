"""Tampilan akun guest: hanya data aktual dan ML/prediction, tanpa kurva WellPlan (K-45).

Disaring di server (bukan hanya disembunyikan di layar), jadi respons API guest tidak memuat
nilai T&D model, batas operasi, maupun selisih terhadap WellPlan.
"""


def profile_for_guest(p: dict) -> dict:
    p["calibration"] = {"available": False, "mode": "raw"}
    for o in p["operations"].values():
        o["wellplan"] = []
        o["wellplan_baseline_ff"] = None
        o["limits"] = []
        o["diff"] = {
            "ml_minus_actual": o["diff"]["ml_minus_actual"],
            "wp_minus_actual": {"depth": [], "abs": [], "pct": []},
            "ml_minus_wp": {"depth": [], "abs": [], "pct": []},
        }
        if o.get("metrics"):
            o["metrics"]["wellplan"] = None
    return p


def _first_sentence(s: str) -> str:
    """Kalimat pertama (arah prediction ML) tanpa faktor T&D model / batas operasi."""
    i = s.find(").")
    return s[: i + 2] if i >= 0 else ""


def forecast_for_guest(fc: dict) -> dict:
    fc["calibration"] = None
    for o in fc["operations"].values():
        o["wellplan"] = []
        if o.get("actual_check"):
            o["actual_check"]["td_within"] = None
        if o.get("backtest"):
            o["backtest"]["td_within"] = None
        ex = o.get("explanation") or {}
        ex["drivers"] = []
        ex["plan_changes"] = []
        ex["limit_crossings"] = []
        ex["sentence"] = _first_sentence(ex.get("sentence") or "")
    fc["summary"] = " ".join(
        o["explanation"]["sentence"] for o in fc["operations"].values() if o.get("explanation")
    )
    return fc
