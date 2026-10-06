"""Pelatihan, validasi, dan pencatatan model kalibrasi (paket 6 minggu).

Alur (lihat docs/keputusan.md K-10 .. K-26):
1. Dataset BEKU (versi + hash) dimuat; sumur blind test disisihkan seluruhnya.
2. Uji manfaat grup fitur (ablation) dengan XGBoost: grup dipertahankan bila RMSE turun >= 1%.
3. Per operasi: Ridge, XGBoost, Random Forest, SVR (+ MLP opsional), target langsung atau
   selisih terhadap WellPlan, beberapa setelan kecil. Validasi silang per kelompok SUMUR
   (GroupKFold 5) - satu sumur tidak pernah ada di data latih dan uji sekaligus.
4. Model tunggal vs model terpisah per kombinasi section x tipe (>= 10 sumur).
5. Kurva belajar, analisis kesalahan, SHAP / pentingnya fitur, interval ketidakpastian.
6. Banding dengan model aktif: model baru yang lebih buruk DITAHAN (tidak diaktifkan).
7. Blind test dijalankan terpisah, SEKALI per model (run_blind_test).
"""

import copy
import logging
import traceback
import warnings
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
import xgboost
from sklearn.compose import ColumnTransformer, TransformedTargetRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.svm import SVR
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Dataset, MLModel, Prediction, PredictionPoint, Well
from app.services import dataset as dsm
from app.services.backtest import forecast_backtest
from app.services.metrics import all_metrics, band_coverage, rmse, tolerance_si, within_frac
from app.services.operations import BASELINE_FF, OPERATIONS

log = logging.getLogger(__name__)
warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")

MIN_WELLS = 5  # sumur latih minimum per operasi
MIN_WELLS_PER_GROUP = 3  # kombinasi section x tipe dengan sumur < ini -> peringatan
COMBO_MIN_WELLS = 10  # model terpisah per kombinasi hanya bila sumurnya >= ini
COMBO_MIN_GAIN = 0.02  # model kombinasi dipakai bila RMSE >= 2% lebih baik
FEATURE_MIN_GAIN = 0.01  # grup fitur dipertahankan bila skor >= 1% lebih baik
N_FOLDS = 5
LEARNING_SIZES = [5, 10, 20, 30]
LEARNING_REPEATS = 2
HOLD_TOLERANCE = 0.01  # model baru ditahan bila skor > aktif x (1 + 1%)
BAND_Q = (0.1, 0.9)

ALGO_GRID: dict[str, list[dict]] = {
    "ridge": [{"alpha": 1.0}, {"alpha": 10.0}],
    "xgboost": [
        {"max_depth": 2, "n_estimators": 300, "learning_rate": 0.05},
        {"max_depth": 4, "n_estimators": 300, "learning_rate": 0.05},
    ],
    "random_forest": [
        {"n_estimators": 200, "max_depth": None, "min_samples_leaf": 3},
        {"n_estimators": 200, "max_depth": 8, "min_samples_leaf": 5},
    ],
    "svr": [{"C": 10.0, "epsilon": 0.05}, {"C": 100.0, "epsilon": 0.05}],
    "mlp": [{"hidden_layer_sizes": (32, 16), "alpha": 1e-3}],
}
ALGO_LABEL = {
    "ridge": "Ridge",
    "xgboost": "XGBoost",
    "random_forest": "Random Forest",
    "svr": "SVR",
    "mlp": "MLP",
}
XGB_FIXED = {
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 3,
    "reg_lambda": 1.0,
    "n_jobs": 2,
    "random_state": 42,
}
ABLATION_SPEC = {"algo": "xgboost", "form": "residual", "params": ALGO_GRID["xgboost"][0]}


# ---------------------------------------------------------------- model


def _preprocess(num: list[str], cat: list[str], scale: bool) -> ColumnTransformer:
    steps = [
        ("impute", SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True))
    ]
    if scale:
        steps.append(("scale", StandardScaler()))
    return ColumnTransformer(
        [
            ("num", Pipeline(steps), num),
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), cat),
        ],
        verbose_feature_names_out=True,
    )


def make_pipeline(spec: dict, num: list[str], cat: list[str]) -> Pipeline:
    algo, p = spec["algo"], spec["params"]
    if algo == "ridge":
        return Pipeline([("prep", _preprocess(num, cat, True)), ("model", Ridge(alpha=p["alpha"]))])
    if algo == "xgboost":
        return Pipeline(
            [
                ("prep", _preprocess(num, cat, False)),
                ("model", xgboost.XGBRegressor(**p, **XGB_FIXED)),
            ]
        )
    if algo == "random_forest":
        return Pipeline(
            [
                ("prep", _preprocess(num, cat, False)),
                ("model", RandomForestRegressor(**p, n_jobs=2, random_state=42)),
            ]
        )
    if algo == "svr":
        est = TransformedTargetRegressor(
            regressor=SVR(C=p["C"], epsilon=p["epsilon"]), transformer=StandardScaler()
        )
        return Pipeline([("prep", _preprocess(num, cat, True)), ("model", est)])
    if algo == "mlp":
        est = TransformedTargetRegressor(
            regressor=MLPRegressor(
                hidden_layer_sizes=p["hidden_layer_sizes"],
                alpha=p["alpha"],
                max_iter=800,
                early_stopping=True,
                random_state=42,
            ),
            transformer=StandardScaler(),
        )
        return Pipeline([("prep", _preprocess(num, cat, True)), ("model", est)])
    raise ValueError(f"Unknown algorithm: {algo}")


class CalibrationModel:
    """Model satu operasi. Disimpan dengan joblib, dipakai ulang oleh prediksi."""

    def __init__(self, op: str, spec: dict, num: list[str], cat: list[str]):
        self.op, self.spec, self.num, self.cat = op, spec, num, cat
        self.pipeline = make_pipeline(spec, num, cat)

    @property
    def features(self) -> list[str]:
        return self.num + self.cat

    def fit(self, df: pd.DataFrame) -> "CalibrationModel":
        y = df.target - df.wp_base if self.spec["form"] == "residual" else df.target
        self.pipeline.fit(df[self.features], y)
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        p = np.asarray(self.pipeline.predict(df[self.features]), dtype=float)
        if self.spec["form"] == "residual":
            p = p + df.wp_base.to_numpy()
        return p


class RoutedModel:
    """Model tunggal + model per kombinasi section x tipe (bila dipilih)."""

    def __init__(self, single: CalibrationModel, combos: dict[str, CalibrationModel] | None = None):
        self.single, self.combos = single, combos or {}

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        out = self.single.predict(df)
        if self.combos:
            keys = (df.section.astype(str) + "|" + df.well_type.astype(str)).to_numpy()
            for key, m in self.combos.items():
                mask = keys == key
                if mask.any():
                    out[mask] = m.predict(df[mask])
        return out


def candidates(algorithm: str, include_mlp: bool) -> dict[str, dict]:
    algos = list(ALGO_GRID) if algorithm == "all" else [algorithm]
    if not include_mlp and algorithm == "all":
        algos = [a for a in algos if a != "mlp"]
    out = {}
    for algo in algos:
        for k, params in enumerate(ALGO_GRID[algo], start=1):
            for form in ("direct", "residual"):
                out[f"{algo}{k}_{form}"] = {"algo": algo, "form": form, "params": params}
    return out


def folds(df: pd.DataFrame, n: int = N_FOLDS):
    groups = df.well_name.to_numpy()
    k = min(n, len(np.unique(groups)))
    return list(GroupKFold(n_splits=k).split(df, groups=groups))


def oof(df: pd.DataFrame, op: str, spec: dict, num, cat, fold_idx=None) -> np.ndarray:
    pred = np.full(len(df), np.nan)
    for tr, te in fold_idx if fold_idx is not None else folds(df):
        m = CalibrationModel(op, spec, num, cat).fit(df.iloc[tr])
        pred[te] = m.predict(df.iloc[te])
    return pred


# ---------------------------------------------------------------- laporan


def group_report(df: pd.DataFrame, pred_col: str, by: list[str]) -> list[dict]:
    rows = []
    for key, g in df.groupby(by, dropna=False):
        key = key if isinstance(key, tuple) else (key,)
        n_wells = g.well_name.nunique()
        rows.append(
            {
                **dict(zip(by, key, strict=True)),
                "n_wells": int(n_wells),
                "wellplan": all_metrics(g.target, g.wp_base),
                "ml": all_metrics(g.target, g[pred_col]),
                "ml_better_frac": better_frac(g.target, g[pred_col], g.wp_base),
                "warning": n_wells < MIN_WELLS_PER_GROUP,
            }
        )
    return rows


def better_frac(y, ml, wp) -> float:
    y, ml, wp = (np.asarray(a, float) for a in (y, ml, wp))
    return float(np.mean(np.abs(ml - y) < np.abs(wp - y))) if len(y) else float("nan")


def skill(ops_metrics: dict) -> float | None:
    """Rasio rata-rata RMSE ML / RMSE WellPlan (lebih kecil = lebih baik)."""
    r = [
        m["overall"]["ml"]["rmse"] / m["overall"]["wellplan"]["rmse"]
        for m in ops_metrics.values()
        if m["overall"]["wellplan"]["rmse"] and m["overall"]["ml"]["rmse"] is not None
    ]
    return float(np.mean(r)) if r else None


def _score_groups(train: pd.DataFrame, groups: list[str]) -> float:
    num, cat = dsm.feature_columns(groups)
    ratios = []
    for op in OPERATIONS:
        d = train[train.operation == op].reset_index(drop=True)
        if d.well_name.nunique() < MIN_WELLS:
            continue
        p = oof(d, op, ABLATION_SPEC, num, cat)
        wp = rmse(d.target, d.wp_base)
        if wp:
            ratios.append(rmse(d.target, p) / wp)
    return float(np.mean(ratios)) if ratios else float("inf")


def select_feature_groups(train: pd.DataFrame) -> tuple[list[str], list[dict]]:
    """Greedy: tambahkan grup fitur satu per satu, pertahankan bila skor turun >= 1%."""
    chosen: list[str] = []
    base = _score_groups(train, chosen)
    log_rows = [{"group": "base", "score": base, "used": True, "note": "base features"}]
    for g in dsm.FEATURE_GROUPS:
        s = _score_groups(train, chosen + [g])
        keep = s < base * (1 - FEATURE_MIN_GAIN)
        log_rows.append(
            {
                "group": g,
                "score": s,
                "used": bool(keep),
                "note": f"{(base - s) / base:+.1%} vs without this group",
            }
        )
        if keep:
            chosen.append(g)
            base = s
    return chosen, log_rows


def learning_curve(d: pd.DataFrame, op: str, spec: dict, num, cat) -> list[dict]:
    rng = np.random.default_rng(42)
    n_total = d.well_name.nunique()
    sizes = [s for s in LEARNING_SIZES if s < n_total * 0.8] + [None]
    out = []
    for size in sizes:
        ys, ps, wps = [], [], []
        for tr, te in folds(d):
            tr_df = d.iloc[tr]
            names = tr_df.well_name.unique()
            reps = 1 if size is None or size >= len(names) else LEARNING_REPEATS
            for _ in range(reps):
                pick = (
                    names
                    if size is None or size >= len(names)
                    else rng.choice(names, size, replace=False)
                )
                sub = tr_df[tr_df.well_name.isin(pick)]
                m = CalibrationModel(op, spec, num, cat).fit(sub)
                te_df = d.iloc[te]
                ys.append(te_df.target.to_numpy())
                ps.append(m.predict(te_df))
                wps.append(te_df.wp_base.to_numpy())
        y, p, wp = np.concatenate(ys), np.concatenate(ps), np.concatenate(wps)
        out.append(
            {
                "n_wells": int(size or len(d.well_name.unique()) * (N_FOLDS - 1) // N_FOLDS),
                "label": "all" if size is None else str(size),
                "rmse_ml": rmse(y, p),
                "rmse_wp": rmse(y, wp),
            }
        )
    return out


def explain(model: CalibrationModel, d: pd.DataFrame) -> dict:
    """SHAP (model pohon / linear) atau permutation importance (SVR, MLP), diringkas per fitur."""
    sample = d.sample(min(len(d), 400), random_state=42)
    X = sample[model.features]
    prep = model.pipeline.named_steps["prep"]
    est = model.pipeline.named_steps["model"]
    names = list(prep.get_feature_names_out())
    method = "SHAP"
    try:
        import shap

        Xt = prep.transform(X)
        if model.spec["algo"] in ("xgboost", "random_forest"):
            sv = shap.TreeExplainer(est).shap_values(Xt)
        elif model.spec["algo"] == "ridge":
            sv = shap.LinearExplainer(est, Xt).shap_values(Xt)
        else:
            raise TypeError
        imp = np.abs(sv).mean(axis=0)
        signed = [
            float(np.corrcoef(Xt[:, j], sv[:, j])[0, 1])
            if np.std(Xt[:, j]) > 0 and np.std(sv[:, j]) > 0
            else 0.0
            for j in range(Xt.shape[1])
        ]
    except Exception:
        method = "permutation importance"
        y = sample.target - sample.wp_base if model.spec["form"] == "residual" else sample.target
        r = permutation_importance(model.pipeline, X, y, n_repeats=5, random_state=42)
        imp, names, signed = r.importances_mean, model.features, [0.0] * len(model.features)
    agg: dict[str, list[float]] = {}
    for n, v, s in zip(names, imp, signed, strict=True):
        base = _base_feature(n, model.num, model.cat)
        a = agg.setdefault(base, [0.0, 0.0])
        a[0] += float(v)
        if abs(s) > abs(a[1]):
            a[1] = s
    rows = sorted(
        ({"feature": k, "importance": v[0], "direction": v[1]} for k, v in agg.items()),
        key=lambda r: -r["importance"],
    )
    top = [r["feature"] for r in rows[:4]]
    physical = {
        "inc_deg",
        "dls_deg_30m",
        "tortuosity",
        "depth_m",
        "open_hole_len_m",
        "depth_from_kop_m",
    }
    if model.spec["form"] == "residual":
        # target = koreksi terhadap WellPlan: wajar bila geometri sumur / kedalaman yang dominan
        physics_ok = any(f.startswith("wp_") or f in physical for f in top)
        note = (
            "Target is a correction to the T&D model. Plausible: well geometry/depth or T&D model "
            "features are among the top 4."
            if physics_ok
            else "CHECK: the top 4 features are not physical (T&D model, inclination, depth)."
        )
    else:
        physics_ok = any(f.startswith("wp_") for f in top)
        note = (
            "Plausible: T&D model values (function of friction factor) are among the top features."
            if physics_ok
            else "CHECK: T&D model values are not among the top 4 features; the model may rely on "
            "non-physical features."
        )
    if "plan_format" in top:
        note += (
            " File format (roadmap vs WellPlan report) also matters: there is a systematic difference "
            "between the two model sources."
        )
    if "inc_deg" in agg:
        rank = [r["feature"] for r in rows].index("inc_deg") + 1
        note += f" Inclination ranks #{rank}."
    return {
        "method": method,
        "features": rows,
        "physics_ok": physics_ok,
        "note": note,
        "form": model.spec["form"],
    }


def _base_feature(name: str, num: list[str], cat: list[str]) -> str:
    n = name.split("__", 1)[-1]
    n = n.replace("missingindicator_", "")
    if n in num:
        return n
    for c in sorted(cat, key=len, reverse=True):
        if n.startswith(c + "_") or n == c:
            return c
    return n


def depth_bins(d: pd.DataFrame, col: str) -> list[dict]:
    q = pd.qcut(d.depth_m, q=min(5, d.depth_m.nunique()), duplicates="drop")
    rows = []
    for interval, g in d.groupby(q, observed=True):
        rows.append(
            {
                "depth_from_m": float(interval.left),
                "depth_to_m": float(interval.right),
                "wellplan": all_metrics(g.target, g.wp_base),
                "ml": all_metrics(g.target, g[col]),
                "ml_better_frac": better_frac(g.target, g[col], g.wp_base),
            }
        )
    return rows


# ---------------------------------------------------------------- pelatihan


def latest_dataset(db: Session) -> Dataset | None:
    return db.scalar(select(Dataset).order_by(Dataset.version.desc()))


def train(
    db: Session,
    model_row: MLModel,
    algorithm: str = "all",
    include_mlp: bool = False,
    dataset_id: int | None = None,
) -> MLModel:
    settings = get_settings()
    model_row.status = "running"
    db.commit()

    dataset = db.get(Dataset, dataset_id) if dataset_id else latest_dataset(db)
    if dataset is None:
        dataset = dsm.freeze_dataset(db)
    model_row.dataset_id = dataset.id
    db.commit()
    df = dsm.load_frozen(dataset)
    train_df = df[~df.is_blind].reset_index(drop=True)
    n_wells = train_df.well_name.nunique()
    if n_wells < MIN_WELLS:
        raise ValueError(
            f"At least {MIN_WELLS} training wells needed (excluding blind test), got {n_wells}"
        )

    groups, feature_log = select_feature_groups(train_df)
    num, cat = dsm.feature_columns(groups)
    cands = candidates(algorithm, include_mlp)

    bundle: dict = {"operations": {}}
    metrics: dict = {
        "operations": {},
        "notes": list(dataset.notes or []),
        "feature_selection": feature_log,
        "feature_groups": groups,
        "features": {"numeric": num, "categorical": cat},
    }
    oof_frames = []
    for op in OPERATIONS:
        d = train_df[train_df.operation == op].reset_index(drop=True)
        if d.well_name.nunique() < MIN_WELLS:
            metrics["notes"].append(f"{op}: training wells < {MIN_WELLS}, not trained")
            continue
        fidx = folds(d)
        scores, preds = {}, {}
        for name, spec in cands.items():
            preds[name] = oof(d, op, spec, num, cat, fidx)
            scores[name] = all_metrics(d.target, preds[name])
        best = min(scores, key=lambda k: scores[k]["rmse"])
        spec = cands[best]
        d["ml_single"] = preds[best]
        d["ml_oof"] = d["ml_single"]

        # model tunggal vs per kombinasi section x tipe
        strategy = []
        combo_specs = {}
        d["combo"] = d.section.astype(str) + "|" + d.well_type.astype(str)
        for key, g in d.groupby("combo"):
            nw = g.well_name.nunique()
            row = {"combo": key, "n_wells": int(nw), "rmse_single": rmse(g.target, g.ml_single)}
            if nw >= COMBO_MIN_WELLS:
                gg = g.reset_index()
                p = oof(gg, op, spec, num, cat)
                row["rmse_combo"] = rmse(gg.target, p)
                if row["rmse_combo"] < row["rmse_single"] * (1 - COMBO_MIN_GAIN):
                    row["used"] = "per combination"
                    combo_specs[key] = spec
                    d.loc[gg["index"], "ml_oof"] = p
                else:
                    row["used"] = "single"
            else:
                row["used"] = f"single (< {COMBO_MIN_WELLS} wells)"
            strategy.append(row)

        final_single = CalibrationModel(op, spec, num, cat).fit(d)
        combos = {
            k: CalibrationModel(op, s, num, cat).fit(d[d.combo == k])
            for k, s in combo_specs.items()
        }
        resid = (d.target - d.ml_oof).to_numpy()
        bundle["operations"][op] = {
            "model": RoutedModel(final_single, combos),
            "spec": spec,
            "band": [float(np.quantile(resid, BAND_Q[0])), float(np.quantile(resid, BAND_Q[1]))],
        }
        oof_frames.append(d)

        worst = d.assign(err=(d.ml_oof - d.target).abs()).nlargest(10, "err")
        metrics["operations"][op] = {
            "chosen": best,
            "chosen_label": f"{ALGO_LABEL[spec['algo']]} ({spec['form']})",
            "chosen_spec": spec,
            "candidates": scores,
            "algo_best": _best_per_algo(scores),
            "overall": {
                "wellplan": all_metrics(d.target, d.wp_base),
                "ml": all_metrics(d.target, d.ml_oof),
                "n_wells": int(d.well_name.nunique()),
                "ml_better_frac": better_frac(d.target, d.ml_oof, d.wp_base),
                "within": {
                    "wellplan": within_frac(d.target, d.wp_base, tolerance_si(op)),
                    "ml": within_frac(d.target, d.ml_oof, tolerance_si(op)),
                },
                # pita dibuat dari kuantil 10/90 residu out-of-fold yang sama -> ~80% (K-29)
                "band_coverage": band_coverage(
                    d.target, d.ml_oof, bundle["operations"][op]["band"]
                ),
            },
            "forecast_backtest": forecast_backtest(d, op),
            "strategy": strategy,
            "by_section": group_report(d, "ml_oof", ["section"]),
            "by_type": group_report(d, "ml_oof", ["well_type"]),
            "by_section_type": group_report(d, "ml_oof", ["section", "well_type"]),
            "by_depth": depth_bins(d, "ml_oof"),
            "per_well": sorted(
                (
                    {
                        "well_name": w,
                        "section": g.section.iloc[0],
                        "well_type": g.well_type.iloc[0],
                        "wellplan": all_metrics(g.target, g.wp_base),
                        "ml": all_metrics(g.target, g.ml_oof),
                    }
                    for (w, _s), g in d.groupby(["well_name", "section"])
                ),
                key=lambda r: -(r["ml"]["rmse"] or 0),
            ),
            "worst_points": [
                {
                    "well_name": r.well_name,
                    "section": r.section,
                    "depth_m": float(r.depth_m),
                    "actual": float(r.target),
                    "wellplan": float(r.wp_base),
                    "ml": float(r.ml_oof),
                }
                for r in worst.itertuples()
            ],
            "learning_curve": learning_curve(d, op, spec, num, cat),
            "explain": explain(final_single, d),
            "band": bundle["operations"][op]["band"],
        }
        log.info("Model %s %s: %s", model_row.id, op, best)

    if not bundle["operations"]:
        raise ValueError("No operation could be trained. " + "; ".join(metrics["notes"]))

    wells_tbl = train_df.drop_duplicates(["well_name", "section"])[
        ["well_name", "section", "well_type"]
    ]
    per_well = train_df.drop_duplicates("well_name")[["well_name", "well_type"]]
    combos_ct = wells_tbl.groupby(["section", "well_type"]).well_name.nunique()
    bundle.update(
        {
            "features": {"numeric": num, "categorical": cat, "groups": groups},
            "train_combos": {f"{s}|{t}": int(n) for (s, t), n in combos_ct.items()},
            "train_sections": sorted(wells_tbl.section.astype(str).unique().tolist()),
            "train_types": sorted(per_well.well_type.unique().tolist()),
            "depth_range_m": [float(train_df.depth_m.min()), float(train_df.depth_m.max())],
            "trained_wells": sorted(per_well.well_name.unique().tolist()),
            "dataset_id": dataset.id,
            "dataset_version": dataset.version,
            "versions": {"sklearn": sklearn.__version__, "xgboost": xgboost.__version__},
            "baseline_ff": BASELINE_FF,
        }
    )
    metrics["dataset"] = {
        "id": dataset.id,
        "version": dataset.version,
        "hash": dataset.content_hash,
        "rows_train": int(len(train_df)),
        "wells_train": int(n_wells),
        "rows_blind": int(df.is_blind.sum()),
        "wells_blind": int(df[df.is_blind].well_name.nunique()),
        "train_combos": bundle["train_combos"],
    }
    metrics["skill"] = skill(metrics["operations"])

    settings.model_dir.mkdir(parents=True, exist_ok=True)
    path = Path(settings.model_dir) / f"model_{model_row.id}.joblib"
    joblib.dump(bundle, path)
    model_row.path = str(path)
    model_row.metrics = _json_safe(metrics)
    model_row.params = _json_safe(
        {
            "algorithm": algorithm,
            "include_mlp": include_mlp,
            "chosen": {op: m["chosen"] for op, m in metrics["operations"].items()},
            "grid": ALGO_GRID,
            "xgb_fixed": XGB_FIXED,
            "feature_groups": groups,
            "n_folds": N_FOLDS,
            "baseline_ff": BASELINE_FF,
            "versions": bundle["versions"],
            "dataset_version": dataset.version,
        }
    )
    _save_oof(db, model_row, pd.concat(oof_frames, ignore_index=True), bundle)
    _compare_and_activate(db, model_row)
    if model_row.active:
        from app.services.predict import refresh_monitoring_predictions

        refresh_monitoring_predictions(db, model_row)
    model_row.finished_at = datetime.now(UTC)
    db.commit()
    return model_row


def _best_per_algo(scores: dict) -> dict:
    best: dict = {}
    for name, s in scores.items():
        algo = name.split("_")[0].rstrip("0123456789")
        if algo not in best or s["rmse"] < best[algo]["rmse"]:
            best[algo] = {"candidate": name, **s}
    return best


def _compare_and_activate(db: Session, row: MLModel) -> None:
    active = db.scalar(select(MLModel).where(MLModel.active.is_(True), MLModel.id != row.id))
    new = (row.metrics or {}).get("skill")
    cmp = {"new_skill": new, "active_id": None, "active_skill": None}
    if active is not None:
        old = (active.metrics or {}).get("skill")
        cmp.update({"active_id": active.id, "active_skill": old})
        if old is not None and new is not None and new > old * (1 + HOLD_TOLERANCE):
            cmp["decision"] = (
                f"Held: RMSE ratio ML/model {new:.3f} is worse than the active model "
                f"#{active.id} ({old:.3f}). It can be activated manually if needed."
            )
            row.comparison = cmp
            row.status = "held"
            row.active = False
            return
        cmp["decision"] = (
            f"Activated: ratio {new:.3f} vs active model #{active.id} "
            f"({old if old is None else round(old, 3)})"
        )
    else:
        cmp["decision"] = "Activated: no active model yet"
    row.comparison = cmp
    db.execute(update(MLModel).values(active=False))
    row.active = True
    row.status = "done"


def _save_oof(db: Session, model_row: MLModel, oof_df: pd.DataFrame, bundle: dict) -> None:
    """Prediksi out-of-fold di grid kedalaman tiap sumur latih: model fold yang tidak pernah
    melihat sumur itu (sama dengan fold validasi)."""
    ids = oof_df.well_id.unique().tolist()
    wells = dsm.load_wells(db, ids)
    plan, survey = dsm.load_plan(db, ids), dsm.load_survey(db, ids)
    db.execute(
        delete(Prediction).where(Prediction.kind == "oof", Prediction.model_id == model_row.id)
    )
    num, cat = bundle["features"]["numeric"], bundle["features"]["categorical"]
    preds: dict[int, Prediction] = {}
    for op, entry in bundle["operations"].items():
        d = oof_df[oof_df.operation == op].reset_index(drop=True)
        spec = entry["spec"]
        combo_keys = list(entry["model"].combos)
        for tr, te in folds(d):
            tr_df = d.iloc[tr]
            routed = RoutedModel(
                CalibrationModel(op, spec, num, cat).fit(tr_df),
                {
                    k: CalibrationModel(op, spec, num, cat).fit(tr_df[tr_df.combo == k])
                    for k in combo_keys
                    if (tr_df.combo == k).sum() > 10
                },
            )
            for wid in d.iloc[te].well_id.unique():
                w = wells[wells.well_id == wid].iloc[0]
                grid = dsm.plan_grid(db, int(wid))
                if not len(grid):
                    continue
                f = dsm.features_frame(w, op, grid, plan, survey).dropna(subset=["wp_base"])
                if f.empty:
                    continue
                for c in ("section", "well_type", "plan_format", "interval_type"):
                    f[c] = f[c].fillna("unknown").astype(str)
                yhat = routed.predict(f)
                pred = preds.get(int(wid))
                if pred is None:
                    pred = Prediction(
                        well_id=int(wid), model_id=model_row.id, kind="oof", warnings=[]
                    )
                    db.add(pred)
                    db.flush()
                    preds[int(wid)] = pred
                db.add_all(
                    PredictionPoint(
                        prediction_id=pred.id,
                        operation=op,
                        depth_m=float(dep),
                        wellplan_si=float(wp),
                        ml_si=float(y),
                    )
                    for dep, wp, y in zip(f.depth_m, f.wp_base, yhat, strict=True)
                )
    db.flush()


def run_blind_test(db: Session, model: MLModel) -> dict:
    """Uji sekali pada sumur blind test (tidak pernah dipakai untuk tuning)."""
    if model.blind_result:
        raise ValueError(
            "The blind test of this model has already been run; it cannot be repeated."
        )
    if model.status not in ("done", "held") or not model.path:
        raise ValueError("Model has not finished training")
    dataset = db.get(Dataset, model.dataset_id)
    df = dsm.load_frozen(dataset)
    blind = df[df.is_blind].reset_index(drop=True)
    if blind.empty:
        raise ValueError("This dataset has no blind-test wells")
    bundle = joblib.load(model.path)
    res: dict = {
        "operations": {},
        "wells": sorted(blind.well_name.unique().tolist()),
        "run_at": datetime.now(UTC).isoformat(),
    }
    for op, entry in bundle["operations"].items():
        d = blind[blind.operation == op]
        if d.empty:
            continue
        p = entry["model"].predict(d)
        res["operations"][op] = {
            "wellplan": all_metrics(d.target, d.wp_base),
            "ml": all_metrics(d.target, p),
            "ml_better_frac": better_frac(d.target, p, d.wp_base),
            "within": {
                "wellplan": within_frac(d.target, d.wp_base, tolerance_si(op)),
                "ml": within_frac(d.target, p, tolerance_si(op)),
            },
            "band_coverage": band_coverage(d.target, p, entry.get("band")),
            "per_well": [
                {
                    "well_name": w,
                    "section": g.section.iloc[0],
                    "wellplan": all_metrics(g.target, g.wp_base),
                    "ml": all_metrics(g.target, p[g.index.to_numpy()]),
                }
                for (w, _s), g in d.reset_index(drop=True).groupby(["well_name", "section"])
            ],
        }
    model.blind_result = _json_safe(res)
    db.commit()
    # prediksi penuh untuk sumur blind agar bisa dilihat di dashboard setelah uji
    from app.services.predict import predict_well

    for wid in blind.well_id.unique():
        w = db.get(Well, int(wid))
        if w is not None:
            try:
                predict_well(db, w, model)
            except ValueError:
                pass
    return model.blind_result


def backfill_band_coverage(db: Session, model: MLModel) -> dict:
    """Isi susulan '% di dalam pita P10–P90' untuk model lama (tanpa melatih ulang).

    Validasi silang: pita = kuantil 10/90 residu out-of-fold -> secara konstruksi 80%.
    Blind test: dihitung dari prediksi model yang sama pada sumur blind (bukan blind test ulang;
    tidak ada keputusan model yang berubah).
    """
    m = copy.deepcopy(model.metrics or {})  # salinan penuh: perubahan JSON harus terdeteksi
    bundle = joblib.load(model.path)
    out = {}
    for op, d in (m.get("operations") or {}).items():
        lo, hi = bundle["operations"][op]["band"]
        d.setdefault("overall", {})["band_coverage"] = d["overall"].get(
            "band_coverage", BAND_Q[1] - BAND_Q[0]
        )
        out[op] = {"cv": d["overall"]["band_coverage"]}
    model.metrics = _json_safe(m)
    if model.blind_result:
        br = copy.deepcopy(model.blind_result)
        df = dsm.load_frozen(db.get(Dataset, model.dataset_id))
        blind = df[df.is_blind]
        for op, r in br.get("operations", {}).items():
            dd = blind[blind.operation == op]
            r["band_coverage"] = band_coverage(
                dd.target,
                bundle["operations"][op]["model"].predict(dd),
                bundle["operations"][op]["band"],
            )
            out[op]["blind"] = r["band_coverage"]
        model.blind_result = _json_safe(br)
    db.commit()
    return out


def recompute_tolerance(db: Session, model: MLModel) -> dict:
    """Hitung ulang '% dalam toleransi' dan backtest prediction setelah toleransi client berubah
    (tanpa melatih ulang, tanpa blind test ulang; tidak ada keputusan model yang berubah).

    Validasi silang: prediksi out-of-fold tersimpan (kind="oof") diinterpolasi ke kedalaman aktual.
    Blind test: prediksi model yang sama pada sumur blind.
    """
    m = copy.deepcopy(model.metrics or {})
    df = dsm.load_frozen(db.get(Dataset, model.dataset_id))
    pts = pd.DataFrame(
        db.execute(
            select(
                Prediction.well_id,
                PredictionPoint.operation,
                PredictionPoint.depth_m,
                PredictionPoint.ml_si,
            )
            .join(PredictionPoint, PredictionPoint.prediction_id == Prediction.id)
            .where(Prediction.model_id == model.id, Prediction.kind == "oof")
        ).all(),
        columns=["well_id", "operation", "depth_m", "ml_si"],
    )
    out: dict = {}
    for op, entry in (m.get("operations") or {}).items():
        d = df[(~df.is_blind) & (df.operation == op)].reset_index(drop=True)
        d["ml_oof"] = np.nan
        for wid, g in pts[pts.operation == op].groupby("well_id"):
            g = g.sort_values("depth_m")
            idx = d.well_id == wid
            dep = d.loc[idx, "depth_m"].to_numpy()
            inside = (dep >= g.depth_m.iloc[0]) & (dep <= g.depth_m.iloc[-1])
            d.loc[idx, "ml_oof"] = np.where(inside, np.interp(dep, g.depth_m, g.ml_si), np.nan)
        d = d.dropna(subset=["ml_oof"])
        if d.empty:
            continue
        tol = tolerance_si(op)
        entry.setdefault("overall", {})["within"] = {
            "wellplan": within_frac(d.target, d.wp_base, tol),
            "ml": within_frac(d.target, d.ml_oof, tol),
        }
        entry["forecast_backtest"] = forecast_backtest(d, op)
        out[op] = {"cv": entry["overall"]["within"]}
    model.metrics = _json_safe(m)
    if model.blind_result and model.path:
        bundle = joblib.load(model.path)
        br = copy.deepcopy(model.blind_result)
        blind = df[df.is_blind]
        for op, r in br.get("operations", {}).items():
            dd = blind[blind.operation == op]
            if dd.empty or op not in bundle["operations"]:
                continue
            p = bundle["operations"][op]["model"].predict(dd)
            r["within"] = {
                "wellplan": within_frac(dd.target, dd.wp_base, tolerance_si(op)),
                "ml": within_frac(dd.target, p, tolerance_si(op)),
            }
            out.setdefault(op, {})["blind"] = r["within"]
        model.blind_result = _json_safe(br)
    db.commit()
    return out


def _json_safe(obj):
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, float | np.floating):
        f = float(obj)
        return None if np.isnan(f) or np.isinf(f) else f
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


def run_training_job(
    model_id: int, algorithm: str, include_mlp: bool = False, dataset_id: int | None = None
) -> None:
    """Proses latar belakang FastAPI dengan sesi DB sendiri."""
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        row = db.get(MLModel, model_id)
        try:
            train(db, row, algorithm, include_mlp, dataset_id)
        except Exception as exc:
            db.rollback()
            row = db.get(MLModel, model_id)
            row.status = "failed"
            row.message = str(exc)
            row.finished_at = datetime.now(UTC)
            db.commit()
            log.error("Pelatihan model %s gagal: %s\n%s", model_id, exc, traceback.format_exc())
    finally:
        db.close()


def active_model(db: Session) -> MLModel | None:
    return db.scalar(select(MLModel).where(MLModel.active.is_(True), MLModel.status == "done"))
