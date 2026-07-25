"""Shared xGOT feature engineering utilities.

xGOT is a post-shot model. It starts from the shot-level feature table used by
the xG model, then adds goalmouth placement features and eligibility flags for
on-target shot training.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

try:
    from Data.xg_features import GOAL_Y, GOAL_WIDTH, build_shot_feature_table
except ModuleNotFoundError:
    from xg_features import GOAL_Y, GOAL_WIDTH, build_shot_feature_table


MODEL_VERSION = "xgot-v1-candidate"
GOAL_MOUTH_CENTER_Y = GOAL_Y
GOAL_MOUTH_LEFT_POST_Y = GOAL_Y - GOAL_WIDTH / 2
GOAL_MOUTH_RIGHT_POST_Y = GOAL_Y + GOAL_WIDTH / 2
GOAL_MOUTH_CROSSBAR_Z = 38.0
SHOT_ON_TARGET_TYPES = {"Goal", "SavedShot", "ShotOnPost"}

NUMERIC_FEATURES = [
    "xG",
    "x",
    "y",
    "shot_distance",
    "shot_angle",
    "goal_mouth_y",
    "goal_mouth_z",
    "goal_mouth_y_centered",
    "goal_mouth_z_normalized",
    "goal_mouth_distance_to_center",
    "goal_mouth_distance_to_nearest_post",
    "goal_mouth_distance_to_crossbar",
    "is_header",
    "is_left_foot",
    "is_right_foot",
    "is_big_chance",
    "is_penalty",
    "is_open_play",
    "is_counter",
    "is_set_piece",
    "game_state_goal_diff",
]

CATEGORICAL_FEATURES = [
    "league",
    "season",
    "h_a",
    "situation_clean",
    "body_part",
    "shot_family",
    "shot_zone",
    "goal_mouth_zone",
    "score_state",
]


def _num(series: pd.Series, default=np.nan) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(default)


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, float) and math.isnan(value):
        return False
    return str(value).strip().lower() in {"1", "1.0", "true", "yes", "y", "successful"}


def _goal_mouth_zone(goal_mouth_y: float, goal_mouth_z: float, event_type: str) -> str:
    if event_type == "ShotOnPost":
        return "post"
    if not np.isfinite(goal_mouth_y) or not np.isfinite(goal_mouth_z):
        return "unknown"

    if goal_mouth_z < GOAL_MOUTH_CROSSBAR_Z / 3:
        vertical = "low"
    elif goal_mouth_z < (GOAL_MOUTH_CROSSBAR_Z * 2) / 3:
        vertical = "mid"
    else:
        vertical = "high"

    if goal_mouth_y < GOAL_MOUTH_CENTER_Y - GOAL_WIDTH / 6:
        lateral = "left"
    elif goal_mouth_y > GOAL_MOUTH_CENTER_Y + GOAL_WIDTH / 6:
        lateral = "right"
    else:
        lateral = "center"
    return f"{vertical}_{lateral}"


def _shot_is_blocked(row: pd.Series) -> bool:
    event_type = str(row.get("type") or "")
    return (
        _truthy(row.get("is_blocked"))
        or _truthy(row.get("shotBlocked"))
        or event_type == "BlockedShot"
    )


def _shot_is_on_target(row: pd.Series) -> bool:
    event_type = str(row.get("type") or "")
    return event_type in SHOT_ON_TARGET_TYPES or _truthy(row.get("is_on_target")) or _truthy(row.get("shotOnTarget"))


def build_xgot_feature_table(events: pd.DataFrame) -> pd.DataFrame:
    shots = build_shot_feature_table(events)
    if shots.empty:
        return pd.DataFrame()
    return build_xgot_feature_table_from_shots(shots)


def build_xgot_feature_table_from_shots(shots: pd.DataFrame) -> pd.DataFrame:
    if shots.empty:
        return pd.DataFrame()

    df = shots.copy()
    for column in ("xG", "x", "y", "shot_distance", "shot_angle", "goal_mouth_y", "goal_mouth_z"):
        if column not in df.columns:
            df[column] = np.nan
        df[column] = pd.to_numeric(df[column], errors="coerce")

    event_type = df["type"].fillna("").astype(str)
    df["isGoal"] = pd.to_numeric(df.get("isGoal", 0), errors="coerce").fillna(0).astype(int)
    df["xgot_is_on_target"] = df.apply(_shot_is_on_target, axis=1).astype(bool)
    df["xgot_is_blocked"] = df.apply(_shot_is_blocked, axis=1).astype(bool)
    df["xgot_zero_value"] = (~df["xgot_is_on_target"]) | df["xgot_is_blocked"]
    df["xgot_training_eligible"] = (
        df["xgot_is_on_target"]
        & ~df["xgot_is_blocked"]
        & df["goal_mouth_y"].notna()
        & df["goal_mouth_z"].notna()
        & event_type.isin(SHOT_ON_TARGET_TYPES)
    )

    df["goal_mouth_y_centered"] = (df["goal_mouth_y"] - GOAL_MOUTH_CENTER_Y).abs()
    df["goal_mouth_z_normalized"] = df["goal_mouth_z"] / GOAL_MOUTH_CROSSBAR_Z
    df["goal_mouth_distance_to_center"] = np.sqrt(
        (df["goal_mouth_y"] - GOAL_MOUTH_CENTER_Y) ** 2
        + ((df["goal_mouth_z"] - GOAL_MOUTH_CROSSBAR_Z / 2) / 4) ** 2
    )
    df["goal_mouth_distance_to_nearest_post"] = np.minimum(
        (df["goal_mouth_y"] - GOAL_MOUTH_LEFT_POST_Y).abs(),
        (df["goal_mouth_y"] - GOAL_MOUTH_RIGHT_POST_Y).abs(),
    )
    df["goal_mouth_distance_to_crossbar"] = (GOAL_MOUTH_CROSSBAR_Z - df["goal_mouth_z"]).abs()
    df["goal_mouth_zone"] = [
        _goal_mouth_zone(float(row.goal_mouth_y), float(row.goal_mouth_z), str(row.type))
        for row in df[["goal_mouth_y", "goal_mouth_z", "type"]].itertuples(index=False)
    ]

    df["xgot_model_target"] = df["isGoal"].astype(int)
    df["xgot_fixed"] = np.where(df["xgot_zero_value"], 0.0, np.nan)
    df["xgot_feature_version"] = MODEL_VERSION

    for column in NUMERIC_FEATURES:
        if column not in df.columns:
            df[column] = 0.0
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0.0)
    for column in CATEGORICAL_FEATURES:
        if column not in df.columns:
            df[column] = "unknown"
        df[column] = df[column].fillna("unknown").astype(str).replace({"": "unknown", "nan": "unknown"})
    return df


def training_frame(shots: pd.DataFrame, include_penalties: bool = True) -> pd.DataFrame:
    if shots.empty:
        return shots.copy()
    frame = shots[shots["xgot_training_eligible"]].copy()
    if not include_penalties and "shot_family" in frame.columns:
        frame = frame[frame["shot_family"] != "penalty"].copy()
    frame = frame.dropna(subset=["xgot_model_target"])
    return frame
