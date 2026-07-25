"""Shared expected-pass feature engineering utilities.

xPass is the modeled probability that an attempted pass is completed. The
feature table deliberately avoids outcome-specific inputs: accurate/inaccurate
flags are only used to build neutral pass-type categories.
"""

from __future__ import annotations

import ast
import json
import math
import re
from typing import Iterable

import numpy as np
import pandas as pd


PITCH_LENGTH = 105.0
PITCH_WIDTH = 68.0
GOAL_X = 105.0
GOAL_Y = 34.0
MODEL_VERSION = "xpass-v1-candidate"

NUMERIC_FEATURES = [
    "x",
    "y",
    "endX",
    "endY",
    "minute",
    "second",
    "expanded_minute",
    "pass_distance",
    "pass_angle",
    "pass_forward_distance",
    "pass_lateral_distance",
    "start_distance_to_goal",
    "end_distance_to_goal",
    "distance_to_goal_delta",
    "start_lateral_to_goal",
    "end_lateral_to_goal",
    "is_cross",
    "is_through_ball",
    "is_long_ball",
    "is_chipped",
    "is_headed",
    "is_right_foot",
    "is_left_foot",
    "is_corner",
    "is_free_kick",
    "is_throw_in",
    "enters_final_third",
    "enters_penalty_area",
    "ends_in_penalty_area",
    "is_switch",
    "previous_action_team_same",
    "previous_pass_distance",
    "previous_pass_angle",
    "carry_distance_before_pass",
    "pass_count_in_possession",
    "pass_count_log",
    "game_state_goal_diff",
]

CATEGORICAL_FEATURES = [
    "league",
    "season",
    "h_a",
    "pass_type",
    "play_pattern",
    "pass_direction",
    "start_third",
    "end_third",
    "start_lane",
    "end_lane",
    "minute_bucket",
    "score_state",
    "previous_action_type",
]

ID_COLUMNS = [
    "matchId",
    "eventId",
    "league",
    "season",
    "startDate",
    "teamId",
    "teamName",
    "playerId",
    "playerName",
    "minute",
    "second",
    "period",
    "type",
    "outcomeType",
    "xPass",
]


def _series(df: pd.DataFrame, column: str, default=None) -> pd.Series:
    if column in df.columns:
        return df[column]
    return pd.Series(default, index=df.index)


def _num(series: pd.Series | Iterable, default=np.nan) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(default)


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, float) and math.isnan(value):
        return False
    text = str(value).strip().lower()
    return text in {"1", "1.0", "true", "yes", "y", "successful"}


def _bool_col(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(False, index=df.index)
    return df[column].map(_truthy).fillna(False).astype(bool)


def _parse_qualifiers(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, float) and math.isnan(value):
        return []
    if isinstance(value, list):
        items = value
    else:
        text = str(value).strip()
        if not text:
            return []
        try:
            parsed = ast.literal_eval(text)
            items = parsed if isinstance(parsed, list) else [parsed]
        except Exception:
            try:
                parsed = json.loads(text)
                items = parsed if isinstance(parsed, list) else [parsed]
            except Exception:
                items = [text]
    labels: list[str] = []
    for item in items:
        if isinstance(item, dict):
            item_type = item.get("type")
            item_value = item.get("value")
            if item_type is not None:
                labels.append(str(item_type))
            if item_value is not None:
                labels.append(str(item_value))
        else:
            labels.append(str(item))
    return labels


def _qualifier_text(row: pd.Series) -> str:
    parts = []
    for column in ("qualifiers", "satisfiedEventsTypes"):
        if column in row.index:
            parts.extend(_parse_qualifiers(row.get(column)))
    return " ".join(parts)


def _contains_qualifier(events: pd.DataFrame, pattern: str) -> pd.Series:
    if events.empty:
        return pd.Series(False, index=events.index)
    if "_xpass_qualifier_text" in events.columns:
        text = events["_xpass_qualifier_text"].fillna("").astype(str)
    else:
        text = events.apply(_qualifier_text, axis=1)
    return text.str.contains(pattern, case=False, na=False, regex=True)


def _distance_to_goal(x: pd.Series, y: pd.Series) -> pd.Series:
    return np.sqrt((GOAL_X - x) ** 2 + (GOAL_Y - y) ** 2)


def _third(x: float) -> str:
    if pd.isna(x):
        return "unknown"
    if x < PITCH_LENGTH / 3:
        return "defensive"
    if x < 2 * PITCH_LENGTH / 3:
        return "middle"
    return "attacking"


def _lane(y: float) -> str:
    if pd.isna(y):
        return "unknown"
    if y < PITCH_WIDTH / 3:
        return "left"
    if y < 2 * PITCH_WIDTH / 3:
        return "center"
    return "right"


def _minute_bucket(minute: float) -> str:
    if minute < 15:
        return "00-15"
    if minute < 30:
        return "15-30"
    if minute < 45:
        return "30-45"
    if minute < 60:
        return "45-60"
    if minute < 75:
        return "60-75"
    if minute < 90:
        return "75-90"
    return "90+"


def _score_state(diff: float) -> str:
    if pd.isna(diff):
        return "unknown"
    if diff <= -2:
        return "trailing_2plus"
    if diff == -1:
        return "trailing_1"
    if diff == 0:
        return "level"
    if diff == 1:
        return "leading_1"
    return "leading_2plus"


def _score_diff_from_row(row: pd.Series) -> float:
    score = row.get("score")
    if score is None or (isinstance(score, float) and math.isnan(score)):
        return np.nan
    match = re.search(r"(-?\d+)\s*[-:]\s*(-?\d+)", str(score))
    if not match:
        return np.nan
    home_goals = float(match.group(1))
    away_goals = float(match.group(2))
    home_away = str(row.get("h_a") or "").strip().lower()
    if home_away in {"a", "away"}:
        return away_goals - home_goals
    return home_goals - away_goals


def _normalize_pass_type(passes: pd.DataFrame) -> pd.Series:
    conditions = [
        _bool_col(passes, "passThroughBallAccurate")
        | _bool_col(passes, "passThroughBallInaccurate")
        | _bool_col(passes, "passThroughBallInacurate")
        | _contains_qualifier(passes, r"\bThroughball\b|\bThroughBall\b"),
        _bool_col(passes, "passCrossAccurate")
        | _bool_col(passes, "passCrossInaccurate")
        | _contains_qualifier(passes, r"\bCross\b"),
        _bool_col(passes, "passLongBallAccurate")
        | _bool_col(passes, "passLongBallInaccurate")
        | _contains_qualifier(passes, r"\bLongball\b|\bLongBall\b"),
        _bool_col(passes, "passChipped") | _contains_qualifier(passes, r"\bChipped\b|\bChip\b"),
        _bool_col(passes, "passHead") | _contains_qualifier(passes, r"\bHead\b"),
    ]
    choices = ["through_ball", "cross", "long_ball", "chipped", "headed"]
    return pd.Series(np.select(conditions, choices, default="ground_pass"), index=passes.index)


def _normalize_play_pattern(passes: pd.DataFrame) -> pd.Series:
    conditions = [
        _bool_col(passes, "passCorner")
        | _bool_col(passes, "passCornerAccurate")
        | _bool_col(passes, "passCornerInaccurate")
        | _contains_qualifier(passes, r"\bCorner\b"),
        _bool_col(passes, "passFreekick")
        | _bool_col(passes, "passFreekickAccurate")
        | _bool_col(passes, "passFreekickInaccurate")
        | _contains_qualifier(passes, r"\bFreeKick\b|\bFreekick\b"),
        _bool_col(passes, "throwIn") | _contains_qualifier(passes, r"\bThrowIn\b|\bThrow-in\b"),
    ]
    choices = ["corner", "free_kick", "throw_in"]
    return pd.Series(np.select(conditions, choices, default="open_play"), index=passes.index)


def _sort_columns(events: pd.DataFrame) -> list[str]:
    return [column for column in ("period", "expandedMinute", "minute", "second", "eventId", "index") if column in events.columns]


def _pass_completion_target(passes: pd.DataFrame) -> pd.Series:
    outcome = _series(passes, "outcomeType", "").astype(str).str.lower()
    return outcome.eq("successful").astype(int)


def _attempted_pass_mask(events: pd.DataFrame) -> pd.Series:
    if events.empty or "type" not in events.columns:
        return pd.Series(False, index=events.index)
    return events["type"].astype(str).eq("Pass")


def build_pass_feature_table(events: pd.DataFrame) -> pd.DataFrame:
    """Build attempted-pass rows with xPass features and completion target."""
    if events.empty:
        return pd.DataFrame()

    sort_cols = _sort_columns(events)
    ordered = events.sort_values(sort_cols, kind="mergesort").copy() if sort_cols else events.copy()
    ordered["_original_index"] = ordered.index
    ordered["_xpass_qualifier_text"] = ordered.apply(_qualifier_text, axis=1)

    for column in ("x", "y", "endX", "endY", "minute", "second", "expandedMinute"):
        ordered[column] = _num(_series(ordered, column))

    previous = ordered.shift(1)
    ordered["_previous_action_type"] = previous.get("type", pd.Series("", index=ordered.index)).fillna("").astype(str)
    ordered["_previous_action_team_same"] = (
        _series(ordered, "teamId").astype(str).eq(_series(previous, "teamId").astype(str))
        if "teamId" in ordered.columns
        else pd.Series(False, index=ordered.index)
    )
    previous_is_pass = previous.get("type", pd.Series("", index=ordered.index)).fillna("").astype(str).eq("Pass")
    prev_dx = _num(previous.get("endX", pd.Series(np.nan, index=ordered.index))) - _num(
        previous.get("x", pd.Series(np.nan, index=ordered.index))
    )
    prev_dy = _num(previous.get("endY", pd.Series(np.nan, index=ordered.index))) - _num(
        previous.get("y", pd.Series(np.nan, index=ordered.index))
    )
    ordered["_previous_pass_distance"] = np.where(previous_is_pass, np.sqrt(prev_dx**2 + prev_dy**2), 0.0)
    ordered["_previous_pass_angle"] = np.where(previous_is_pass, np.arctan2(prev_dy, prev_dx), 0.0)

    previous_is_carry = previous.get("type", pd.Series("", index=ordered.index)).fillna("").astype(str).eq("Carry")
    same_player_previous = (
        _series(ordered, "playerId").astype(str).eq(_series(previous, "playerId").astype(str))
        if "playerId" in ordered.columns
        else pd.Series(False, index=ordered.index)
    )
    carry_dx = _num(previous.get("endX", pd.Series(np.nan, index=ordered.index))) - _num(
        previous.get("x", pd.Series(np.nan, index=ordered.index))
    )
    carry_dy = _num(previous.get("endY", pd.Series(np.nan, index=ordered.index))) - _num(
        previous.get("y", pd.Series(np.nan, index=ordered.index))
    )
    ordered["_carry_distance_before_pass"] = np.where(
        previous_is_carry & same_player_previous,
        np.sqrt(carry_dx**2 + carry_dy**2),
        0.0,
    )

    possession_col = next((column for column in ("possession_id", "possessionId", "sequence_id", "sequenceId") if column in ordered.columns), None)
    if possession_col:
        ordered["_pass_count_in_possession"] = (
            ordered["type"].astype(str).eq("Pass").groupby([ordered.get("matchId"), ordered[possession_col]]).cumsum()
        )
    else:
        ordered["_pass_count_in_possession"] = ordered["type"].astype(str).eq("Pass").groupby(ordered.get("matchId", 0)).cumsum()

    passes = ordered[_attempted_pass_mask(ordered)].copy()
    if passes.empty:
        return pd.DataFrame()

    dx = passes["endX"] - passes["x"]
    dy = passes["endY"] - passes["y"]
    passes["expanded_minute"] = passes["expandedMinute"].fillna(passes["minute"])
    passes["pass_distance"] = np.sqrt(dx**2 + dy**2)
    passes["pass_angle"] = np.arctan2(dy, dx)
    passes["pass_forward_distance"] = dx
    passes["pass_lateral_distance"] = dy.abs()
    passes["start_distance_to_goal"] = _distance_to_goal(passes["x"], passes["y"])
    passes["end_distance_to_goal"] = _distance_to_goal(passes["endX"], passes["endY"])
    passes["distance_to_goal_delta"] = passes["start_distance_to_goal"] - passes["end_distance_to_goal"]
    passes["start_lateral_to_goal"] = (passes["y"] - GOAL_Y).abs()
    passes["end_lateral_to_goal"] = (passes["endY"] - GOAL_Y).abs()

    passes["pass_type"] = _normalize_pass_type(passes)
    passes["play_pattern"] = _normalize_play_pattern(passes)
    passes["pass_direction"] = np.select([dx > 5, dx < -5], ["forward", "backward"], default="sideways")
    passes["start_third"] = passes["x"].map(_third)
    passes["end_third"] = passes["endX"].map(_third)
    passes["start_lane"] = passes["y"].map(_lane)
    passes["end_lane"] = passes["endY"].map(_lane)
    passes["minute_bucket"] = passes["minute"].map(_minute_bucket)

    passes["is_cross"] = passes["pass_type"].eq("cross").astype(int)
    passes["is_through_ball"] = passes["pass_type"].eq("through_ball").astype(int)
    passes["is_long_ball"] = passes["pass_type"].eq("long_ball").astype(int)
    passes["is_chipped"] = passes["pass_type"].eq("chipped").astype(int)
    passes["is_headed"] = passes["pass_type"].eq("headed").astype(int)
    passes["is_right_foot"] = (_bool_col(passes, "passRightFoot") | _contains_qualifier(passes, r"\bRightFoot\b")).astype(int)
    passes["is_left_foot"] = (_bool_col(passes, "passLeftFoot") | _contains_qualifier(passes, r"\bLeftFoot\b")).astype(int)
    passes["is_corner"] = passes["play_pattern"].eq("corner").astype(int)
    passes["is_free_kick"] = passes["play_pattern"].eq("free_kick").astype(int)
    passes["is_throw_in"] = passes["play_pattern"].eq("throw_in").astype(int)
    passes["enters_final_third"] = ((passes["x"] < 70) & (passes["endX"] >= 70)).astype(int)
    passes["ends_in_penalty_area"] = ((passes["endX"] >= 88.5) & passes["endY"].between(13.84, 54.16)).astype(int)
    passes["enters_penalty_area"] = (
        ~((passes["x"] >= 88.5) & passes["y"].between(13.84, 54.16))
        & (passes["ends_in_penalty_area"] == 1)
    ).astype(int)
    passes["is_switch"] = (
        (passes["pass_distance"] >= 30)
        & ((passes["y"] < PITCH_WIDTH / 3) & (passes["endY"] > 2 * PITCH_WIDTH / 3)
           | (passes["y"] > 2 * PITCH_WIDTH / 3) & (passes["endY"] < PITCH_WIDTH / 3))
    ).astype(int)

    passes["previous_action_team_same"] = passes["_previous_action_team_same"].astype(int)
    passes["previous_action_type"] = passes["_previous_action_type"].replace({"": "none", "nan": "none"}).fillna("none")
    passes["previous_pass_distance"] = pd.to_numeric(passes["_previous_pass_distance"], errors="coerce").fillna(0.0)
    passes["previous_pass_angle"] = pd.to_numeric(passes["_previous_pass_angle"], errors="coerce").fillna(0.0)
    passes["carry_distance_before_pass"] = pd.to_numeric(passes["_carry_distance_before_pass"], errors="coerce").fillna(0.0)
    passes["pass_count_in_possession"] = pd.to_numeric(passes["_pass_count_in_possession"], errors="coerce").fillna(1.0)
    passes["pass_count_log"] = np.log1p(passes["pass_count_in_possession"])

    if "score" in passes.columns:
        passes["game_state_goal_diff"] = passes.apply(_score_diff_from_row, axis=1)
    else:
        passes["game_state_goal_diff"] = np.nan
    passes["score_state"] = passes["game_state_goal_diff"].map(_score_state)

    passes["xpass_completed"] = _pass_completion_target(passes)
    passes["xpass_pass_type"] = passes["pass_type"]
    passes["xpass_play_pattern"] = passes["play_pattern"]
    passes["xpass_pass_direction"] = passes["pass_direction"]
    passes["xpass_feature_version"] = MODEL_VERSION

    output_columns = [
        *[column for column in ID_COLUMNS if column in passes.columns],
        *NUMERIC_FEATURES,
        *CATEGORICAL_FEATURES,
        "xpass_completed",
        "xpass_pass_type",
        "xpass_play_pattern",
        "xpass_pass_direction",
        "xpass_feature_version",
    ]
    deduped_columns = list(dict.fromkeys(output_columns))
    return passes[deduped_columns].copy()


def training_frame(passes: pd.DataFrame) -> pd.DataFrame:
    """Return rows usable for xPass model training."""
    if passes.empty:
        return passes.copy()
    required = ["x", "y", "endX", "endY", "pass_distance", "pass_angle", "outcomeType"]
    frame = passes.dropna(subset=[column for column in required if column in passes.columns]).copy()
    outcome = frame["outcomeType"].astype(str).str.lower()
    frame = frame[outcome.isin({"successful", "unsuccessful"})]
    frame = frame[frame["pass_distance"].between(0.1, 105.0, inclusive="both")]
    return frame
