"""Player analysis view builder."""

from __future__ import annotations

import logging

from typing import Any

import pandas as pd

from app.services.matches import (
    SHOT_TYPES,
    _available_game_state_options,
    _bool_series,
    _build_shot_detail_rows,
    _build_shot_player_summary_from_rows,
    _coerce_numeric,
    _filter_score_state,
    _filter_time_range,
    _is_shot_on_target,
    _match_team_order,
    _normalize_time_range_to_window,
    _pass_network_passes_df,
    _safe_float,
    _safe_int,
    _time_bounds_for_state,
    _time_range_option,
    _truthy_value,
    _with_game_state,
    filter_shots,
)
from app.services.views.common import (
    _duel_mask,
    _progressive_action_mask,
    _row_successful,
)
from app.services.views.match_summary import player_position_timeline, position_at_minute


PLAYER_ANALYSIS_EXCLUDED_TYPES = {
    "Start",
    "End",
    "FormationChange",
    "FormationSet",
    "SubstitutionOff",
    "SubstitutionOn",
    "Card",
    "PlayerOff",
    "PlayerOn",
    "OffsideProvoked",
}


logger = logging.getLogger(__name__)


_ACTION_REQUIRED_FIELDS = {
    "id",
    "minute",
    "second",
    "team",
    "player",
    "player_id",
    "type",
    "phase",
    "outcome",
    "is_successful",
    "x",
    "y",
    "end_x",
    "end_y",
    "position",
}


def _compact_action(action: dict[str, Any]) -> dict[str, Any]:
    """Omit optional defaults that the web client already treats as false/zero."""
    return {
        key: value
        for key, value in action.items()
        if key in _ACTION_REQUIRED_FIELDS or value not in (None, "", False, 0, 0.0)
    }


def _player_analysis_phase(event_type: str, row: pd.Series) -> str:
    if _duel_mask(pd.DataFrame([row]), "Total").iloc[0]:
        return "duel"
    if event_type in {"Pass", "Carry", "TakeOn", "GoodSkill", "BallTouch", "Goal", "SavedShot", "MissedShots", "ShotOnPost"}:
        return "in_possession"
    if event_type in {"Tackle", "Interception", "BallRecovery", "Clearance", "BlockedPass", "Challenge", "Aerial"}:
        return "out_of_possession"
    if event_type in {"Dispossessed", "Turnover"}:
        return "transition"
    return "other"


def build_player_analysis_view(
    df: pd.DataFrame,
    team: str | None = None,
    score_state: str | None = "all",
    time_range: str | None = "all",
) -> dict[str, Any]:
    if df.empty or "teamName" not in df.columns or "playerName" not in df.columns:
        return {"team": team or "", "teams": [], "players": [], "actions": []}

    enriched_df = _with_game_state(df)
    if "index" not in enriched_df.columns:
        enriched_df = enriched_df.copy()
        enriched_df["index"] = range(len(enriched_df))
    pass_events = _pass_network_passes_df(enriched_df)
    receiver_by_index = (
        pass_events.set_index("index")["receiverName"].to_dict()
        if not pass_events.empty and {"index", "receiverName"}.issubset(pass_events.columns)
        else {}
    )

    teams = _match_team_order(enriched_df)
    position_by_player = player_position_timeline(enriched_df, teams)
    selected_team = team if team and team != "__both__" else (teams[0] if teams else str(enriched_df["teamName"].dropna().iloc[0]))
    team_df = enriched_df[enriched_df["teamName"].astype(str).eq(str(selected_team))].copy()
    if team_df.empty:
        return {"team": selected_team, "teams": teams, "players": [], "actions": []}

    minute_values = _coerce_numeric(team_df.get("minute", pd.Series(0, index=team_df.index))).fillna(-1)
    full_time = int(max(90, minute_values[minute_values >= 0].max())) if not minute_values[minute_values >= 0].empty else 90
    bounds_start, bounds_end = _time_bounds_for_state(team_df, {"minute_start": 0, "minute_end": full_time}, score_state)
    normalized_time_range = _normalize_time_range_to_window(time_range, {"minute_start": bounds_start, "minute_end": bounds_end})
    scoped = _filter_score_state(team_df, score_state)
    scoped = _filter_time_range(scoped, normalized_time_range)

    shot_scope = _filter_score_state(enriched_df[enriched_df["teamName"].astype(str).eq(str(selected_team))].copy(), score_state)
    shot_scope = _filter_time_range(shot_scope, normalized_time_range)
    shot_rows = _build_shot_detail_rows(enriched_df, filter_shots(shot_scope, team=selected_team))
    shot_summary = _build_shot_player_summary_from_rows(shot_rows)

    event_type = scoped.get("type", pd.Series("", index=scoped.index)).astype(str)
    player_name = scoped.get("playerName", pd.Series("", index=scoped.index)).astype(str).str.strip()
    x_values = _coerce_numeric(scoped.get("x", pd.Series(dtype=float))).fillna(-1)
    y_values = _coerce_numeric(scoped.get("y", pd.Series(dtype=float))).fillna(-1)
    valid_mask = (
        player_name.ne("")
        & ~event_type.isin(PLAYER_ANALYSIS_EXCLUDED_TYPES)
        & x_values.between(0, 105)
        & y_values.between(0, 68)
    )
    action_df = scoped[valid_mask].copy()
    action_df["is_progressive"] = False
    action_type_for_progression = action_df.get("type", pd.Series("", index=action_df.index)).astype(str)
    progressive_action_mask = action_type_for_progression.isin(["Pass", "Carry"])
    if progressive_action_mask.any():
        action_df.loc[progressive_action_mask, "is_progressive"] = _progressive_action_mask(action_df.loc[progressive_action_mask]).astype(bool)

    player_status: dict[str, dict[str, Any]] = {}
    full_player_name = team_df.get("playerName", pd.Series("", index=team_df.index)).astype(str).str.strip()
    for player, full_player_df in team_df[full_player_name.ne("")].groupby("playerName"):
        player_text = str(player).strip()
        if not player_text:
            continue
        full_player_minutes = _coerce_numeric(full_player_df.get("minute", pd.Series(0, index=full_player_df.index))).fillna(-1)
        full_player_types = full_player_df.get("type", pd.Series("", index=full_player_df.index)).astype(str)
        sub_on_minutes = full_player_minutes[full_player_types.eq("SubstitutionOn") & (full_player_minutes >= 0)]
        sub_off_minutes = full_player_minutes[full_player_types.eq("SubstitutionOff") & (full_player_minutes >= 0)]
        start_minute = int(sub_on_minutes.min()) if not sub_on_minutes.empty else 0
        off_after_start = sub_off_minutes[sub_off_minutes >= start_minute]
        end_minute = int(off_after_start.min()) if not off_after_start.empty else full_time
        player_status[player_text] = {
            "minutes_played": max(0, min(full_time, end_minute) - min(full_time, start_minute)),
        }

    players: list[dict[str, Any]] = []
    for player_value, player_df in scoped[player_name.ne("")].groupby("playerName"):
        player_text = str(player_value).strip()
        if not player_text:
            continue
        types = player_df.get("type", pd.Series("", index=player_df.index)).astype(str)
        valid_player_actions = player_df[~types.isin(PLAYER_ANALYSIS_EXCLUDED_TYPES)].copy()
        valid_types = valid_player_actions.get("type", pd.Series("", index=valid_player_actions.index)).astype(str)
        valid_success = valid_player_actions.apply(_row_successful, axis=1) if not valid_player_actions.empty else pd.Series(dtype=bool)
        valid_touch_mask = _bool_series(valid_player_actions, "isTouch") & ~valid_types.eq("Carry") if not valid_player_actions.empty else pd.Series(dtype=bool)
        status = player_status.get(player_text, {"minutes_played": 0})
        position_info = position_by_player.get(player_text, {})
        players.append(
            {
                "player": player_text,
                "team": selected_team,
                "player_id": _safe_int(player_df.get("playerId", pd.Series(0, index=player_df.index)).iloc[0]) if "playerId" in player_df.columns else 0,
                "position": position_info.get("primary_position"),
                "position_group": position_info.get("position_group"),
                "positions": position_info.get("positions", []),
                "position_timeline": position_info.get("timeline", []),
                "minutes": int(status["minutes_played"]),
                "actions": int(len(valid_player_actions)),
                "touches": int(valid_touch_mask.sum()),
                "in_possession": int(valid_types.isin(["Pass", "Carry", "BallTouch", "TakeOn", "GoodSkill", "Goal", "SavedShot", "MissedShots", "ShotOnPost"]).sum()),
                "out_of_possession": int(valid_types.isin(["Tackle", "Interception", "BallRecovery", "Clearance", "BlockedPass", "Challenge", "Aerial"]).sum()),
                "duels": int(_duel_mask(valid_player_actions, "Total").sum()) if not valid_player_actions.empty else 0,
                "shots": int(valid_types.isin(SHOT_TYPES).sum()),
                "xPass": round(float(_coerce_numeric(valid_player_actions.loc[valid_types.eq("Pass"), "xPass"]).fillna(0.0).sum()), 3)
                if "xPass" in valid_player_actions.columns
                else 0.0,
                "epv_added": round(float(_coerce_numeric(valid_player_actions.loc[valid_types.isin(["Pass", "Carry"]), "epv_added"]).fillna(0.0).sum()), 3)
                if "epv_added" in valid_player_actions.columns
                else 0.0,
            }
        )
    players = sorted(players, key=lambda row: (-int(row["actions"]), str(row["player"])))

    actions: list[dict[str, Any]] = []
    sort_cols = [col for col in ("minute", "second", "index") if col in action_df.columns]
    action_df = action_df.sort_values(sort_cols) if sort_cols else action_df
    for _, row in action_df.iterrows():
        raw_type = str(row.get("type", ""))
        display_type = "TakeOn" if raw_type == "GoodSkill" else raw_type
        row_index = _safe_int(row.get("index"))
        row_player = str(row.get("playerName", ""))
        row_timeline = position_by_player.get(row_player, {}).get("timeline", [])
        actions.append(
            _compact_action({
                "id": str(row.get("index", "")),
                "minute": _safe_int(row.get("minute")),
                "second": _safe_int(row.get("second")),
                "team": str(row.get("teamName", selected_team)),
                "player": row_player,
                "player_id": _safe_int(row.get("playerId")),
                "position": position_at_minute(row_timeline, _safe_float(row.get("minute"))),
                "type": display_type,
                "phase": _player_analysis_phase(raw_type, row),
                "outcome": str(row.get("outcomeType", "")),
                "is_successful": _row_successful(row),
                "is_touch": _truthy_value(row.get("isTouch", False)),
                "is_ball_touch": _truthy_value(row.get("isTouch", False)) and raw_type != "Carry",
                "x": round(_safe_float(row.get("x")), 2),
                "y": round(_safe_float(row.get("y")), 2),
                "end_x": round(_safe_float(row.get("endX")), 2),
                "end_y": round(_safe_float(row.get("endY")), 2),
                "is_progressive": bool(row.get("is_progressive", False)),
                "xG": round(_safe_float(row.get("xG")), 3),
                "xT": round(_safe_float(row.get("xT", row.get("xThreat"))), 3),
                "xA": round(_safe_float(row.get("xA")), 3),
                "xPass": round(_safe_float(row.get("xPass")), 4),
                "epv_start": round(_safe_float(row.get("epv_start")), 4),
                "epv_end": round(_safe_float(row.get("epv_end")), 4),
                "epv_added": round(_safe_float(row.get("epv_added")), 4),
                "epv_model_version": str(row.get("epv_model_version", "")),
                "epv_grid_version": str(row.get("epv_grid_version", "")),
                "epv_action_eligible": _truthy_value(row.get("epv_action_eligible", False)),
                "xpass_model_version": str(row.get("xpass_model_version", "")),
                "xpass_pass_type": str(row.get("xpass_pass_type", "")),
                "xpass_play_pattern": str(row.get("xpass_play_pattern", "")),
                "xpass_pass_direction": str(row.get("xpass_pass_direction", "")),
                "situation": str(row.get("situation", "")),
                "body_part": str(row.get("shotBodyType", "")),
                "qualifiers": str(row.get("qualifiers", "")),
                "satisfied_events": str(row.get("satisfiedEventsTypes", row.get("satisfied_events", ""))),
                "pass_cross": _truthy_value(row.get("passCross", False)),
                "pass_cross_accurate": _truthy_value(row.get("passCrossAccurate", False)),
                "pass_cross_inaccurate": _truthy_value(row.get("passCrossInaccurate", False)),
                "pass_corner": _truthy_value(row.get("passCorner", False)),
                "pass_freekick": _truthy_value(row.get("passFreekick", row.get("passFreekickTaken", False))),
                "pass_throw_in": _truthy_value(row.get("passThrowIn", False)),
                "throw_in": _truthy_value(row.get("throwIn", False)),
                "pass_through_ball": _truthy_value(row.get("passThroughBall", False)),
                "pass_through_ball_accurate": _truthy_value(row.get("passThroughBallAccurate", False)),
                "pass_through_ball_inaccurate": _truthy_value(row.get("passThroughBallInaccurate", row.get("passThroughBallInacurate", False))),
                "pass_long_ball_accurate": _truthy_value(row.get("passLongBallAccurate", False)),
                "pass_long_ball_inaccurate": _truthy_value(row.get("passLongBallInaccurate", False)),
                "pass_chipped": _truthy_value(row.get("passChipped", False)),
                "pass_key": _truthy_value(row.get("passKey", False)),
                "key_pass_cross": _truthy_value(row.get("keyPassCross", False)),
                "key_pass_corner": _truthy_value(row.get("keyPassCorner", False)),
                "key_pass_through_ball": _truthy_value(row.get("keyPassThroughball", False)),
                "key_pass_freekick": _truthy_value(row.get("keyPassFreekick", False)),
                "key_pass_throw_in": _truthy_value(row.get("keyPassThrowin", False)),
                "pass_assist": _truthy_value(row.get("isGoalAssist", row.get("goalAssist", False))),
                "assist_cross": _truthy_value(row.get("assistCross", False)),
                "assist_corner": _truthy_value(row.get("assistCorner", False)),
                "assist_through_ball": _truthy_value(row.get("assistThroughball", False)),
                "assist_freekick": _truthy_value(row.get("assistFreekick", False)),
                "assist_throw_in": _truthy_value(row.get("assistThrowin", False)),
                "pass_height": str(row.get("passHeight", "")),
                "blocked": bool(row.get("shotBlocked", False)),
                "on_target": _is_shot_on_target(row) if display_type in SHOT_TYPES else False,
                "goal_mouth_y": round(_safe_float(row.get("goalMouthY")), 2),
                "goal_mouth_z": round(_safe_float(row.get("goalMouthZ")), 2),
                "game_state": str(row.get("team_score_state", "level")),
                "game_state_label": str(row.get("team_score_state_label", "Level")),
                "score_before": str(row.get("score_before", "0-0")),
            })
        )
        receiver_name = str(receiver_by_index.get(row_index, "")).strip()
        if raw_type == "Pass" and _row_successful(row) and receiver_name and receiver_name.lower() != "nan":
            actions.append(
                {
                    "id": f"{row.get('index', '')}:received",
                    "minute": _safe_int(row.get("minute")),
                    "second": _safe_int(row.get("second")),
                    "team": str(row.get("teamName", selected_team)),
                    "player": receiver_name,
                    "passer": str(row.get("playerName", "")),
                    "player_id": 0,
                    "type": "PassReceived",
                    "phase": "touches",
                    "outcome": str(row.get("outcomeType", "")),
                    "is_successful": True,
                    "is_touch": False,
                    "is_received": True,
                    "source_x": round(_safe_float(row.get("x")), 2),
                    "source_y": round(_safe_float(row.get("y")), 2),
                    "x": round(_safe_float(row.get("endX")), 2),
                    "y": round(_safe_float(row.get("endY")), 2),
                    "end_x": round(_safe_float(row.get("endX")), 2),
                    "end_y": round(_safe_float(row.get("endY")), 2),
                    "is_progressive": bool(row.get("is_progressive", False)),
                    "game_state": str(row.get("team_score_state", "level")),
                    "game_state_label": str(row.get("team_score_state_label", "Level")),
                    "score_before": str(row.get("score_before", "0-0")),
                }
            )

    return {
        "team": selected_team,
        "teams": teams,
        "players": players,
        "actions": actions,
        "shot_rows": shot_rows,
        "shot_player_summary": shot_summary,
        "score_state": score_state or "all",
        "time_range": normalized_time_range,
        "game_state_options": _available_game_state_options(team_df),
        "time_range_options": _time_range_option(bounds_start, bounds_end, "Available minutes"),
    }


# ── Player season history ─────────────────────────────────────────────────────

_HISTORY_METRICS: list[tuple[str, str, bool]] = [
    # (column, label, per90-able)
    ("goals", "Goals", True),
    ("xG", "xG", True),
    ("xA", "xA", True),
    ("key_passes", "Key Passes", True),
    ("prog_passes", "Progressive Passes", True),
    ("xT", "xT", True),
    ("tackles", "Tackles", True),
    ("interceptions", "Interceptions", True),
    ("dribbles_won", "Dribbles Won", True),
    ("aerial_duels_won", "Aerials Won", True),
]


def _normalize_player_name(name: str) -> str:
    import unicodedata

    text = unicodedata.normalize("NFKD", str(name or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.lower().split())


def _league_season_from_path(file_path: str | None) -> tuple[str | None, str | None]:
    parts = str(file_path or "").split("/event_data/")
    if len(parts) < 2:
        return None, None
    tail = parts[1].split("/")
    if len(tail) < 2:
        return None, None
    return tail[0], tail[1]


def _player_summary_and_percentiles(stats: pd.DataFrame, resolved_name: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    player_rows = stats[stats["playerName"].astype(str) == resolved_name].copy()
    for col, _, _ in _HISTORY_METRICS:
        if col in player_rows.columns:
            player_rows[col] = pd.to_numeric(player_rows[col], errors="coerce").fillna(0.0)
    player_rows["mins_played"] = pd.to_numeric(player_rows["mins_played"], errors="coerce").fillna(0.0)
    total_mins = float(player_rows["mins_played"].sum())
    summary: dict[str, Any] = {"matches": int(len(player_rows)), "minutes": int(total_mins)}
    for col, _, per90able in _HISTORY_METRICS:
        if col not in player_rows.columns:
            continue
        total = float(player_rows[col].sum())
        summary[col] = round(total, 2)
        if per90able and total_mins > 0:
            summary[f"{col}_per90"] = round(total / total_mins * 90.0, 2)

    peers = stats.copy()
    peers["mins_played"] = pd.to_numeric(peers["mins_played"], errors="coerce").fillna(0.0)
    for col, _, _ in _HISTORY_METRICS:
        if col in peers.columns:
            peers[col] = pd.to_numeric(peers[col], errors="coerce").fillna(0.0)
    grouped = peers.groupby("playerName").agg({"mins_played": "sum", **{col: "sum" for col, _, _ in _HISTORY_METRICS if col in peers.columns}})
    grouped = grouped[grouped["mins_played"] >= 300]
    percentiles: list[dict[str, Any]] = []
    if resolved_name in grouped.index and total_mins >= 1:
        for col, label, per90able in _HISTORY_METRICS:
            if col not in grouped.columns or not per90able:
                continue
            per90 = grouped[col] / grouped["mins_played"] * 90.0
            value = float(per90.loc[resolved_name])
            percentiles.append({
                "metric": col,
                "label": label,
                "per90": round(value, 2),
                "percentile": round(float((per90 < value).mean() * 100.0)),
            })
    return summary, percentiles


def _resolve_stats_player(stats: pd.DataFrame, player: str) -> str | None:
    wanted = _normalize_player_name(player)
    normalized = stats["playerName"].astype(str).map(_normalize_player_name)
    mask = normalized.eq(wanted)
    if not mask.any():
        surname = wanted.split(" ")[-1]
        mask = normalized.str.endswith(f" {surname}") | normalized.eq(surname)
        if mask.sum() > 1:
            refined = mask & normalized.str.startswith(wanted[0])
            mask = refined if refined.any() else mask
    if not mask.any():
        return None
    return str(stats.loc[mask, "playerName"].iloc[0])


def build_player_history_view(
    file_path: str | None,
    player: str | None,
    match_id: str | None = None,
    player_b: str | None = None,
) -> dict[str, Any]:
    from app.services.season_stats import load_player_season_stats

    empty = {"player": player or "", "matches": [], "season": {}, "percentiles": [], "available": False}
    league, season = _league_season_from_path(file_path)
    if not league or not season or not player:
        return empty

    try:
        stats = load_player_season_stats(league, season)
    except Exception:
        logger.warning("failed to load player season stats for %s/%s", league, season, exc_info=True)
        return empty
    if stats.empty:
        return empty

    resolved_name = _resolve_stats_player(stats, player)
    if not resolved_name:
        return empty

    player_rows = stats[stats["playerName"].astype(str) == resolved_name].copy()
    player_rows["date"] = player_rows["date"].astype(str)
    player_rows = player_rows.sort_values("date")
    for col, _, _ in _HISTORY_METRICS:
        if col in player_rows.columns:
            player_rows[col] = pd.to_numeric(player_rows[col], errors="coerce").fillna(0.0)
    player_rows["mins_played"] = pd.to_numeric(player_rows["mins_played"], errors="coerce").fillna(0.0)

    # matchId -> event file path for deep links, from fixture listing
    file_path_by_match: dict[str, str] = {}
    try:
        from app.services import r2

        for fixture in r2.list_fixtures(league, season, limit=500, offset=0):
            fixture_id = str(fixture.get("match_id", "") or "")
            fixture_path = str(fixture.get("file_path", "") or "")
            if fixture_id and fixture_path:
                file_path_by_match[fixture_id] = fixture_path
    except Exception:
        logger.warning("failed to map fixtures for player history deep links", exc_info=True)

    wanted_match = str(match_id or "")
    matches = []
    for row in player_rows.itertuples():
        row_match_id = str(int(float(row.matchId))) if pd.notna(row.matchId) else ""
        matches.append({
            "match_id": row_match_id,
            "file_path": file_path_by_match.get(row_match_id, ""),
            "date": str(row.date),
            "team": str(row.teamName),
            "mins": int(row.mins_played),
            "is_current": bool(wanted_match and row_match_id == wanted_match),
            **{col: round(float(getattr(row, col, 0.0)), 3) for col, _, _ in _HISTORY_METRICS if hasattr(row, col)},
        })

    season_summary, percentiles = _player_summary_and_percentiles(stats, resolved_name)

    comparison: dict[str, Any] | None = None
    if player_b:
        resolved_b = _resolve_stats_player(stats, player_b)
        if resolved_b and resolved_b != resolved_name:
            summary_b, percentiles_b = _player_summary_and_percentiles(stats, resolved_b)
            comparison = {"player": resolved_b, "season_summary": summary_b, "percentiles": percentiles_b}

    peers_mins = stats.copy()
    peers_mins["mins_played"] = pd.to_numeric(peers_mins["mins_played"], errors="coerce").fillna(0.0)
    eligible = peers_mins.groupby("playerName")["mins_played"].sum()
    league_players = sorted(name for name, mins in eligible.items() if mins >= 300)

    return {
        "player": resolved_name,
        "league": league,
        "season": season,
        "matches": matches,
        "season_summary": season_summary,
        "percentiles": percentiles,
        "comparison": comparison,
        "league_players": league_players,
        "available": True,
    }
