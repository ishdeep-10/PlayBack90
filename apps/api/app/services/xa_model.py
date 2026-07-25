"""Production xA model loading and prediction helpers.

xA here is provider-style: the modeled probability that a completed pass becomes
a goal assist. It is not xAG / xG assisted.
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

from Data.xa_features import (  # noqa: E402
    CATEGORICAL_FEATURES,
    MODEL_VERSION,
    NUMERIC_FEATURES,
    build_pass_feature_table,
)


DEFAULT_XA_VERSION = "v1"
DEFAULT_ARTIFACT_DIR = STREAMLIT_ROOT / "models" / "xa"


class XAModelUnavailable(RuntimeError):
    """Raised when the configured xA model artifact cannot be loaded."""


@lru_cache(maxsize=4)
def load_xa_artifact(version: str = DEFAULT_XA_VERSION, artifact_dir: str | None = None) -> dict[str, Any]:
    root = Path(artifact_dir) if artifact_dir else DEFAULT_ARTIFACT_DIR
    model_dir = root / version
    model_path = model_dir / "model.joblib"
    schema_path = model_dir / "feature_schema.json"
    if not model_path.exists() or not schema_path.exists():
        raise XAModelUnavailable(f"xA model artifact not found under {model_dir}")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    model = joblib.load(model_path)
    return {"version": version, "model": model, "schema": schema}


def predict_pass_xa(
    events: pd.DataFrame,
    version: str = DEFAULT_XA_VERSION,
    artifact_dir: str | None = None,
) -> pd.DataFrame:
    """Return one row per completed pass with predicted provider-style xA."""

    passes = build_pass_feature_table(events)
    if passes.empty:
        return pd.DataFrame(columns=["matchId", "eventId", "xA", "xa_model_version"])

    artifact = load_xa_artifact(version=version, artifact_dir=artifact_dir)
    model = artifact["model"]
    feature_columns = NUMERIC_FEATURES + CATEGORICAL_FEATURES
    missing = [column for column in feature_columns if column not in passes.columns]
    if missing:
        raise ValueError(f"xA feature table missing required columns: {missing}")

    xa = np.clip(model.predict_proba(passes[feature_columns])[:, 1], 0, 1)
    result_columns = [
        "matchId",
        "eventId",
        "type",
        "outcomeType",
        "playerName",
        "teamName",
        "pass_type",
        "play_pattern",
        "pass_direction",
        "xa_is_direct_shot_assist",
        "xa_target_event_id",
        "xa_target_xg",
    ]
    result = passes[[column for column in result_columns if column in passes.columns]].copy()
    result["xA"] = xa
    result["xa_model_version"] = version
    result["xa_feature_version"] = MODEL_VERSION
    result["xa_pass_type"] = passes["xa_pass_type"]
    result["xa_play_pattern"] = passes["xa_play_pattern"]
    return result


def apply_pass_xa(
    events: pd.DataFrame,
    version: str = DEFAULT_XA_VERSION,
    artifact_dir: str | None = None,
    force: bool = False,
) -> pd.DataFrame:
    """Return an event dataframe with xA columns updated for completed pass rows."""

    df = events.copy()
    if "xA" not in df.columns:
        df["xA"] = np.nan
    if "xa_model_version" not in df.columns:
        df["xa_model_version"] = None
    if "eventId" not in df.columns:
        raise ValueError("Cannot apply xA predictions without eventId column.")

    predictions = predict_pass_xa(df, version=version, artifact_dir=artifact_dir)
    if predictions.empty:
        df["xA"] = pd.to_numeric(df["xA"], errors="coerce").fillna(0.0)
        return df

    key_cols = ["matchId", "eventId"] if "matchId" in df.columns and "matchId" in predictions.columns else ["eventId"]
    by_event: dict[Any, pd.Series] = {}
    for _, pred in predictions.iterrows():
        event_key = tuple(pred.get(col) for col in key_cols) if len(key_cols) > 1 else pred.get("eventId")
        by_event.setdefault(event_key, pred)

    for idx, row in df.iterrows():
        event_key = tuple(row.get(col) for col in key_cols) if len(key_cols) > 1 else row.get("eventId")
        pred = by_event.get(event_key)
        if pred is None:
            continue
        current_version = row.get("xa_model_version")
        if current_version == version and not force:
            continue
        df.at[idx, "xA"] = float(pred["xA"])
        df.at[idx, "xa_model_version"] = version
        df.at[idx, "xa_feature_version"] = MODEL_VERSION
        df.at[idx, "xa_pass_type"] = str(pred.get("xa_pass_type", ""))
        df.at[idx, "xa_play_pattern"] = str(pred.get("xa_play_pattern", ""))
        if "xa_is_direct_shot_assist" in pred.index:
            df.at[idx, "xa_is_direct_shot_assist"] = int(pred.get("xa_is_direct_shot_assist") or 0)
        if "xa_target_event_id" in pred.index and pd.notna(pred.get("xa_target_event_id")):
            df.at[idx, "xa_target_event_id"] = pred.get("xa_target_event_id")
        if "xa_target_xg" in pred.index and pd.notna(pred.get("xa_target_xg")):
            df.at[idx, "xa_target_xg"] = pred.get("xa_target_xg")

    df["xA"] = pd.to_numeric(df["xA"], errors="coerce").fillna(0.0)
    return df
