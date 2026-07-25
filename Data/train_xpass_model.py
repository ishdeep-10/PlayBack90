"""Train and evaluate expected-pass completion models.

Examples:
  apps/api/.venv/bin/python Data/train_xpass_model.py
  apps/api/.venv/bin/python Data/train_xpass_model.py --input models/data/xpass_training_passes.parquet --version v1
"""

from __future__ import annotations

import argparse
import json
import subprocess
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

from xpass_features import CATEGORICAL_FEATURES, MODEL_VERSION, NUMERIC_FEATURES, training_frame


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "models" / "data" / "xpass_training_passes.parquet"
DEFAULT_OUTPUT_DIR = ROOT / "models" / "xpass"


def _one_hot_encoder() -> OneHotEncoder:
    try:
        return OneHotEncoder(handle_unknown="ignore", min_frequency=100, sparse_output=True)
    except TypeError:
        return OneHotEncoder(handle_unknown="ignore", min_frequency=100, sparse=True)


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


def _expected_calibration_error(y_true: np.ndarray, y_pred: np.ndarray, bins: int = 15) -> float:
    edges = np.linspace(0, 1, bins + 1)
    ece = 0.0
    for low, high in zip(edges[:-1], edges[1:]):
        mask = (y_pred >= low) & (y_pred < high if high < 1 else y_pred <= high)
        if not mask.any():
            continue
        ece += mask.mean() * abs(float(y_true[mask].mean()) - float(y_pred[mask].mean()))
    return float(ece)


def _calibration_buckets(y_true: np.ndarray, y_pred: np.ndarray, bins: int = 10) -> list[dict[str, float | int]]:
    edges = np.linspace(0, 1, bins + 1)
    rows: list[dict[str, float | int]] = []
    for low, high in zip(edges[:-1], edges[1:]):
        mask = (y_pred >= low) & (y_pred < high if high < 1 else y_pred <= high)
        rows.append(
            {
                "low": round(float(low), 2),
                "high": round(float(high), 2),
                "passes": int(mask.sum()),
                "predicted_completion": round(float(y_pred[mask].mean()), 5) if mask.any() else None,
                "actual_completion": round(float(y_true[mask].mean()), 5) if mask.any() else None,
            }
        )
    return rows


def _metrics_from_prediction(name: str, frame: pd.DataFrame, pred: np.ndarray) -> dict[str, Any]:
    y = frame["xpass_completed"].astype(int).to_numpy()
    pred = np.clip(pred, 1e-8, 1 - 1e-8)
    completed = int(y.sum())
    expected = float(pred.sum())
    return {
        "model": name,
        "passes": int(len(frame)),
        "completed": completed,
        "completion_rate": round(float(y.mean()), 6),
        "log_loss": round(float(log_loss(y, pred)), 6),
        "brier": round(float(brier_score_loss(y, pred)), 8),
        "roc_auc": round(float(roc_auc_score(y, pred)), 6) if len(np.unique(y)) > 1 else None,
        "average_precision": round(float(average_precision_score(y, pred)), 6) if len(np.unique(y)) > 1 else None,
        "calibration_error": round(_expected_calibration_error(y, pred), 8),
        "predicted_completed_total": round(expected, 3),
        "actual_completed_total": completed,
        "completion_over_expected": round(float(completed - expected), 3),
    }


def _metrics(name: str, model, frame: pd.DataFrame) -> dict[str, Any]:
    x = frame[NUMERIC_FEATURES + CATEGORICAL_FEATURES]
    pred = model.predict_proba(x)[:, 1]
    return _metrics_from_prediction(name, frame, pred)


def _xgb_pipeline() -> Pipeline:
    return Pipeline(
        [
            ("preprocess", _preprocessor(scale_numeric=False)),
            (
                "model",
                XGBClassifier(
                    n_estimators=500,
                    max_depth=5,
                    learning_rate=0.05,
                    subsample=0.88,
                    colsample_bytree=0.88,
                    min_child_weight=20,
                    reg_lambda=3.0,
                    objective="binary:logistic",
                    eval_metric="logloss",
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
            ("model", LogisticRegression(max_iter=1000, C=1.0, n_jobs=4)),
        ]
    )


def _calibrate_prefit(model, cal: pd.DataFrame) -> CalibratedClassifierCV:
    calibrator = CalibratedClassifierCV(FrozenEstimator(model), method="sigmoid")
    calibrator.fit(cal[NUMERIC_FEATURES + CATEGORICAL_FEATURES], cal["xpass_completed"].astype(int))
    return calibrator


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return None


def _group_report(frame: pd.DataFrame, model, columns: list[str]) -> dict[str, list[dict[str, Any]]]:
    pred = model.predict_proba(frame[NUMERIC_FEATURES + CATEGORICAL_FEATURES])[:, 1]
    tmp = frame.copy()
    tmp["_pred_xpass"] = pred
    out: dict[str, list[dict[str, Any]]] = {}
    for column in columns:
        if column not in tmp.columns:
            continue
        grouped = (
            tmp.groupby(column, dropna=False)
            .agg(passes=("xpass_completed", "size"), completed=("xpass_completed", "sum"), xpass=("_pred_xpass", "sum"))
            .sort_values("passes", ascending=False)
            .head(40)
        )
        out[column] = [
            {
                "value": str(idx),
                "passes": int(row.passes),
                "completed": int(row.completed),
                "xpass": round(float(row.xpass), 3),
                "completion_over_expected": round(float(row.completed - row.xpass), 3),
            }
            for idx, row in grouped.iterrows()
        ]
    return out


def _player_over_expected(frame: pd.DataFrame, model, min_attempts: int = 500) -> dict[str, list[dict[str, Any]]]:
    pred = model.predict_proba(frame[NUMERIC_FEATURES + CATEGORICAL_FEATURES])[:, 1]
    tmp = frame.copy()
    tmp["_pred_xpass"] = pred
    grouped = (
        tmp.groupby(["playerName", "teamName"], dropna=False)
        .agg(passes=("xpass_completed", "size"), completed=("xpass_completed", "sum"), xpass=("_pred_xpass", "sum"))
        .reset_index()
    )
    grouped = grouped[grouped["passes"] >= min_attempts].copy()
    if grouped.empty:
        return {"top": [], "bottom": []}
    grouped["completion_over_expected"] = grouped["completed"] - grouped["xpass"]
    grouped["completion_over_expected_per_100"] = 100.0 * grouped["completion_over_expected"] / grouped["passes"]
    grouped["completion_rate"] = grouped["completed"] / grouped["passes"]
    columns = [
        "playerName",
        "teamName",
        "passes",
        "completed",
        "xpass",
        "completion_rate",
        "completion_over_expected",
        "completion_over_expected_per_100",
    ]
    return {
        "top": grouped.sort_values("completion_over_expected_per_100", ascending=False).head(25)[columns].round(4).to_dict("records"),
        "bottom": grouped.sort_values("completion_over_expected_per_100", ascending=True).head(25)[columns].round(4).to_dict("records"),
    }


def _extreme_examples(frame: pd.DataFrame, model) -> dict[str, list[dict[str, Any]]]:
    pred = model.predict_proba(frame[NUMERIC_FEATURES + CATEGORICAL_FEATURES])[:, 1]
    tmp = frame.copy()
    tmp["_pred_xpass"] = pred
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
        "_pred_xpass",
        "xpass_completed",
    ]
    cols = [col for col in base_cols if col in tmp.columns]
    hard_completed = tmp[tmp["xpass_completed"].eq(1)].sort_values("_pred_xpass", ascending=True).head(30)[cols]
    easy_failed = tmp[tmp["xpass_completed"].eq(0)].sort_values("_pred_xpass", ascending=False).head(30)[cols]
    return {
        "hardest_completed_passes": hard_completed.round(4).to_dict("records"),
        "easiest_failed_passes": easy_failed.round(4).to_dict("records"),
    }


def train_model(input_path: Path, output_dir: Path, version: str) -> dict[str, Any]:
    if not input_path.exists():
        raise FileNotFoundError(f"xPass training pass table not found: {input_path}")
    passes = pd.read_parquet(input_path)
    frame = training_frame(passes)
    if len(frame) < 10_000:
        raise RuntimeError(f"Only {len(frame)} xPass training passes found; build a larger dataset first.")

    train, cal, test = _time_split(frame)
    train_cal = pd.concat([train, cal], ignore_index=True)
    candidates = {
        "logistic": (_logistic_pipeline(), train_cal),
        "xgboost": (_xgb_pipeline(), train),
    }

    fitted: dict[str, Any] = {}
    metrics: list[dict[str, Any]] = []
    for name, (model, fit_frame) in candidates.items():
        print(f"Training {name} on {len(fit_frame):,} attempted passes", flush=True)
        model.fit(fit_frame[NUMERIC_FEATURES + CATEGORICAL_FEATURES], fit_frame["xpass_completed"].astype(int))
        fitted[name] = model
        metrics.append(_metrics(name, model, test))

    print(f"Calibrating xgboost on {len(cal):,} attempted passes", flush=True)
    calibrated_xgb = _calibrate_prefit(fitted["xgboost"], cal)
    fitted["xgboost_calibrated"] = calibrated_xgb
    metrics.append(_metrics("xgboost_calibrated", calibrated_xgb, test))

    metric_rank = sorted(metrics, key=lambda row: (row["log_loss"], row["brier"], row["calibration_error"]))
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
        "metric_definition": "attempted_pass_completion_probability",
        "target_column": "xpass_completed",
    }
    (artifact_dir / "feature_schema.json").write_text(json.dumps(schema, indent=2), encoding="utf-8")

    best_pred = np.clip(best_model.predict_proba(test[NUMERIC_FEATURES + CATEGORICAL_FEATURES])[:, 1], 1e-8, 1 - 1e-8)
    y_test = test["xpass_completed"].astype(int).to_numpy()
    report = {
        "version": version,
        "git_sha": _git_sha(),
        "input": str(input_path),
        "passes_total": int(len(passes)),
        "training_passes": int(len(frame)),
        "completed_passes": int(frame["xpass_completed"].sum()),
        "completion_rate": round(float(frame["xpass_completed"].mean()), 6),
        "split": {
            "train": int(len(train)),
            "calibration": int(len(cal)),
            "test": int(len(test)),
            "train_matches": int(train["matchId"].nunique()),
            "calibration_matches": int(cal["matchId"].nunique()),
            "test_matches": int(test["matchId"].nunique()),
            "train_completion_rate": round(float(train["xpass_completed"].mean()), 6),
            "calibration_completion_rate": round(float(cal["xpass_completed"].mean()), 6),
            "test_completion_rate": round(float(test["xpass_completed"].mean()), 6),
        },
        "metrics": metrics,
        "selected_model": best_name,
        "selected_model_calibration_buckets": _calibration_buckets(y_test, best_pred),
        "test_group_report": _group_report(test, best_model, ["league", "season", "pass_type", "play_pattern", "pass_direction", "end_third", "end_lane"]),
        "player_over_expected": _player_over_expected(test, best_model),
        "extreme_examples": _extreme_examples(test, best_model),
    }
    (artifact_dir / "metrics.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    markdown = [
        f"# xPass Model {version}",
        "",
        f"Selected model: `{best_name}`",
        "",
        "xPass: modeled probability that an attempted pass is completed.",
        "",
        "## Test Metrics",
        "",
        "| Model | Log loss | Brier | ROC AUC | AP | Calib error | xPass completed | Actual completed | +/- Expected |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in metrics:
        markdown.append(
            f"| {row['model']} | {row['log_loss']} | {row['brier']} | {row['roc_auc']} | "
            f"{row['average_precision']} | {row['calibration_error']} | {row['predicted_completed_total']} | "
            f"{row['actual_completed_total']} | {row['completion_over_expected']} |"
        )
    markdown.extend(
        [
            "",
            "## Notes",
            "",
            "- Training universe is attempted pass rows.",
            "- Target is pass completion.",
            "- Outcome-specific accurate/inaccurate flags are not model inputs; they are only collapsed into neutral pass type/play pattern categories.",
            "- Time-based match split is used for train/calibration/test.",
        ]
    )
    (artifact_dir / "report.md").write_text("\n".join(markdown), encoding="utf-8")

    print(json.dumps(report, indent=2, sort_keys=True), flush=True)
    print(f"Saved model artifact to {artifact_dir}", flush=True)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train candidate expected-pass models.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Canonical attempted-pass training parquet.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Directory for versioned model artifacts.")
    parser.add_argument("--version", default="v1", help="Artifact version name.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    train_model(args.input, args.output_dir, args.version)


if __name__ == "__main__":
    main()
