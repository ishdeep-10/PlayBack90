"""Production xPass model loading and prediction helpers.

xPass is the modeled probability that an attempted pass is completed. It is
assigned to all pass attempts, successful and unsuccessful.
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

from Data.xpass_features import (  # noqa: E402
    CATEGORICAL_FEATURES,
    MODEL_VERSION,
    NUMERIC_FEATURES,
    build_pass_feature_table,
)


DEFAULT_XPASS_VERSION = "v1"
DEFAULT_ARTIFACT_DIR = STREAMLIT_ROOT / "models" / "xpass"


class XPassModelUnavailable(RuntimeError):
    """Raised when the configured xPass model artifact cannot be loaded."""


@lru_cache(maxsize=4)
def load_xpass_artifact(version: str = DEFAULT_XPASS_VERSION, artifact_dir: str | None = None) -> dict[str, Any]:
    root = Path(artifact_dir) if artifact_dir else DEFAULT_ARTIFACT_DIR
    model_dir = root / version
    model_path = model_dir / "model.joblib"
    schema_path = model_dir / "feature_schema.json"
    if not model_path.exists() or not schema_path.exists():
        raise XPassModelUnavailable(f"xPass model artifact not found under {model_dir}")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    model = joblib.load(model_path)
    return {"version": version, "model": model, "schema": schema}


def predict_pass_xpass(
    events: pd.DataFrame,
    version: str = DEFAULT_XPASS_VERSION,
    artifact_dir: str | None = None,
) -> pd.DataFrame:
    """Return one row per attempted pass with predicted completion probability."""

    passes = build_pass_feature_table(events)
    if passes.empty:
        return pd.DataFrame(columns=["matchId", "eventId", "xPass", "xpass_model_version"])

    artifact = load_xpass_artifact(version=version, artifact_dir=artifact_dir)
    model = artifact["model"]
    feature_columns = NUMERIC_FEATURES + CATEGORICAL_FEATURES
    missing = [column for column in feature_columns if column not in passes.columns]
    if missing:
        raise ValueError(f"xPass feature table missing required columns: {missing}")

    xpass = np.clip(model.predict_proba(passes[feature_columns])[:, 1], 0, 1)
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
        "xpass_completed",
    ]
    result = passes[[column for column in result_columns if column in passes.columns]].copy()
    result["xPass"] = xpass
    result["xpass_model_version"] = version
    result["xpass_feature_version"] = MODEL_VERSION
    result["xpass_pass_type"] = passes["xpass_pass_type"]
    result["xpass_play_pattern"] = passes["xpass_play_pattern"]
    result["xpass_pass_direction"] = passes["xpass_pass_direction"]
    return result


def apply_pass_xpass(
    events: pd.DataFrame,
    version: str = DEFAULT_XPASS_VERSION,
    artifact_dir: str | None = None,
    force: bool = False,
) -> pd.DataFrame:
    """Return an event dataframe with xPass columns updated for pass rows."""

    df = events.copy()
    if "xPass" not in df.columns:
        df["xPass"] = np.nan
    if "xpass_model_version" not in df.columns:
        df["xpass_model_version"] = None
    if "eventId" not in df.columns:
        raise ValueError("Cannot apply xPass predictions without eventId column.")

    predictions = predict_pass_xpass(df, version=version, artifact_dir=artifact_dir)
    if predictions.empty:
        df["xPass"] = pd.to_numeric(df["xPass"], errors="coerce").fillna(0.0)
        return df

    pass_rows = df["type"].astype(str).eq("Pass") if "type" in df.columns else pd.Series(False, index=df.index)
    key_cols = ["matchId", "eventId"] if "matchId" in df.columns and "matchId" in predictions.columns else ["eventId"]
    by_event: dict[Any, pd.Series] = {}
    for _, pred in predictions.iterrows():
        event_key = tuple(pred.get(col) for col in key_cols) if len(key_cols) > 1 else pred.get("eventId")
        by_event.setdefault(event_key, pred)

    for idx, row in df.iterrows():
        if not bool(pass_rows.loc[idx]):
            continue
        event_key = tuple(row.get(col) for col in key_cols) if len(key_cols) > 1 else row.get("eventId")
        pred = by_event.get(event_key)
        if pred is None:
            continue
        current_version = row.get("xpass_model_version")
        if current_version == version and not force:
            continue
        df.at[idx, "xPass"] = float(pred["xPass"])
        df.at[idx, "xpass_model_version"] = version
        df.at[idx, "xpass_feature_version"] = MODEL_VERSION
        df.at[idx, "xpass_pass_type"] = str(pred.get("xpass_pass_type", ""))
        df.at[idx, "xpass_play_pattern"] = str(pred.get("xpass_play_pattern", ""))
        df.at[idx, "xpass_pass_direction"] = str(pred.get("xpass_pass_direction", ""))
        if "xpass_completed" in pred.index:
            df.at[idx, "xpass_completed"] = int(pred.get("xpass_completed") or 0)

    df["xPass"] = pd.to_numeric(df["xPass"], errors="coerce").fillna(0.0)
    return df
