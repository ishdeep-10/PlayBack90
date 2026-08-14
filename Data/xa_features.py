"""Shared xA feature engineering utilities.

This module builds a completed-pass training table for provider-style xA:
the modeled probability that a completed pass becomes a goal assist.
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

PASS_TYPES = {"Pass"}
SHOT_TYPES = {"Goal", "SavedShot", "MissedShots", "ShotOnPost"}
MODEL_VERSION = "xa-v1-candidate"

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
    "is_corner",
    "is_free_kick",
    "is_throw_in",
    "enters_final_third",
    "enters_penalty_area",
    "ends_in_penalty_area",
    "ends_in_box_centre",
    "is_cutback_proxy",
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
    "assist",
    "passKey",
    "xA",
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
    if "_xa_qualifier_text" in events.columns:
        text = events["_xa_qualifier_text"].fillna("").astype(str)
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


def _score_diff_from_score(score: object, team_name: object, home_team: object | None = None, away_team: object | None = None) -> float:
    if score is None or (isinstance(score, float) and math.isnan(score)):
        return np.nan
    match = re.search(r"(-?\d+)\s*[-:]\s*(-?\d+)", str(score))
    if not match:
        return np.nan
    home_goals = float(match.group(1))
    away_goals = float(match.group(2))
    if home_team is not None and str(team_name) == str(home_team):
        return home_goals - away_goals
    if away_team is not None and str(team_name) == str(away_team):
        return away_goals - home_goals
    return home_goals - away_goals


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
        _bool_col(passes, "passThroughBallAccurate") | _bool_col(passes, "passThroughBallInaccurate") | _bool_col(passes, "passThroughBallInacurate") | _contains_qualifier(passes, r"\bThroughball\b|\bThroughBall\b"),
        _bool_col(passes, "passCrossAccurate") | _bool_col(passes, "passCrossInaccurate") | _contains_qualifier(passes, r"\bCross\b"),
        _bool_col(passes, "passLongBallAccurate") | _bool_col(passes, "passLongBallInaccurate") | _contains_qualifier(passes, r"\bLongball\b|\bLongBall\b"),
        _bool_col(passes, "passChipped") | _contains_qualifier(passes, r"\bChipped\b|\bChip\b"),
        _bool_col(passes, "passHead") | _contains_qualifier(passes, r"\bHead\b"),
    ]
    choices = ["through_ball", "cross", "long_ball", "chipped", "headed"]
    return pd.Series(np.select(conditions, choices, default="ground_pass"), index=passes.index)


def _normalize_play_pattern(passes: pd.DataFrame) -> pd.Series:
    conditions = [
        _bool_col(passes, "passCorner") | _bool_col(passes, "passCornerAccurate") | _bool_col(passes, "passCornerInaccurate") | _contains_qualifier(passes, r"\bCorner\b"),
        _bool_col(passes, "passFreekick") | _bool_col(passes, "passFreekickAccurate") | _bool_col(passes, "passFreekickInaccurate") | _contains_qualifier(passes, r"\bFreeKick\b|\bFreekick\b"),
        _bool_col(passes, "throwIn") | _contains_qualifier(passes, r"\bThrowIn\b|\bThrow-in\b"),
    ]
    choices = ["corner", "free_kick", "throw_in"]
    return pd.Series(np.select(conditions, choices, default="open_play"), index=passes.index)


def assist_target_mask(events: pd.DataFrame) -> pd.Series:
    """Return the provider-style goal-assist target for completed passes."""
    if events.empty:
        return pd.Series(False, index=events.index)
    assist_cols = [
        "assist",
        "isGoalAssist",
        "goalAssist",
        "intentionalAssist",
        "assistCross",
        "assistCorner",
        "assistThroughball",
        "assistFreekick",
        "assistThrowin",
        "assistOther",
    ]
    mask = pd.Series(False, index=events.index)
    for column in assist_cols:
        mask = mask | _bool_col(events, column)
    mask = mask | _contains_qualifier(events, r"\bIntentionalGoalAssist\b|\bGoalAssist\b")
    return mask.astype(bool)


def shot_assist_mask(events: pd.DataFrame) -> pd.Series:
    """Return pass rows that directly created any shot, whether or not it was a goal."""
    if events.empty:
        return pd.Series(False, index=events.index)
    mask = _bool_col(events, "passKey")
    mask = mask | _contains_qualifier(events, r"\bShotAssist\b|\bKeyPass\b|\bBigChanceCreated\b|\bIntentionalAssist\b")
    return mask.astype(bool)


def _shot_link_table(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame(columns=["eventId", "xa_target_event_id", "xa_target_xg", "xa_target_is_goal", "xa_target_type"])
    shots = events[_series(events, "type", "").isin(SHOT_TYPES) | _bool_col(events, "isShot")].copy()
    if shots.empty or "relatedEventId" not in shots.columns:
        return pd.DataFrame(columns=["eventId", "xa_target_event_id", "xa_target_xg", "xa_target_is_goal", "xa_target_type"])
    related = pd.to_numeric(shots["relatedEventId"], errors="coerce")
    shots = shots[related.notna()].copy()
    if shots.empty:
        return pd.DataFrame(columns=["eventId", "xa_target_event_id", "xa_target_xg", "xa_target_is_goal", "xa_target_type"])
    shots["xa_linked_pass_event_id"] = related[related.notna()].astype(float).values
    shots["xa_target_event_id"] = pd.to_numeric(shots.get("eventId"), errors="coerce")
    link = shots[["xa_linked_pass_event_id", "xa_target_event_id"]].copy()
    link = link.rename(columns={"xa_linked_pass_event_id": "eventId"})
    link["xa_target_xg"] = pd.to_numeric(shots.get("xG"), errors="coerce")
    link["xa_target_is_goal"] = _bool_col(shots, "isGoal").astype(int).values
    link["xa_target_type"] = shots.get("type", pd.Series("", index=shots.index)).astype(str).values
    return link.dropna(subset=["eventId"]).drop_duplicates(subset=["eventId"], keep="last")


def build_pass_feature_table(events: pd.DataFrame) -> pd.DataFrame:
    """Build completed-pass rows with xA training labels and audit helpers."""
    if events.empty:
        return pd.DataFrame()

    passes = events[
        _series(events, "type", "").eq("Pass")
        & _series(events, "outcomeType", "").astype(str).str.lower().eq("successful")
    ].copy()
    if passes.empty:
        return pd.DataFrame()

    # Backfilled parquet files may already contain these derived audit fields.
    # They are recomputed below; retaining them would make the shot-link merge
    # create _x/_y columns and break resumable/idempotent backfills.
    passes = passes.drop(
        columns=[
            "xa_target_event_id",
            "xa_target_xg",
            "xa_target_is_goal",
            "xa_target_type",
            "xa_link_method",
        ],
        errors="ignore",
    )

    passes["_xa_qualifier_text"] = passes.apply(_qualifier_text, axis=1)

    for column in ("x", "y", "endX", "endY", "minute", "second", "expandedMinute"):
        passes[column] = _num(_series(passes, column))

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
    passes["pass_direction"] = np.select(
        [dx > 5, dx < -5],
        ["forward", "backward"],
        default="sideways",
    )
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
    passes["is_corner"] = passes["play_pattern"].eq("corner").astype(int)
    passes["is_free_kick"] = passes["play_pattern"].eq("free_kick").astype(int)
    passes["is_throw_in"] = passes["play_pattern"].eq("throw_in").astype(int)
    passes["is_key_pass"] = shot_assist_mask(passes).astype(int)
    passes["is_big_chance_created"] = (_bool_col(passes, "bigChanceCreated") | _contains_qualifier(passes, r"\bBigChanceCreated\b")).astype(int)
    passes["is_intentional_assist_flag"] = (_bool_col(passes, "intentionalAssist") | _contains_qualifier(passes, r"\bIntentionalAssist\b")).astype(int)
    passes["enters_final_third"] = ((passes["x"] < 70) & (passes["endX"] >= 70)).astype(int)
    passes["ends_in_penalty_area"] = ((passes["endX"] >= 88.5) & passes["endY"].between(13.84, 54.16)).astype(int)
    passes["enters_penalty_area"] = (
        ~((passes["x"] >= 88.5) & passes["y"].between(13.84, 54.16))
        & (passes["ends_in_penalty_area"] == 1)
    ).astype(int)
    passes["ends_in_box_centre"] = ((passes["endX"] >= 88.5) & passes["endY"].between(24.0, 44.0)).astype(int)
    passes["is_cutback_proxy"] = (
        (passes["x"] >= 88.5)
        & (passes["y"].between(0, 16) | passes["y"].between(52, 68))
        & (passes["endX"] < passes["x"])
        & passes["endY"].between(20, 48)
    ).astype(int)

    if "score" in passes.columns:
        passes["game_state_goal_diff"] = passes.apply(_score_diff_from_row, axis=1)
    else:
        passes["game_state_goal_diff"] = np.nan
    passes["score_state"] = passes["game_state_goal_diff"].map(_score_state)

    passes["xa_target_assist"] = assist_target_mask(passes).astype(int)
    passes["xa_is_direct_shot_assist"] = shot_assist_mask(passes).astype(int)
    passes["xa_pass_type"] = passes["pass_type"]
    passes["xa_play_pattern"] = passes["play_pattern"]

    links = _shot_link_table(events)
    passes["eventId_numeric"] = pd.to_numeric(passes.get("eventId"), errors="coerce")
    if not links.empty:
        passes = passes.merge(
            links.rename(columns={"eventId": "eventId_numeric"}),
            on="eventId_numeric",
            how="left",
        )
    else:
        passes["xa_target_event_id"] = np.nan
        passes["xa_target_xg"] = np.nan
        passes["xa_target_is_goal"] = np.nan
        passes["xa_target_type"] = ""
    passes["xa_link_method"] = np.where(passes["xa_target_event_id"].notna(), "relatedEventId", "")
    passes["xa_model_target"] = passes["xa_target_assist"].astype(int)
    passes["xa_feature_version"] = MODEL_VERSION

    output_columns = [
        *[column for column in ID_COLUMNS if column in passes.columns],
        *NUMERIC_FEATURES,
        *CATEGORICAL_FEATURES,
        "xa_model_target",
        "xa_target_assist",
        "xa_is_direct_shot_assist",
        "xa_target_event_id",
        "xa_target_xg",
        "xa_target_is_goal",
        "xa_target_type",
        "xa_link_method",
        "xa_pass_type",
        "xa_play_pattern",
        "xa_feature_version",
    ]
    deduped_columns = list(dict.fromkeys(output_columns))
    return passes[deduped_columns].copy()


def training_frame(passes: pd.DataFrame) -> pd.DataFrame:
    """Return rows usable for provider-style xA model training."""
    if passes.empty:
        return passes.copy()
    required = ["x", "y", "endX", "endY", "pass_distance", "pass_angle"]
    frame = passes.dropna(subset=[column for column in required if column in passes.columns]).copy()
    frame = frame[frame["pass_distance"].between(0.1, 105.0, inclusive="both")]
    return frame
