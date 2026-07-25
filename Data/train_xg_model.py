"""
Train and evaluate candidate xG models from the canonical shot table.

Examples:
  python Data/train_xg_model.py
  python Data/train_xg_model.py --input models/data/xg_training_shots.parquet --version v2
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
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBClassifier

from xg_features import CATEGORICAL_FEATURES, NUMERIC_FEATURES, MODEL_VERSION, training_frame


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "models" / "data" / "xg_training_shots.parquet"
DEFAULT_OUTPUT_DIR = ROOT / "models" / "xg"


def _one_hot_encoder() -> OneHotEncoder:
    try:
        return OneHotEncoder(handle_unknown="ignore", min_frequency=10, sparse_output=True)
    except TypeError:
        return OneHotEncoder(handle_unknown="ignore", min_frequency=10, sparse=True)


def _preprocessor(scale_numeric: bool = False) -> ColumnTransformer:
    numeric_steps: list[tuple[str, Any]] = [("imputer", SimpleImputer(strategy="median"))]
    if scale_numeric:
        numeric_steps.append(("scale", StandardScaler()))
    return ColumnTransformer(
        transformers=[
            ("num", Pipeline(numeric_steps), NUMERIC_FEATURES),
            ("cat", Pipeline([("imputer", SimpleImputer(strategy="most_frequent")), ("onehot", _one_hot_encoder())]), CATEGORICAL_FEATURES),
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


def _metrics(name: str, model, frame: pd.DataFrame) -> dict:
    x = frame[NUMERIC_FEATURES + CATEGORICAL_FEATURES]
    y = frame["isGoal"].astype(int).to_numpy()
    pred = np.clip(model.predict_proba(x)[:, 1], 1e-6, 1 - 1e-6)
    return {
        "model": name,
        "shots": int(len(frame)),
        "goals": int(y.sum()),
        "goal_rate": round(float(y.mean()), 5),
        "log_loss": round(float(log_loss(y, pred)), 6),
        "brier": round(float(brier_score_loss(y, pred)), 6),
        "roc_auc": round(float(roc_auc_score(y, pred)), 6) if len(np.unique(y)) > 1 else None,
        "average_precision": round(float(average_precision_score(y, pred)), 6) if len(np.unique(y)) > 1 else None,
        "calibration_error": round(_expected_calibration_error(y, pred), 6),
        "predicted_xg_total": round(float(pred.sum()), 3),
        "actual_goals": int(y.sum()),
    }


def _xgb_pipeline() -> Pipeline:
    return Pipeline(
        [
            ("preprocess", _preprocessor(scale_numeric=False)),
            (
                "model",
                XGBClassifier(
                    n_estimators=650,
                    max_depth=3,
                    learning_rate=0.035,
                    subsample=0.86,
                    colsample_bytree=0.86,
                    min_child_weight=8,
                    reg_lambda=4.0,
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
            ("model", LogisticRegression(max_iter=2000, C=0.8, class_weight="balanced", n_jobs=4)),
        ]
    )


def _calibrated_xgb_pipeline() -> CalibratedClassifierCV:
    try:
        return CalibratedClassifierCV(estimator=_xgb_pipeline(), method="sigmoid", cv=3)
    except TypeError:
        return CalibratedClassifierCV(base_estimator=_xgb_pipeline(), method="sigmoid", cv=3)


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return None


def _group_report(frame: pd.DataFrame, model, columns: list[str]) -> dict:
    x = frame[NUMERIC_FEATURES + CATEGORICAL_FEATURES]
    pred = model.predict_proba(x)[:, 1]
    tmp = frame.copy()
    tmp["_pred_xg"] = pred
    out = {}
    for column in columns:
        if column not in tmp.columns:
            continue
        grouped = (
            tmp.groupby(column, dropna=False)
            .agg(shots=("isGoal", "size"), goals=("isGoal", "sum"), xg=("_pred_xg", "sum"))
            .sort_values("shots", ascending=False)
            .head(30)
        )
        out[column] = [
            {"value": str(idx), "shots": int(row.shots), "goals": int(row.goals), "xg": round(float(row.xg), 3)}
            for idx, row in grouped.iterrows()
        ]
    return out


def train_model(input_path: Path, output_dir: Path, version: str) -> dict:
    if not input_path.exists():
        raise FileNotFoundError(f"Training shot table not found: {input_path}")
    shots = pd.read_parquet(input_path)
    frame = training_frame(shots, include_penalties=False)
    if len(frame) < 500:
        raise RuntimeError(f"Only {len(frame)} non-penalty training shots found; build a larger dataset first.")

    train, cal, test = _time_split(frame)
    train_cal = pd.concat([train, cal], ignore_index=True)

    candidates = {
        "logistic": _logistic_pipeline(),
        "xgboost": _xgb_pipeline(),
        "xgboost_calibrated": _calibrated_xgb_pipeline(),
    }

    fitted = {}
    metrics = []
    for name, model in candidates.items():
        model.fit(train_cal[NUMERIC_FEATURES + CATEGORICAL_FEATURES], train_cal["isGoal"].astype(int))
        fitted[name] = model
        metrics.append(_metrics(name, model, test))

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
        "fixed_penalty_xg": 0.78,
        "best_model": best_name,
        "training_input": str(input_path),
    }
    (artifact_dir / "feature_schema.json").write_text(json.dumps(schema, indent=2), encoding="utf-8")

    report = {
        "version": version,
        "git_sha": _git_sha(),
        "input": str(input_path),
        "shots_total": int(len(shots)),
        "training_shots_non_penalty": int(len(frame)),
        "split": {
            "train": int(len(train)),
            "calibration": int(len(cal)),
            "test": int(len(test)),
            "train_matches": int(train["matchId"].nunique()),
            "calibration_matches": int(cal["matchId"].nunique()),
            "test_matches": int(test["matchId"].nunique()),
        },
        "metrics": metrics,
        "selected_model": best_name,
        "test_group_report": _group_report(test, best_model, ["league", "season", "shot_family", "body_part", "situation_clean"]),
    }
    (artifact_dir / "metrics.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    markdown = [
        f"# xG Model {version}",
        "",
        f"Selected model: `{best_name}`",
        "",
        "## Test Metrics",
        "",
        "| Model | Log loss | Brier | ROC AUC | AP | Calib error | xG | Goals |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in metrics:
        markdown.append(
            f"| {row['model']} | {row['log_loss']} | {row['brier']} | {row['roc_auc']} | "
            f"{row['average_precision']} | {row['calibration_error']} | {row['predicted_xg_total']} | {row['actual_goals']} |"
        )
    markdown.extend(
        [
            "",
            "## Notes",
            "",
            "- Penalties are excluded from model fitting and assigned fixed xG = 0.78 in production/backfills.",
            "- Competition/league is included as a categorical model feature.",
            "- Time-based match split is used for train/calibration/test.",
        ]
    )
    (artifact_dir / "report.md").write_text("\n".join(markdown), encoding="utf-8")

    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"Saved model artifact to {artifact_dir}")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train candidate xG models.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Canonical shot training parquet.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Directory for versioned model artifacts.")
    parser.add_argument("--version", default="v2", help="Artifact version name.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    train_model(args.input, args.output_dir, args.version)


if __name__ == "__main__":
    main()
