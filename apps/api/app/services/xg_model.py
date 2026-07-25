"""Production xG model loading and prediction helpers.

The active model artifact is versioned under `models/xg/{version}` and uses the
shared feature builder from `Data/xg_features.py`. Penalties are assigned a fixed
value and are not predicted by the fitted classifier.
"""

from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd


STREAMLIT_ROOT = Path(__file__).resolve().parents[4]
if str(STREAMLIT_ROOT) not in sys.path:
    sys.path.insert(0, str(STREAMLIT_ROOT))

from Data.xg_features import (  # noqa: E402
    CATEGORICAL_FEATURES,
    MODEL_VERSION,
    NUMERIC_FEATURES,
    PENALTY_XG,
    build_shot_feature_table,
    own_goal_mask,
    shot_mask,
)


DEFAULT_XG_VERSION = "v2"
DEFAULT_ARTIFACT_DIR = STREAMLIT_ROOT / "models" / "xg"


class XGModelUnavailable(RuntimeError):
    """Raised when the configured xG model artifact cannot be loaded."""


@lru_cache(maxsize=4)
def load_xg_artifact(version: str = DEFAULT_XG_VERSION, artifact_dir: str | None = None) -> dict[str, Any]:
    root = Path(artifact_dir) if artifact_dir else DEFAULT_ARTIFACT_DIR
    model_dir = root / version
    model_path = model_dir / "model.joblib"
    schema_path = model_dir / "feature_schema.json"
    if not model_path.exists() or not schema_path.exists():
        raise XGModelUnavailable(f"xG model artifact not found under {model_dir}")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    model = joblib.load(model_path)
    return {"version": version, "model": model, "schema": schema}


def predict_shot_xg(
    events: pd.DataFrame,
    version: str = DEFAULT_XG_VERSION,
    artifact_dir: str | None = None,
) -> pd.DataFrame:
    """Return one row per shot with predicted xG and feature debug fields."""

    shots = build_shot_feature_table(events)
    if shots.empty:
        return pd.DataFrame(columns=["matchId", "eventId", "xG", "xg_model_version"])

    artifact = load_xg_artifact(version=version, artifact_dir=artifact_dir)
    model = artifact["model"]
    feature_columns = NUMERIC_FEATURES + CATEGORICAL_FEATURES
    missing = [column for column in feature_columns if column not in shots.columns]
    if missing:
        raise ValueError(f"xG feature table missing required columns: {missing}")

    xg = np.full(len(shots), np.nan, dtype=float)
    penalty_mask = shots["shot_family"].eq("penalty").to_numpy()
    xg[penalty_mask] = PENALTY_XG
    model_mask = ~penalty_mask
    if model_mask.any():
        xg[model_mask] = np.clip(model.predict_proba(shots.loc[model_mask, feature_columns])[:, 1], 0.003, 0.95)

    result = shots[
        [
            "matchId",
            "eventId",
            "type",
            "playerName",
            "teamName",
            "shot_family",
            "shot_distance",
            "shot_angle",
        ]
    ].copy()
    result["xG"] = np.clip(xg, 0, 1)
    result["xg_model_version"] = version
    result["xg_feature_version"] = MODEL_VERSION
    return result


def apply_shot_xg(
    events: pd.DataFrame,
    version: str = DEFAULT_XG_VERSION,
    artifact_dir: str | None = None,
    force: bool = False,
) -> pd.DataFrame:
    """Return an event dataframe with `xG` and model-version columns updated."""

    df = events.copy()
    if "xG" not in df.columns:
        df["xG"] = np.nan
    if "xg_model_version" not in df.columns:
        df["xg_model_version"] = None
    if "eventId" not in df.columns:
        raise ValueError("Cannot apply xG predictions without eventId column.")

    own_goals = own_goal_mask(df)
    if own_goals.any():
        df.loc[own_goals, "xG"] = 0.0
        df.loc[own_goals, "xg_model_version"] = version
        df.loc[own_goals, "xg_feature_version"] = MODEL_VERSION
        df.loc[own_goals, "xg_shot_family"] = "own_goal"

    predictions = predict_shot_xg(df, version=version, artifact_dir=artifact_dir)
    if predictions.empty:
        return df

    eligible_rows = shot_mask(df)
    key_cols = ["matchId", "eventId"] if "matchId" in df.columns and "matchId" in predictions.columns else ["eventId"]
    by_event: dict[Any, pd.Series] = {}
    for _, pred in predictions.iterrows():
        event_key = tuple(pred.get(col) for col in key_cols) if len(key_cols) > 1 else pred.get("eventId")
        by_event.setdefault(event_key, pred)

    for idx, row in df.iterrows():
        if not bool(eligible_rows.loc[idx]):
            continue
        event_key = tuple(row.get(col) for col in key_cols) if len(key_cols) > 1 else row.get("eventId")
        pred = by_event.get(event_key)
        if pred is None:
            continue
        current_version = row.get("xg_model_version")
        if current_version == version and not force:
            continue
        df.at[idx, "xG"] = float(pred["xG"])
        df.at[idx, "xg_model_version"] = version
        df.at[idx, "xg_feature_version"] = MODEL_VERSION
        df.at[idx, "xg_shot_distance"] = float(pred["shot_distance"])
        df.at[idx, "xg_shot_angle"] = float(pred["shot_angle"])
        df.at[idx, "xg_shot_family"] = str(pred["shot_family"])
    return df
