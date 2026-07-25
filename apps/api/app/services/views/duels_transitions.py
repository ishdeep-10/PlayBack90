"""Duels & transitions view builder and helpers."""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.services.matches import (
    _available_game_state_options,
    _coerce_numeric,
    _filter_score_state,
    _filter_time_range,
    _match_team_order,
    _normalize_time_range_to_window,
    _opponent_team_name,
    _safe_float,
    _safe_int,
    _shot_team_state_controls,
    _time_bounds_for_state,
    _time_range_option,
    _truthy_value,
    _with_game_state,
)
from app.services.views.common import (
    GROUND_DUEL_TYPES,
    _duel_mask,
    _row_successful,
)


TRANSITION_ATTACK_TYPES = {"Goal", "SavedShot", "MissedShots", "ShotOnPost", "CornerAwarded"}
SHOT_EVENTS = {"Goal", "SavedShot", "MissedShots", "ShotOnPost"}
SAVE_EVENTS = {"Save", "KeeperSave", "KeeperPickup", "Claim"}


def _classify_duel_category(row: pd.Series) -> str:
    event_type = str(row.get("type", ""))
    if _truthy_value(row.get("duelAerialWon")) or _truthy_value(row.get("duelAerialLost")) or event_type == "Aerial":
        return "Aerial"
    if event_type in GROUND_DUEL_TYPES:
        return "Ground"
    return "Total"


def _duel_won(row: pd.Series) -> bool:
    if str(row.get("type", "")) == "Foul":
        return _foul_won(row)
    if _truthy_value(row.get("duelAerialWon")):
        return True
    if _truthy_value(row.get("duelAerialLost")):
        return False
    outcome = str(row.get("outcomeType", "")).strip().lower()
    return outcome == "successful"


def _compact_event_label(event_type: str) -> str:
    normalized = str(event_type or "").strip()
    if normalized == "TakeOn":
        return "takeon"
    if normalized == "Foul":
        return "foul won"
    if normalized in {"Tackle", "Challenge"}:
        return "tackle"
    if normalized == "GoodSkill":
        return "skill"
    return normalized.lower() if normalized else "event"


def _foul_won(row: pd.Series) -> bool:
    if _truthy_value(row.get("foulGiven")):
        return True
    if _truthy_value(row.get("foulCommitted")):
        return False
    satisfied = str(row.get("satisfiedEventsTypes", "")).lower()
    if "foulgiven" in satisfied:
        return True
    if "foulcommitted" in satisfied:
        return False
    outcome = str(row.get("outcomeType", "")).strip().lower()
    return outcome == "successful"


def _duel_classification_label(row: pd.Series) -> str:
    if str(row.get("type", "")) == "Foul":
        return "foul won" if _foul_won(row) else "foul committed"
    return _compact_event_label(str(row.get("type", "")))


def _duel_context_event_label(row: pd.Series) -> str:
    event_type = str(row.get("type", "")).strip()
    if event_type == "Carry":
        return "Carry"
    if event_type == "TakeOn":
        return "Take-on"
    if event_type == "GoodSkill":
        return "Skill"
    if event_type == "SavedShot" and _truthy_value(row.get("shotBlocked")):
        return "Blocked Shot"
    if event_type == "SavedShot":
        return "Saved Shot"
    if event_type == "MissedShots":
        return "Shot"
    if event_type == "ShotOnPost":
        return "Shot on Post"
    if event_type in SAVE_EVENTS or event_type.lower().startswith("save") or event_type.lower().startswith("keeper"):
        return "Save"
    return event_type


DUEL_CONTEXT_IGNORED_TYPES = {
    "Start",
    "End",
    "FormationChange",
    "FormationSet",
    "SubstitutionOff",
    "SubstitutionOn",
    "Card",
    "Pause",
    "Resume",
    "CornerAwarded",
    "BallTouch",
}

DUEL_CONTEXT_MOVEMENT_TYPES = {"Pass", "Carry", "TakeOn", "GoodSkill"}


def _valid_duel_context_events(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty or "type" not in events.columns:
        return events.iloc[0:0].copy()
    valid = events.copy()
    event_type = valid["type"].astype(str).str.strip()
    valid = valid[event_type.ne("") & ~event_type.isin(DUEL_CONTEXT_IGNORED_TYPES)]
    if "x" in valid.columns and "y" in valid.columns:
        valid = valid[(_coerce_numeric(valid["x"]).notna()) & (_coerce_numeric(valid["y"]).notna())]
    return valid


def _valid_duel_movement_events(events: pd.DataFrame) -> pd.DataFrame:
    valid = _valid_duel_context_events(events)
    if valid.empty:
        return valid
    return valid[valid["type"].astype(str).isin(DUEL_CONTEXT_MOVEMENT_TYPES)].copy()


def _event_has_movement(row: pd.Series) -> bool:
    if str(row.get("type", "")) not in DUEL_CONTEXT_MOVEMENT_TYPES:
        return False
    start_x = _safe_float(row.get("x"))
    start_y = _safe_float(row.get("y"))
    end_x = _safe_float(row.get("endX"))
    end_y = _safe_float(row.get("endY"))
    has_end_point = end_x != 0 or end_y != 0
    moved = abs(start_x - end_x) > 0.1 or abs(start_y - end_y) > 0.1
    return has_end_point and moved


def _align_context_coordinate(value: Any, axis_max: float, event_team: str, duel_team: str) -> float:
    coordinate = _safe_float(value)
    if event_team and duel_team and event_team != duel_team:
        return axis_max - coordinate
    return coordinate


def _context_coordinates(row: pd.Series, duel_team: str) -> dict[str, float]:
    event_team = str(row.get("teamName", "")).strip()
    return {
        "x": _align_context_coordinate(row.get("x"), 105.0, event_team, duel_team),
        "y": _align_context_coordinate(row.get("y"), 68.0, event_team, duel_team),
        "end_x": _align_context_coordinate(row.get("endX"), 105.0, event_team, duel_team),
        "end_y": _align_context_coordinate(row.get("endY"), 68.0, event_team, duel_team),
    }


def _aligned_duel_x(row: pd.Series, reference_team: str) -> float:
    event_team = str(row.get("teamName", "")).strip()
    return _align_context_coordinate(row.get("x"), 105.0, event_team, reference_team)


def _aligned_duel_y(row: pd.Series, reference_team: str) -> float:
    event_team = str(row.get("teamName", "")).strip()
    return _align_context_coordinate(row.get("y"), 68.0, event_team, reference_team)


def _duel_pair_candidates(events: pd.DataFrame, row: pd.Series, position: int) -> pd.DataFrame:
    row_time = _transition_event_time(row)
    row_category = _classify_duel_category(row)
    row_team = str(row.get("teamName", "")).strip()
    row_x = _aligned_duel_x(row, row_team)
    row_y = _aligned_duel_y(row, row_team)
    candidates = events.iloc[max(0, position - 3) : min(len(events), position + 4)].copy()
    if candidates.empty:
        return candidates
    candidates = candidates[_duel_mask(candidates, "Total")].copy()
    if candidates.empty:
        return candidates
    candidate_time = candidates.apply(_transition_event_time, axis=1)
    candidates = candidates[(candidate_time - row_time).abs() <= 1.1].copy()
    if candidates.empty:
        return candidates
    category_match = candidates.apply(_classify_duel_category, axis=1).eq(row_category)
    candidates = candidates[category_match].copy()
    if candidates.empty:
        return candidates
    x_match = candidates.apply(lambda candidate: abs(_aligned_duel_x(candidate, row_team) - row_x) <= 3.5, axis=1)
    y_match = candidates.apply(lambda candidate: abs(_aligned_duel_y(candidate, row_team) - row_y) <= 3.5, axis=1)
    return candidates[x_match & y_match].copy()


def _same_duel_pair_mask(candidates: pd.DataFrame, row: pd.Series) -> pd.Series:
    if candidates.empty:
        return pd.Series(False, index=candidates.index)
    row_time = _transition_event_time(row)
    row_category = _classify_duel_category(row)
    row_team = str(row.get("teamName", "")).strip()
    row_x = _aligned_duel_x(row, row_team)
    row_y = _aligned_duel_y(row, row_team)
    candidate_time = candidates.apply(_transition_event_time, axis=1)
    time_match = (candidate_time - row_time).abs() <= 1.1
    category_match = candidates.apply(_classify_duel_category, axis=1).eq(row_category)
    x_match = candidates.apply(lambda candidate: abs(_aligned_duel_x(candidate, row_team) - row_x) <= 3.5, axis=1)
    y_match = candidates.apply(lambda candidate: abs(_aligned_duel_y(candidate, row_team) - row_y) <= 3.5, axis=1)
    return time_match & category_match & x_match & y_match


def _duel_context_payload(row: pd.Series, prefix: str, duel_team: str, events: pd.DataFrame, position: int) -> dict[str, Any]:
    event_team = str(row.get("teamName", "")).strip()
    pair = _duel_pair_candidates(events, row, position)
    players = [
        {
            "player": str(candidate.get("playerName", "")).strip(),
            "team": str(candidate.get("teamName", "")).strip(),
            "won": _duel_won(candidate),
        }
        for _, candidate in pair.iterrows()
    ]
    winners = [item for item in players if item["won"]]
    losers = [item for item in players if not item["won"]]
    winner = winners[0] if winners else (players[0] if players else {"player": str(row.get("playerName", "")).strip(), "team": event_team, "won": _duel_won(row)})
    loser = next(
        (
            item
            for item in (losers if losers else players)
            if item["player"] != winner["player"] or item["team"] != winner["team"]
        ),
        None,
    )
    if loser:
        summary = f"{_classify_duel_category(row)} duel between {winner['player']} and {loser['player']}"
    else:
        summary = f"{_classify_duel_category(row)} duel by {winner['player']}"
    return {
        f"{prefix}_duel": True,
        f"{prefix}_duel_id": _safe_int(row.get("__row_id")),
        f"{prefix}_duel_player": str(row.get("playerName", "")).strip(),
        f"{prefix}_duel_team": event_team,
        f"{prefix}_duel_category": _classify_duel_category(row),
        f"{prefix}_duel_classification": _duel_classification_label(row),
        f"{prefix}_duel_won": _duel_won(row),
        f"{prefix}_duel_summary": summary,
        f"{prefix}_duel_winner": winner["player"],
        f"{prefix}_duel_winner_team": winner["team"],
        f"{prefix}_duel_loser": loser["player"] if loser else "",
        f"{prefix}_duel_loser_team": loser["team"] if loser else "",
        f"{prefix}_duel_minute": _safe_int(row.get("minute")),
        f"{prefix}_duel_second": _safe_int(row.get("second")),
        f"{prefix}_duel_x": _align_context_coordinate(row.get("x"), 105.0, event_team, duel_team),
        f"{prefix}_duel_y": _align_context_coordinate(row.get("y"), 68.0, event_team, duel_team),
    }


def _nearby_previous_duel(events: pd.DataFrame, position: int, team_name: str, max_seconds: float = 2.5) -> dict[str, Any]:
    if position <= 0:
        return {}
    current = events.iloc[position]
    current_time = _transition_event_time(current)
    candidates = events.iloc[max(0, position - 10) : position].copy()
    if candidates.empty:
        return {}
    candidates = candidates[_duel_mask(candidates, "Total")].copy()
    if candidates.empty:
        return {}
    candidates = candidates[~_same_duel_pair_mask(candidates, current)].copy()
    if candidates.empty:
        return {}
    candidate_time = candidates.apply(_transition_event_time, axis=1)
    candidates = candidates[(current_time - candidate_time >= 0) & (current_time - candidate_time <= max_seconds)].copy()
    if candidates.empty:
        return {}
    row = candidates.iloc[-1]
    payload = _duel_context_payload(row, "previous", team_name, events, _safe_int(row.get("__row_id")))
    return payload if payload.get("previous_duel_loser") else {}


def _nearby_next_duel(events: pd.DataFrame, position: int, team_name: str, max_seconds: float = 2.5) -> dict[str, Any]:
    current = events.iloc[position]
    current_time = _transition_event_time(current)
    candidates = events.iloc[position + 1 : position + 11].copy()
    if candidates.empty:
        return {}
    candidates = candidates[_duel_mask(candidates, "Total")].copy()
    if candidates.empty:
        return {}
    candidates = candidates[~_same_duel_pair_mask(candidates, current)].copy()
    if candidates.empty:
        return {}
    candidate_time = candidates.apply(_transition_event_time, axis=1)
    candidates = candidates[(candidate_time - current_time >= 0) & (candidate_time - current_time <= max_seconds)].copy()
    if candidates.empty:
        return {}
    row = candidates.iloc[0]
    payload = _duel_context_payload(row, "next", team_name, events, _safe_int(row.get("__row_id")))
    return payload if payload.get("next_duel_loser") else {}


def _describe_previous_duel_event(events: pd.DataFrame, position: int, team_name: str) -> dict[str, Any]:
    previous_duel = _nearby_previous_duel(events, position, team_name)
    if previous_duel:
        return previous_duel
    candidates = events.iloc[max(0, position - 8) : position].copy()
    if candidates.empty:
        return {}
    candidates = _valid_duel_movement_events(candidates)
    if candidates.empty:
        return {}
    previous = candidates.iloc[-1]
    event_type = str(previous.get("type", ""))
    player = str(previous.get("playerName", "")).strip()
    minute = _safe_int(previous.get("minute"))
    second = _safe_int(previous.get("second"))
    outcome = str(previous.get("outcomeType", "")).strip()
    if event_type in {"Pass", "Carry", "TakeOn", "GoodSkill"}:
        label = _duel_context_event_label(previous)
    elif event_type in {"Tackle", "Interception", "BallRecovery", "Challenge"}:
        label = "Defensive action"
    else:
        label = event_type
    coords = _context_coordinates(previous, team_name)
    return {
        "previous_event": event_type,
        "previous_event_label": label,
        "previous_player": player,
        "previous_minute": minute,
        "previous_second": second,
        "previous_outcome": outcome,
        "previous_successful": _row_successful(previous),
        "previous_team": str(previous.get("teamName", "")).strip(),
        "previous_can_plot": _event_has_movement(previous),
        "previous_x": coords["x"],
        "previous_y": coords["y"],
        "previous_end_x": coords["end_x"],
        "previous_end_y": coords["end_y"],
    }


def _describe_next_duel_event(events: pd.DataFrame, position: int, team_name: str) -> dict[str, Any]:
    current = events.iloc[position]
    next_duel = _nearby_next_duel(events, position, team_name)
    start_time = _transition_event_time(current)
    previous_team = ""
    previous_events = _valid_duel_movement_events(events.iloc[max(0, position - 8) : position].copy())
    if not previous_events.empty:
        previous_team = str(previous_events.iloc[-1].get("teamName", "")).strip()
    candidates = events.iloc[position + 1 : position + 24].copy()
    if candidates.empty:
        return next_duel or {
            "duel_context": "unknown",
            "duel_context_label": "No follow-up",
        }
    candidate_time = candidates.apply(_transition_event_time, axis=1)
    candidates = candidates[(candidate_time - start_time >= 0) & (candidate_time - start_time <= 15.0)].copy()
    same_team_attack_candidates = candidates[candidates["teamName"].astype(str).eq(team_name)].copy()
    valid_candidates = _valid_duel_context_events(candidates)
    if valid_candidates.empty:
        return next_duel or {
            "duel_context": "unknown",
            "duel_context_label": "No follow-up",
        }

    same_team = valid_candidates[valid_candidates["teamName"].astype(str).eq(team_name)].copy()
    opponent = valid_candidates[~valid_candidates["teamName"].astype(str).eq(team_name)].copy()
    movement_candidates = _valid_duel_movement_events(valid_candidates)
    shot_candidates = valid_candidates[valid_candidates["type"].astype(str).isin(SHOT_EVENTS)].copy()
    save_candidates = valid_candidates[valid_candidates["type"].astype(str).isin(SAVE_EVENTS)].copy()

    if not movement_candidates.empty:
        next_event = movement_candidates.iloc[0]
        if not _row_successful(next_event):
            controlled_opponent = movement_candidates[
                (~movement_candidates["teamName"].astype(str).eq(team_name))
                & movement_candidates.apply(_row_successful, axis=1)
            ].copy()
            if not controlled_opponent.empty:
                next_event = controlled_opponent.iloc[0]
    elif not save_candidates.empty:
        first_save = save_candidates.iloc[0]
        save_time = _transition_event_time(first_save)
        shots_before_save = shot_candidates[shot_candidates.apply(_transition_event_time, axis=1) <= save_time].copy()
        next_event = shots_before_save.iloc[-1] if not shots_before_save.empty else first_save
    elif not same_team.empty:
        next_event = same_team.iloc[0]
    elif not opponent.empty:
        next_event = opponent.iloc[0]
    else:
        next_event = valid_candidates.iloc[0]

    led_to_attack = (
        not same_team_attack_candidates[same_team_attack_candidates.apply(_is_duel_led_to_attack_event, axis=1)].empty
        if not same_team_attack_candidates.empty
        else False
    )
    if not _duel_won(current) and _transition_third(current.get("x")) == "Defensive Third":
        led_to_attack = False
    next_event_successful = _row_successful(next_event)
    retained = str(next_event.get("teamName", "")) == team_name and next_event_successful
    context = "led_to_attack" if led_to_attack else ("retained" if retained else "turnover")
    event_type = str(next_event.get("type", ""))
    next_team = str(next_event.get("teamName", "")).strip()
    next_player = str(next_event.get("playerName", "")).strip()
    if led_to_attack:
        context_label = "Led to attack"
    elif retained:
        if _classify_duel_category(current) == "Aerial" and previous_team and previous_team != team_name:
            context_label = "Second ball recovered"
        else:
            context_label = "Ball retained"
    elif _classify_duel_category(current) == "Aerial" and next_team and next_team != team_name:
        context_label = "Second ball lost"
    elif event_type == "Dispossessed":
        context_label = f"Possession lost by {next_player}" if next_player else "Possession lost"
    else:
        context_label = "Turnover"
    if event_type in {"Pass", "Carry", "TakeOn", "GoodSkill"} or event_type in SAVE_EVENTS:
        label = _duel_context_event_label(next_event)
    elif event_type in {"Tackle", "Interception", "BallRecovery", "Challenge"}:
        label = "Defensive action"
    else:
        label = event_type
    coords = _context_coordinates(next_event, team_name)

    payload = {
        "duel_context": context,
        "duel_context_label": context_label,
        "next_event": event_type,
        "next_event_label": label,
        "next_player": next_player,
        "next_team": next_team,
        "next_can_plot": _event_has_movement(next_event),
        "next_minute": _safe_int(next_event.get("minute")),
        "next_second": _safe_int(next_event.get("second")),
        "next_outcome": str(next_event.get("outcomeType", "")).strip(),
        "next_successful": next_event_successful,
        "next_x": coords["x"],
        "next_y": coords["y"],
        "next_end_x": coords["end_x"],
        "next_end_y": coords["end_y"],
    }
    if not movement_candidates.empty:
        return payload
    payload.update(next_duel)
    return payload


def _transition_third(x_value: Any) -> str:
    x = _safe_float(x_value)
    if x < 35:
        return "Defensive Third"
    if x < 70:
        return "Middle Third"
    return "Attacking Third"


def _transition_event_time(row: pd.Series) -> float:
    return (_safe_float(row.get("minute")) * 60.0) + _safe_float(row.get("second"))


def _is_transition_attack_event(row: pd.Series) -> bool:
    event_type = str(row.get("type", ""))
    if event_type in TRANSITION_ATTACK_TYPES:
        return True
    if event_type in {"Pass", "Carry", "TakeOn", "GoodSkill"} and _row_successful(row):
        return max(_safe_float(row.get("x")), _safe_float(row.get("endX"))) >= 70
    return False


def _transition_end_product_label(row: pd.Series | None) -> str:
    if row is None:
        return "No attacking follow-up"
    event_type = str(row.get("type", "")).strip()
    player = str(row.get("playerName", "")).strip()
    suffix = f" by {player}" if player else ""
    if event_type == "Goal":
        return f"Goal{suffix}"
    if event_type == "SavedShot" and _truthy_value(row.get("shotBlocked")):
        return f"Blocked shot{suffix}"
    if event_type == "SavedShot":
        return f"Saved shot{suffix}"
    if event_type == "MissedShots":
        return f"Shot{suffix}"
    if event_type == "ShotOnPost":
        return f"Shot on post{suffix}"
    if event_type == "CornerAwarded":
        return "Corner won"
    if event_type in {"Pass", "Carry", "TakeOn", "GoodSkill"}:
        label = _duel_context_event_label(row)
        end_x = _safe_float(row.get("endX"))
        end_y = _safe_float(row.get("endY"))
        if end_x == 0 and end_y == 0:
            end_x = _safe_float(row.get("x"))
            end_y = _safe_float(row.get("y"))
        if end_x >= 88.5 and 13.84 <= end_y <= 54.16:
            return f"{label} into box{suffix}"
        return f"Advanced {label.lower()}{suffix}"
    return f"{_duel_context_event_label(row)}{suffix}"


def _transition_chain_label(row: pd.Series, follow_team: str) -> str | None:
    event_type = str(row.get("type", "")).strip()
    player = str(row.get("playerName", "")).strip()
    team_name = str(row.get("teamName", "")).strip()
    suffix = f" by {player}" if player else ""
    if team_name and team_name != follow_team:
        label = _duel_context_event_label(row)
        return f"{label}{suffix} ({team_name})"
    if event_type in {"BallRecovery", "Tackle", "Challenge", "Interception"}:
        return None
    if event_type in {"Pass", "Carry", "TakeOn", "GoodSkill"} and not _row_successful(row):
        return f"Unsuccessful {_duel_context_event_label(row).lower()}{suffix}"
    if _truthy_value(row.get("dispossessed")) or _truthy_value(row.get("turnover")) or event_type == "Dispossessed":
        return f"Possession lost{suffix}"
    return _transition_end_product_label(row)


def _transition_terminal_label(row: pd.Series, follow_team: str) -> str | None:
    event_type = str(row.get("type", "")).strip()
    team_name = str(row.get("teamName", "")).strip()
    player = str(row.get("playerName", "")).strip()
    suffix = f" by {player}" if player else ""
    if team_name and team_name != follow_team:
        label = _duel_context_event_label(row)
        return f"{label}{suffix} ({team_name})"
    if event_type in TRANSITION_ATTACK_TYPES:
        return _transition_end_product_label(row)
    if event_type in {"Pass", "Carry", "TakeOn", "GoodSkill"} and not _row_successful(row):
        return f"Unsuccessful {_duel_context_event_label(row).lower()}{suffix}"
    if _truthy_value(row.get("dispossessed")) or _truthy_value(row.get("turnover")) or event_type == "Dispossessed":
        return f"Possession lost{suffix}"
    return None


def _transition_chain_labels(candidates: pd.DataFrame, follow_team: str, limit: int = 5) -> list[str]:
    labels: list[str] = []
    for _, row in candidates.iterrows():
        label = _transition_chain_label(row, follow_team)
        if not label or (labels and labels[-1] == label):
            continue
        labels.append(label)
        if len(labels) >= limit:
            break
    return labels


def _is_duel_led_to_attack_event(row: pd.Series) -> bool:
    event_type = str(row.get("type", ""))
    if event_type in SHOT_EVENTS:
        return True
    if event_type == "CornerAwarded":
        return True
    if event_type not in {"Pass", "Carry", "TakeOn", "GoodSkill"} or not _row_successful(row):
        return False
    end_x = _safe_float(row.get("endX"))
    end_y = _safe_float(row.get("endY"))
    if end_x == 0 and end_y == 0:
        end_x = _safe_float(row.get("x"))
        end_y = _safe_float(row.get("y"))
    return end_x >= 88.5 and 13.84 <= end_y <= 54.16


def _next_meaningful_transition_event(events: pd.DataFrame, position: int, team_name: str, max_rows: int = 18) -> pd.Series | None:
    candidates = events.iloc[position + 1 : position + 1 + max_rows]
    for _, candidate in candidates.iterrows():
        if str(candidate.get("teamName", "")) == team_name and str(candidate.get("type", "")).strip():
            return candidate
    return None


def _transition_followup(
    events: pd.DataFrame,
    start_position: int,
    team_name: str,
    possession_id: Any,
    max_seconds: float = 12.0,
) -> tuple[bool, pd.Series | None, list[str], str]:
    start_row = events.iloc[start_position]
    start_time = _transition_event_time(start_row)
    candidates = events.iloc[start_position + 1 : start_position + 24].copy()
    if candidates.empty:
        return False, None, [], "No attacking follow-up"
    candidate_time = candidates.apply(_transition_event_time, axis=1)
    candidates = candidates[(candidate_time - start_time >= 0) & (candidate_time - start_time <= max_seconds)]
    candidates = candidates.copy()
    same_team_candidates = candidates[candidates["teamName"].astype(str).eq(team_name)].copy()
    if "possession_id" in candidates.columns and not pd.isna(possession_id):
        same_possession = same_team_candidates[same_team_candidates["possession_id"] == possession_id]
        if not same_possession.empty:
            same_team_candidates = same_possession
    if same_team_candidates.empty:
        return False, None, [], "No attacking follow-up"
    attack_events = same_team_candidates[same_team_candidates.apply(_is_transition_attack_event, axis=1)]
    event_types = _transition_chain_labels(same_team_candidates, team_name)
    if not attack_events.empty:
        attack_index = attack_events.index[0]
        attack_row = attack_events.iloc[0]
        terminal_row: pd.Series | None = None
        terminal_label: str | None = None
        for candidate_index, candidate in candidates.iterrows():
            if candidate_index < attack_index:
                continue
            terminal_label = _transition_terminal_label(candidate, team_name)
            if terminal_label:
                terminal_row = candidate
                break
        if terminal_row is None:
            terminal_row = attack_row
            terminal_label = "Attack developed; no terminal event in window"
        chain_window = candidates.loc[: terminal_row.name] if terminal_row.name in candidates.index else same_team_candidates
        event_types = _transition_chain_labels(chain_window, team_name)
        return True, terminal_row, event_types, terminal_label
    return False, same_team_candidates.iloc[-1], event_types, "No attacking follow-up"


def build_duels_transitions_view(
    df: pd.DataFrame,
    team: str | None = None,
    duel_type: str | None = "Total",
    transition_type: str | None = "Offensive",
    score_state: str | None = "all",
    time_range: str | None = "all",
) -> dict[str, Any]:
    if df.empty or "teamName" not in df.columns:
        return {
            "team": team or "",
            "duel_type": duel_type or "Total",
            "transition_type": transition_type or "Offensive",
            "duels": [],
            "transitions": [],
            "player_summary": [],
            "team_summary": [],
            "game_state_options": [],
            "time_range_options": [],
        }

    enriched_df = _with_game_state(df).copy()
    enriched_df["__row_id"] = range(len(enriched_df))
    teams = _match_team_order(enriched_df)
    requested_team = str(team or "").strip()
    include_both_teams = requested_team.lower() in {"both", "both teams", "all", "__both__"}
    selected_team = "__both__" if include_both_teams else (team or (teams[0] if teams else str(enriched_df["teamName"].dropna().iloc[0])))
    state_reference_team = teams[0] if include_both_teams and teams else selected_team
    team_events = enriched_df[enriched_df["teamName"].astype(str).eq(state_reference_team)].copy()
    minute = _coerce_numeric(enriched_df.get("minute", pd.Series(0, index=enriched_df.index))).fillna(0)
    full_time = int(max(90, minute.max())) if not minute.empty else 90
    bounds_start, bounds_end = _time_bounds_for_state(team_events, {"minute_start": 0, "minute_end": full_time}, score_state)
    effective_window = {"minute_start": bounds_start, "minute_end": bounds_end}
    normalized_time_range = _normalize_time_range_to_window(time_range, effective_window)

    scoped_events = enriched_df.copy() if include_both_teams else enriched_df[enriched_df["teamName"].astype(str).eq(selected_team)].copy()
    scoped_events = _filter_score_state(scoped_events, score_state)
    scoped_events = _filter_time_range(scoped_events, normalized_time_range)

    filtered_row_ids = set(scoped_events["__row_id"].astype(int).tolist())
    duel_source = enriched_df[_duel_mask(enriched_df, duel_type)].copy()
    duel_source = duel_source[duel_source["__row_id"].astype(int).isin(filtered_row_ids)].copy()

    duels: list[dict[str, Any]] = []
    if not duel_source.empty:
        for _, row in duel_source.sort_values([col for col in ("minute", "second", "__row_id") if col in duel_source.columns]).iterrows():
            x = _safe_float(row.get("x"))
            category = _classify_duel_category(row)
            row_team = str(row.get("teamName", ""))
            row_position = _safe_int(row.get("__row_id"))
            previous_context = _describe_previous_duel_event(enriched_df, row_position, row_team)
            next_context = _describe_next_duel_event(enriched_df, row_position, row_team)
            duel_row = {
                "id": row_position,
                "minute": _safe_int(row.get("minute")),
                "second": _safe_int(row.get("second")),
                "team": row_team,
                "player": str(row.get("playerName", "")),
                "player_id": _safe_int(row.get("playerId")),
                "type": str(row.get("type", "")),
                "category": category,
                "classification": _duel_classification_label(row),
                "outcome": str(row.get("outcomeType", "")),
                "won": _duel_won(row),
                "x": x,
                "y": _safe_float(row.get("y")),
                "zone": _transition_third(x),
                "game_state": str(row.get("team_score_state", "level")),
                "game_state_label": str(row.get("team_score_state_label", "Level")),
                "score_before": str(row.get("score_before", "0-0")),
            }
            duel_row.update(previous_context)
            duel_row.update(next_context)
            duels.append(duel_row)

    sort_cols = [col for col in ("minute", "second", "__row_id") if col in enriched_df.columns]
    ordered = enriched_df.sort_values(sort_cols).reset_index(drop=True)
    transitions: list[dict[str, Any]] = []
    transition_mode = str(transition_type or "Offensive")

    def add_transition(start_row: pd.Series, start_position: int, transition_team: str, follow_team: str, direction_label: str) -> None:
        led_to_attack, end_row, event_types, end_product = _transition_followup(ordered, start_position, follow_team, start_row.get("possession_id"), 14.0)
        end_x = _safe_float(end_row.get("x")) if end_row is not None else _safe_float(start_row.get("endX"))
        end_y = _safe_float(end_row.get("y")) if end_row is not None else _safe_float(start_row.get("endY"))
        if end_x == 0 and end_y == 0:
            end_x = _safe_float(start_row.get("x"))
            end_y = _safe_float(start_row.get("y"))
        start_x = _safe_float(start_row.get("x"))
        transitions.append(
            {
                "id": _safe_int(start_row.get("__row_id")),
                "minute": _safe_int(start_row.get("minute")),
                "second": _safe_int(start_row.get("second")),
                "team": transition_team,
                "player": str(start_row.get("playerName", "")),
                "player_id": _safe_int(start_row.get("playerId")),
                "type": str(start_row.get("type", "")),
                "transition_type": transition_mode,
                "direction": direction_label,
                "led_to_attack": bool(led_to_attack),
                "x": start_x,
                "y": _safe_float(start_row.get("y")),
                "end_x": end_x,
                "end_y": end_y,
                "third": _transition_third(start_x),
                "followup": ", ".join(event_types[:3]),
                "end_product": end_product,
                "game_state": str(start_row.get("team_score_state", "level")),
                "game_state_label": str(start_row.get("team_score_state_label", "Level")),
                "score_before": str(start_row.get("score_before", "0-0")),
            }
        )

    for position, row in ordered.iterrows():
        row_id = _safe_int(row.get("__row_id"))
        row_team = str(row.get("teamName", ""))
        is_loss_event = _truthy_value(row.get("dispossessed")) or _truthy_value(row.get("turnover"))

        if transition_mode == "Defensive":
            if row_id not in filtered_row_ids or (not include_both_teams and row_team != selected_team) or not is_loss_event:
                continue
            next_event = _next_meaningful_transition_event(ordered, position, _opponent_team_name(enriched_df, row_team))
            if next_event is None:
                continue
            add_transition(row, position, row_team, str(next_event.get("teamName", "")), "Opponent attack")
            continue

        if not is_loss_event:
            continue
        if include_both_teams or row_team == selected_team:
            continue
        next_event = _next_meaningful_transition_event(ordered, position, selected_team)
        if next_event is None:
            continue
        next_row_id = _safe_int(next_event.get("__row_id"))
        if next_row_id not in filtered_row_ids:
            continue
        add_transition(next_event, _safe_int(next_event.name), selected_team, selected_team, "To attack")

    player_map: dict[str, dict[str, Any]] = {}
    for row in duels:
        player = str(row.get("player", ""))
        if not player:
            continue
        item = player_map.setdefault(
            player,
            {"player": player, "duels": 0, "duels_won": 0, "ground": 0, "aerial": 0, "transitions": 0, "transitions_to_attack": 0},
        )
        item["duels"] += 1
        item["duels_won"] += 1 if row.get("won") else 0
        category = str(row.get("category", "")).lower()
        if category in {"ground", "aerial"}:
            item[category] += 1
    for row in transitions:
        player = str(row.get("player", ""))
        if not player:
            continue
        item = player_map.setdefault(
            player,
            {"player": player, "duels": 0, "duels_won": 0, "ground": 0, "aerial": 0, "transitions": 0, "transitions_to_attack": 0},
        )
        item["transitions"] += 1
        item["transitions_to_attack"] += 1 if row.get("led_to_attack") else 0
    player_summary = list(player_map.values())
    for row in player_summary:
        row["duel_win_pct"] = round((int(row["duels_won"]) / int(row["duels"]) * 100), 1) if int(row["duels"]) else 0.0
        row["transition_hit_pct"] = round((int(row["transitions_to_attack"]) / int(row["transitions"]) * 100), 1) if int(row["transitions"]) else 0.0
    player_summary.sort(key=lambda row: (int(row["duels_won"]), int(row["transitions_to_attack"]), int(row["duels"])), reverse=True)

    team_summary: list[dict[str, Any]] = []
    for team_name in teams:
        if not include_both_teams and team_name != selected_team:
            continue
        team_duels = [row for row in duels if row.get("team") == team_name]
        team_transitions = [row for row in transitions if row.get("team") == team_name]
        won = sum(1 for row in team_duels if row.get("won"))
        team_summary.append(
            {
                "team": team_name,
                "duels": len(team_duels),
                "duels_won": won,
                "duel_win_pct": round((won / len(team_duels) * 100), 1) if team_duels else 0.0,
                "transitions": len(team_transitions),
                "transitions_to_attack": sum(1 for row in team_transitions if row.get("led_to_attack")),
            }
        )

    return {
        "team": selected_team,
        "teams": teams,
        "duel_type": duel_type or "Total",
        "transition_type": transition_mode,
        "duels": duels,
        "transitions": transitions,
        "player_summary": player_summary,
        "team_summary": team_summary,
        "score_state": score_state or "all",
        "time_range": normalized_time_range,
        "game_state_options": _available_game_state_options(team_events),
        "time_range_options": _time_range_option(bounds_start, bounds_end, f"{bounds_start}'-{bounds_end}'"),
        "team_state_controls": _shot_team_state_controls(enriched_df),
        "full_time": full_time,
    }
