"""Pelatihan dan validasi model kalibrasi.

- Satu model per operasi (5 target). Lihat K-10.
- Kandidat: Ridge dan XGBoost, masing-masing dengan target langsung (nilai aktual)
  atau target selisih (aktual - WellPlan FF baseline).
- Validasi per kelompok sumur: leave-one-well-out (atau GroupKFold bila sumur > 20).
  Satu sumur tidak pernah ada di data latih dan uji sekaligus.
- Pembanding: baseline WellPlan apa adanya (FF nominal 0.3).
- Prediksi out-of-fold disimpan untuk dashboard (perbandingan jujur).
"""

import logging
import traceback
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
import xgboost
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold, LeaveOneGroupOut
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import MLModel, Prediction, PredictionPoint
from app.services import dataset as dsm
from app.services.metrics import all_metrics
from app.services.operations import BASELINE_FF, OPERATIONS

log = logging.getLogger(__name__)

MIN_WELLS = 3  # minimum sumur untuk melatih
MIN_WELLS_PER_GROUP = 3  # kombinasi section x tipe dengan sumur < ini -> peringatan
FEATURES = dsm.NUMERIC_FEATURES + dsm.CATEGORICAL_FEATURES

XGB_GRID = [
    {"max_depth": 2, "n_estimators": 300, "learning_rate": 0.05},
    {"max_depth": 3, "n_estimators": 200, "learning_rate": 0.05},
]
XGB_FIXED = {
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 3,
    "reg_lambda": 1.0,
    "n_jobs": 2,
    "random_state": 42,
}
RIDGE_ALPHA = 1.0


def _preprocess(scale: bool) -> ColumnTransformer:
    num = [("impute", SimpleImputer(strategy="median"))]
    if scale:
        num.append(("scale", StandardScaler()))
    return ColumnTransformer(
        [
            ("num", Pipeline(num), dsm.NUMERIC_FEATURES),
            ("cat", OneHotEncoder(handle_unknown="ignore"), dsm.CATEGORICAL_FEATURES),
        ]
    )


def candidates() -> dict[str, dict]:
    out = {}
    for form in ("langsung", "selisih"):
        out[f"ridge_{form}"] = {"algo": "ridge", "form": form, "params": {"alpha": RIDGE_ALPHA}}
        for k, g in enumerate(XGB_GRID):
            out[f"xgboost{k + 1}_{form}"] = {"algo": "xgboost", "form": form, "params": g}
    return out


def make_pipeline(spec: dict) -> Pipeline:
    if spec["algo"] == "ridge":
        est = Ridge(alpha=spec["params"]["alpha"])
        return Pipeline([("prep", _preprocess(scale=True)), ("model", est)])
    est = xgboost.XGBRegressor(**spec["params"], **XGB_FIXED)
    return Pipeline([("prep", _preprocess(scale=False)), ("model", est)])


class CalibrationModel:
    """Model per operasi. Dipakai ulang oleh prediksi (disimpan dengan joblib)."""

    def __init__(self, op: str, spec: dict, pipeline: Pipeline):
        self.op, self.spec, self.pipeline = op, spec, pipeline

    def fit(self, df: pd.DataFrame) -> "CalibrationModel":
        y = df.target - df.wp_base if self.spec["form"] == "selisih" else df.target
        self.pipeline.fit(df[FEATURES], y)
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        p = self.pipeline.predict(df[FEATURES])
        if self.spec["form"] == "selisih":
            p = p + df.wp_base.to_numpy()
        return np.asarray(p, dtype=float)


def splitter(groups: pd.Series):
    n = groups.nunique()
    return LeaveOneGroupOut() if n <= 20 else GroupKFold(n_splits=10)


def oof_predict(df: pd.DataFrame, op: str, spec: dict) -> np.ndarray:
    pred = np.full(len(df), np.nan)
    for tr, te in splitter(df.well_name).split(df, groups=df.well_name):
        m = CalibrationModel(op, spec, make_pipeline(spec)).fit(df.iloc[tr])
        pred[te] = m.predict(df.iloc[te])
    return pred


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
                "warning": n_wells < MIN_WELLS_PER_GROUP,
            }
        )
    return rows


def train(db: Session, model_row: MLModel, algorithm: str = "terbaik") -> MLModel:
    """Latih semua operasi, simpan bundle, metrik, dan prediksi out-of-fold."""
    settings = get_settings()
    model_row.status = "berjalan"
    db.commit()

    ds, notes = dsm.build_dataset(db)
    if ds.empty:
        raise ValueError("Dataset kosong: " + "; ".join(notes))
    n_wells = ds.well_name.nunique()
    if n_wells < MIN_WELLS:
        raise ValueError(f"Butuh minimal {MIN_WELLS} sumur dengan data aktual, baru {n_wells}")

    cands = candidates()
    if algorithm == "ridge":
        cands = {k: v for k, v in cands.items() if v["algo"] == "ridge"}
    elif algorithm == "xgboost":
        cands = {k: v for k, v in cands.items() if v["algo"] == "xgboost"}

    bundle: dict = {"operations": {}}
    metrics: dict = {"operations": {}, "notes": notes}
    oof_frames = []
    for op in OPERATIONS:
        d = ds[ds.operation == op].reset_index(drop=True)
        if d.well_name.nunique() < MIN_WELLS:
            metrics["notes"].append(f"{op}: sumur dengan data aktual < {MIN_WELLS}, tidak dilatih")
            continue
        cand_scores = {}
        cand_preds = {}
        for name, spec in cands.items():
            p = oof_predict(d, op, spec)
            cand_preds[name] = p
            cand_scores[name] = all_metrics(d.target, p)
        best = min(cand_scores, key=lambda k: cand_scores[k]["rmse"])
        d["ml_oof"] = cand_preds[best]
        oof_frames.append(d)

        final = CalibrationModel(op, cands[best], make_pipeline(cands[best])).fit(d)
        bundle["operations"][op] = final

        per_well = []
        for w, g in d.groupby("well_name"):
            per_well.append(
                {
                    "well_name": w,
                    "section": g.section.iloc[0],
                    "well_type": g.well_type.iloc[0],
                    "wellplan": all_metrics(g.target, g.wp_base),
                    "ml": all_metrics(g.target, g.ml_oof),
                }
            )
        per_well.sort(key=lambda r: -r["ml"]["rmse"])
        metrics["operations"][op] = {
            "chosen": best,
            "chosen_spec": cands[best],
            "candidates": cand_scores,
            "overall": {
                "wellplan": all_metrics(d.target, d.wp_base),
                "ml": all_metrics(d.target, d.ml_oof),
                "n_wells": int(d.well_name.nunique()),
            },
            "by_section": group_report(d, "ml_oof", ["section"]),
            "by_type": group_report(d, "ml_oof", ["well_type"]),
            "by_section_type": group_report(d, "ml_oof", ["section", "well_type"]),
            "per_well": per_well,
        }

    if not bundle["operations"]:
        raise ValueError("Tidak ada operasi yang bisa dilatih. " + "; ".join(metrics["notes"]))

    wells_tbl = ds.drop_duplicates("well_name")[["well_name", "section", "well_type"]]
    combos = wells_tbl.groupby(["section", "well_type"]).size()
    bundle["train_combos"] = {f"{s}|{t}": int(n) for (s, t), n in combos.items()}
    bundle["train_sections"] = sorted(wells_tbl.section.unique().tolist())
    bundle["train_types"] = sorted(wells_tbl.well_type.unique().tolist())
    bundle["depth_range_m"] = [float(ds.depth_m.min()), float(ds.depth_m.max())]
    bundle["trained_well_ids"] = sorted(int(x) for x in ds.well_id.unique())
    bundle["versions"] = {"sklearn": sklearn.__version__, "xgboost": xgboost.__version__}
    bundle["baseline_ff"] = BASELINE_FF

    metrics["dataset"] = {
        "rows": int(len(ds)),
        "wells": int(n_wells),
        "train_combos": bundle["train_combos"],
    }

    settings.model_dir.mkdir(parents=True, exist_ok=True)
    path = Path(settings.model_dir) / f"model_{model_row.id}.joblib"
    joblib.dump(bundle, path)

    model_row.path = str(path)
    model_row.metrics = _json_safe(metrics)
    model_row.params = _json_safe(
        {
            "algorithm": algorithm,
            "chosen": {op: m["chosen"] for op, m in metrics["operations"].items()},
            "xgb_grid": XGB_GRID,
            "xgb_fixed": XGB_FIXED,
            "ridge_alpha": RIDGE_ALPHA,
            "baseline_ff": BASELINE_FF,
            "versions": bundle["versions"],
        }
    )
    _save_oof(db, model_row, pd.concat(oof_frames, ignore_index=True), bundle)

    db.execute(update(MLModel).values(active=False))
    model_row.active = True
    model_row.status = "selesai"
    model_row.finished_at = datetime.now(UTC)
    db.commit()
    return model_row


def _save_oof(db: Session, model_row: MLModel, oof: pd.DataFrame, bundle: dict) -> None:
    """Prediksi out-of-fold di seluruh grid kedalaman WellPlan tiap sumur latih.

    Untuk sumur X, model dilatih ulang tanpa X lalu memprediksi grid X. Dengan
    leave-one-well-out ini berarti satu model per sumur per operasi."""
    ds_ids = oof.well_id.unique().tolist()
    wells = dsm.load_wells(db, ds_ids)
    plan, survey = dsm.load_plan(db, ds_ids), dsm.load_survey(db, ds_ids)
    full_ds = oof
    db.execute(
        delete(Prediction).where(Prediction.kind == "oof", Prediction.model_id == model_row.id)
    )
    preds: dict[int, Prediction] = {}
    for op, cm in bundle["operations"].items():
        d = full_ds[full_ds.operation == op]
        for _, w in wells.iterrows():
            train_part = d[d.well_name != w.well_name]
            if train_part.well_name.nunique() < 2:
                continue
            grid = dsm.plan_grid(db, int(w.well_id))
            if not len(grid):
                continue
            feats = dsm.features_frame(w, op, grid, plan, survey).dropna(subset=["wp_base"])
            if feats.empty:
                continue
            for c in ("section", "well_type"):
                feats[c] = feats[c].fillna("tidak diketahui")
            m = CalibrationModel(op, cm.spec, make_pipeline(cm.spec)).fit(train_part)
            yhat = m.predict(feats)
            pred = preds.get(int(w.well_id))
            if pred is None:
                pred = Prediction(well_id=int(w.well_id), model_id=model_row.id, kind="oof")
                db.add(pred)
                db.flush()
                preds[int(w.well_id)] = pred
            db.add_all(
                PredictionPoint(
                    prediction_id=pred.id,
                    operation=op,
                    depth_m=float(dep),
                    wellplan_si=float(wp),
                    ml_si=float(y),
                )
                for dep, wp, y in zip(feats.depth_m, feats.wp_base, yhat, strict=True)
            )
    db.flush()


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


def run_training_job(model_id: int, algorithm: str) -> None:
    """Dijalankan sebagai proses latar belakang FastAPI dengan sesi DB sendiri."""
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        row = db.get(MLModel, model_id)
        try:
            train(db, row, algorithm)
        except Exception as exc:
            db.rollback()
            row = db.get(MLModel, model_id)
            row.status = "gagal"
            row.message = str(exc)
            row.finished_at = datetime.now(UTC)
            db.commit()
            log.error("Pelatihan model %s gagal: %s\n%s", model_id, exc, traceback.format_exc())
    finally:
        db.close()


def active_model(db: Session) -> MLModel | None:
    return db.scalar(select(MLModel).where(MLModel.active.is_(True), MLModel.status == "selesai"))
