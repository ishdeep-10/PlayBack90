from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd

from app.services import r2
from app.services.matches import _with_game_state, filter_shots
from app.services import season_stats as ss
from app.services.opposition_foundation import (
    build_opposition_foundation,
    build_team_style_profiles,
    load_analysis_pool,
    _team_mask,
)
from app.services.opposition_lineup_context import build_lineup_context
from app.services.opposition_team_context import opposition_team_context_service


MetricDef = tuple[str, str, str, bool, bool]

METRICS: list[MetricDef] = [
    ("possession_pct", "Possession", "style", True, False),
    ("pass_accuracy", "Pass accuracy", "style", True, True),
    ("ppda", "PPDA", "style", False, True),
    ("field_tilt_pct", "Field tilt", "style", True, True),
    ("box_entries", "Box entries", "style", True, True),
    ("long_balls", "Long balls", "style", True, False),
    ("shots", "Shots", "chance_profile", True, True),
    ("shots_on_target", "Shots on target", "chance_profile", True, True),
    ("xG", "xG", "chance_profile", True, True),
    ("xG_per_shot", "xG per shot", "chance_profile", True, True),
    ("big_chances", "Big chances", "chance_profile", True, True),
    ("xG_against", "xGA", "defensive_vulnerability", False, True),
    ("shots_against", "Shots conceded", "defensive_vulnerability", False, True),
    ("big_chances_against", "Big chances conceded", "defensive_vulnerability", False, True),
    ("goals_against", "Goals conceded", "defensive_vulnerability", False, True),
]


def _clean_team(value: Any) -> str:
    return str(value or "").strip()


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _percentile(series: pd.Series, value: float, higher_is_better: bool) -> float:
    values = _numeric(series).dropna()
    if values.empty:
        return 50.0
    pct = float((values < value).mean() * 100)
    return pct if higher_is_better else 100.0 - pct


def _metric_rows(team_df: pd.DataFrame, sample_df: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for column, label, category, higher_is_better, evaluative in METRICS:
        if column not in team_df.columns or column not in sample_df.columns:
            continue
        sample_values = _numeric(sample_df[column]).dropna()
        league_values = _numeric(team_df[column]).dropna()
        if sample_values.empty or league_values.empty:
            continue
        value = float(sample_values.mean())
        league_average = float(league_values.mean())
        percentile = _percentile(league_values, value, higher_is_better)
        rows.append(
            {
                "metric": column,
                "label": label,
                "category": category,
                "value": round(value, 2),
                "league_average": round(league_average, 2),
                "percentile": round(percentile, 1),
                "higher_is_better": higher_is_better,
                "evaluative": evaluative,
            }
        )
    return rows


def _strengths_and_weaknesses(metric_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    strengths = sorted(
        [row for row in metric_rows if row.get("evaluative") and float(row["percentile"]) >= 70],
        key=lambda row: float(row["percentile"]),
        reverse=True,
    )[:6]
    weaknesses = sorted(
        [row for row in metric_rows if row.get("evaluative") and float(row["percentile"]) <= 30],
        key=lambda row: float(row["percentile"]),
    )[:6]
    return strengths, weaknesses


def _result_summary(matches: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "wins": sum(1 for match in matches if match.get("result") == "W"),
        "draws": sum(1 for match in matches if match.get("result") == "D"),
        "losses": sum(1 for match in matches if match.get("result") == "L"),
    }


def _recent_form(opponent_rows: pd.DataFrame, window: int = 5) -> dict[str, Any]:
    if opponent_rows.empty:
        return {"window": window, "matches": [], "averages": {}, "record": {"wins": 0, "draws": 0, "losses": 0}}

    rows = opponent_rows.sort_values(["date", "matchId"], ascending=False).head(window)
    matches: list[dict[str, Any]] = []
    for _, row in rows.iterrows():
        goals = int(float(row.get("goals", 0) or 0))
        goals_against = int(float(row.get("goals_against", 0) or 0))
        result = "W" if goals > goals_against else ("D" if goals == goals_against else "L")
        matches.append(
            {
                "match_id": str(row.get("matchId", "")),
                "date": str(row.get("date", "")),
                "season": str(row.get("sampleSeason", "")),
                "opponent": str(row.get("opponentName", "")),
                "home_away": str(row.get("homeAway", "")),
                "result": result,
                "score": f"{goals}-{goals_against}",
                "xg": round(float(row.get("xG", 0) or 0), 2),
                "xga": round(float(row.get("xG_against", 0) or 0), 2),
            }
        )

    averages = {}
    for column in ("goals", "goals_against", "xG", "xG_against", "shots", "shots_against"):
        if column in rows.columns:
            averages[column] = round(float(_numeric(rows[column]).mean()), 2)
    return {"window": window, "matches": matches, "averages": averages, "record": _result_summary(matches)}


def _home_away_split(sample_df: pd.DataFrame) -> dict[str, Any]:
    empty = {
        "available": False,
        "rows": [],
        "metrics": ["xG", "xGA", "shots", "shots_against"],
        "note": "Home and away split is based on the selected analysis sample.",
    }
    if sample_df.empty or "homeAway" not in sample_df.columns:
        return empty

    rows: list[dict[str, Any]] = []
    for venue, label in (("h", "Home"), ("a", "Away")):
        scoped = sample_df[sample_df["homeAway"].astype(str).str.lower().eq(venue)].copy()
        if scoped.empty:
            continue
        matches: list[dict[str, Any]] = []
        for _, row in scoped.iterrows():
            goals = int(float(row.get("goals", 0) or 0))
            goals_against = int(float(row.get("goals_against", 0) or 0))
            matches.append({"result": "W" if goals > goals_against else ("D" if goals == goals_against else "L")})
        metric_values = {}
        for column in ("goals", "goals_against", "xG", "xG_against", "shots", "shots_against", "possession_pct", "ppda"):
            if column in scoped.columns:
                metric_values[column] = round(float(_numeric(scoped[column]).mean()), 2)
        rows.append(
            {
                "venue": venue,
                "label": label,
                "match_count": int(len(scoped)),
                "record": _result_summary(matches),
                "metrics": metric_values,
            }
        )
    return {**empty, "available": bool(rows), "rows": rows}


def _fixture_path_index(league: str, seasons: list[str]) -> dict[str, str]:
    index: dict[str, str] = {}
    for season in seasons:
        try:
            fixtures = r2.list_all_fixtures(league, season)
        except Exception:
            continue
        for fixture in fixtures:
            match_id = str(fixture.get("match_id") or "")
            file_path = str(fixture.get("file_path") or "")
            if match_id and file_path and match_id not in index:
                index[match_id] = file_path
    return index


def _state_from_diff(diff: float) -> str:
    if diff > 0:
        return "leading"
    if diff < 0:
        return "trailing"
    return "level"


def _event_type_series(df: pd.DataFrame) -> pd.Series:
    return df["type"].astype(str) if "type" in df.columns else pd.Series("", index=df.index)


def _event_success_mask(df: pd.DataFrame) -> pd.Series:
    if "outcomeType" not in df.columns:
        return pd.Series(False, index=df.index)
    return df["outcomeType"].astype(str).str.contains("Successful", case=False, na=False)


def _bool_event_column(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(False, index=df.index)
    value = df[column]
    if value.dtype == bool:
        return value.fillna(False)
    return _numeric(value).fillna(0).gt(0)


def _coord(row: pd.Series, column: str) -> float | None:
    if column not in row.index:
        return None
    value = pd.to_numeric(pd.Series([row.get(column)]), errors="coerce").iloc[0]
    if pd.isna(value):
        return None
    return round(float(value), 2)


def _truthy_event_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    text = str(value).strip().lower()
    if text in {"", "nan", "none", "false", "0"}:
        return False
    try:
        return float(text) > 0
    except ValueError:
        return True


def _event_situation(row: pd.Series) -> tuple[str, str]:
    text = f"{row.get('situation') or ''} {row.get('qualifiers') or ''}".lower()
    event_type = str(row.get("type", "")).lower()
    if any(token in text for token in ("corner", "freekick", "free kick", "setpiece", "set piece", "throwin", "throw in")):
        return "set_piece", "Set piece"
    if any(_truthy_event_value(row.get(column)) for column in ("passCorner", "passFreekick", "keyPassCorner", "keyPassFreekick")):
        return "set_piece", "Set piece"
    if any(token in text for token in ("counter", "fastbreak", "fast break")) or _truthy_event_value(row.get("shotCounter")):
        return "transition", "Transition"
    if "longball" in text or _truthy_event_value(row.get("passLongBallAccurate")) or _truthy_event_value(row.get("passLongBallInaccurate")):
        return "direct", "Direct"
    if event_type == "carry" and _truthy_event_value(row.get("prog_carry")):
        return "open_play", "Open play"
    return "open_play", "Open play"


def _event_game_state(row: pd.Series) -> tuple[str, str]:
    raw = str(row.get("team_score_state", "level") or "level").lower()
    if raw.startswith("leading") or raw in {"winning", "ahead"}:
        return "leading", "Leading"
    if raw.startswith("trailing") or raw in {"losing", "behind"}:
        return "trailing", "Trailing"
    return "level", "Level"


def _to_pitch_x(value: float | None) -> float | None:
    if value is None:
        return None
    return round(max(0.0, min(105.0, value)), 2)


def _to_pitch_y(value: float | None) -> float | None:
    if value is None:
        return None
    return round(max(0.0, min(68.0, value)), 2)


def _event_row(
    row: pd.Series,
    *,
    match_id: str,
    date: str,
    kind: str,
    value_column: str | None = None,
) -> dict[str, Any] | None:
    x = _coord(row, "x")
    y = _coord(row, "y")
    end_x = _coord(row, "endX")
    end_y = _coord(row, "endY")
    if x is None or y is None:
        return None
    game_state, game_state_label = _event_game_state(row)
    payload = {
        "match_id": match_id,
        "date": date,
        "kind": kind,
        "type": str(row.get("type", "")),
        "player": str(row.get("playerName", "") or ""),
        "game_state": game_state,
        "game_state_label": game_state_label,
        "x": _to_pitch_x(x),
        "y": _to_pitch_y(y),
        "end_x": _to_pitch_x(end_x),
        "end_y": _to_pitch_y(end_y),
    }
    situation, situation_label = _event_situation(row)
    payload["situation"] = situation
    payload["situation_label"] = situation_label
    if value_column:
        payload["value"] = round(float(pd.to_numeric(pd.Series([row.get(value_column)]), errors="coerce").fillna(0).iloc[0]), 3)
    return payload


def _opta_box_entry_mask(events: pd.DataFrame) -> pd.Series:
    end_x = _numeric(events.get("endX", pd.Series(dtype=float))).fillna(-1)
    end_y = _numeric(events.get("endY", pd.Series(dtype=float))).fillna(-1)
    x = _numeric(events.get("x", pd.Series(dtype=float))).fillna(-1)
    return x.lt(88.5) & end_x.ge(88.5) & end_y.between(13.84, 54.16)


def _progressive_action_mask(events: pd.DataFrame) -> pd.Series:
    types = _event_type_series(events)
    success = _event_success_mask(events)
    tagged = _bool_event_column(events, "prog_pass") | _bool_event_column(events, "prog_carry")
    x = _numeric(events.get("x", pd.Series(dtype=float))).fillna(0)
    end_x = _numeric(events.get("endX", pd.Series(dtype=float))).fillna(0)
    x_delta = end_x - x
    threshold = pd.Series(10.0, index=events.index)
    threshold = threshold.mask(x.lt(35), 30.0)
    threshold = threshold.mask(x.ge(35) & x.lt(70), 15.0)
    coordinate_progressive = x_delta.ge(threshold) & end_x.gt(x)
    return types.isin(["Pass", "Carry"]) & success & (tagged | coordinate_progressive)


def _build_up_action_mask(events: pd.DataFrame) -> pd.Series:
    types = _event_type_series(events)
    success = _event_success_mask(events)
    x = _numeric(events.get("x", pd.Series(dtype=float))).fillna(0)
    end_x = _numeric(events.get("endX", pd.Series(dtype=float))).fillna(0)
    x_delta = end_x - x
    return types.isin(["Pass", "Carry"]) & success & x.lt(70) & x_delta.between(-8, 18)


def _direct_action_mask(events: pd.DataFrame) -> pd.Series:
    types = _event_type_series(events)
    success = _event_success_mask(events)
    x = _numeric(events.get("x", pd.Series(dtype=float))).fillna(0)
    end_x = _numeric(events.get("endX", pd.Series(dtype=float))).fillna(0)
    x_delta = end_x - x
    return types.isin(["Pass", "Carry"]) & success & (x_delta.ge(28) | ((end_x.ge(88.5)) & x_delta.ge(18)))


def _channel_from_y(y: float | None) -> str:
    if y is None:
        return "unknown"
    if y < 22.67:
        return "left"
    if y > 45.33:
        return "right"
    return "central"


def _channel_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = {"left": 0, "central": 0, "right": 0}
    for row in rows:
        y = row.get("y")
        channel = _channel_from_y(float(y) if isinstance(y, (int, float)) else None)
        if channel in counts:
            counts[channel] += 1
    total = max(1, sum(counts.values()))
    return [{"channel": key, "count": value, "pct": round(value / total * 100, 1)} for key, value in counts.items()]


def _event_pitch_profile(
    league: str,
    sample_matches: list[dict[str, Any]],
    *,
    opponent_team: str,
    pool_seasons: list[str],
    max_matches: int = 10,
) -> dict[str, Any]:
    if not sample_matches:
        return {"available": False, "covered_matches": 0, "requested_matches": 0, "max_matches": max_matches}

    target_matches = sample_matches[:max_matches]
    target_ids = {str(sample.get("match_id") or "") for sample in target_matches}
    date_by_match = {str(sample.get("match_id") or ""): str(sample.get("date") or "") for sample in target_matches}
    frames: list[pd.DataFrame] = []
    for season in pool_seasons:
        try:
            events = ss.load_event_locations(league, season)
        except Exception:
            continue
        if events.empty or "matchId" not in events.columns:
            continue
        scoped = events[events["matchId"].astype(str).isin(target_ids)].copy()
        if not scoped.empty:
            frames.append(scoped)
    event_pool = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    progressive: list[dict[str, Any]] = []
    box_entries: list[dict[str, Any]] = []
    build_up_actions: list[dict[str, Any]] = []
    direct_actions: list[dict[str, Any]] = []
    shots: list[dict[str, Any]] = []
    chance_sources: list[dict[str, Any]] = []
    covered_ids: set[str] = set()

    if event_pool.empty or "teamName" not in event_pool.columns:
        return {
            "available": False,
            "covered_matches": 0,
            "requested_matches": min(len(sample_matches), max_matches),
            "max_matches": max_matches,
            "progressive_actions": [],
            "box_entries": [],
            "build_up_actions": [],
            "direct_actions": [],
            "shots": [],
            "chance_sources": [],
            "channels": {"progression": [], "box_entries": [], "shots": []},
        }

    for match_id, df in event_pool.groupby(event_pool["matchId"].astype(str), sort=False):
        team_mask = _team_mask(df["teamName"], opponent_team)
        if not bool(team_mask.any()):
            continue
        covered_ids.add(str(match_id))
        date = date_by_match.get(str(match_id), "")
        team_events = df[team_mask].copy()
        types = _event_type_series(team_events)
        success = _event_success_mask(team_events)
        progressive_mask = _progressive_action_mask(team_events)
        box_mask = types.isin(["Pass", "Carry"]) & success & _opta_box_entry_mask(team_events)
        build_up_mask = _build_up_action_mask(team_events)
        direct_mask = _direct_action_mask(team_events)
        shot_df = filter_shots(team_events)

        for _, row in team_events[build_up_mask].iterrows():
            item = _event_row(row, match_id=match_id, date=date, kind="build_up", value_column=None)
            if item:
                build_up_actions.append(item)
        for _, row in team_events[direct_mask].iterrows():
            item = _event_row(row, match_id=match_id, date=date, kind="direct", value_column=None)
            if item:
                direct_actions.append(item)
        for _, row in team_events[progressive_mask].iterrows():
            item = _event_row(row, match_id=match_id, date=date, kind="progressive", value_column="xT" if "xT" in team_events.columns else None)
            if item:
                progressive.append(item)
        for _, row in team_events[box_mask].iterrows():
            item = _event_row(row, match_id=match_id, date=date, kind="box_entry", value_column="xT" if "xT" in team_events.columns else None)
            if item:
                box_entries.append(item)
        for _, row in shot_df.iterrows():
            item = _event_row(row, match_id=match_id, date=date, kind="shot", value_column="xG" if "xG" in shot_df.columns else None)
            if item:
                item["outcome"] = str(row.get("type", ""))
                shots.append(item)
            previous = team_events.loc[:row.name].iloc[:-1].tail(1) if row.name in team_events.index else pd.DataFrame()
            if not previous.empty:
                source = _event_row(previous.iloc[0], match_id=match_id, date=date, kind="chance_source", value_column="xA" if "xA" in previous.columns else None)
                if source:
                    chance_sources.append(source)

    return {
        "available": bool(covered_ids) and bool(progressive or box_entries or shots),
        "covered_matches": len(covered_ids),
        "requested_matches": min(len(sample_matches), max_matches),
        "max_matches": max_matches,
        "progressive_actions": progressive,
        "box_entries": box_entries,
        "build_up_actions": build_up_actions,
        "direct_actions": direct_actions,
        "shots": shots,
        "chance_sources": chance_sources,
        "channels": {
            "progression": _channel_summary(progressive),
            "box_entries": _channel_summary(box_entries),
            "shots": _channel_summary(shots),
        },
    }


def _game_state_profile(
    league: str,
    sample_matches: list[dict[str, Any]],
    *,
    opponent_team: str,
    pool_seasons: list[str],
) -> dict[str, Any]:
    states = {
        "leading": {"state": "leading", "label": "Leading", "matches": set(), "shots": 0, "shots_against": 0, "xG": 0.0, "xGA": 0.0},
        "level": {"state": "level", "label": "Level", "matches": set(), "shots": 0, "shots_against": 0, "xG": 0.0, "xGA": 0.0},
        "trailing": {"state": "trailing", "label": "Trailing", "matches": set(), "shots": 0, "shots_against": 0, "xG": 0.0, "xGA": 0.0},
    }
    if not sample_matches:
        return {"available": False, "rows": [], "covered_matches": 0, "requested_matches": 0, "warning": "No sample matches available for game-state profiling."}

    path_index = _fixture_path_index(league, pool_seasons)
    covered = 0
    warnings: list[str] = []
    for sample in sample_matches:
        match_id = str(sample.get("match_id") or "")
        file_path = path_index.get(match_id)
        if not file_path:
            continue
        try:
            df = r2.load_match_dataframe(file_path)
        except Exception:
            warnings.append(f"Could not load event data for match {match_id}.")
            continue
        if df.empty or "teamName" not in df.columns:
            continue

        team_mask = _team_mask(df["teamName"], opponent_team)
        if not bool(team_mask.any()):
            continue
        event_team = str(df.loc[team_mask, "teamName"].iloc[0])
        enriched = _with_game_state(df)
        shots_for = filter_shots(enriched, team=event_team)
        shots_against = filter_shots(enriched[~_team_mask(enriched["teamName"], event_team)])
        if shots_for.empty and shots_against.empty:
            continue
        covered += 1
        for state_key, payload in states.items():
            sf = shots_for[shots_for["team_score_state"].astype(str).eq(state_key)] if "team_score_state" in shots_for.columns else shots_for.iloc[0:0]
            if "team_goal_diff_before" in shots_against.columns:
                against_state = _numeric(shots_against["team_goal_diff_before"]).fillna(0).map(lambda diff: _state_from_diff(-float(diff)))
                sa = shots_against[against_state.eq(state_key)]
            else:
                sa = shots_against.iloc[0:0]
            payload["matches"].add(match_id)
            payload["shots"] += int(len(sf))
            payload["shots_against"] += int(len(sa))
            payload["xG"] += float(_numeric(sf.get("xG", pd.Series(dtype=float))).sum()) if not sf.empty else 0.0
            payload["xGA"] += float(_numeric(sa.get("xG", pd.Series(dtype=float))).sum()) if not sa.empty else 0.0

    rows = []
    for payload in states.values():
        match_count = max(1, len(payload["matches"]))
        rows.append(
            {
                "state": payload["state"],
                "label": payload["label"],
                "match_count": len(payload["matches"]),
                "shots": payload["shots"],
                "shots_against": payload["shots_against"],
                "xG": round(payload["xG"], 2),
                "xGA": round(payload["xGA"], 2),
                "xG_per_match": round(payload["xG"] / match_count, 2),
                "xGA_per_match": round(payload["xGA"] / match_count, 2),
            }
        )
    return {
        "available": covered > 0,
        "rows": rows,
        "covered_matches": covered,
        "requested_matches": len(sample_matches),
        "warning": warnings[0] if warnings and covered == 0 else None,
    }


def _reference_profile(pool: pd.DataFrame, reference_team: str, similar_teams: list[dict[str, Any]]) -> dict[str, Any]:
    profiles, features = build_team_style_profiles(pool)
    ref = profiles[_team_mask(profiles["teamName"], reference_team)] if not profiles.empty else pd.DataFrame()
    metrics: dict[str, float] = {}
    if not ref.empty:
        ref_row = ref.iloc[0]
        metrics = {
            feature: round(float(ref_row[feature]), 2)
            for feature in features
            if feature in ref_row and pd.notna(ref_row[feature])
        }
    return {
        "team": reference_team,
        "available": bool(metrics),
        "metrics": metrics,
        "similar_teams": similar_teams,
    }


def _key_players(player_df: pd.DataFrame, opponent_team: str, limit: int = 6) -> list[dict[str, Any]]:
    if player_df.empty or "teamName" not in player_df.columns or "playerName" not in player_df.columns:
        return []
    scoped = player_df[_team_mask(player_df["teamName"], opponent_team)].copy()
    if scoped.empty:
        return []

    for column in ("goals", "xG", "xA", "shots", "mins_played"):
        if column not in scoped.columns:
            scoped[column] = 0
        scoped[column] = _numeric(scoped[column]).fillna(0)

    grouped = (
        scoped.groupby("playerName", sort=False)
        .agg(
            goals=("goals", "sum"),
            xg=("xG", "sum"),
            xa=("xA", "sum"),
            shots=("shots", "sum"),
            mins=("mins_played", "sum"),
        )
        .reset_index()
    )
    grouped["threat_score"] = grouped["xg"] + grouped["xa"] + grouped["shots"] * 0.03
    grouped = grouped.sort_values(["threat_score", "mins"], ascending=False).head(limit)
    return [
        {
            "player": str(row["playerName"]),
            "goals": int(row["goals"]),
            "xg": round(float(row["xg"]), 2),
            "xa": round(float(row["xa"]), 2),
            "shots": int(row["shots"]),
            "mins": int(row["mins"]),
        }
        for _, row in grouped.iterrows()
    ]


def _load_player_pool(league: str, pool_seasons: list[str]) -> pd.DataFrame:
    frames = [ss.load_player_season_stats(league, season) for season in pool_seasons]
    frames = [frame for frame in frames if not frame.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _sample_metric(sample_df: pd.DataFrame, column: str) -> float | None:
    if sample_df.empty or column not in sample_df.columns:
        return None
    values = _numeric(sample_df[column]).dropna()
    if values.empty:
        return None
    return round(float(values.mean()), 2)


def _metric_cards(sample_df: pd.DataFrame, specs: list[tuple[str, str, str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for column, label, unit in specs:
        value = _sample_metric(sample_df, column)
        if value is None:
            continue
        rows.append({"metric": column, "label": label, "value": value, "unit": unit})
    return rows


def _bounded_score(value: float | None, low: float, high: float, invert: bool = False) -> float:
    if value is None or high <= low:
        return 50.0
    score = (value - low) / (high - low) * 100
    score = max(0.0, min(100.0, score))
    return round(100.0 - score if invert else score, 1)


def _derived_sample_metric(sample_df: pd.DataFrame, numerator: str, denominator: str) -> float | None:
    numerator_value = _sample_metric(sample_df, numerator)
    denominator_value = _sample_metric(sample_df, denominator)
    if numerator_value is None or not denominator_value:
        return None
    return round(float(numerator_value) / max(float(denominator_value), 0.01), 2)


def _possession_identity(sample_df: pd.DataFrame) -> dict[str, Any]:
    possession = _sample_metric(sample_df, "possession_pct")
    pass_accuracy = _sample_metric(sample_df, "pass_accuracy")
    field_tilt = _sample_metric(sample_df, "field_tilt_pct")
    box_entries = _sample_metric(sample_df, "box_entries")
    long_balls = _sample_metric(sample_df, "long_balls")
    possessions = _sample_metric(sample_df, "possessions")
    passes_per_possession = _derived_sample_metric(sample_df, "passes", "possessions")
    prog_passes = _sample_metric(sample_df, "prog_passes") or 0.0
    prog_carries = _sample_metric(sample_df, "prog_carries") or 0.0
    progressive_actions = round(prog_passes + prog_carries, 2) if prog_passes or prog_carries else None
    progressive_per_possession = (
        round(progressive_actions / max(float(possessions), 0.01), 2)
        if progressive_actions is not None and possessions
        else None
    )

    quadrants = [
        {
            "key": "control",
            "label": "Control",
            "score": round((_bounded_score(possession, 35, 65) + _bounded_score(pass_accuracy, 68, 90) + _bounded_score(passes_per_possession, 2.5, 6.5)) / 3, 1),
            "metrics": [
                {"label": "Possession", "value": possession, "unit": "%"},
                {"label": "Pass accuracy", "value": pass_accuracy, "unit": "%"},
                {"label": "Passes / possession", "value": passes_per_possession, "unit": ""},
            ],
        },
        {
            "key": "directness",
            "label": "Directness",
            "score": round((_bounded_score(long_balls, 25, 80) + _bounded_score(progressive_per_possession, 1.5, 5.0) + _bounded_score(passes_per_possession, 2.5, 6.5, invert=True)) / 3, 1),
            "metrics": [
                {"label": "Long balls", "value": long_balls, "unit": ""},
                {"label": "Prog. actions / possession", "value": progressive_per_possession, "unit": ""},
                {"label": "Passes / possession", "value": passes_per_possession, "unit": ""},
            ],
        },
        {
            "key": "territory",
            "label": "Territory",
            "score": round((_bounded_score(field_tilt, 35, 65) + _bounded_score(box_entries, 5, 18) + _bounded_score(progressive_actions, 160, 420)) / 3, 1),
            "metrics": [
                {"label": "Field tilt", "value": field_tilt, "unit": "%"},
                {"label": "Box entries", "value": box_entries, "unit": ""},
                {"label": "Progressive actions", "value": progressive_actions, "unit": ""},
            ],
        },
        {
            "key": "tempo",
            "label": "Tempo",
            "score": round((_bounded_score(possessions, 70, 130) + _bounded_score(progressive_per_possession, 1.5, 5.0) + _bounded_score(passes_per_possession, 2.5, 6.5, invert=True)) / 3, 1),
            "metrics": [
                {"label": "Possessions", "value": possessions, "unit": ""},
                {"label": "Prog. actions / possession", "value": progressive_per_possession, "unit": ""},
                {"label": "Passes / possession", "value": passes_per_possession, "unit": ""},
            ],
        },
    ]
    strongest = max(quadrants, key=lambda item: float(item["score"]))
    profile_labels = {
        "control": "Control-first possession",
        "directness": "Direct forward possession",
        "territory": "Territory pressure",
        "tempo": "High-tempo possession",
    }
    return {
        "available": any(metric.get("value") is not None for quadrant in quadrants for metric in quadrant["metrics"]),
        "label": profile_labels.get(strongest["key"], "Possession profile"),
        "quadrants": quadrants,
    }


def _player_role_rows(player_df: pd.DataFrame, opponent_team: str, order_column: str, limit: int = 5) -> list[dict[str, Any]]:
    if player_df.empty or "teamName" not in player_df.columns or "playerName" not in player_df.columns:
        return []
    scoped = player_df[_team_mask(player_df["teamName"], opponent_team)].copy()
    if scoped.empty:
        return []

    for column in ("goals", "xG", "xA", "shots", "key_passes", "prog_passes", "prog_carries", "crosses", "mins_played"):
        if column not in scoped.columns:
            scoped[column] = 0
        scoped[column] = _numeric(scoped[column]).fillna(0)

    grouped = (
        scoped.groupby("playerName", sort=False)
        .agg(
            goals=("goals", "sum"),
            xg=("xG", "sum"),
            xa=("xA", "sum"),
            shots=("shots", "sum"),
            key_passes=("key_passes", "sum"),
            progressive_passes=("prog_passes", "sum"),
            progressive_carries=("prog_carries", "sum"),
            crosses=("crosses", "sum"),
            mins=("mins_played", "sum"),
        )
        .reset_index()
    )
    if order_column not in grouped.columns:
        order_column = "mins"
    grouped = grouped.sort_values([order_column, "mins"], ascending=False).head(limit)
    return [
        {
            "player": str(row["playerName"]),
            "goals": int(row["goals"]),
            "xg": round(float(row["xg"]), 2),
            "xa": round(float(row["xa"]), 2),
            "shots": int(row["shots"]),
            "key_passes": int(row["key_passes"]),
            "progressive_passes": int(row["progressive_passes"]),
            "progressive_carries": int(row["progressive_carries"]),
            "crosses": int(row["crosses"]),
            "mins": int(row["mins"]),
        }
        for _, row in grouped.iterrows()
    ]


def _in_possession_profile(
    sample_df: pd.DataFrame,
    player_df: pd.DataFrame,
    opponent_team: str,
    event_pitch_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    identity = _metric_cards(
        sample_df,
        [
            ("possession_pct", "Possession", "%"),
            ("pass_accuracy", "Pass accuracy", "%"),
            ("field_tilt_pct", "Field tilt", "%"),
            ("ppda", "PPDA", ""),
        ],
    )
    progression = _metric_cards(
        sample_df,
        [
            ("prog_passes", "Progressive passes", ""),
            ("prog_carries", "Progressive carries", ""),
            ("box_entries", "Box entries", ""),
            ("crosses", "Crosses", ""),
            ("through_balls", "Through balls", ""),
            ("long_balls", "Long balls", ""),
        ],
    )
    chance_creation = _metric_cards(
        sample_df,
        [
            ("xG", "xG", ""),
            ("shots", "Shots", ""),
            ("shots_on_target", "Shots on target", ""),
            ("xG_per_shot", "xG per shot", ""),
            ("big_chances", "Big chances", ""),
        ],
    )

    return {
        "available": bool(identity or progression or chance_creation),
        "team": opponent_team,
        "sample_match_count": int(len(sample_df)),
        "identity": identity,
        "possession_identity": _possession_identity(sample_df),
        "progression": progression,
        "chance_creation": chance_creation,
        "player_roles": {
            "finishers": _player_role_rows(player_df, opponent_team, "xg"),
            "creators": _player_role_rows(player_df, opponent_team, "xa"),
            "progressors": _player_role_rows(player_df, opponent_team, "progressive_passes"),
            "carriers": _player_role_rows(player_df, opponent_team, "progressive_carries"),
        },
        "set_pieces": {
            "available": False,
            "note": "Attacking set-piece detail needs the event-location team history aggregate.",
        },
        "event_pitch_profile": event_pitch_profile or {"available": False, "covered_matches": 0, "requested_matches": 0, "max_matches": 10},
    }


def _summary_bullets(
    opponent_team: str,
    sample_matches: list[dict[str, Any]],
    strengths: list[dict[str, Any]],
    weaknesses: list[dict[str, Any]],
    warnings: list[str],
) -> list[str]:
    bullets: list[str] = []
    if sample_matches:
        record = _result_summary(sample_matches)
        bullets.append(
            f"{opponent_team} sample record is {record['wins']}W-{record['draws']}D-{record['losses']}L across {len(sample_matches)} comparable matches."
        )
    if strengths:
        labels = ", ".join(str(row["label"]).lower() for row in strengths[:2])
        bullets.append(f"Main positive indicators in the selected sample: {labels}.")
    if weaknesses:
        labels = ", ".join(str(row["label"]).lower() for row in weaknesses[:2])
        bullets.append(f"Main vulnerability indicators in the selected sample: {labels}.")
    if warnings:
        bullets.append(warnings[0])
    return bullets


def build_opposition_dossier(
    league: str,
    season: str,
    opponent_team: str,
    reference_team: str,
    *,
    fixture_id: str | None = None,
    home_team: str | None = None,
    away_team: str | None = None,
    sample_size: int = 5,
) -> dict[str, Any]:
    foundation = build_opposition_foundation(
        league=league,
        season=season,
        opponent_team=opponent_team,
        reference_team=reference_team,
        sample_size=sample_size,
    )
    pool, pool_strategy, pool_seasons = load_analysis_pool(league, season, opponent_team)
    opponent_rows = pool[_team_mask(pool["teamName"], opponent_team)] if not pool.empty and "teamName" in pool.columns else pd.DataFrame()
    sample_match_ids = {str(match["match_id"]) for match in foundation["sample_matches"]}
    sample_df = opponent_rows[opponent_rows["matchId"].astype(str).isin(sample_match_ids)].copy() if not opponent_rows.empty else pd.DataFrame()
    if sample_df.empty:
        sample_df = opponent_rows.sort_values(["date", "matchId"], ascending=False).head(sample_size).copy()

    metric_rows = _metric_rows(pool, sample_df)
    strengths, weaknesses = _strengths_and_weaknesses(metric_rows)
    player_df = _load_player_pool(league, foundation.get("pool_seasons") or pool_seasons)
    warnings = list(foundation.get("warnings", []))
    team_context = opposition_team_context_service.build_context(
        league,
        season,
        reference_team=reference_team,
        opponent_team=opponent_team,
    )
    recent_form = _recent_form(opponent_rows, window=max(1, sample_size))
    lineup_history = _recent_form(opponent_rows, window=max(1, sample_size))
    lineup_context = build_lineup_context(
        league,
        lineup_history.get("matches", []),
        opponent_team=opponent_team,
        pool_seasons=foundation.get("pool_seasons") or pool_seasons,
        team_context=team_context,
        latest_matches=recent_form.get("matches", [])[:1],
    )

    return {
        "meta": {
            "league": league,
            "fixture_season": season,
            "analysis_seasons": foundation.get("pool_seasons", []),
            "opponent_team": opponent_team,
            "reference_team": reference_team,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "persona": "neutral opposition analyst",
        },
        "fixtureContext": {
            "fixture_id": fixture_id,
            "home_team": home_team,
            "away_team": away_team,
            "reference_team": reference_team,
            "opponent_team": opponent_team,
        },
        "sampleContext": {
            "requested_sample_size": sample_size,
            "actual_sample_size": len(foundation.get("sample_matches", [])),
            "sample_strategy": foundation.get("sample_strategy"),
            "pool_strategy": foundation.get("pool_strategy", pool_strategy),
            "pool_seasons": foundation.get("pool_seasons", pool_seasons),
            "features_used": foundation.get("features_used", []),
            "warnings": warnings,
            "sample_matches": foundation.get("sample_matches", []),
            "similar_teams": foundation.get("similar_teams", []),
        },
        "referenceProfile": _reference_profile(pool, reference_team, foundation.get("similar_teams", [])),
        "teamContext": team_context,
        "lineupContext": lineup_context,
        "summary": {
            "bullets": _summary_bullets(opponent_team, foundation.get("sample_matches", []), strengths, weaknesses, warnings),
            "confidence": "moderate" if len(foundation.get("sample_matches", [])) >= 5 and not warnings else "directional",
        },
        "teamProfile": {
            "team": opponent_team,
            "metrics": metric_rows,
            "match_count": int(len(sample_df)),
        },
        "inPossessionProfile": _in_possession_profile(
            sample_df,
            player_df,
            opponent_team,
            _event_pitch_profile(
                league,
                foundation.get("sample_matches", [])[: min(max(1, sample_size), 10)],
                opponent_team=opponent_team,
                pool_seasons=foundation.get("pool_seasons") or pool_seasons,
            ),
        ),
        "homeAwaySplit": _home_away_split(sample_df),
        "gameStateProfile": _game_state_profile(
            league,
            foundation.get("sample_matches", []),
            opponent_team=opponent_team,
            pool_seasons=foundation.get("pool_seasons") or pool_seasons,
        ),
        "recentForm": recent_form,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "keyPlayers": _key_players(player_df, opponent_team),
    }
