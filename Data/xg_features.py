"""
Shared xG feature engineering utilities.

This module is intentionally usable from both Data scripts and the API. It does
not load a model or mutate source event data; it only identifies shots and builds
a stable feature table.
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
GOAL_WIDTH = 7.32
PENALTY_XG = 0.78
MIN_TRAINING_SHOT_X = 52.5
MAX_TRAINING_SHOT_DISTANCE = 60.0
SHOT_TYPES = {"Goal", "SavedShot", "MissedShots", "ShotOnPost"}
NON_ACTION_TYPES = {"SubstitutionOn", "SubstitutionOff", "FormationChange", "Card", "Start", "End", "Save"}

MODEL_VERSION = "xg-v2-candidate"

NUMERIC_FEATURES = [
    "x",
    "y",
    "minute",
    "second",
    "expanded_minute",
    "shot_distance",
    "shot_angle",
    "shot_lateral_distance",
    "shot_distance_sq",
    "is_header",
    "is_left_foot",
    "is_right_foot",
    "is_big_chance",
    "is_open_play",
    "is_counter",
    "is_set_piece",
    "is_direct_corner",
    "is_from_corner",
    "is_direct_free_kick",
    "is_penalty",
    "prev_time_delta",
    "prev_action_distance",
    "prev_action_angle",
    "prev_action_into_box",
    "prev_action_same_team",
    "prev_action_success",
    "shot_after_carry",
    "shot_after_takeon",
    "shot_after_cross",
    "shot_after_through_ball",
    "shot_after_recovery",
    "shot_after_duel",
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
    "minute_bucket",
    "score_state",
    "prev_action_type",
    "prev_action_subtype",
    "prev_action_outcome",
]

ID_COLUMNS = [
    "matchId",
    "eventId",
    "league",
    "season",
    "startDate",
    "teamId",
    "teamName",
    "opponentTeamId",
    "opponentTeamName",
    "playerId",
    "playerName",
    "minute",
    "second",
    "period",
    "type",
    "situation",
    "shotBodyType",
    "isGoal",
    "xG",
]


def _series(df: pd.DataFrame, column: str, default=None) -> pd.Series:
    if column in df.columns:
        return df[column]
    return pd.Series(default, index=df.index)


def _num(series: pd.Series | Iterable, default=np.nan) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(default)


def _str(series: pd.Series | Iterable, default="") -> pd.Series:
    return pd.Series(series).fillna(default).astype(str)


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


def _contains_col(df: pd.DataFrame, column: str, pattern: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(False, index=df.index)
    return df[column].fillna("").astype(str).str.contains(pattern, case=False, na=False, regex=True)


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
            labels.extend(str(v) for v in item.values() if v is not None)
        else:
            labels.append(str(item))
    return labels


def _qualifier_text(row: pd.Series) -> str:
    parts = []
    for column in ("qualifiers", "satisfiedEventsTypes"):
        if column in row.index:
            parts.extend(_parse_qualifiers(row.get(column)))
    return " ".join(parts)


def _has_qualifier(row: pd.Series, pattern: str) -> bool:
    return re.search(pattern, _qualifier_text(row), flags=re.IGNORECASE) is not None


def _is_own_goal(row: pd.Series) -> bool:
    return (
        _truthy(row.get("isOwnGoal"))
        or _truthy(row.get("goalOwn"))
        or _has_qualifier(row, r"\bown\s*goal\b")
        or _has_qualifier(row, r"\bowngoal\b")
        or _has_qualifier(row, r"\bgoalOwn\b")
    )


def own_goal_mask(events: pd.DataFrame) -> pd.Series:
    if events.empty:
        return pd.Series(False, index=events.index)
    return events.apply(_is_own_goal, axis=1).astype(bool)


def _shot_distance(x: pd.Series, y: pd.Series) -> pd.Series:
    return np.sqrt((GOAL_X - x) ** 2 + (GOAL_Y - y) ** 2)


def _shot_angle(x: pd.Series, y: pd.Series) -> pd.Series:
    left_post_y = GOAL_Y - GOAL_WIDTH / 2
    right_post_y = GOAL_Y + GOAL_WIDTH / 2
    a = np.sqrt((GOAL_X - x) ** 2 + (left_post_y - y) ** 2)
    b = np.sqrt((GOAL_X - x) ** 2 + (right_post_y - y) ** 2)
    c = GOAL_WIDTH
    denom = 2 * a * b
    cos_angle = np.where(denom > 0, (a**2 + b**2 - c**2) / denom, 1)
    return pd.Series(np.arccos(np.clip(cos_angle, -1, 1)), index=x.index)


def _shot_zone(x: float, y: float) -> str:
    if x >= 99 and 24.84 <= y <= 43.16:
        return "six_yard_box"
    if x >= 88.5 and 13.84 <= y <= 54.16:
        return "penalty_area"
    if x >= 88.5:
        return "wide_box_channel"
    if x >= 70:
        return "outside_box_final_third"
    return "deep_shot"


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


def _body_part(row: pd.Series) -> str:
    body = str(row.get("shotBodyType") or "").strip()
    if body and body.lower() != "nan":
        return body
    if _truthy(row.get("shotHead")) or _truthy(row.get("goalHead")):
        return "Head"
    if _truthy(row.get("shotLeftFoot")) or _truthy(row.get("goalLeftFoot")):
        return "LeftFoot"
    if _truthy(row.get("shotRightFoot")) or _truthy(row.get("goalRightFoot")):
        return "RightFoot"
    return "Unknown"


def _is_penalty(row: pd.Series) -> bool:
    situation = str(row.get("situation") or "")
    qualifier_text = _qualifier_text(row)
    return (
        situation.strip().lower() in {"penalty", "penaltykick", "penalty kick"}
        or re.search(r"\bpenalty\s*(kick|taken|scored|missed|saved)\b", qualifier_text, flags=re.IGNORECASE) is not None
        or _truthy(row.get("penaltyScored"))
        or _truthy(row.get("penaltyMissed"))
        or _truthy(row.get("penaltyShootoutScored"))
        or _truthy(row.get("penaltyShootoutMissedOffTarget"))
        or _truthy(row.get("penaltyShootoutSaved"))
    )


def _is_direct_free_kick(row: pd.Series) -> bool:
    text = f"{row.get('situation') or ''} {_qualifier_text(row)}"
    return re.search(r"direct.?free|free.?kick", text, flags=re.IGNORECASE) is not None and not _is_penalty(row)


def _shot_family(row: pd.Series) -> str:
    if _is_penalty(row):
        return "penalty"
    if _is_direct_free_kick(row):
        return "direct_free_kick"
    body = _body_part(row).lower()
    if "head" in body:
        return "header"
    if _truthy(row.get("shotOpenPlay")) or str(row.get("situation") or "").lower() in {"openplay", "open play"}:
        return "open_play_foot"
    if _truthy(row.get("shotSetPiece")) or str(row.get("situation") or "").lower() in {"setpiece", "set piece", "fromcorner"}:
        return "other_set_piece"
    return "other"


def _score_state(row: pd.Series) -> tuple[str, int]:
    raw_score = str(row.get("score") or "").strip()
    match = re.search(r"(\d+)\s*[-:]\s*(\d+)", raw_score)
    if not match:
        return "unknown", 0
    home_goals, away_goals = int(match.group(1)), int(match.group(2))
    is_home = str(row.get("h_a") or "").lower().startswith("h")
    team_goals = home_goals if is_home else away_goals
    opp_goals = away_goals if is_home else home_goals
    diff = team_goals - opp_goals
    if diff > 0:
        return "leading", diff
    if diff < 0:
        return "trailing", diff
    return "level", 0


def _action_success(row: pd.Series) -> bool:
    outcome = str(row.get("outcomeType") or "")
    if "successful" in outcome.lower():
        return True
    if "unsuccessful" in outcome.lower():
        return False
    for column in ("passAccurate", "dribbleWon", "tackleWon", "ballRecovery"):
        if _truthy(row.get(column)):
            return True
    return False


def _action_subtype(row: pd.Series) -> str:
    event_type = str(row.get("type") or "")
    text = _qualifier_text(row)
    if event_type == "Carry":
        return "carry"
    if re.search(r"cross", text, re.IGNORECASE) or _truthy(row.get("passCrossAccurate")) or _truthy(row.get("passCrossInaccurate")):
        return "cross"
    if re.search(r"through", text, re.IGNORECASE) or _truthy(row.get("passThroughBallAccurate")) or _truthy(row.get("passThroughBallInaccurate")):
        return "through_ball"
    if re.search(r"corner", text, re.IGNORECASE) or _truthy(row.get("passCorner")):
        return "corner"
    if re.search(r"free.?kick", text, re.IGNORECASE) or _truthy(row.get("passFreekick")):
        return "free_kick"
    if re.search(r"long", text, re.IGNORECASE) or _truthy(row.get("passLongBallAccurate")) or _truthy(row.get("passLongBallInaccurate")):
        return "long_ball"
    if event_type in {"TakeOn", "Challenge"} or _truthy(row.get("dribbleWon")) or _truthy(row.get("dribbleLost")):
        return "takeon"
    if event_type in {"BallRecovery", "Interception"} or _truthy(row.get("ballRecovery")):
        return "recovery"
    if event_type in {"Aerial", "Tackle"} or _truthy(row.get("duelAerialWon")) or _truthy(row.get("duelAerialLost")):
        return "duel"
    return event_type.lower() or "unknown"


def _prev_action_for_shot(events: pd.DataFrame, shot_position: int) -> pd.Series | None:
    shot = events.iloc[shot_position]
    shot_time = float(shot.get("_xg_event_clock", np.nan))
    shot_match_id = shot.get("matchId")
    for idx in range(shot_position - 1, -1, -1):
        candidate = events.iloc[idx]
        if "matchId" in events.columns and str(candidate.get("matchId")) != str(shot_match_id):
            break
        event_type = str(candidate.get("type") or "")
        if event_type in NON_ACTION_TYPES:
            continue
        if not pd.isna(shot_time):
            delta = shot_time - float(candidate.get("_xg_event_clock", shot_time))
            if delta > 20:
                break
        return candidate
    return None


def normalise_event_frame(events: pd.DataFrame) -> pd.DataFrame:
    df = events.copy()
    dedupe_cols = [
        col
        for col in ("matchId", "eventId", "type", "teamId", "playerId", "minute", "second", "x", "y", "endX", "endY")
        if col in df.columns
    ]
    if dedupe_cols:
        df = df.drop_duplicates(subset=dedupe_cols, keep="first").copy()
    for column in ("minute", "second", "expandedMinute", "x", "y", "endX", "endY", "eventId"):
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    minute = _num(_series(df, "expandedMinute", _series(df, "minute", 0)), 0)
    second = _num(_series(df, "second", 0), 0)
    df["_xg_event_clock"] = minute * 60 + second
    sort_cols = [col for col in ("matchId", "period", "_xg_event_clock", "eventId") if col in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols, kind="mergesort").reset_index(drop=True)
    return df


def shot_mask(events: pd.DataFrame) -> pd.Series:
    event_type = _str(_series(events, "type", ""))
    is_shot_flag = _bool_col(events, "isShot")
    is_shot = event_type.isin(SHOT_TYPES) | is_shot_flag
    return is_shot & ~own_goal_mask(events)


def build_shot_feature_table(events: pd.DataFrame) -> pd.DataFrame:
    df = normalise_event_frame(events)
    shots = df[shot_mask(df)].copy()
    if shots.empty:
        return pd.DataFrame()

    teams_by_match = {}
    if "matchId" in df.columns and "teamId" in df.columns:
        for match_id, group in df.groupby("matchId", dropna=False):
            team_rows = group[["teamId", "teamName"]].dropna(subset=["teamId"]).drop_duplicates()
            teams_by_match[match_id] = team_rows.to_dict("records")

    rows: list[dict] = []
    for shot_idx, shot in shots.iterrows():
        match_id = shot.get("matchId")
        team_id = shot.get("teamId")
        opponent_team_id = None
        opponent_team_name = None
        for team_row in teams_by_match.get(match_id, []):
            if str(team_row.get("teamId")) != str(team_id):
                opponent_team_id = team_row.get("teamId")
                opponent_team_name = team_row.get("teamName")
                break

        x = float(shot.get("x")) if pd.notna(shot.get("x")) else np.nan
        y = float(shot.get("y")) if pd.notna(shot.get("y")) else np.nan
        prev = _prev_action_for_shot(df, int(shot_idx))
        score_state, goal_diff = _score_state(shot)
        family = _shot_family(shot)
        body_part = _body_part(shot)
        prev_type = str(prev.get("type") or "none") if prev is not None else "none"
        prev_subtype = _action_subtype(prev) if prev is not None else "none"
        prev_same_team = prev is not None and str(prev.get("teamId")) == str(team_id)
        prev_success = _action_success(prev) if prev is not None else False
        prev_x = float(prev.get("x")) if prev is not None and pd.notna(prev.get("x")) else np.nan
        prev_y = float(prev.get("y")) if prev is not None and pd.notna(prev.get("y")) else np.nan
        prev_end_x = float(prev.get("endX")) if prev is not None and pd.notna(prev.get("endX")) else np.nan
        prev_end_y = float(prev.get("endY")) if prev is not None and pd.notna(prev.get("endY")) else np.nan
        prev_distance = np.sqrt((prev_end_x - prev_x) ** 2 + (prev_end_y - prev_y) ** 2) if np.isfinite(prev_x + prev_y + prev_end_x + prev_end_y) else 0.0
        prev_angle = math.atan2(prev_end_y - prev_y, prev_end_x - prev_x) if np.isfinite(prev_x + prev_y + prev_end_x + prev_end_y) else 0.0
        shot_clock = float(shot.get("_xg_event_clock", np.nan))
        prev_clock = float(prev.get("_xg_event_clock", np.nan)) if prev is not None else np.nan
        prev_delta = shot_clock - prev_clock if np.isfinite(shot_clock) and np.isfinite(prev_clock) else np.nan
        prev_into_box = np.isfinite(prev_end_x + prev_end_y) and prev_end_x >= 88.5 and 13.84 <= prev_end_y <= 54.16

        row = {
            "matchId": match_id,
            "eventId": shot.get("eventId"),
            "league": shot.get("league"),
            "season": shot.get("season"),
            "startDate": shot.get("startDate"),
            "teamId": team_id,
            "teamName": shot.get("teamName"),
            "opponentTeamId": opponent_team_id,
            "opponentTeamName": opponent_team_name,
            "playerId": shot.get("playerId"),
            "playerName": shot.get("playerName"),
            "period": shot.get("period"),
            "type": shot.get("type"),
            "situation": shot.get("situation"),
            "shotBodyType": shot.get("shotBodyType"),
            "isGoal": int(str(shot.get("type")) == "Goal" or _truthy(shot.get("isGoal"))),
            "xG": pd.to_numeric(shot.get("xG"), errors="coerce"),
            "x": x,
            "y": y,
            "minute": pd.to_numeric(shot.get("minute"), errors="coerce"),
            "second": pd.to_numeric(shot.get("second"), errors="coerce"),
            "expanded_minute": pd.to_numeric(shot.get("expandedMinute", shot.get("minute")), errors="coerce"),
            "goal_mouth_y": pd.to_numeric(shot.get("goalMouthY"), errors="coerce"),
            "goal_mouth_z": pd.to_numeric(shot.get("goalMouthZ"), errors="coerce"),
            "shot_distance": np.nan,
            "shot_angle": np.nan,
            "shot_lateral_distance": abs(y - GOAL_Y) if np.isfinite(y) else np.nan,
            "shot_distance_sq": np.nan,
            "shot_zone": _shot_zone(x, y) if np.isfinite(x) and np.isfinite(y) else "unknown",
            "minute_bucket": _minute_bucket(float(shot.get("minute") or 0)),
            "score_state": score_state,
            "game_state_goal_diff": goal_diff,
            "situation_clean": str(shot.get("situation") or "Unknown"),
            "body_part": body_part,
            "shot_family": family,
            "is_big_chance": int(_truthy(shot.get("bigChanceScored")) or _truthy(shot.get("bigChanceMissed"))),
            "is_header": int("head" in body_part.lower()),
            "is_left_foot": int("left" in body_part.lower() or _truthy(shot.get("shotLeftFoot")) or _truthy(shot.get("goalLeftFoot"))),
            "is_right_foot": int("right" in body_part.lower() or _truthy(shot.get("shotRightFoot")) or _truthy(shot.get("goalRightFoot"))),
            "is_open_play": int(_truthy(shot.get("shotOpenPlay")) or str(shot.get("situation") or "").lower() in {"openplay", "open play"}),
            "is_counter": int(_truthy(shot.get("shotCounter")) or str(shot.get("situation") or "").lower() == "counter"),
            "is_set_piece": int(_truthy(shot.get("shotSetPiece")) or "set" in str(shot.get("situation") or "").lower()),
            "is_direct_corner": int(_truthy(shot.get("shotDirectCorner"))),
            "is_blocked": int(str(shot.get("type") or "") == "SavedShot" and _truthy(shot.get("shotBlocked"))),
            "is_on_target": int(_truthy(shot.get("shotOnTarget")) or str(shot.get("type") or "") in {"Goal", "SavedShot"}),
            "is_from_corner": int(str(shot.get("situation") or "").lower() == "fromcorner" or _has_qualifier(shot, r"corner")),
            "is_direct_free_kick": int(family == "direct_free_kick"),
            "is_penalty": int(family == "penalty"),
            "prev_action_type": prev_type,
            "prev_action_subtype": prev_subtype,
            "prev_action_outcome": "successful" if prev_success else "unsuccessful",
            "prev_time_delta": prev_delta if np.isfinite(prev_delta) else 99.0,
            "prev_action_distance": prev_distance,
            "prev_action_angle": prev_angle,
            "prev_action_into_box": int(prev_into_box),
            "prev_action_same_team": int(prev_same_team),
            "prev_action_success": int(prev_success),
            "shot_after_carry": int(prev_subtype == "carry"),
            "shot_after_takeon": int(prev_subtype == "takeon"),
            "shot_after_cross": int(prev_subtype == "cross"),
            "shot_after_through_ball": int(prev_subtype == "through_ball"),
            "shot_after_recovery": int(prev_subtype == "recovery"),
            "shot_after_duel": int(prev_subtype == "duel"),
            "xg_fixed": PENALTY_XG if family == "penalty" else np.nan,
            "xg_model_version": MODEL_VERSION,
        }
        if np.isfinite(x) and np.isfinite(y):
            dist = float(_shot_distance(pd.Series([x]), pd.Series([y])).iloc[0])
            row["shot_distance"] = dist
            row["shot_distance_sq"] = dist * dist
            row["shot_angle"] = float(_shot_angle(pd.Series([x]), pd.Series([y])).iloc[0])
        rows.append(row)

    out = pd.DataFrame(rows)
    for column in NUMERIC_FEATURES:
        if column not in out.columns:
            out[column] = 0.0
        out[column] = pd.to_numeric(out[column], errors="coerce").fillna(0.0)
    for column in CATEGORICAL_FEATURES:
        if column not in out.columns:
            out[column] = "unknown"
        out[column] = out[column].fillna("unknown").astype(str).replace({"": "unknown", "nan": "unknown"})
    return out


def model_feature_columns() -> tuple[list[str], list[str]]:
    return NUMERIC_FEATURES.copy(), CATEGORICAL_FEATURES.copy()


def training_frame(shots: pd.DataFrame, include_penalties: bool = False) -> pd.DataFrame:
    if shots.empty:
        return shots.copy()
    frame = shots.copy()
    if not include_penalties:
        frame = frame[frame["shot_family"] != "penalty"].copy()
    frame = frame[
        (pd.to_numeric(frame["x"], errors="coerce") >= MIN_TRAINING_SHOT_X)
        & (pd.to_numeric(frame["shot_distance"], errors="coerce") <= MAX_TRAINING_SHOT_DISTANCE)
    ].copy()
    frame = frame.dropna(subset=["isGoal"])
    return frame
