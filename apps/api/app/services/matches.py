from __future__ import annotations

import logging
import math
import time
from typing import Any

import pandas as pd

from app.domain import TEAM_DICT
from app.schemas import MatchContext, TeamSummary
from app.services import r2

logger = logging.getLogger(__name__)


AVAILABLE_VIEWS = [
    "match-dynamics",
    "match-summary",
    "team-stats",
    "player-stats",
    "shot-map",
    "shot-player-summary",
    "shot-details",
    "pass-network",
    "defensive-actions",
    "duels-transitions",
    "transitions",
    "player-comparison",
    "player-analysis",
]


def _minute_bucket(value: Any) -> int | None:
    minute = pd.to_numeric(value, errors="coerce")
    if pd.isna(minute):
        return None
    minute_int = int(minute)
    if minute_int < 0:
        return None
    return min(minute_int, 95)


def _coerce_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


_PREPARED_MATCH_CACHE: dict[str, tuple[pd.DataFrame, pd.DataFrame]] = {}
_PREPARED_MATCH_CACHE_MAX_ITEMS = 16


def _prepared_match_key(df: pd.DataFrame) -> str:
    if df.empty:
        return "__empty__"
    match_id = ""
    if "matchId" in df.columns and not df["matchId"].dropna().empty:
        match_id = str(df["matchId"].dropna().iloc[0])
    return f"{match_id}:{len(df)}:{tuple(df.columns)}"


def _prepared_in_possession_frames(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    key = _prepared_match_key(df)
    cached = _PREPARED_MATCH_CACHE.get(key)
    if cached is not None:
        return cached
    enriched_df = _with_game_state(df)
    passes_df = _pass_network_passes_df(enriched_df)
    if len(_PREPARED_MATCH_CACHE) >= _PREPARED_MATCH_CACHE_MAX_ITEMS:
        oldest_key = next(iter(_PREPARED_MATCH_CACHE))
        _PREPARED_MATCH_CACHE.pop(oldest_key, None)
    _PREPARED_MATCH_CACHE[key] = (enriched_df, passes_df)
    return enriched_df, passes_df


SHOT_TYPES = ["Goal", "MissedShots", "SavedShot", "ShotOnPost"]

TEAM_COLORS = {
    "Arsenal": "#EF0107",
    "Aston Villa": "#95BFE5",
    "Bournemouth": "#DA291C",
    "Brentford": "#E30613",
    "Brighton": "#0057B8",
    "Burnley": "#6C1D45",
    "Chelsea": "#034694",
    "Crystal Palace": "#1B458F",
    "Everton": "#003399",
    "Fulham": "#FFFFFF",
    "Ipswich": "#005BAC",
    "Leeds": "#F2F2F2",
    "Leicester": "#003090",
    "Liverpool": "#C8102E",
    "Man City": "#6CABDD",
    "Man Utd": "#DA291C",
    "Newcastle": "#F8F5F6",
    "Nottingham Forest": "#E53233",
    "Southampton": "#D71920",
    "Tottenham": "#132257",
    "West Ham": "#7A263A",
    "Wolves": "#FDB913",
    "Barcelona": "#A50044",
    "Real Madrid": "#FCBF00",
    "Atletico Madrid": "#CE3524",
    "Bayern Munich": "#DC052D",
    "Bayer Leverkusen": "#E30613",
    "PSG": "#004170",
    "Inter": "#1E2943",
    "AC Milan": "#FB090B",
    "Juventus": "#F8F4F4",
}


def _fallback_team_color(name: str) -> str:
    palette = ["#22c55e", "#60a5fa", "#f97316", "#eab308", "#a855f7", "#14b8a6", "#ef4444", "#f59e0b"]
    return palette[sum(ord(ch) for ch in name) % len(palette)]


def _ensure_possession_ids(df: pd.DataFrame) -> pd.DataFrame:
    if "possession_id" in df.columns or df.empty or not {"type", "teamName"}.issubset(df.columns):
        return df

    events = df.copy()
    sort_cols = [col for col in ("minute", "second", "index") if col in events.columns]
    if sort_cols:
        events = events.sort_values(sort_cols)

    ignored = {
        "SubstitutionOn", "SubstitutionOff", "FormationChange", "FormationSet", "End",
        "OffsideProvoked", "Start", "GoodSkill", "PenaltyFaced", "ChanceMissed", "CrossNotClaimed",
    }
    filtered = events[~events["type"].isin(ignored)].copy()
    if filtered.empty:
        events["possession_id"] = pd.NA
        return events.reindex(df.index)

    possession_ids: dict[Any, int] = {}
    current_possession = 1
    previous_team: str | None = None
    previous_type = ""
    previous_outcome = ""
    previous_turnover = False

    defensive_control = {
        "Tackle", "Interception", "Clearance", "BallRecovery", "Aerial",
        "BlockedPass", "Challenge", "KeeperPickup", "KeeperSweeper", "Claim",
    }
    possession_enders = {"Goal", "SavedShot", "MissedShots", "ShotOnPost", "OffsideGiven", "Dispossessed", "CornerAwarded"}

    for original_index, row in filtered.iterrows():
        team = str(row.get("teamName", ""))
        event_type = str(row.get("type", ""))
        outcome = str(row.get("outcomeType", ""))
        change_possession = previous_team is None

        if previous_team is not None:
            if previous_type == "Goal":
                change_possession = True
            elif bool(row.get("turnover", False)) and team != previous_team:
                change_possession = True
            elif bool(previous_turnover) and team != previous_team:
                change_possession = True
            elif team != previous_team and event_type in defensive_control and outcome == "Successful":
                change_possession = True
            elif previous_type in possession_enders and team != previous_team:
                change_possession = True
            elif team != previous_team and previous_outcome == "Unsuccessful":
                change_possession = True

        if change_possession and previous_team is not None:
            current_possession += 1

        possession_ids[original_index] = current_possession
        previous_team = team
        previous_type = event_type
        previous_outcome = outcome
        previous_turnover = bool(row.get("turnover", False))

    events["possession_id"] = events.index.map(possession_ids)
    return events.reindex(df.index)


def _with_match_dynamics_possessions(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or not {"type", "teamName"}.issubset(df.columns):
        return df

    events = df.copy()
    if "index" not in events.columns:
        events["index"] = range(len(events))
    if "second" not in events.columns:
        events["second"] = 0
    if "matchId" not in events.columns:
        events["matchId"] = "__match__"

    events = _ensure_possession_ids(events)

    if "cumulative_mins" not in events.columns:
        minute = _coerce_numeric(events.get("minute", pd.Series(0, index=events.index))).fillna(0.0)
        second = _coerce_numeric(events.get("second", pd.Series(0, index=events.index))).fillna(0.0)
        events["cumulative_mins"] = minute + (second / 60.0)

        if "period" in events.columns:
            for period in sorted(_coerce_numeric(events["period"]).dropna().unique()):
                if period <= 1:
                    continue
                previous = events[_coerce_numeric(events["period"]) == period - 1]["cumulative_mins"]
                current = events[_coerce_numeric(events["period"]) == period]["cumulative_mins"]
                if previous.empty or current.empty:
                    continue
                delta = float(previous.max() - current.min())
                if delta > 0:
                    events.loc[_coerce_numeric(events["period"]) == period, "cumulative_mins"] += delta

    return events


def _build_possession_windows(
    df: pd.DataFrame,
    teams: list[str],
    full_time: int,
    window_size: int = 15,
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    if df.empty or "teamName" not in df.columns:
        return [], {team: 0.0 for team in teams}

    match_end = float(full_time)
    if "cumulative_mins" in df.columns:
        match_end = max(match_end, float(_coerce_numeric(df["cumulative_mins"]).fillna(0.0).max()))
    windows = list(range(0, int(math.ceil(match_end / window_size) * window_size) + 1, window_size))

    if "type" in df.columns:
        pass_df = df[df["type"].astype(str).str.lower() == "pass"].copy()
        if not pass_df.empty:
            if "cumulative_mins" in pass_df.columns:
                time_values = _coerce_numeric(pass_df["cumulative_mins"]).fillna(-1.0)
            else:
                time_values = _coerce_numeric(pass_df.get("minute", pd.Series(-1, index=pass_df.index))).fillna(-1.0)
            pass_df = pass_df[time_values >= 0].copy()
            pass_df["time_bin"] = ((time_values[time_values >= 0] // window_size).astype(int) * window_size).to_numpy()

            rows: list[dict[str, Any]] = []
            for window_start in windows:
                if window_start >= match_end:
                    continue
                window_passes = pass_df[pass_df["time_bin"] == window_start]
                total = int(window_passes["teamName"].isin(teams).sum())
                for team in teams:
                    attempts = int((window_passes["teamName"] == team).sum())
                    rows.append(
                        {
                            "minute": int(window_start),
                            "team": team,
                            "possession_pct": round(100.0 * attempts / total, 2) if total > 0 else 0.0,
                        }
                    )

            full_attempts = {team: int((pass_df["teamName"] == team).sum()) for team in teams}
            full_total = sum(full_attempts.values())
            full_match_pct = {
                team: round(100.0 * full_attempts.get(team, 0) / full_total, 1) if full_total > 0 else 0.0
                for team in teams
            }
            return rows, full_match_pct

    if not {"possession_id", "cumulative_mins"}.issubset(df.columns):
        return [], {team: 0.0 for team in teams}

    sort_cols = [col for col in ("cumulative_mins", "minute", "second", "index") if col in df.columns]
    events = df.dropna(subset=["possession_id", "teamName", "cumulative_mins"]).copy()
    events["cumulative_mins"] = _coerce_numeric(events["cumulative_mins"]).fillna(0.0)
    events = events.sort_values(sort_cols if sort_cols else ["cumulative_mins"])
    if events.empty:
        return [], {team: 0.0 for team in teams}

    possessions = (
        events.groupby("possession_id", sort=False)
        .agg(team=("teamName", "first"), start=("cumulative_mins", "first"), end=("cumulative_mins", "last"))
        .reset_index()
    )
    possessions = possessions[possessions["team"].isin(teams)].sort_values("start").reset_index(drop=True)
    if possessions.empty:
        return [], {team: 0.0 for team in teams}

    possessions["duration"] = possessions["end"] - possessions["start"]
    possessions = possessions[possessions["duration"] >= 0].copy()
    possessions["time_bin"] = (possessions["start"] // window_size).astype(int) * window_size

    by_window_team: dict[tuple[int, str], float] = {}
    full_match_totals = {team: 0.0 for team in teams}
    for _, row in possessions.iterrows():
        team = str(row["team"])
        window_start = int(row["time_bin"])
        duration = max(0.0, float(row["duration"]))
        full_match_totals[team] += duration
        by_window_team[(window_start, team)] = by_window_team.get((window_start, team), 0.0) + duration

    rows: list[dict[str, Any]] = []
    for window_start in windows:
        if window_start >= match_end:
            continue
        total = sum(by_window_team.get((window_start, team), 0.0) for team in teams)
        for team in teams:
            possession_time = by_window_team.get((window_start, team), 0.0)
            rows.append(
                {
                    "minute": int(window_start),
                    "team": team,
                    "possession_pct": round(100.0 * possession_time / total, 2) if total > 0 else 0.0,
                }
            )

    full_total = sum(full_match_totals.values())
    full_match_pct = {
        team: round(100.0 * full_match_totals.get(team, 0.0) / full_total, 1) if full_total > 0 else 0.0
        for team in teams
    }
    return rows, full_match_pct


def _bool_count(df: pd.DataFrame, column: str) -> int:
    if column not in df.columns:
        return 0
    return int(df[column].fillna(False).astype(bool).sum())


def _is_successful_defensive_action(row: pd.Series, def_actions: set[str]) -> bool:
    if str(row.get("type", "")) not in def_actions:
        return False
    outcome = row.get("outcomeType")
    return pd.isna(outcome) or str(outcome) == "Successful"


DEFENSIVE_ACTION_TYPES = {
    "Aerial",
    "BallRecovery",
    "BlockedPass",
    "Challenge",
    "Clearance",
    "Error",
    "Foul",
    "Interception",
    "Tackle",
}


def _defensive_action_mask(df: pd.DataFrame) -> pd.Series:
    if df.empty or "type" not in df.columns:
        return pd.Series(False, index=df.index)
    action_type = df["type"].astype(str)
    mask = action_type.isin(DEFENSIVE_ACTION_TYPES)
    if "qualifiers" in df.columns:
        mask = mask & ((action_type != "Aerial") | df["qualifiers"].astype(str).str.contains("Defensive", case=False, na=False))
    if "outcomeType" in df.columns:
        outcome = df["outcomeType"].astype(str).str.lower()
        mask = mask & (outcome.eq("successful") | outcome.eq("nan") | df["outcomeType"].isna())
    return mask


def _zone_from_x(x_value: Any) -> str:
    # Event coordinates are on a 105x68 pitch, so thirds split at 35/70.
    x = _safe_float(x_value)
    if x >= 70:
        return "Attacking Third"
    if x >= 35:
        return "Middle Third"
    return "Defensive Third"


def _count_corners_taken(team_df: pd.DataFrame) -> int:
    if team_df.empty:
        return 0
    if "passCorner" in team_df.columns:
        corners = _bool_count(team_df, "passCorner")
        if corners > 0:
            return corners
    if "cornerAwarded" in team_df.columns:
        corners = _bool_count(team_df, "cornerAwarded")
        if corners > 0:
            return corners
    if "type" in team_df.columns:
        return int(team_df["type"].astype(str).eq("CornerAwarded").sum())
    return 0


def _bool_series(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(False, index=df.index)
    return df[column].fillna(False).astype(bool)


def _match_team_order(df: pd.DataFrame) -> list[str]:
    if df.empty or "teamName" not in df.columns:
        return []
    teams: list[str] = []
    if "h_a" in df.columns:
        for side in ("h", "a"):
            rows = df[df["h_a"] == side]
            if not rows.empty:
                team = str(rows["teamName"].dropna().iloc[0])
                if team and team not in teams:
                    teams.append(team)
    for team in df["teamName"].dropna().astype(str).unique().tolist():
        if team and team not in teams:
            teams.append(team)
    return teams[:2]


def _score_state_label(goal_diff: int) -> str:
    if goal_diff == 0:
        return "Level"
    if goal_diff == 1:
        return "Leading by 1"
    if goal_diff > 1:
        return "Leading by 2+"
    if goal_diff == -1:
        return "Trailing by 1"
    return "Trailing by 2+"


def _score_state_value(goal_diff: int) -> str:
    if goal_diff == 0:
        return "level"
    if goal_diff == 1:
        return "leading_by_1"
    if goal_diff > 1:
        return "leading_by_2_plus"
    if goal_diff == -1:
        return "trailing_by_1"
    return "trailing_by_2_plus"


def _truthy_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return bool(value)


def _with_game_state(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "teamName" not in df.columns:
        return df

    events = df.copy()
    teams = _match_team_order(events)
    if len(teams) < 2:
        events["team_goal_diff_before"] = 0
        events["team_score_state"] = "level"
        events["team_score_state_label"] = "Level"
        events["score_before"] = "0-0"
        return events

    home_team, away_team = teams[0], teams[1]
    scores = {home_team: 0, away_team: 0}
    sort_cols = [col for col in ("minute", "second", "index") if col in events.columns]
    ordered = events.sort_values(sort_cols) if sort_cols else events
    state_rows: dict[Any, dict[str, Any]] = {}

    for index, row in ordered.iterrows():
        team = str(row.get("teamName", ""))
        team_score = scores.get(team, 0)
        opponent_score = scores.get(away_team if team == home_team else home_team, 0)
        diff = int(team_score - opponent_score)
        state_rows[index] = {
            "home_score_before": int(scores[home_team]),
            "away_score_before": int(scores[away_team]),
            "team_goal_diff_before": diff,
            "team_score_state": _score_state_value(diff),
            "team_score_state_label": _score_state_label(diff),
            "score_before": f"{int(scores[home_team])}-{int(scores[away_team])}",
        }

        is_own_goal = _truthy_value(row.get("goalOwn", False))
        if str(row.get("type", "")) == "Goal" and not is_own_goal:
            if team in scores:
                scores[team] += 1
        elif str(row.get("type", "")) == "Goal" and is_own_goal:
            opponent = away_team if team == home_team else home_team
            scores[opponent] += 1

    for column in ("home_score_before", "away_score_before", "team_goal_diff_before", "team_score_state", "team_score_state_label", "score_before"):
        events[column] = events.index.map(lambda index: state_rows.get(index, {}).get(column))
    return events


def _filter_score_state(df: pd.DataFrame, score_state: str | None) -> pd.DataFrame:
    if df.empty or not score_state or score_state == "all" or "team_score_state" not in df.columns:
        return df
    if score_state == "leading":
        return df[_coerce_numeric(df.get("team_goal_diff_before", pd.Series(0, index=df.index))).fillna(0) > 0].copy()
    if score_state == "trailing":
        return df[_coerce_numeric(df.get("team_goal_diff_before", pd.Series(0, index=df.index))).fillna(0) < 0].copy()
    return df[df["team_score_state"].astype(str).eq(score_state)].copy()


GAME_STATE_LABELS = {
    "all": "All states",
    "level": "Level",
    "leading": "Leading",
    "trailing": "Trailing",
    "leading_by_1": "Leading by 1",
    "leading_by_2_plus": "Leading by 2+",
    "trailing_by_1": "Trailing by 1",
    "trailing_by_2_plus": "Trailing by 2+",
}


def _available_game_state_options(df: pd.DataFrame) -> list[dict[str, str]]:
    if df.empty or "team_score_state" not in df.columns:
        return [{"value": "all", "label": GAME_STATE_LABELS["all"]}]
    states = set(df["team_score_state"].dropna().astype(str).tolist())
    options = [{"value": "all", "label": GAME_STATE_LABELS["all"]}]
    if "level" in states:
        options.append({"value": "level", "label": GAME_STATE_LABELS["level"]})
    if any(state.startswith("leading") for state in states):
        options.append({"value": "leading", "label": GAME_STATE_LABELS["leading"]})
    if any(state.startswith("trailing") for state in states):
        options.append({"value": "trailing", "label": GAME_STATE_LABELS["trailing"]})
    for value in ("leading_by_1", "leading_by_2_plus", "trailing_by_1", "trailing_by_2_plus"):
        if value in states:
            options.append({"value": value, "label": GAME_STATE_LABELS[value]})
    return options


def _time_range_options(df: pd.DataFrame, bin_size: int = 15) -> list[dict[str, Any]]:
    minute = _coerce_numeric(df.get("minute", pd.Series(dtype=float))).fillna(-1)
    valid = minute[minute >= 0]
    full_time = int(max(90, valid.max())) if not valid.empty else 90
    end_limit = int(math.ceil(full_time / bin_size) * bin_size)
    options: list[dict[str, Any]] = [{"value": "all", "label": "Full match", "minute_start": 0, "minute_end": full_time}]
    for start in range(0, end_limit, bin_size):
        end = min(start + bin_size, full_time)
        if start >= end:
            continue
        label = "Stoppage" if start >= 90 else f"{start}'-{end}'"
        options.append({"value": f"{start}-{end}", "label": label, "minute_start": start, "minute_end": end})
    return options


def _time_range_option(start: int, end: int, label: str | None = None) -> list[dict[str, Any]]:
    start = int(max(0, start))
    end = int(max(start + 1, end))
    return [{"value": f"{start}-{end}", "label": label or f"{start}'-{end}'", "minute_start": start, "minute_end": end}]


def _time_bounds_for_state(df: pd.DataFrame, window: dict[str, Any], score_state: str | None) -> tuple[int, int]:
    window_start = int(window.get("minute_start", 0))
    window_end = int(window.get("minute_end", 90))
    if df.empty or not score_state or score_state == "all":
        return window_start, window_end
    scoped = _filter_score_state(df, score_state)
    if scoped.empty or "minute" not in scoped.columns:
        return window_start, window_end
    minutes = _coerce_numeric(scoped["minute"]).dropna()
    minutes = minutes[(minutes >= window_start) & (minutes <= window_end)]
    if minutes.empty:
        return window_start, window_end
    start = max(window_start, int(math.floor(float(minutes.min()))))
    end = min(window_end, int(math.ceil(float(minutes.max()))))
    return start, max(start + 1, end)


def _parse_time_range(time_range: str | None, df: pd.DataFrame) -> tuple[int, int] | None:
    if not time_range or time_range == "all":
        return None
    try:
        raw_start, raw_end = str(time_range).split("-", 1)
        start = max(0, int(float(raw_start)))
        end = max(start + 1, int(float(raw_end)))
        return start, end
    except (TypeError, ValueError):
        return None


def _window_scoped_events(df: pd.DataFrame, window: dict[str, Any]) -> pd.DataFrame:
    if df.empty:
        return df
    minute = _coerce_numeric(df.get("minute", pd.Series(0, index=df.index))).fillna(-1)
    start = int(window.get("minute_start", 0))
    end = int(window.get("minute_end", 90))
    return df[(minute >= start) & (minute < end)].copy()


def _normalize_time_range_to_window(time_range: str | None, window: dict[str, Any]) -> str:
    start = int(window.get("minute_start", 0))
    end = int(window.get("minute_end", 90))
    parsed = _parse_time_range(time_range, pd.DataFrame())
    if parsed is None:
        return f"{start}-{end}"
    range_start, range_end = parsed
    range_start = min(max(range_start, start), end - 1)
    range_end = min(max(range_end, range_start + 1), end)
    return f"{range_start}-{range_end}"


def _filter_time_range(df: pd.DataFrame, time_range: str | None) -> pd.DataFrame:
    parsed = _parse_time_range(time_range, df)
    if df.empty or parsed is None:
        return df
    start, end = parsed
    minute = _coerce_numeric(df.get("minute", pd.Series(0, index=df.index))).fillna(-1)
    return df[(minute >= start) & (minute < end)].copy()


def _safe_int(value: Any) -> int:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return 0
    return int(numeric)


def _safe_float(value: Any) -> float:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return 0.0
    return float(numeric)


def _is_shot_on_target(row: pd.Series) -> bool:
    shot_type = str(row.get("type", ""))
    if shot_type == "Goal":
        return True
    if shot_type != "SavedShot":
        return False
    return not bool(row.get("shotBlocked", False))


def _shot_distance_from_goal(row: pd.Series) -> float:
    shot_x = _safe_float(row.get("x"))
    shot_y = _safe_float(row.get("y"))
    return math.sqrt((105.0 - shot_x) ** 2 + (34.0 - shot_y) ** 2)


def _opponent_team_name(events_df: pd.DataFrame, team_name: str) -> str:
    teams = _match_team_order(events_df)
    for candidate in teams:
        if candidate != team_name:
            return candidate
    return team_name


def _shot_display_coordinates(events_df: pd.DataFrame, row: pd.Series, is_own_goal: bool) -> tuple[float, float, float]:
    x = _safe_float(row.get("x"))
    y = _safe_float(row.get("y"))
    distance = _shot_distance_from_goal(row)
    if not is_own_goal:
        return x, y, distance
    display_x = 105.0 - x
    display_y = 68.0 - y
    return display_x, display_y, math.sqrt((105.0 - display_x) ** 2 + (34.0 - display_y) ** 2)


SHOT_EVENT_TYPES = {"Goal", "MissedShots", "SavedShot", "ShotOnPost"}


def _sca_category(event_type: str) -> str:
    normalized = event_type.strip().lower()
    if normalized == "pass":
        return "SCA Passes"
    if normalized == "carry":
        return "SCA Carries"
    if normalized == "takeon":
        return "SCA TakeOns"
    if normalized in {"goal", "missedshots", "savedshot", "shotonpost"}:
        return "SCA Shots"
    return "SCA Def Actions"


def _shot_leadup_events(events_df: pd.DataFrame, shot_row: pd.Series, max_events: int = 3) -> list[dict[str, Any]]:
    if events_df.empty or "teamName" not in events_df.columns or "type" not in events_df.columns:
        return []

    shot_team = str(shot_row.get("teamName", ""))
    shot_is_goal = str(shot_row.get("type", "")) == "Goal"
    shot_period = shot_row.get("period")
    shot_time = _safe_float(shot_row.get("cumulative_mins"))
    if shot_time <= 0:
        shot_time = _safe_float(shot_row.get("minute")) + (_safe_float(shot_row.get("second")) / 60.0)

    candidates = events_df.copy()
    if "cumulative_mins" not in candidates.columns:
        candidates["cumulative_mins"] = (
            _coerce_numeric(candidates.get("minute", pd.Series(0, index=candidates.index))).fillna(0.0)
            + (_coerce_numeric(candidates.get("second", pd.Series(0, index=candidates.index))).fillna(0.0) / 60.0)
        )

    candidates = candidates[candidates["teamName"].astype(str) == shot_team].copy()
    if "period" in candidates.columns and not pd.isna(shot_period):
        shot_period_numeric = pd.to_numeric(shot_period, errors="coerce")
        if not pd.isna(shot_period_numeric):
            candidates = candidates[_coerce_numeric(candidates["period"]) == int(shot_period_numeric)]

    event_time = _coerce_numeric(candidates["cumulative_mins"]).fillna(-1.0)
    candidates = candidates[(event_time < shot_time) & ((shot_time - event_time) <= 0.25)].copy()
    if candidates.empty:
        return []

    related_event_id = pd.to_numeric(shot_row.get("relatedEventId"), errors="coerce")
    direct_assist_mask = pd.Series(False, index=candidates.index)
    if not pd.isna(related_event_id) and "eventId" in candidates.columns:
        direct_assist_mask = direct_assist_mask | (_coerce_numeric(candidates["eventId"]) == float(related_event_id))
    if "qualifiers" in candidates.columns:
        direct_assist_mask = direct_assist_mask | candidates["qualifiers"].astype(str).str.contains("ShotAssist|IntentionalGoalAssist|BigChanceCreated", case=False, na=False)
    direct_assists = candidates[direct_assist_mask].copy()
    if not direct_assists.empty and "playerName" in direct_assists.columns:
        shooter_name = str(shot_row.get("playerName", ""))
        if shooter_name:
            direct_assists = direct_assists[~direct_assists["playerName"].astype(str).eq(shooter_name)]

    action_types = {
        "Pass",
        "Carry",
        "TakeOn",
        "BallRecovery",
        "Interception",
        "Tackle",
        "Challenge",
        "Aerial",
        "Clearance",
        "BlockedPass",
    }
    if not direct_assists.empty:
        candidates = candidates[~candidates.index.isin(direct_assists.index)].copy()
    candidates = candidates[candidates["type"].astype(str).isin(action_types | SHOT_EVENT_TYPES)]
    if "outcomeType" in candidates.columns:
        is_shot_event = candidates["type"].astype(str).isin(SHOT_EVENT_TYPES)
        candidates = candidates[is_shot_event | candidates["outcomeType"].astype(str).str.lower().eq("successful")]
    # A headed/duelled shot pairs the shooter's own duel event (e.g. Aerial) with
    # the shot at the same moment — that artifact must not count as SCA.
    shooter = str(shot_row.get("playerName", ""))
    if shooter and "playerName" in candidates.columns and not candidates.empty:
        paired_types = {"Aerial", "Challenge", "Tackle", "BallRecovery", "Interception", "Clearance", "BlockedPass"}
        candidate_time = _coerce_numeric(candidates["cumulative_mins"]).fillna(-1.0)
        paired_mask = (
            candidates["playerName"].astype(str).eq(shooter)
            & candidates["type"].astype(str).isin(paired_types)
            & ((shot_time - candidate_time) <= 0.05)
        )
        candidates = candidates[~paired_mask]
    if candidates.empty and direct_assists.empty:
        return []

    def scoped_by(column_names: tuple[str, ...]) -> pd.DataFrame:
        scope_col = next((col for col in column_names if col in candidates.columns and col in shot_row.index), None)
        if not scope_col:
            return candidates.iloc[0:0]
        shot_scope = shot_row.get(scope_col)
        if pd.isna(shot_scope):
            return candidates.iloc[0:0]
        return candidates[candidates[scope_col] == shot_scope]

    same_sequence = scoped_by(("sequence_id", "sequenceId", "sequence"))
    same_possession = scoped_by(("possession_id", "possessionId", "possession"))

    shot_situation = str(shot_row.get("situation", "")).lower()
    is_restart_shot = any(token in shot_situation for token in ("corner", "setpiece", "free", "throw"))
    restart_types = {"CornerAwarded", "Start", "FormationChange", "SubstitutionOff", "SubstitutionOn"}

    if not same_sequence.empty:
        candidates = same_sequence
    elif not same_possession.empty:
        candidates = same_possession
    else:
        candidates = candidates if is_restart_shot else candidates[~candidates["type"].astype(str).isin(restart_types)]

    sort_cols = [col for col in ("cumulative_mins", "minute", "second", "eventId", "index") if col in candidates.columns]
    if sort_cols:
        candidates = candidates.sort_values(sort_cols)
        direct_assists = direct_assists.sort_values(sort_cols)
    else:
        candidates = candidates.sort_index()
        direct_assists = direct_assists.sort_index()

    direct_assists = direct_assists.tail(max_events)
    remaining_slots = max(0, max_events - len(direct_assists))
    candidates = pd.concat([candidates.tail(remaining_slots), direct_assists], ignore_index=False)
    if sort_cols and not candidates.empty:
        candidates = candidates.sort_values(sort_cols).tail(max_events)
    else:
        candidates = candidates.sort_index().tail(max_events)

    leadup: list[dict[str, Any]] = []
    shot_x = _safe_float(shot_row.get("x"))
    shot_y = _safe_float(shot_row.get("y"))
    for event_index, event in candidates.iterrows():
        start_x = _safe_float(event.get("x"))
        start_y = _safe_float(event.get("y"))
        end_x = _safe_float(event.get("endX", event.get("x")))
        end_y = _safe_float(event.get("endY", event.get("y")))
        is_direct_assist = event_index in direct_assists.index
        if (end_x == 0.0 and end_y == 0.0) or pd.isna(event.get("endX", pd.NA)) or pd.isna(event.get("endY", pd.NA)):
            end_x = start_x
            end_y = start_y
        if is_direct_assist and abs(end_x - start_x) < 0.01 and abs(end_y - start_y) < 0.01:
            end_x = shot_x
            end_y = shot_y
        is_goal_assist = shot_is_goal and is_direct_assist
        xt_value = _safe_float(event.get("xT")) if "xT" in event.index else _safe_float(event.get("xThreat"))
        xa_value = _safe_float(event.get("xA"))
        leadup.append(
            {
                "event_id": event.get("eventId"),
                "minute": _safe_int(event.get("minute")),
                "second": _safe_int(event.get("second")),
                "player": str(event.get("playerName", "")),
                "type": str(event.get("type", "")),
                "outcome": str(event.get("outcomeType", "")),
                "is_assist": bool(is_goal_assist),
                "xT": round(xt_value, 3),
                "xA": round(xa_value, 3),
                "epv_added": round(_safe_float(event.get("epv_added", event.get("EPV_added"))), 3),
                "x": start_x,
                "y": start_y,
                "end_x": end_x,
                "end_y": end_y,
            }
        )
    # If another shot occurred between the assist pass and this shot (a rebound),
    # the goal has no assist — void any assist credited before that shot.
    last_shot_pos = max(
        (position for position, event in enumerate(leadup) if event["type"] in SHOT_EVENT_TYPES),
        default=None,
    )
    if last_shot_pos is not None:
        for position, event in enumerate(leadup):
            if position < last_shot_pos and event["is_assist"]:
                event["is_assist"] = False
    return leadup


def _clamp_display_color(hex_color: str) -> str:
    """Clamp a kit color's lightness so it reads on both dark and light themes."""
    import colorsys

    value = hex_color.lstrip("#")
    if len(value) != 6:
        return hex_color
    r, g, b = (int(value[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    h, l, sat = colorsys.rgb_to_hls(r, g, b)
    l = min(0.68, max(0.38, l))
    sat = max(0.25, sat) if l not in (0.0, 1.0) else sat
    r2, g2, b2 = colorsys.hls_to_rgb(h, l, sat)
    return "#{:02x}{:02x}{:02x}".format(int(r2 * 255), int(g2 * 255), int(b2 * 255))


def _color_distance(color_a: str, color_b: str) -> float:
    def rgb(hex_color: str) -> tuple[int, int, int]:
        value = hex_color.lstrip("#")
        return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)

    try:
        (r1, g1, b1), (r2, g2, b2) = rgb(color_a), rgb(color_b)
    except ValueError:
        return 999.0
    return ((r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2) ** 0.5


def display_team_colors(home_team: str, away_team: str) -> dict[str, str]:
    home = _clamp_display_color(TEAM_COLORS.get(home_team, "#22c55e"))
    away = _clamp_display_color(TEAM_COLORS.get(away_team, "#38bdf8"))
    if _color_distance(home, away) < 70:
        for candidate in ("#38bdf8", "#f97316", "#a855f7", "#22c55e"):
            if _color_distance(home, candidate) >= 70:
                away = candidate
                break
    return {home_team: home, away_team: away}


def derive_match_context(df: pd.DataFrame, file_path: str | None, source: str) -> MatchContext:
    home_team = "Unknown"
    away_team = "Unknown"
    score = None
    league = None
    season = None
    match_id = "unknown"
    start_date_label = None

    if not df.empty:
        if "h_a" in df.columns and "teamName" in df.columns:
            home_rows = df[df["h_a"] == "h"]
            away_rows = df[df["h_a"] == "a"]
            if not home_rows.empty:
                home_team = str(home_rows["teamName"].iloc[0])
            if not away_rows.empty:
                away_team = str(away_rows["teamName"].iloc[0])
        if "league" in df.columns and not df["league"].dropna().empty:
            league = str(df["league"].dropna().iloc[0])
        if "season" in df.columns and not df["season"].dropna().empty:
            season = str(df["season"].dropna().iloc[0])
        if "matchId" in df.columns and not df["matchId"].dropna().empty:
            match_id = str(df["matchId"].dropna().iloc[0])
        if "score" in df.columns and not df["score"].dropna().empty:
            score = str(df["score"].dropna().iloc[0])

    if file_path:
        fixture = r2.parse_fixture_filename(file_path)
        if fixture:
            score = fixture["score"]
            match_id = str(fixture["match_id"])
            home_team = str(fixture["home_team"])
            away_team = str(fixture["away_team"])
            start_date_label = str(fixture["start_date_label"])

    return MatchContext(
        match_id=match_id,
        league=league,
        season=season,
        home_team=home_team,
        away_team=away_team,
        score=score,
        source="live" if source == "live" else "import" if source == "import" else "r2",
        start_date_label=start_date_label,
        available_views=AVAILABLE_VIEWS,
        team_colors=display_team_colors(home_team, away_team),
    )


def _normalize_team_names(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    normalized = df.copy()

    def mapped_name(raw_name: Any, raw_id: Any = None) -> str:
        numeric_id = pd.to_numeric(raw_id, errors="coerce")
        if not pd.isna(numeric_id) and int(numeric_id) in TEAM_DICT:
            return TEAM_DICT[int(numeric_id)]
        name = str(raw_name).strip()
        numeric_name = pd.to_numeric(name, errors="coerce")
        if not pd.isna(numeric_name) and int(numeric_name) in TEAM_DICT:
            return TEAM_DICT[int(numeric_name)]
        return name

    if "teamName" in normalized.columns:
        team_ids = normalized["teamId"] if "teamId" in normalized.columns else pd.Series([None] * len(normalized), index=normalized.index)
        normalized["teamName"] = [mapped_name(name, team_id) for name, team_id in zip(normalized["teamName"], team_ids)]
    elif "teamId" in normalized.columns:
        normalized["teamName"] = [mapped_name("", team_id) for team_id in normalized["teamId"]]

    return normalized


_MATCH_DF_CACHE: dict[str, tuple[float, pd.DataFrame, MatchContext]] = {}
_MATCH_DF_CACHE_MAX_ITEMS = 12
_MATCH_DF_CACHE_TTL_SECONDS = 15 * 60


def get_match_by_file(file_path: str) -> tuple[pd.DataFrame, MatchContext]:
    now = time.monotonic()
    cached = _MATCH_DF_CACHE.get(file_path)
    if cached is not None and (now - cached[0]) < _MATCH_DF_CACHE_TTL_SECONDS:
        _, df, context = cached
        return df.copy(), context

    df = _normalize_team_names(r2.load_match_dataframe(file_path))
    context = derive_match_context(df, file_path=file_path, source="r2")

    if len(_MATCH_DF_CACHE) >= _MATCH_DF_CACHE_MAX_ITEMS:
        oldest_key = min(_MATCH_DF_CACHE, key=lambda key: _MATCH_DF_CACHE[key][0])
        _MATCH_DF_CACHE.pop(oldest_key, None)
    _MATCH_DF_CACHE[file_path] = (now, df, context)
    logger.info("match dataframe cached for %s (%d events)", file_path, len(df))
    return df.copy(), context


def build_summary_cards(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty:
        return {
            "events": 0,
            "shots": 0,
            "goals": 0,
            "xg_total": 0.0,
            "xgot_total": 0.0,
        }

    shots = int(df["isShot"].fillna(False).astype(bool).sum()) if "isShot" in df.columns else 0
    goals = int(df["isGoal"].fillna(False).astype(bool).sum()) if "isGoal" in df.columns else 0
    xg_total = (
        float(_coerce_numeric(df["xG"]).fillna(0).sum()) if "xG" in df.columns else 0.0
    )
    xgot_total = (
        float(_coerce_numeric(df["xGOT"]).fillna(0).sum()) if "xGOT" in df.columns else 0.0
    )
    return {
        "events": int(len(df)),
        "shots": shots,
        "goals": goals,
        "xg_total": round(xg_total, 2),
        "xgot_total": round(xgot_total, 2),
    }


def build_team_summaries(df: pd.DataFrame) -> list[TeamSummary]:
    if df.empty or "teamName" not in df.columns:
        return []

    rows: list[TeamSummary] = []
    for team_name, team_df in df.groupby("teamName"):
        shots = int(team_df["isShot"].fillna(False).astype(bool).sum()) if "isShot" in team_df.columns else 0
        goals = int(team_df["isGoal"].fillna(False).astype(bool).sum()) if "isGoal" in team_df.columns else 0
        xg = float(_coerce_numeric(team_df["xG"]).fillna(0).sum()) if "xG" in team_df.columns else 0.0
        xgot = float(_coerce_numeric(team_df["xGOT"]).fillna(0).sum()) if "xGOT" in team_df.columns else 0.0

        completed_passes = None
        pass_accuracy = None
        if "type" in team_df.columns:
            passes = team_df[team_df["type"].astype(str).str.lower() == "pass"]
            if not passes.empty:
                completed_passes = int(
                    passes["outcomeType"].astype(str).str.lower().eq("successful").sum()
                ) if "outcomeType" in passes.columns else len(passes)
                if "outcomeType" in passes.columns:
                    pass_accuracy = round(
                        100.0 * passes["outcomeType"].astype(str).str.lower().eq("successful").mean(),
                        1,
                    )

        rows.append(
            TeamSummary(
                team=str(team_name),
                goals=goals,
                shots=shots,
                xg=round(xg, 2),
                xgot=round(xgot, 2),
                completed_passes=completed_passes,
                pass_accuracy=pass_accuracy,
            )
        )

    return rows


def build_available_filters(df: pd.DataFrame) -> dict[str, list[str]]:
    filters: dict[str, list[str]] = {}
    for column in ("teamName", "playerName", "period", "situation", "type"):
        if column in df.columns:
            values = [str(value) for value in df[column].dropna().unique().tolist()]
            filters[column] = sorted(values)
    return filters


def build_player_stats(df: pd.DataFrame, team: str | None = None) -> list[dict[str, Any]]:
    if df.empty or "playerName" not in df.columns:
        return []

    scoped_df = df
    if team and "teamName" in df.columns:
        scoped_df = df[df["teamName"] == team]

    records: list[dict[str, Any]] = []
    for player, player_df in scoped_df.groupby("playerName"):
        if not player or (isinstance(player, float) and math.isnan(player)):
            continue
        records.append(
            {
                "player": str(player),
                "team": str(player_df["teamName"].iloc[0]) if "teamName" in player_df.columns else None,
                "events": int(len(player_df)),
                "shots": int(player_df["isShot"].fillna(False).astype(bool).sum()) if "isShot" in player_df.columns else 0,
                "goals": int(player_df["isGoal"].fillna(False).astype(bool).sum()) if "isGoal" in player_df.columns else 0,
                "xg": round(float(_coerce_numeric(player_df["xG"]).fillna(0).sum()), 2) if "xG" in player_df.columns else 0.0,
            }
        )

    records.sort(key=lambda row: (row["goals"], row["xg"], row["events"]), reverse=True)
    return records[:25]


def build_shot_events(df: pd.DataFrame, team: str | None = None) -> list[dict[str, Any]]:
    if df.empty:
        return []

    shot_df = filter_shots(df, team=team)

    rows: list[dict[str, Any]] = []
    for _, row in shot_df.head(100).iterrows():
        rows.append(
            {
                "event_id": row.get("eventId"),
                "minute": _safe_int(row.get("minute")),
                "team": str(row.get("teamName", "")),
                "player": str(row.get("playerName", "")),
                "xg": round(_safe_float(row.get("xG")), 3),
                "xgot": round(_safe_float(row.get("xGOT")), 3),
                "outcome": str(row.get("outcomeType", "")),
                "situation": str(row.get("situation", "")),
                "x": _safe_float(row.get("x")),
                "y": _safe_float(row.get("y")),
            }
        )
    return rows


def filter_shots(
    df: pd.DataFrame,
    team: str | None = None,
    situation: str | None = None,
    player: str | None = None,
) -> pd.DataFrame:
    if df.empty or "type" not in df.columns:
        return df.iloc[0:0].copy()

    shot_df = df[df["type"].isin(SHOT_TYPES)].copy()
    if team and "teamName" in shot_df.columns:
        shot_df = shot_df[shot_df["teamName"] == team]
    if situation and situation != "All" and "situation" in shot_df.columns:
        shot_df = shot_df[shot_df["situation"] == situation]
    if player and "playerName" in shot_df.columns:
        shot_df = shot_df[shot_df["playerName"] == player]

    if "xG" in shot_df.columns:
        shot_df["xG"] = pd.to_numeric(shot_df["xG"], errors="coerce").fillna(0.05)
    if "xGOT" in shot_df.columns:
        shot_df["xGOT"] = pd.to_numeric(shot_df["xGOT"], errors="coerce").fillna(0.0)
    return shot_df.reset_index(drop=True)


def _prepare_shot_sca_frames(df: pd.DataFrame) -> pd.DataFrame:
    try:
        enriched_df = _with_match_dynamics_possessions(df)
    except Exception:
        logger.warning("match-dynamics possession enrichment failed; using raw events", exc_info=True)
        enriched_df = df.copy()
    enriched_df = _with_game_state(enriched_df)
    if "cumulative_mins" not in enriched_df.columns:
        enriched_df["cumulative_mins"] = (
            _coerce_numeric(enriched_df.get("minute", pd.Series(0, index=enriched_df.index))).fillna(0.0)
            + (_coerce_numeric(enriched_df.get("second", pd.Series(0, index=enriched_df.index))).fillna(0.0) / 60.0)
        )
    return enriched_df


def _build_shot_detail_rows(enriched_df: pd.DataFrame, shots_df: pd.DataFrame) -> list[dict[str, Any]]:
    if shots_df.empty:
        return []

    rows: list[dict[str, Any]] = []
    for _, row in shots_df.sort_values(
        by=[col for col in ["minute", "second"] if col in shots_df.columns]
    ).iterrows():
        raw_team = str(row.get("teamName", ""))
        is_own_goal = _truthy_value(row.get("goalOwn", False))
        credited_team = _opponent_team_name(enriched_df, raw_team) if is_own_goal else raw_team
        display_x, display_y, display_distance = _shot_display_coordinates(enriched_df, row, is_own_goal)
        raw_goal_diff = _safe_int(row.get("team_goal_diff_before"))
        display_goal_diff = -raw_goal_diff if is_own_goal else raw_goal_diff
        rows.append(
            {
                "minute": _safe_int(row.get("minute")),
                "second": _safe_int(row.get("second")),
                "player": f"{str(row.get('playerName', '')).strip()} (OG)" if is_own_goal else str(row.get("playerName", "")),
                "shooting_team": raw_team,
                "team": credited_team,
                "type": str(row.get("type", "")),
                "xg": 0.0 if is_own_goal else round(_safe_float(row.get("xG")), 3),
                "xgot": 0.0 if is_own_goal else round(_safe_float(row.get("xGOT")), 3),
                "xgot_model_version": str(row.get("xgot_model_version", "")),
                "xgot_shot_placement_zone": str(row.get("xgot_shot_placement_zone", "")),
                "situation": str(row.get("situation", "")),
                "body_part": str(row.get("shotBodyType", "")),
                "blocked": bool(row.get("shotBlocked", False)),
                "off_target": bool(row.get("shotOffTarget", False)),
                "on_target": _is_shot_on_target(row),
                "shot_distance": round(display_distance, 1),
                "x": display_x,
                "y": display_y,
                "raw_x": _safe_float(row.get("x")),
                "raw_y": _safe_float(row.get("y")),
                "goal_mouth_y": _safe_float(row.get("goalMouthY")),
                "goal_mouth_z": _safe_float(row.get("goalMouthZ")),
                "own_goal": is_own_goal,
                "score_before": str(row.get("score_before", "0-0")),
                "game_state": _score_state_value(display_goal_diff),
                "game_state_label": _score_state_label(display_goal_diff),
                "goal_diff_before": display_goal_diff,
                "leadup_events": _shot_leadup_events(enriched_df, row),
            }
        )
    return rows


def _shot_result_bucket(row: dict[str, Any]) -> str:
    if bool(row.get("blocked")):
        return "BlockedShots"
    shot_type = str(row.get("type", ""))
    if shot_type == "Goal":
        return "Goals"
    if shot_type == "SavedShot":
        return "On Target"
    if shot_type == "ShotOnPost":
        return "Woodwork"
    return "Off Target"


def _build_shot_player_summary_from_rows(shot_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    players: dict[str, dict[str, Any]] = {}

    def ensure_player(name: str, team_name: str) -> dict[str, Any]:
        row = players.setdefault(
            name,
            {
                "playerName": name,
                "Team": team_name,
                "Goals": 0,
                "On Target": 0,
                "Off Target": 0,
                "Woodwork": 0,
                "BlockedShots": 0,
                "Shots On Target": 0,
                "Total Shots": 0,
                "Total xG": 0.0,
                "Total xGOT": 0.0,
                "xG/Shot": 0.0,
                "xGOT/Shot": 0.0,
                "Avg Shot Distance": 0.0,
                "_shot_distance_total": 0.0,
                "SCA Count": 0,
                "SCA Passes": 0,
                "SCA Carries": 0,
                "SCA TakeOns": 0,
                "SCA Shots": 0,
                "SCA Def Actions": 0,
                "SCA xT": 0.0,
                "xT/SCA": 0.0,
                "Assists": 0,
                "xA": 0.0,
            },
        )
        if not row.get("Team") and team_name:
            row["Team"] = team_name
        return row

    for shot in shot_rows:
        shooter = str(shot.get("player", "")).strip()
        shot_team = str(shot.get("team", "")).strip()
        if shooter and not bool(shot.get("own_goal")):
            player_row = ensure_player(shooter, shot_team)
            bucket = _shot_result_bucket(shot)
            player_row[bucket] += 1
            player_row["Total Shots"] += 1
            player_row["Total xG"] += _safe_float(shot.get("xg"))
            player_row["Total xGOT"] += _safe_float(shot.get("xgot"))
            player_row["_shot_distance_total"] += _safe_float(shot.get("shot_distance"))

        for leadup_event in shot.get("leadup_events", []):
            creator = str(leadup_event.get("player", "")).strip()
            if not creator:
                continue
            player_row = ensure_player(creator, shot_team)
            category = _sca_category(str(leadup_event.get("type", "")))
            player_row["SCA Count"] += 1
            player_row[category] = player_row.get(category, 0) + 1
            player_row["SCA xT"] += _safe_float(leadup_event.get("xT"))
            player_row["xA"] += _safe_float(leadup_event.get("xA"))
            if bool(leadup_event.get("is_assist")):
                player_row["Assists"] += 1

    summary: list[dict[str, Any]] = []
    for row in players.values():
        total_shots = int(row["Total Shots"])
        row["Shots On Target"] = int(row["Goals"]) + int(row["On Target"])
        if total_shots > 0:
            row["xG/Shot"] = round(float(row["Total xG"]) / total_shots, 3)
            row["xGOT/Shot"] = round(float(row["Total xGOT"]) / total_shots, 3)
            row["Avg Shot Distance"] = round(float(row["_shot_distance_total"]) / total_shots, 1)
        if int(row["SCA Count"]) > 0:
            row["xT/SCA"] = round(float(row["SCA xT"]) / int(row["SCA Count"]), 3)
        row["Total xG"] = round(float(row["Total xG"]), 3)
        row["Total xGOT"] = round(float(row["Total xGOT"]), 3)
        row["SCA xT"] = round(float(row["SCA xT"]), 3)
        row["xA"] = round(float(row["xA"]), 3)
        row.pop("_shot_distance_total", None)
        if row["Total Shots"] > 0 or row["SCA Count"] > 0:
            summary.append(row)

    return sorted(summary, key=lambda item: (float(item["Total xG"]), float(item["Total xGOT"]), int(item["SCA Count"])), reverse=True)


def _build_shot_team_totals(shot_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    totals: dict[str, dict[str, Any]] = {}
    for shot in shot_rows:
        team_name = str(shot.get("team", "")).strip()
        if not team_name:
            continue
        row = totals.setdefault(
            team_name,
            {
                "team": team_name,
                "shots": 0,
                "goals": 0,
                "shots_on_target": 0,
                "xg": 0.0,
                "xgot": 0.0,
                "sca": 0,
                "sca_xt": 0.0,
                "assists": 0,
                "xa": 0.0,
            },
        )
        if not bool(shot.get("own_goal")):
            row["shots"] += 1
            row["xg"] += _safe_float(shot.get("xg"))
            row["xgot"] += _safe_float(shot.get("xgot"))
        if str(shot.get("type", "")) == "Goal":
            row["goals"] += 1
        if bool(shot.get("on_target")) and not bool(shot.get("own_goal")):
            row["shots_on_target"] += 1
        for event in shot.get("leadup_events", []):
            row["sca"] += 1
            row["sca_xt"] += _safe_float(event.get("xT"))
            row["xa"] += _safe_float(event.get("xA"))
            if bool(event.get("is_assist")):
                row["assists"] += 1

    for row in totals.values():
        row["xg"] = round(float(row["xg"]), 3)
        row["xgot"] = round(float(row["xgot"]), 3)
        row["sca_xt"] = round(float(row["sca_xt"]), 3)
        row["xa"] = round(float(row["xa"]), 3)
    return list(totals.values())


def _shot_team_state_controls(enriched_df: pd.DataFrame) -> dict[str, Any]:
    if enriched_df.empty or "teamName" not in enriched_df.columns:
        return {}
    minute = _coerce_numeric(enriched_df.get("minute", pd.Series(0, index=enriched_df.index))).fillna(0)
    full_time = int(max(90, minute.max())) if not minute.empty else 90
    window = {"minute_start": 0, "minute_end": full_time}
    controls: dict[str, Any] = {}
    for team_name in _match_team_order(enriched_df):
        team_events = enriched_df[enriched_df["teamName"].astype(str).eq(team_name)].copy()
        options = _available_game_state_options(team_events)
        ranges = {}
        for option in options:
            value = str(option.get("value", "all"))
            start, end = _time_bounds_for_state(team_events, window, value)
            ranges[value] = {"value": f"{start}-{end}", "minute_start": start, "minute_end": end, "label": f"{start}'-{end}'"}
        controls[team_name] = {
            "game_state_options": options,
            "state_time_ranges": ranges,
            "full_time": full_time,
        }
    return controls


def build_shots_sca_view(
    df: pd.DataFrame,
    situation: str | None = None,
) -> dict[str, Any]:
    enriched_df = _prepare_shot_sca_frames(df)
    shots_df = filter_shots(enriched_df, situation=situation)
    shot_rows = _build_shot_detail_rows(enriched_df, shots_df)
    return {
        "shot_rows": shot_rows,
        "player_summary": _build_shot_player_summary_from_rows(shot_rows),
        "team_totals": _build_shot_team_totals(shot_rows),
        "game_state_options": _available_game_state_options(enriched_df),
        "time_range_options": _time_range_options(enriched_df),
        "team_state_controls": _shot_team_state_controls(enriched_df),
    }


def _pass_network_passes_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "type" not in df.columns:
        return df.iloc[0:0].copy()

    events = df.copy()
    if "index" not in events.columns:
        events["index"] = range(len(events))
    sort_cols = [col for col in ("minute", "second", "index") if col in events.columns]
    if sort_cols:
        events = events.sort_values(sort_cols)
    ignored = "SubstitutionOn|FormationChange|FormationSet|Card"
    events = events[~events["type"].astype(str).str.contains(ignored, case=False, na=False)].copy()
    if "playerId" in events.columns:
        next_player = events["playerId"].shift(-1)
        next_team = events["teamName"].shift(-1) if "teamName" in events.columns else pd.NA
        events["receiver"] = next_player.where(events["teamName"] == next_team, pd.NA)
    else:
        events["receiver"] = pd.NA

    pass_columns = [
        "index", "x", "y", "minute", "endX", "endY", "teamName", "playerId",
        "receiver", "type", "outcomeType", "isFirstEleven", "playerName", "xT", "prog_pass",
        "team_goal_diff_before", "team_score_state", "team_score_state_label", "score_before",
    ]
    for column in pass_columns:
        if column not in events.columns:
            events[column] = pd.NA
    passes = events[events["type"].astype(str) == "Pass"][pass_columns].copy()
    id_to_name = dict(zip(passes["playerId"], passes["playerName"]))
    passes["receiverName"] = passes["receiver"].map(id_to_name)
    return passes


def build_shot_player_summary(
    df: pd.DataFrame,
    team: str | None = None,
    situation: str | None = None,
) -> list[dict[str, Any]]:
    payload = build_shots_sca_view(df, situation=situation)
    rows = payload["player_summary"]
    if team:
        rows = [row for row in rows if row.get("Team") == team]
    return rows

def build_shot_details(
    df: pd.DataFrame,
    team: str | None = None,
    situation: str | None = None,
    player: str | None = None,
) -> list[dict[str, Any]]:
    enriched_df = _prepare_shot_sca_frames(df)
    shots_df = filter_shots(enriched_df, team=team, situation=situation, player=player)
    return _build_shot_detail_rows(enriched_df, shots_df)[:50]


def build_event_timeline(df: pd.DataFrame, team: str | None = None) -> list[dict[str, Any]]:
    if df.empty:
        return []

    scoped_df = df
    if team and "teamName" in df.columns:
        scoped_df = df[df["teamName"] == team]

    timeline: list[dict[str, Any]] = []
    for _, row in scoped_df.head(300).iterrows():
        minute = pd.to_numeric(row.get("minute"), errors="coerce")
        if pd.isna(minute):
            continue
        timeline.append(
            {
                "minute": int(minute),
                "team": str(row.get("teamName", "")),
                "player": str(row.get("playerName", "")),
                "event_type": str(row.get("type", "")),
                "outcome": str(row.get("outcomeType", "")),
                "is_shot": bool(row.get("isShot", False)),
                "is_goal": bool(row.get("isGoal", False)),
            }
        )

    timeline.sort(key=lambda row: (row["minute"], row["team"]))
    return timeline


def build_player_comparison(df: pd.DataFrame, players: list[str] | None = None) -> list[dict[str, Any]]:
    records = build_player_stats(df)
    if players:
        requested = set(players)
        records = [row for row in records if row["player"] in requested]
    return records[:12]


def build_match_summary_view(df: pd.DataFrame) -> dict[str, Any]:
    periods: dict[str, dict[str, int]] = {}
    if "period" in df.columns and "type" in df.columns:
        for period, period_df in df.groupby("period"):
            periods[str(period)] = {
                "events": int(len(period_df)),
                "shots": int(period_df["isShot"].fillna(False).astype(bool).sum()) if "isShot" in period_df.columns else 0,
                "goals": int(period_df["isGoal"].fillna(False).astype(bool).sum()) if "isGoal" in period_df.columns else 0,
            }

    return {
        "summary_cards": build_summary_cards(df),
        "team_summaries": [row.model_dump() for row in build_team_summaries(df)],
        "periods": periods,
    }


def build_match_dynamics(df: pd.DataFrame) -> dict[str, Any]:
    df = _with_match_dynamics_possessions(df)
    team_summaries = build_team_summaries(df)
    teams = [row.team for row in team_summaries][:2]
    if len(teams) < 2:
        return {
            "teams": teams,
            "team_summary_rows": [],
            "match_summary": "",
            "event_markers": [],
            "xg_flow": [],
            "possession_pass_accuracy": [],
            "attack_flanks": [],
            "ppda_turnovers": [],
            "xt_momentum": [],
            "epv_momentum": [],
        }

    first_team, second_team = teams
    team_colors = {team: TEAM_COLORS.get(team, _fallback_team_color(team)) for team in teams}
    minute_series = _coerce_numeric(df.get("minute", pd.Series(dtype=float))).fillna(-1).astype(int)
    valid_minutes = minute_series[minute_series >= 0]
    full_time = int(max(90, valid_minutes.max())) if not valid_minutes.empty else 90
    windows = list(range(0, full_time + 1, 15))

    type_series = df["type"].astype(str) if "type" in df.columns else pd.Series("", index=df.index, dtype=str)
    outcome_series = df["outcomeType"].astype(str) if "outcomeType" in df.columns else pd.Series("", index=df.index, dtype=str)

    # xG flow with goal + substitution markers
    shot_df = filter_shots(df).copy()
    shot_df["minute"] = _coerce_numeric(shot_df.get("minute", pd.Series(dtype=float))).fillna(-1).astype(int)
    shot_df["xG"] = _coerce_numeric(shot_df.get("xG", pd.Series(dtype=float))).fillna(0.0)
    shot_df = shot_df[shot_df["minute"] >= 0]
    xg_flow: list[dict[str, Any]] = []
    xg_markers: list[dict[str, Any]] = []
    for team in teams:
        team_shots = shot_df[shot_df.get("teamName") == team].sort_values("minute").copy()
        minute_xg = team_shots.groupby("minute")["xG"].sum().reindex(range(0, full_time + 1), fill_value=0.0)
        cumulative = minute_xg.cumsum()
        for minute, value in cumulative.items():
            xg_flow.append({"team": team, "minute": int(minute), "cumulative_xg": round(float(value), 3)})
        if "type" in team_shots.columns:
            goals = team_shots[team_shots["type"].astype(str) == "Goal"]
        else:
            goals = team_shots.iloc[0:0]
        for _, row in goals.iterrows():
            m = int(row["minute"])
            xg_markers.append(
                {
                    "team": team,
                    "minute": m,
                    "event_type": "goal",
                    "player": str(row.get("playerName", "")),
                    "xg": round(float(row.get("xG", 0.0)), 3),
                    "cumulative_xg": round(float(cumulative.get(m, cumulative.iloc[-1] if not cumulative.empty else 0.0)), 3),
                }
            )
        team_subs = df[(df.get("teamName") == team) & (type_series == "SubstitutionOn")].copy() if "type" in df.columns else df.iloc[0:0]
        for _, row in team_subs.iterrows():
            m = _minute_bucket(row.get("minute"))
            if m is None:
                continue
            mm = min(m, full_time)
            xg_markers.append(
                {
                    "team": team,
                    "minute": mm,
                    "event_type": "substitution",
                    "player": str(row.get("playerName", "")),
                    "cumulative_xg": round(float(cumulative.get(mm, cumulative.iloc[-1] if not cumulative.empty else 0.0)), 3),
                }
            )

    # Possession % and pass accuracy by 15-minute windows.
    pos_pass_rows, full_match_possession = _build_possession_windows(df, teams, full_time)
    pos_row_lookup = {(row["minute"], row["team"]): row for row in pos_pass_rows}
    for start in windows:
        end = min(full_time + 1, start + 15)
        if "cumulative_mins" in df.columns:
            time_series = _coerce_numeric(df["cumulative_mins"]).fillna(-1)
            in_window = (time_series >= start) & (time_series < end)
        else:
            in_window = (minute_series >= start) & (minute_series < end)
        wdf = df[in_window].copy()
        if wdf.empty:
            continue
        pass_df = wdf[wdf["type"].astype(str).str.lower() == "pass"] if "type" in wdf.columns else wdf.iloc[0:0]
        for team in teams:
            attempted = int((pass_df.get("teamName") == team).sum()) if not pass_df.empty and "teamName" in pass_df.columns else 0
            successful = int(((pass_df.get("teamName") == team) & pass_df["outcomeType"].astype(str).str.lower().eq("successful")).sum()) if not pass_df.empty and "outcomeType" in pass_df.columns else 0
            row = pos_row_lookup.setdefault((start, team), {"minute": start, "team": team, "possession_pct": 0.0})
            row["pass_accuracy_pct"] = round(100.0 * successful / attempted, 2) if attempted else 0.0
    pos_pass_rows = sorted(pos_row_lookup.values(), key=lambda row: (row["minute"], teams.index(row["team"]) if row["team"] in teams else 99))

    # Attacks by flank (with xG)
    attack_types = {"Pass", "Carry", "SavedShot", "MissedShots", "Goal", "ShotOnPost"}
    shot_types = {"SavedShot", "MissedShots", "Goal", "ShotOnPost"}
    attack_flanks: list[dict[str, Any]] = []
    if "possession_id" in df.columns:
        for team in teams:
            counters = {"Left": {"attacks": 0, "xg": 0.0}, "Center": {"attacks": 0, "xg": 0.0}, "Right": {"attacks": 0, "xg": 0.0}}
            team_poss = df[df.get("teamName") == team].groupby("possession_id")
            for _, pe in team_poss:
                pe_type = pe["type"] if "type" in pe.columns else pd.Series("", index=pe.index, dtype=str)
                q = pe[pe_type.isin(attack_types) & (_coerce_numeric(pe.get("x", pd.Series(dtype=float))) > 70.12)]
                if q.empty:
                    continue
                y = float(pd.to_numeric(q.iloc[0].get("y"), errors="coerce")) if "y" in q.columns else 34.0
                flank = "Left" if y < 22.67 else "Center" if y < 45.33 else "Right"
                counters[flank]["attacks"] += 1
                q_type = q["type"] if "type" in q.columns else pd.Series("", index=q.index, dtype=str)
                shots = q[q_type.isin(shot_types)]
                counters[flank]["xg"] += float(_coerce_numeric(shots.get("xG", pd.Series(dtype=float))).fillna(0).sum()) if not shots.empty else 0.0
            for flank in ("Left", "Center", "Right"):
                attack_flanks.append(
                    {"team": team, "flank": flank, "num_attacks": counters[flank]["attacks"], "total_xg": round(counters[flank]["xg"], 3)}
                )

    if not attack_flanks or all(row["num_attacks"] == 0 for row in attack_flanks):
        attack_flanks = []
        for team in teams:
            team_events = df[df.get("teamName") == team].copy()
            team_types = team_events["type"] if "type" in team_events.columns else pd.Series("", index=team_events.index, dtype=str)
            final_third = team_events[
                team_types.isin(attack_types)
                & (_coerce_numeric(team_events.get("x", pd.Series(dtype=float))) > 70.12)
            ].copy()
            final_third["xG"] = _coerce_numeric(final_third.get("xG", pd.Series(dtype=float))).fillna(0.0)
            y_values = _coerce_numeric(final_third.get("y", pd.Series(dtype=float))).fillna(34.0)
            flank_masks = {
                "Left": y_values < 22.67,
                "Center": (y_values >= 22.67) & (y_values < 45.33),
                "Right": y_values >= 45.33,
            }
            for flank, mask in flank_masks.items():
                flank_events = final_third[mask]
                flank_types = flank_events["type"] if "type" in flank_events.columns else pd.Series("", index=flank_events.index, dtype=str)
                attack_flanks.append(
                    {
                        "team": team,
                        "flank": flank,
                        "num_attacks": int(mask.sum()),
                        "total_xg": round(float(flank_events[flank_types.isin(shot_types)]["xG"].sum()), 3) if not flank_events.empty else 0.0,
                    }
                )

    # PPDA + turnovers by 15-minute windows
    ppda_rows: list[dict[str, Any]] = []
    def_actions = {"Interception", "Tackle", "Clearance", "BlockedPass", "BallRecovery", "Challenge"}
    ppda_by_window_team: dict[tuple[int, str], float] = {}
    if {"possession_id", "teamName", "type"}.issubset(df.columns):
        ppda_df = df.dropna(subset=["possession_id", "teamName"]).copy()
        if "second" not in ppda_df.columns:
            ppda_df["second"] = 0
        timestamp = _coerce_numeric(ppda_df.get("minute", pd.Series(0, index=ppda_df.index))).fillna(0) * 60 + _coerce_numeric(ppda_df.get("second", pd.Series(0, index=ppda_df.index))).fillna(0)
        ppda_df["time_bin"] = (timestamp // 900).fillna(-1).astype(int)
        ppda_df["is_pass"] = ppda_df["type"].astype(str).eq("Pass")
        ppda_df["is_def_action"] = ppda_df.apply(lambda row: _is_successful_defensive_action(row, def_actions), axis=1)
        team_set = set(teams)

        def opposition_for(team_name: Any) -> str | None:
            team_str = str(team_name)
            return next((team for team in teams if team != team_str), None) if team_str in team_set else None

        poss_summary = (
            ppda_df.groupby("possession_id", sort=False)
            .agg(
                team=("teamName", "first"),
                passes=("is_pass", "sum"),
                def_actions=("is_def_action", "sum"),
                time_bin=("time_bin", "first"),
            )
            .reset_index()
        )
        poss_summary["opposition"] = poss_summary["team"].map(opposition_for)
        ppda_summary = (
            poss_summary.dropna(subset=["opposition"])
            .groupby(["time_bin", "opposition"])
            .agg(total_passes=("passes", "sum"), total_def_actions=("def_actions", "sum"))
            .reset_index()
        )
        for _, row in ppda_summary.iterrows():
            ppda_team = str(row["opposition"])
            total_def_actions = float(row["total_def_actions"])
            ppda_by_window_team[(int(row["time_bin"]) * 15, ppda_team)] = round(float(row["total_passes"]) / total_def_actions, 3) if total_def_actions > 0 else 0.0

    for start in windows:
        end = min(full_time + 1, start + 15)
        if "cumulative_mins" in df.columns:
            time_series = _coerce_numeric(df["cumulative_mins"]).fillna(-1)
            in_window = (time_series >= start) & (time_series < end)
        else:
            in_window = (minute_series >= start) & (minute_series < end)
        wdf = df[in_window].copy()
        for team in teams:
            team_df = wdf[wdf.get("teamName") == team]
            turnovers = int((_coerce_numeric(team_df.get("turnover", pd.Series(dtype=float))).fillna(0) + _coerce_numeric(team_df.get("dispossessed", pd.Series(dtype=float))).fillna(0)).sum())
            ppda_rows.append({"minute": start, "team": team, "ppda": ppda_by_window_team.get((start, team), 0.0), "turnovers": turnovers})

    # xT momentum flow (teamA positive, teamB negative)
    xt_col = "xT" if "xT" in df.columns else "xThreat" if "xThreat" in df.columns else None
    xt_rows: list[dict[str, Any]] = []
    if xt_col:
        if "type" in df.columns:
            xt_df = df[(type_series.isin(["Pass", "Carry"])) & (outcome_series == "Successful")].copy()
        else:
            xt_df = df.iloc[0:0]
        xt_df["minute"] = _coerce_numeric(xt_df.get("minute", pd.Series(dtype=float))).fillna(-1).astype(int)
        xt_df = xt_df[xt_df["minute"] >= 0]
        xt_df["xt_clip"] = _coerce_numeric(xt_df.get(xt_col, pd.Series(dtype=float))).fillna(0.0).clip(lower=0.0, upper=0.1)
        max_per_min = xt_df.groupby(["teamName", "minute"])["xt_clip"].max()
        for minute in range(0, full_time + 1):
            t1 = 0.0
            t2 = 0.0
            for back in (0, 1, 2):
                w = math.exp(-0.1 * back)
                t1 += w * float(max_per_min.get((first_team, minute - back), 0.0))
                t2 += w * float(max_per_min.get((second_team, minute - back), 0.0))
            xt_rows.append({"minute": minute, first_team: round(t1, 4), second_team: round(-t2, 4), "momentum": round(t1 - t2, 4)})

    # EPV momentum flow (teamA positive, teamB negative)
    epv_rows: list[dict[str, Any]] = []
    if "epv_added" in df.columns:
        if "type" in df.columns:
            epv_df = df[(type_series.isin(["Pass", "Carry"])) & (outcome_series == "Successful")].copy()
        else:
            epv_df = df.iloc[0:0]
        epv_df["minute"] = _coerce_numeric(epv_df.get("minute", pd.Series(dtype=float))).fillna(-1).astype(int)
        epv_df = epv_df[epv_df["minute"] >= 0]
        epv_df["epv_clip"] = _coerce_numeric(epv_df.get("epv_added", pd.Series(dtype=float))).fillna(0.0).clip(lower=0.0, upper=0.18)
        max_epv_per_min = epv_df.groupby(["teamName", "minute"])["epv_clip"].max()
        for minute in range(0, full_time + 1):
            t1 = 0.0
            t2 = 0.0
            for back in (0, 1, 2):
                w = math.exp(-0.1 * back)
                t1 += w * float(max_epv_per_min.get((first_team, minute - back), 0.0))
                t2 += w * float(max_epv_per_min.get((second_team, minute - back), 0.0))
            epv_rows.append({"minute": minute, first_team: round(t1, 4), second_team: round(-t2, 4), "momentum": round(t1 - t2, 4)})

    # Rich team summary for the public match dynamics page.
    team_summary_rows: list[dict[str, Any]] = []
    total_events = max(1, len(df))
    possession_lookup = full_match_possession
    ppda_lookup = {
        team: round(
            float(pd.Series([row["ppda"] for row in ppda_rows if row["team"] == team and row["ppda"] > 0]).mean()),
            2,
        )
        if any(row["team"] == team and row["ppda"] > 0 for row in ppda_rows)
        else 0.0
        for team in teams
    }
    turnover_lookup = {team: int(sum(row["turnovers"] for row in ppda_rows if row["team"] == team)) for team in teams}
    attack_lookup = {team: int(sum(row["num_attacks"] for row in attack_flanks if row["team"] == team)) for team in teams}
    flank_xg_lookup = {team: round(float(sum(row["total_xg"] for row in attack_flanks if row["team"] == team)), 2) for team in teams}

    for summary in team_summaries:
        team = summary.team
        team_df = df[df.get("teamName") == team].copy()
        team_types = team_df["type"].astype(str) if "type" in team_df.columns else pd.Series("", index=team_df.index, dtype=str)
        shot_team_df = shot_df[shot_df.get("teamName") == team].copy()
        shots_on_target = int(shot_team_df.apply(_is_shot_on_target, axis=1).sum()) if not shot_team_df.empty else 0
        passes = team_df[team_types.str.lower() == "pass"]
        pass_attempts = int(len(passes))
        completed_passes = int(passes["outcomeType"].astype(str).str.lower().eq("successful").sum()) if pass_attempts and "outcomeType" in passes.columns else 0
        accurate_passes = team_df[
            team_types.eq("Pass")
            & team_df.get("outcomeType", pd.Series("", index=team_df.index)).astype(str).eq("Successful")
        ]
        final_third_entries = int((_coerce_numeric(accurate_passes.get("endX", pd.Series(dtype=float))).fillna(0.0) > 75).sum())
        big_chances_created = _bool_count(team_df, "bigChanceCreated")
        big_chances_missed = _bool_count(team_df, "bigChanceMissed")
        corners_taken = _count_corners_taken(team_df)
        xt_total = 0.0
        if xt_col:
            team_xt = team_df[team_types.isin(["Pass", "Carry"])].copy()
            if "outcomeType" in team_xt.columns:
                team_xt = team_xt[team_xt["outcomeType"].astype(str) == "Successful"]
            xt_total = float(_coerce_numeric(team_xt.get(xt_col, pd.Series(dtype=float))).fillna(0.0).clip(lower=0.0).sum())
        epv_total = 0.0
        if "epv_added" in team_df.columns:
            team_epv = team_df[team_types.isin(["Pass", "Carry"])].copy()
            if "outcomeType" in team_epv.columns:
                team_epv = team_epv[team_epv["outcomeType"].astype(str) == "Successful"]
            epv_total = float(_coerce_numeric(team_epv.get("epv_added", pd.Series(dtype=float))).fillna(0.0).sum())
        team_summary_rows.append(
            {
                "team": team,
                "goals": summary.goals,
                "xg": summary.xg,
                "xgot": summary.xgot,
                "shots": summary.shots,
                "shots_on_target": shots_on_target,
                "pass_accuracy": summary.pass_accuracy if summary.pass_accuracy is not None else (round(100.0 * completed_passes / pass_attempts, 1) if pass_attempts else 0.0),
                "completed_passes": completed_passes,
                "big_chances_created": big_chances_created,
                "big_chances_missed": big_chances_missed,
                "possession_pct": possession_lookup.get(team, 0.0),
                "ppda": ppda_lookup.get(team, 0.0),
                "turnovers": turnover_lookup.get(team, 0),
                "final_third_entries": final_third_entries,
                "corners_taken": corners_taken,
                "attacks": attack_lookup.get(team, 0),
                "flank_xg": flank_xg_lookup.get(team, 0.0),
                "xt": round(xt_total, 2),
                "epv_added": round(epv_total, 2),
                "event_share": round(100.0 * len(team_df) / total_events, 1),
            }
        )

    sorted_by_goals = sorted(team_summary_rows, key=lambda row: (row["goals"], row["xg"], row["shots"]), reverse=True)
    sorted_by_xg = sorted(team_summary_rows, key=lambda row: (row["xg"], row["shots"]), reverse=True)
    winner = sorted_by_goals[0] if sorted_by_goals else {}
    opponent = sorted_by_goals[1] if len(sorted_by_goals) > 1 else {}
    xg_leader = sorted_by_xg[0] if sorted_by_xg else {}
    if winner and opponent:
        match_summary = (
            f"{winner['team']} finished {winner['goals']}-{opponent['goals']} while creating "
            f"{winner['xg']:.2f} xG from {winner['shots']} shots. "
            f"{xg_leader.get('team', winner['team'])} had the stronger chance profile, and the game state was shaped by "
            f"possession control, flank entries, pressure spells and xT swings across the 90 minutes."
        )
    else:
        match_summary = "The match dynamics view combines chance flow, possession control, pressure, turnovers, flank attacks and xT momentum across the full match."

    # Goal and card markers for the momentum chart.
    event_markers: list[dict[str, Any]] = []
    goal_marker_rows = shot_df[shot_df["type"].astype(str) == "Goal"] if "type" in shot_df.columns else shot_df.iloc[0:0]
    for _, row in goal_marker_rows.iterrows():
        minute = _minute_bucket(row.get("minute"))
        if minute is not None:
            event_markers.append(
                {
                    "team": str(row.get("teamName", "")),
                    "minute": min(minute, full_time),
                    "event_type": "goal",
                    "player": str(row.get("playerName", "")),
                    "label": "Goal",
                }
            )

    possible_card_columns = [col for col in ("cardType", "card_type", "qualifiers", "qualifiersText") if col in df.columns]
    for _, row in df.iterrows():
        event_type = str(row.get("type", ""))
        if event_type != "Card":
            continue
        card_text = " ".join(str(row.get(col, "")) for col in possible_card_columns)
        combined = f"{event_type} {card_text}".lower()
        is_second_yellow = (
            "second yellow" in combined
            or "secondyellow" in combined
            or "2nd yellow" in combined
            or "second booking" in combined
            or "second caution" in combined
            or "yellow red" in combined
            or "yellow-red" in combined
        )
        is_yellow = "yellow" in combined
        is_red = "red" in combined or is_second_yellow
        minute = _minute_bucket(row.get("minute"))
        if minute is None:
            continue
        card_kind = "second_yellow_red" if is_second_yellow else "straight_red" if is_red else "yellow"
        event_markers.append(
            {
                "team": str(row.get("teamName", "")),
                "minute": min(minute, full_time),
                "event_type": "red_card" if is_red else "yellow_card",
                "player": str(row.get("playerName", "")),
                "label": "Second yellow red" if card_kind == "second_yellow_red" else "Straight red" if card_kind == "straight_red" else "Yellow card",
                "card_kind": card_kind,
            }
        )

    from app.services.views.match_summary import build_lineups, build_stat_breakdowns, build_thirds_series

    try:
        stat_breakdowns = build_stat_breakdowns(df, teams)
    except Exception:
        logger.exception("Failed to build stat breakdowns")
        stat_breakdowns = {}
    try:
        thirds_series = build_thirds_series(df, teams, full_time)
    except Exception:
        logger.exception("Failed to build per-third series")
        thirds_series = []
    try:
        lineups = build_lineups(df, teams)
    except Exception:
        logger.exception("Failed to build lineups")
        lineups = {}

    return {
        "teams": teams,
        "team_colors": team_colors,
        "team_summary_rows": team_summary_rows,
        "match_summary": match_summary,
        "event_markers": event_markers,
        "xg_flow": xg_flow,
        "xg_markers": xg_markers,
        "possession_pass_accuracy": pos_pass_rows,
        "attack_flanks": attack_flanks,
        "ppda_turnovers": ppda_rows,
        "xt_momentum": xt_rows,
        "epv_momentum": epv_rows,
        "full_time": full_time,
        "stat_breakdowns": stat_breakdowns,
        "thirds_series": thirds_series,
        "lineups": lineups,
    }
