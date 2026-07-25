"""Train and evaluate provider-style xA models from the canonical pass table.

Examples:
  apps/api/.venv/bin/python Data/train_xa_model.py
  apps/api/.venv/bin/python Data/train_xa_model.py --input models/data/xa_training_passes.parquet --version v1
"""

from __future__ import annotations

import argparse
import json
import subprocess
import warnings
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.frozen import FrozenEstimator
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBClassifier

from xa_features import CATEGORICAL_FEATURES, MODEL_VERSION, NUMERIC_FEATURES, training_frame


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "models" / "data" / "xa_training_passes.parquet"
DEFAULT_OUTPUT_DIR = ROOT / "models" / "xa"
LEGACY_MODEL = ROOT / "Data" / "expected_assist_model.pkl"
LEGACY_ENCODER = ROOT / "Data" / "xA_encoder.pkl"
LEGACY_SCALER = ROOT / "Data" / "xA_scaler.pkl"


def _one_hot_encoder() -> OneHotEncoder:
    try:
        return OneHotEncoder(handle_unknown="ignore", min_frequency=50, sparse_output=True)
    except TypeError:
        return OneHotEncoder(handle_unknown="ignore", min_frequency=50, sparse=True)


def _preprocessor(scale_numeric: bool = False) -> ColumnTransformer:
    numeric_steps: list[tuple[str, Any]] = [("imputer", SimpleImputer(strategy="median"))]
    if scale_numeric:
        numeric_steps.append(("scale", StandardScaler()))
    return ColumnTransformer(
        transformers=[
            ("num", Pipeline(numeric_steps), NUMERIC_FEATURES),
            (
                "cat",
                Pipeline([("imputer", SimpleImputer(strategy="most_frequent")), ("onehot", _one_hot_encoder())]),
                CATEGORICAL_FEATURES,
            ),
        ],
        remainder="drop",
    )


def _time_split(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    df = frame.copy()
    if "startDate" in df.columns:
        df["_split_date"] = pd.to_datetime(df["startDate"], errors="coerce")
    else:
        df["_split_date"] = pd.NaT
    if df["_split_date"].notna().sum() > len(df) * 0.5:
        df = df.sort_values(["_split_date", "matchId", "eventId"], kind="mergesort")
    else:
        df = df.sort_values(["matchId", "eventId"], kind="mergesort")

    match_ids = df["matchId"].drop_duplicates().tolist()
    if len(match_ids) < 5:
        raise RuntimeError("Need at least five matches for a train/calibration/test split.")
    train_end = max(1, int(len(match_ids) * 0.7))
    cal_end = max(train_end + 1, int(len(match_ids) * 0.85))
    train_ids = set(match_ids[:train_end])
    cal_ids = set(match_ids[train_end:cal_end])
    test_ids = set(match_ids[cal_end:])
    train = df[df["matchId"].isin(train_ids)].drop(columns=["_split_date"])
    cal = df[df["matchId"].isin(cal_ids)].drop(columns=["_split_date"])
    test = df[df["matchId"].isin(test_ids)].drop(columns=["_split_date"])
    return train, cal, test


def _expected_calibration_error(y_true: np.ndarray, y_pred: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0, 1, bins + 1)
    ece = 0.0
    for low, high in zip(edges[:-1], edges[1:]):
        mask = (y_pred >= low) & (y_pred < high if high < 1 else y_pred <= high)
        if not mask.any():
            continue
        ece += mask.mean() * abs(float(y_true[mask].mean()) - float(y_pred[mask].mean()))
    return float(ece)


def _metrics_from_prediction(name: str, frame: pd.DataFrame, pred: np.ndarray) -> dict:
    y = frame["xa_model_target"].astype(int).to_numpy()
    pred = np.clip(pred, 1e-8, 1 - 1e-8)
    return {
        "model": name,
        "passes": int(len(frame)),
        "assists": int(y.sum()),
        "assist_rate": round(float(y.mean()), 6),
        "log_loss": round(float(log_loss(y, pred)), 6),
        "brier": round(float(brier_score_loss(y, pred)), 8),
        "roc_auc": round(float(roc_auc_score(y, pred)), 6) if len(np.unique(y)) > 1 else None,
        "average_precision": round(float(average_precision_score(y, pred)), 6) if len(np.unique(y)) > 1 else None,
        "calibration_error": round(_expected_calibration_error(y, pred), 8),
        "predicted_xa_total": round(float(pred.sum()), 3),
        "actual_assists": int(y.sum()),
    }


def _metrics(name: str, model, frame: pd.DataFrame) -> dict:
    x = frame[NUMERIC_FEATURES + CATEGORICAL_FEATURES]
    pred = model.predict_proba(x)[:, 1]
    return _metrics_from_prediction(name, frame, pred)


def _scale_pos_weight(frame: pd.DataFrame) -> float:
    y = frame["xa_model_target"].astype(int)
    positives = max(1, int(y.sum()))
    negatives = max(1, int(len(y) - positives))
    return min(negatives / positives, 500.0)


def _xgb_pipeline(scale_pos_weight: float) -> Pipeline:
    return Pipeline(
        [
            ("preprocess", _preprocessor(scale_numeric=False)),
            (
                "model",
                XGBClassifier(
                    n_estimators=450,
                    max_depth=3,
                    learning_rate=0.045,
                    subsample=0.88,
                    colsample_bytree=0.88,
                    min_child_weight=8,
                    reg_lambda=5.0,
                    objective="binary:logistic",
                    eval_metric="logloss",
                    scale_pos_weight=scale_pos_weight,
                    random_state=42,
                    n_jobs=4,
                ),
            ),
        ]
    )


def _logistic_pipeline() -> Pipeline:
    return Pipeline(
        [
            ("preprocess", _preprocessor(scale_numeric=True)),
            ("model", LogisticRegression(max_iter=2000, C=0.6, class_weight="balanced", n_jobs=4)),
        ]
    )


def _calibrate_prefit(model, cal: pd.DataFrame) -> CalibratedClassifierCV:
    calibrator = CalibratedClassifierCV(FrozenEstimator(model), method="sigmoid")
    calibrator.fit(cal[NUMERIC_FEATURES + CATEGORICAL_FEATURES], cal["xa_model_target"].astype(int))
    return calibrator


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return None


def _legacy_predictions(frame: pd.DataFrame) -> np.ndarray | None:
    if not (LEGACY_MODEL.exists() and LEGACY_ENCODER.exists() and LEGACY_SCALER.exists()):
        return None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = joblib.load(LEGACY_MODEL)
            encoder = joblib.load(LEGACY_ENCODER)
            scaler = joblib.load(LEGACY_SCALER)
        legacy = frame[["x", "y", "endX", "endY", "pass_distance", "pass_angle", "pass_type", "play_pattern"]].copy()
        legacy["Pass_Type"] = legacy["pass_type"].replace({"headed": "header", "chipped": "ground_pass"})
        legacy["Play_Pattern"] = legacy["play_pattern"].replace({"corner": "open_play", "free_kick": "open_play", "counter": "open_play"})
        encoded = pd.DataFrame(
            encoder.transform(legacy[["Pass_Type", "Play_Pattern"]]),
            columns=encoder.get_feature_names_out(["Pass_Type", "Play_Pattern"]),
            index=legacy.index,
        )
        numeric = legacy[["x", "y", "endX", "endY", "pass_distance", "pass_angle"]].copy()
        numeric.loc[:, :] = scaler.transform(numeric)
        model_frame = pd.concat([numeric, encoded], axis=1)
        if hasattr(model, "feature_names_in_"):
            for column in model.feature_names_in_:
                if column not in model_frame.columns:
                    model_frame[column] = 0
            model_frame = model_frame[list(model.feature_names_in_)]
        return np.clip(model.predict(model_frame), 0, 1)
    except Exception as exc:
        print(f"Warning: legacy xA baseline failed: {exc}", flush=True)
        return None


def _group_report(frame: pd.DataFrame, model, columns: list[str]) -> dict:
    x = frame[NUMERIC_FEATURES + CATEGORICAL_FEATURES]
    pred = model.predict_proba(x)[:, 1]
    tmp = frame.copy()
    tmp["_pred_xa"] = pred
    out = {}
    for column in columns:
        if column not in tmp.columns:
            continue
        grouped = (
            tmp.groupby(column, dropna=False)
            .agg(passes=("xa_model_target", "size"), assists=("xa_model_target", "sum"), xa=("_pred_xa", "sum"))
            .sort_values("passes", ascending=False)
            .head(30)
        )
        out[column] = [
            {"value": str(idx), "passes": int(row.passes), "assists": int(row.assists), "xa": round(float(row.xa), 3)}
            for idx, row in grouped.iterrows()
        ]
    return out


def _extreme_examples(frame: pd.DataFrame, model) -> dict[str, list[dict]]:
    x = frame[NUMERIC_FEATURES + CATEGORICAL_FEATURES]
    tmp = frame.copy()
    tmp["_pred_xa"] = model.predict_proba(x)[:, 1]
    base_cols = [
        "matchId",
        "eventId",
        "minute",
        "second",
        "teamName",
        "playerName",
        "pass_type",
        "play_pattern",
        "pass_direction",
        "x",
        "y",
        "endX",
        "endY",
        "_pred_xa",
        "xa_model_target",
        "xa_is_direct_shot_assist",
        "xa_target_xg",
    ]
    cols = [col for col in base_cols if col in tmp.columns]
    high_non_assist = tmp[tmp["xa_model_target"].eq(0)].sort_values("_pred_xa", ascending=False).head(25)[cols]
    low_assist = tmp[tmp["xa_model_target"].eq(1)].sort_values("_pred_xa", ascending=True).head(25)[cols]
    return {
        "high_xa_non_assist_passes": high_non_assist.round(4).to_dict("records"),
        "low_xa_actual_assists": low_assist.round(4).to_dict("records"),
    }


def train_model(input_path: Path, output_dir: Path, version: str) -> dict:
    if not input_path.exists():
        raise FileNotFoundError(f"xA training pass table not found: {input_path}")
    passes = pd.read_parquet(input_path)
    frame = training_frame(passes)
    if len(frame) < 10_000:
        raise RuntimeError(f"Only {len(frame)} xA training passes found; build a larger dataset first.")

    train, cal, test = _time_split(frame)
    train_cal = pd.concat([train, cal], ignore_index=True)
    scale_pos_weight = _scale_pos_weight(train)

    candidates = {
        "logistic": (_logistic_pipeline(), train_cal),
        "xgboost": (_xgb_pipeline(scale_pos_weight), train),
    }

    fitted = {}
    metrics = []
    for name, (model, fit_frame) in candidates.items():
        print(f"Training {name} on {len(fit_frame):,} completed passes", flush=True)
        model.fit(fit_frame[NUMERIC_FEATURES + CATEGORICAL_FEATURES], fit_frame["xa_model_target"].astype(int))
        fitted[name] = model
        metrics.append(_metrics(name, model, test))

    print(f"Calibrating xgboost on {len(cal):,} completed passes", flush=True)
    calibrated_xgb = _calibrate_prefit(fitted["xgboost"], cal)
    fitted["xgboost_calibrated"] = calibrated_xgb
    metrics.append(_metrics("xgboost_calibrated", calibrated_xgb, test))

    legacy_pred = _legacy_predictions(test)
    if legacy_pred is not None:
        metrics.append(_metrics_from_prediction("legacy_rf", test, legacy_pred))

    selectable_metrics = [row for row in metrics if row["model"] != "legacy_rf"]
    metric_rank = sorted(selectable_metrics, key=lambda row: (row["log_loss"], row["brier"], row["calibration_error"]))
    best_name = metric_rank[0]["model"]
    best_model = fitted[best_name]

    artifact_dir = output_dir / version
    artifact_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(best_model, artifact_dir / "model.joblib")

    schema = {
        "version": version,
        "base_feature_version": MODEL_VERSION,
        "numeric_features": NUMERIC_FEATURES,
        "categorical_features": CATEGORICAL_FEATURES,
        "best_model": best_name,
        "training_input": str(input_path),
        "metric_definition": "provider_style_completed_pass_goal_assist_probability",
        "target_column": "xa_model_target",
    }
    (artifact_dir / "feature_schema.json").write_text(json.dumps(schema, indent=2), encoding="utf-8")

    report = {
        "version": version,
        "git_sha": _git_sha(),
        "input": str(input_path),
        "passes_total": int(len(passes)),
        "training_passes": int(len(frame)),
        "assist_targets": int(frame["xa_model_target"].sum()),
        "assist_rate": round(float(frame["xa_model_target"].mean()), 6),
        "scale_pos_weight": round(float(scale_pos_weight), 3),
        "split": {
            "train": int(len(train)),
            "calibration": int(len(cal)),
            "test": int(len(test)),
            "train_matches": int(train["matchId"].nunique()),
            "calibration_matches": int(cal["matchId"].nunique()),
            "test_matches": int(test["matchId"].nunique()),
            "train_assists": int(train["xa_model_target"].sum()),
            "calibration_assists": int(cal["xa_model_target"].sum()),
            "test_assists": int(test["xa_model_target"].sum()),
        },
        "metrics": metrics,
        "selected_model": best_name,
        "test_group_report": _group_report(test, best_model, ["league", "season", "pass_type", "play_pattern", "pass_direction", "end_third", "end_lane"]),
        "extreme_examples": _extreme_examples(test, best_model),
    }
    (artifact_dir / "metrics.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    markdown = [
        f"# xA Model {version}",
        "",
        f"Selected model: `{best_name}`",
        "",
        "Provider-style xA: modeled probability that a completed pass becomes a goal assist.",
        "",
        "## Test Metrics",
        "",
        "| Model | Log loss | Brier | ROC AUC | AP | Calib error | xA | Assists |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in metrics:
        markdown.append(
            f"| {row['model']} | {row['log_loss']} | {row['brier']} | {row['roc_auc']} | "
            f"{row['average_precision']} | {row['calibration_error']} | {row['predicted_xa_total']} | {row['actual_assists']} |"
        )
    markdown.extend(
        [
            "",
            "## Notes",
            "",
            "- Training universe is completed passes only.",
            "- Target is provider-style actual goal assist probability.",
            "- Direct shot-assist and linked shot xG columns are kept only for diagnostics and future xAG work.",
            "- Time-based match split is used for train/calibration/test.",
        ]
    )
    (artifact_dir / "report.md").write_text("\n".join(markdown), encoding="utf-8")

    print(json.dumps(report, indent=2, sort_keys=True), flush=True)
    print(f"Saved model artifact to {artifact_dir}", flush=True)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train candidate provider-style xA models.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Canonical completed-pass training parquet.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Directory for versioned model artifacts.")
    parser.add_argument("--version", default="v1", help="Artifact version name.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    train_model(args.input, args.output_dir, args.version)


if __name__ == "__main__":
    main()
