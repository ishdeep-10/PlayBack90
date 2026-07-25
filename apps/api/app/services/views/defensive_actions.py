"""Defensive actions view builder."""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.services.matches import (
    _available_game_state_options,
    _coerce_numeric,
    _defensive_action_mask,
    _filter_score_state,
    _filter_time_range,
    _match_team_order,
    _normalize_time_range_to_window,
    _safe_float,
    _safe_int,
    _shot_team_state_controls,
    _time_bounds_for_state,
    _time_range_option,
    _with_game_state,
    _zone_from_x,
)

COUNTERPRESS_WINDOW_SECONDS = 5.0
MAX_RECOVERY_SECONDS = 60.0
POSSESSION_LOSS_TYPES = {"Turnover", "Dispossessed"}
REGAIN_ACTION_TYPES = {"BallRecovery", "Interception", "Tackle", "Challenge", "Aerial"}
COUNTERPRESS_ACTION_TYPES = {"BallRecovery", "Interception", "Tackle", "Challenge"}
CONTROL_ACTION_TYPES = {
    "Pass",
    "Carry",
    "TakeOn",
    "GoodSkill",
    "KeeperPickup",
    "KeeperSweeper",
    "Claim",
    "Goal",
    "SavedShot",
    "MissedShots",
    "ShotOnPost",
}


def _truthy(value: Any) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return bool(value)


def _event_seconds(row: pd.Series) -> float:
    return (_safe_float(row.get("minute")) * 60.0) + _safe_float(row.get("second"))


def _period_key(row: pd.Series) -> str:
    value = row.get("period")
    return "" if pd.isna(value) else str(value)


def _successful(row: pd.Series) -> bool:
    outcome = row.get("outcomeType")
    return pd.isna(outcome) or str(outcome).strip().lower() in {"", "successful", "goal", "saved"}


def _is_possession_loss(row: pd.Series) -> bool:
    return (
        str(row.get("type", "")).strip() in POSSESSION_LOSS_TYPES
        or _truthy(row.get("turnover"))
        or _truthy(row.get("dispossessed"))
    )


def _is_regain_action(row: pd.Series) -> bool:
    return str(row.get("type", "")).strip() in REGAIN_ACTION_TYPES and _successful(row)


def _is_counterpress_action(row: pd.Series) -> bool:
    return str(row.get("type", "")).strip() in COUNTERPRESS_ACTION_TYPES


def _confirms_control(row: pd.Series) -> bool:
    event_type = str(row.get("type", "")).strip()
    return _is_regain_action(row) or (event_type in CONTROL_ACTION_TYPES and _successful(row))


def _defensive_transition_sequences(
    enriched_df: pd.DataFrame,
    selected_team: str,
    score_state: str | None,
    time_range: str | None,
) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
    """Pair team possession losses with the next confirmed regain."""
    sort_cols = [col for col in ("minute", "second", "__row_id") if col in enriched_df.columns]
    ordered = enriched_df.sort_values(sort_cols).reset_index(drop=True)
    meaningful = ordered[
        ordered.get("type", pd.Series("", index=ordered.index)).astype(str).str.strip().ne("")
        & ordered.get("teamName", pd.Series("", index=ordered.index)).astype(str).str.strip().ne("")
    ].copy()
    if meaningful.empty:
        return [], {}

    loss_candidates = meaningful[
        meaningful["teamName"].astype(str).eq(selected_team)
        & meaningful.apply(_is_possession_loss, axis=1)
    ].copy()
    loss_candidates = _filter_score_state(loss_candidates, score_state)
    loss_candidates = _filter_time_range(loss_candidates, time_range)
    positions = {int(row_id): pos for pos, row_id in enumerate(meaningful["__row_id"].tolist())}

    sequences: list[dict[str, Any]] = []
    action_context: dict[int, dict[str, Any]] = {}
    for sequence_number, (_, loss) in enumerate(loss_candidates.iterrows(), start=1):
        loss_row_id = _safe_int(loss.get("__row_id"))
        position = positions.get(loss_row_id)
        if position is None:
            continue
        loss_time = _event_seconds(loss)
        loss_period = _period_key(loss)
        counterpress_action_ids: list[int] = []
        counterpress_action_players: list[str] = []
        regain: pd.Series | None = None

        for _, candidate in meaningful.iloc[position + 1 :].iterrows():
            candidate_period = _period_key(candidate)
            if loss_period and candidate_period and candidate_period != loss_period:
                break
            elapsed = _event_seconds(candidate) - loss_time
            if elapsed < 0:
                continue
            if elapsed > MAX_RECOVERY_SECONDS:
                break
            if str(candidate.get("teamName", "")) != selected_team:
                continue
            if elapsed <= COUNTERPRESS_WINDOW_SECONDS and _is_counterpress_action(candidate):
                counterpress_action_ids.append(_safe_int(candidate.get("__row_id")))
                player_name = str(candidate.get("playerName", "")).strip()
                if player_name:
                    counterpress_action_players.append(player_name)
            if _confirms_control(candidate):
                regain = candidate
                break

        recovery_seconds = round(_event_seconds(regain) - loss_time, 1) if regain is not None else None
        quick_regain = recovery_seconds is not None and recovery_seconds <= COUNTERPRESS_WINDOW_SECONDS
        counterpress_success = bool(quick_regain and counterpress_action_ids)
        regain_row_id = _safe_int(regain.get("__row_id")) if regain is not None else None
        sequence_id = f"{loss_row_id}-{sequence_number}"
        sequence = {
            "sequence_id": sequence_id,
            "loss_minute": _safe_int(loss.get("minute")),
            "loss_second": _safe_int(loss.get("second")),
            "loss_player": str(loss.get("playerName", "")),
            "loss_type": str(loss.get("type", "")),
            "loss_x": _safe_float(loss.get("x")),
            "loss_y": _safe_float(loss.get("y")),
            "recovery_seconds": recovery_seconds,
            "regain_minute": _safe_int(regain.get("minute")) if regain is not None else None,
            "regain_second": _safe_int(regain.get("second")) if regain is not None else None,
            "regain_player": str(regain.get("playerName", "")) if regain is not None else "",
            "regain_type": str(regain.get("type", "")) if regain is not None else "",
            "regain_x": _safe_float(regain.get("x")) if regain is not None else None,
            "regain_y": _safe_float(regain.get("y")) if regain is not None else None,
            "counterpress_actions": len(counterpress_action_ids),
            "counterpress_action_players": counterpress_action_players,
            "counterpress_success": counterpress_success,
        }
        sequences.append(sequence)

        shared_context = {
            "transition_sequence_id": sequence_id,
            "loss_minute": sequence["loss_minute"],
            "loss_second": sequence["loss_second"],
            "loss_player": sequence["loss_player"],
            "loss_type": sequence["loss_type"],
            "loss_x": sequence["loss_x"],
            "loss_y": sequence["loss_y"],
            "recovery_seconds": recovery_seconds,
        }
        for action_row_id in counterpress_action_ids:
            action_context[action_row_id] = {
                **shared_context,
                "counterpress_action": True,
                "counterpress_regain": bool(counterpress_success and action_row_id == regain_row_id),
            }
        if regain_row_id is not None and _is_regain_action(regain):
            action_context[regain_row_id] = {
                **shared_context,
                **action_context.get(regain_row_id, {}),
                "is_transition_regain": True,
                "counterpress_action": regain_row_id in counterpress_action_ids,
                "counterpress_regain": bool(counterpress_success and regain_row_id in counterpress_action_ids),
            }

    return sequences, action_context


def build_defensive_actions_view(
    df: pd.DataFrame,
    team: str | None = None,
    score_state: str | None = "all",
    time_range: str | None = "all",
) -> dict[str, Any]:
    if df.empty or "teamName" not in df.columns:
        return {"team": team or "", "actions": [], "player_summary": [], "team_totals": [], "game_state_options": [], "time_range_options": []}

    enriched_df = _with_game_state(df).copy()
    enriched_df["__row_id"] = range(len(enriched_df))
    selected_team = team or str(enriched_df["teamName"].dropna().iloc[0])
    minute = _coerce_numeric(enriched_df.get("minute", pd.Series(0, index=enriched_df.index))).fillna(0)
    full_time = int(max(90, minute.max())) if not minute.empty else 90
    team_events = enriched_df[enriched_df["teamName"].astype(str).eq(selected_team)].copy()
    bounds_start, bounds_end = _time_bounds_for_state(team_events, {"minute_start": 0, "minute_end": full_time}, score_state)
    effective_window = {"minute_start": bounds_start, "minute_end": bounds_end}
    normalized_time_range = _normalize_time_range_to_window(time_range, effective_window)
    transition_sequences, transition_action_context = _defensive_transition_sequences(
        enriched_df,
        selected_team,
        score_state,
        normalized_time_range,
    )

    defensive_df = enriched_df[_defensive_action_mask(enriched_df)].copy()
    scoped = defensive_df[defensive_df["teamName"].astype(str).eq(selected_team)].copy()
    scoped = _filter_score_state(scoped, score_state)
    scoped = _filter_time_range(scoped, normalized_time_range)
    sort_cols = [col for col in ("minute", "second", "__row_id") if col in enriched_df.columns]
    ordered_events = enriched_df.sort_values(sort_cols).reset_index(drop=True)
    event_positions = {int(row_id): pos for pos, row_id in enumerate(ordered_events["__row_id"].tolist())}

    def _is_meaningful_event(row: pd.Series) -> bool:
        event_type = row.get("type")
        if pd.isna(event_type) or not str(event_type).strip() or str(event_type).lower() == "nan":
            return False
        team_name = row.get("teamName")
        if pd.isna(team_name) or not str(team_name).strip() or str(team_name).lower() == "nan":
            return False
        return True

    def _next_event_context(row: pd.Series) -> dict[str, Any]:
        row_id = _safe_int(row.get("__row_id"))
        position = event_positions.get(row_id)
        if position is None:
            return {}
        next_events = ordered_events.iloc[position + 1 : position + 16]
        context: dict[str, Any] = {}
        meaningful_events = [next_row for _, next_row in next_events.iterrows() if _is_meaningful_event(next_row)][:3]
        for offset, next_row in enumerate(meaningful_events, start=1):
            prefix = f"next_{offset}"
            context[f"{prefix}_team"] = str(next_row.get("teamName", ""))
            context[f"{prefix}_player"] = str(next_row.get("playerName", ""))
            context[f"{prefix}_type"] = str(next_row.get("type", ""))
            context[f"{prefix}_minute"] = _safe_int(next_row.get("minute"))
            context[f"{prefix}_second"] = _safe_int(next_row.get("second"))
            context[f"{prefix}_outcome"] = str(next_row.get("outcomeType", ""))
            context[f"{prefix}_x"] = _safe_float(next_row.get("x"))
            context[f"{prefix}_y"] = _safe_float(next_row.get("y"))
            context[f"{prefix}_end_x"] = _safe_float(next_row.get("endX"))
            context[f"{prefix}_end_y"] = _safe_float(next_row.get("endY"))
        first_next_team = str(context.get("next_1_team", ""))
        first_next_type = str(context.get("next_1_type", ""))
        context["next_team_retained"] = bool(first_next_team and first_next_team == str(row.get("teamName", "")))
        context["next_event_label"] = (
            f"{first_next_type} by {context.get('next_1_player', '')}"
            if first_next_type
            else ""
        )
        return context

    actions: list[dict[str, Any]] = []
    if not scoped.empty:
        for _, row in scoped.sort_values([col for col in ("minute", "second", "index") if col in scoped.columns]).iterrows():
            x = _safe_float(row.get("x"))
            action = {
                "minute": _safe_int(row.get("minute")),
                "second": _safe_int(row.get("second")),
                "team": str(row.get("teamName", "")),
                "player": str(row.get("playerName", "")),
                "player_id": _safe_int(row.get("playerId")),
                "type": str(row.get("type", "")),
                "outcome": str(row.get("outcomeType", "")),
                "x": x,
                "y": _safe_float(row.get("y")),
                "zone": _zone_from_x(x),
                "game_state": str(row.get("team_score_state", "level")),
                "game_state_label": str(row.get("team_score_state_label", "Level")),
                "score_before": str(row.get("score_before", "0-0")),
            }
            action.update(_next_event_context(row))
            action.update(transition_action_context.get(_safe_int(row.get("__row_id")), {}))
            actions.append(action)

    player_summary: list[dict[str, Any]] = []
    if actions:
        action_df = pd.DataFrame(actions)
        # Events with no player attribution stringify to "nan"/"" — drop them.
        action_df = action_df[~action_df["player"].astype(str).str.lower().isin(["", "nan", "none"])]
        grouped = action_df.groupby("player")
        for player_name, player_df in grouped:
            by_type = player_df["type"].value_counts().to_dict()
            by_zone = player_df["zone"].value_counts().to_dict()
            player_counterpress_actions = sum(
                row.get("counterpress_action_players", []).count(str(player_name))
                for row in transition_sequences
            )
            player_counterpress_regains = sum(
                bool(row.get("counterpress_success")) and str(row.get("regain_player", "")) == str(player_name)
                for row in transition_sequences
            )
            player_summary.append(
                {
                    "player": str(player_name),
                    "total": int(len(player_df)),
                    "tackles": int(by_type.get("Tackle", 0)),
                    "interceptions": int(by_type.get("Interception", 0)),
                    "recoveries": int(by_type.get("BallRecovery", 0)),
                    "clearances": int(by_type.get("Clearance", 0)),
                    "blocked_passes": int(by_type.get("BlockedPass", 0)),
                    "aerials": int(by_type.get("Aerial", 0)),
                    "defensive_third": int(by_zone.get("Defensive Third", 0)),
                    "middle_third": int(by_zone.get("Middle Third", 0)),
                    "attacking_third": int(by_zone.get("Attacking Third", 0)),
                    "counterpress_actions": player_counterpress_actions,
                    "counterpress_regains": player_counterpress_regains,
                    "counterpress_success_pct": float(round(
                        100.0
                        * player_counterpress_regains
                        / max(1, player_counterpress_actions),
                        1,
                    )),
                    "avg_time_to_player_regain": round(
                        float(
                            pd.to_numeric(
                                player_df.loc[
                                    player_df.get("is_transition_regain", pd.Series(False, index=player_df.index)).fillna(False).astype(bool),
                                    "recovery_seconds",
                                ],
                                errors="coerce",
                            ).mean()
                        ),
                        1,
                    )
                    if "recovery_seconds" in player_df.columns
                    and player_df.get("is_transition_regain", pd.Series(False, index=player_df.index)).fillna(False).astype(bool).any()
                    else None,
                }
            )
    player_summary.sort(key=lambda row: int(row["total"]), reverse=True)

    team_totals: list[dict[str, Any]] = []
    for team_name in _match_team_order(enriched_df):
        team_def = defensive_df[defensive_df["teamName"].astype(str).eq(team_name)]
        by_type = team_def["type"].value_counts().to_dict() if not team_def.empty else {}
        team_totals.append(
            {
                "team": team_name,
                "total": int(len(team_def)),
                "tackles": int(by_type.get("Tackle", 0)),
                "interceptions": int(by_type.get("Interception", 0)),
                "recoveries": int(by_type.get("BallRecovery", 0)),
                "clearances": int(by_type.get("Clearance", 0)),
                "blocked_passes": int(by_type.get("BlockedPass", 0)),
                "aerials": int(by_type.get("Aerial", 0)),
            }
        )

    recovery_times = [
        float(row["recovery_seconds"])
        for row in transition_sequences
        if row.get("recovery_seconds") is not None
    ]
    counterpress_regains = sum(bool(row.get("counterpress_success")) for row in transition_sequences)
    transition_summary = {
        "counterpress_window_seconds": COUNTERPRESS_WINDOW_SECONDS,
        "recovery_cap_seconds": MAX_RECOVERY_SECONDS,
        "opportunities": len(transition_sequences),
        "counterpress_actions": sum(int(row.get("counterpress_actions", 0)) for row in transition_sequences),
        "counterpress_regains": counterpress_regains,
        "counterpress_success_pct": round(100.0 * counterpress_regains / max(1, len(transition_sequences)), 1),
        "confirmed_recoveries": len(recovery_times),
        "avg_recovery_seconds": round(sum(recovery_times) / len(recovery_times), 1) if recovery_times else None,
        "median_recovery_seconds": round(float(pd.Series(recovery_times).median()), 1) if recovery_times else None,
        "fastest_recovery_seconds": round(min(recovery_times), 1) if recovery_times else None,
        "within_5_seconds": sum(value <= 5 for value in recovery_times),
        "within_10_seconds": sum(value <= 10 for value in recovery_times),
        "within_15_seconds": sum(value <= 15 for value in recovery_times),
    }

    return {
        "team": selected_team,
        "actions": actions,
        "player_summary": player_summary,
        "team_totals": team_totals,
        "transition_summary": transition_summary,
        "transition_sequences": transition_sequences,
        "score_state": score_state or "all",
        "time_range": normalized_time_range,
        "game_state_options": _available_game_state_options(team_events),
        "time_range_options": _time_range_option(bounds_start, bounds_end, f"{bounds_start}'-{bounds_end}'"),
        "team_state_controls": _shot_team_state_controls(enriched_df),
        "full_time": full_time,
    }
