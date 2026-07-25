"""Production xGOT model loading and prediction helpers.

xGOT is a post-shot model. Off-target and blocked shots are assigned 0.0, while
on-target, unblocked shots are scored by the fitted classifier under
`models/xgot/{version}`.
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

from Data.xg_features import own_goal_mask, shot_mask  # noqa: E402
from Data.xgot_features import (  # noqa: E402
    CATEGORICAL_FEATURES,
    MODEL_VERSION,
    NUMERIC_FEATURES,
    build_xgot_feature_table,
)


DEFAULT_XGOT_VERSION = "v1"
DEFAULT_ARTIFACT_DIR = STREAMLIT_ROOT / "models" / "xgot"


class XGOTModelUnavailable(RuntimeError):
    """Raised when the configured xGOT model artifact cannot be loaded."""


@lru_cache(maxsize=4)
def load_xgot_artifact(version: str = DEFAULT_XGOT_VERSION, artifact_dir: str | None = None) -> dict[str, Any]:
    root = Path(artifact_dir) if artifact_dir else DEFAULT_ARTIFACT_DIR
    model_dir = root / version
    model_path = model_dir / "model.joblib"
    schema_path = model_dir / "feature_schema.json"
    if not model_path.exists() or not schema_path.exists():
        raise XGOTModelUnavailable(f"xGOT model artifact not found under {model_dir}")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    model = joblib.load(model_path)
    return {"version": version, "model": model, "schema": schema}


def predict_shot_xgot(
    events: pd.DataFrame,
    version: str = DEFAULT_XGOT_VERSION,
    artifact_dir: str | None = None,
) -> pd.DataFrame:
    """Return one row per shot with predicted xGOT and placement debug fields."""

    shots = build_xgot_feature_table(events)
    if shots.empty:
        return pd.DataFrame(columns=["matchId", "eventId", "xGOT", "xgot_model_version"])

    artifact = load_xgot_artifact(version=version, artifact_dir=artifact_dir)
    model = artifact["model"]
    feature_columns = NUMERIC_FEATURES + CATEGORICAL_FEATURES
    missing = [column for column in feature_columns if column not in shots.columns]
    if missing:
        raise ValueError(f"xGOT feature table missing required columns: {missing}")

    xgot = np.zeros(len(shots), dtype=float)
    model_mask = shots["xgot_training_eligible"].astype(bool).to_numpy()
    if model_mask.any():
        xgot[model_mask] = np.clip(model.predict_proba(shots.loc[model_mask, feature_columns])[:, 1], 0.001, 0.995)

    result = shots[
        [
            "matchId",
            "eventId",
            "type",
            "playerName",
            "teamName",
            "xG",
            "goal_mouth_y",
            "goal_mouth_z",
            "goal_mouth_zone",
            "xgot_is_on_target",
            "xgot_is_blocked",
            "xgot_zero_value",
            "xgot_training_eligible",
        ]
    ].copy()
    result["xGOT"] = np.clip(xgot, 0, 1)
    result["xgot_model_version"] = version
    result["xgot_feature_version"] = MODEL_VERSION
    return result


def apply_shot_xgot(
    events: pd.DataFrame,
    version: str = DEFAULT_XGOT_VERSION,
    artifact_dir: str | None = None,
    force: bool = False,
) -> pd.DataFrame:
    """Return an event dataframe with xGOT columns updated for shot rows."""

    df = events.copy()
    if "xGOT" not in df.columns:
        df["xGOT"] = np.nan
    if "xgot_model_version" not in df.columns:
        df["xgot_model_version"] = None
    for column in ("xgot_is_on_target", "xgot_is_blocked"):
        if column not in df.columns:
            df[column] = pd.Series(pd.NA, index=df.index, dtype="object")
        else:
            df[column] = df[column].astype("object")
    if "eventId" not in df.columns:
        raise ValueError("Cannot apply xGOT predictions without eventId column.")

    own_goals = own_goal_mask(df)
    if own_goals.any():
        df.loc[own_goals, "xGOT"] = 0.0
        df.loc[own_goals, "xgot_model_version"] = version
        df.loc[own_goals, "xgot_feature_version"] = MODEL_VERSION
        df.loc[own_goals, "xgot_shot_placement_zone"] = "own_goal"
        df.loc[own_goals, "xgot_is_on_target"] = False
        df.loc[own_goals, "xgot_is_blocked"] = False

    predictions = predict_shot_xgot(df, version=version, artifact_dir=artifact_dir)
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
        current_version = row.get("xgot_model_version")
        if current_version == version and not force:
            continue
        df.at[idx, "xGOT"] = float(pred["xGOT"])
        df.at[idx, "xgot_model_version"] = version
        df.at[idx, "xgot_feature_version"] = MODEL_VERSION
        df.at[idx, "xgot_goal_mouth_y"] = float(pred["goal_mouth_y"])
        df.at[idx, "xgot_goal_mouth_z"] = float(pred["goal_mouth_z"])
        df.at[idx, "xgot_shot_placement_zone"] = str(pred["goal_mouth_zone"])
        df.at[idx, "xgot_is_on_target"] = bool(pred["xgot_is_on_target"])
        df.at[idx, "xgot_is_blocked"] = bool(pred["xgot_is_blocked"])
    return df
