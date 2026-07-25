from __future__ import annotations

import json
import math
from typing import Any

import numpy as np
import pandas as pd

from app.services.epv_model import apply_epv_values
from app.services.xa_model import apply_pass_xa
from app.services.xpass_model import apply_pass_xpass


PITCH_LENGTH = 105.0
PITCH_WIDTH = 68.0
PERIOD_MAP = {"1H": "FirstHalf", "2H": "SecondHalf", "E1": "FirstPeriodOfExtraTime", "E2": "SecondPeriodOfExtraTime"}
POSITION_MAP = {
    "gk": "GK",
    "rb": "RB",
    "rcb": "RCB",
    "cb": "CB",
    "lcb": "LCB",
    "lb": "LB",
    "rwb": "RB",
    "lwb": "LB",
    "rdmf": "RDM",
    "dmf": "CDM",
    "ldmf": "LDM",
    "rcmf": "RCM",
    "cmf": "CM",
    "lcmf": "LCM",
    "rmf": "RM",
    "lmf": "LM",
    "ramf": "RAM",
    "amf": "CAM",
    "lamf": "LAM",
    "rw": "RW",
    "lw": "LW",
    "ss": "RF",
    "cf": "ST",
}
FORMATION_IDS = {
    "4-4-2": 2,
    "4-1-2-1-2": 3,
    "4-3-3": 4,
    "4-5-1": 5,
    "4-4-1-1": 6,
    "4-1-4-1": 7,
    "4-2-3-1": 8,
    "4-3-2-1": 9,
    "5-3-2": 10,
    "5-4-1": 11,
    "3-5-2": 12,
    "3-4-3": 13,
    "3-4-2-1": 17,
    "4-2-2-2": 15,
}
FORMATION_SLOT_BY_POSITION = {
    2: {"GK": 1, "RB": 2, "LB": 3, "RCM": 4, "CM": 4, "RCB": 5, "CB": 5, "LCB": 6, "RM": 7, "RW": 7, "LCM": 8, "ST": 9, "CF": 9, "RF": 10, "LF": 9, "SS": 10, "LM": 11, "LW": 11},
    4: {"GK": 1, "RB": 2, "LB": 3, "CM": 4, "RCB": 5, "CB": 5, "LCB": 6, "RCM": 7, "LCM": 8, "ST": 9, "RW": 10, "LW": 11},
    8: {"GK": 1, "RB": 2, "LB": 3, "RDM": 4, "CDM": 4, "RCB": 5, "LCB": 6, "RAM": 7, "RW": 7, "LDM": 8, "ST": 9, "CF": 9, "CAM": 10, "LAM": 11, "LW": 11},
}


class WyscoutImportError(ValueError):
    """Raised when an uploaded Wyscout payload cannot be normalized."""


def _get(data: dict[str, Any] | None, *path: str, default: Any = None) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return default if current is None else current


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _scale_x(value: Any) -> float:
    return round(max(0.0, min(100.0, _num(value))) * 1.05, 4)


def _scale_y(value: Any) -> float:
    return round(max(0.0, min(100.0, _num(value))) * 0.68, 4)


def _player_lookup(payload: dict[str, Any]) -> dict[int, dict[str, Any]]:
    players: dict[int, dict[str, Any]] = {}
    raw = payload.get("players")
    team_groups = raw.values() if isinstance(raw, dict) else raw if isinstance(raw, list) else []
    for group in team_groups:
        items = group if isinstance(group, list) else [group]
        for item in items:
            player = item.get("player") if isinstance(item, dict) else None
            if not isinstance(player, dict):
                continue
            player_id = int(_num(player.get("wyId"), -1))
            if player_id >= 0:
                players[player_id] = player
    return players


def _team_lookup(payload: dict[str, Any]) -> dict[int, dict[str, Any]]:
    teams: dict[int, dict[str, Any]] = {}
    for raw_id, item in (payload.get("teams") or {}).items():
        team = item.get("team") if isinstance(item, dict) else None
        if isinstance(team, dict):
            team_id = int(_num(team.get("wyId", raw_id), -1))
            if team_id >= 0:
                teams[team_id] = team
    return teams


def _home_away(payload: dict[str, Any], teams: dict[int, dict[str, Any]]) -> tuple[int | None, int | None, dict[int, str], str | None]:
    match = payload.get("match") or {}
    sides: dict[int, str] = {}
    scores: dict[int, int] = {}
    for raw_id, item in (match.get("teamsData") or {}).items():
        team_id = int(_num(item.get("teamId", raw_id), -1))
        if team_id < 0:
            continue
        sides[team_id] = "h" if item.get("side") == "home" else "a"
        scores[team_id] = int(_num(item.get("score"), 0))
    home_id = next((team_id for team_id, side in sides.items() if side == "h"), None)
    away_id = next((team_id for team_id, side in sides.items() if side == "a"), None)
    score = None
    if home_id is not None and away_id is not None:
        score = f"{scores.get(home_id, 0)}-{scores.get(away_id, 0)}"
    if home_id is None or away_id is None:
        ids = list(teams.keys())[:2]
        home_id = home_id or (ids[0] if ids else None)
        away_id = away_id or (ids[1] if len(ids) > 1 else None)
    return home_id, away_id, sides, score


def _player_name(player_id: Any, raw_player: dict[str, Any] | None, players: dict[int, dict[str, Any]]) -> str:
    if isinstance(raw_player, dict) and raw_player.get("name"):
        return str(raw_player["name"])
    resolved = players.get(int(_num(player_id, -1)), {})
    return str(resolved.get("shortName") or resolved.get("lastName") or "")


def _period(raw: str | None) -> str:
    return PERIOD_MAP.get(str(raw or ""), str(raw or ""))


def _position_group_code(position: str) -> int:
    pos = position.upper()
    if pos == "GK":
        return 1
    if pos in {"RB", "RCB", "CB", "LCB", "LB", "RWB", "LWB"}:
        return 2
    if pos in {"RDM", "CDM", "LDM", "RCM", "CM", "LCM", "RM", "LM", "RAM", "CAM", "LAM"}:
        return 3
    if pos in {"RW", "LW", "RF", "LF", "ST", "CF", "SS"}:
        return 4
    return 5


def _qualifier(name: str, value: Any = True) -> dict[str, Any]:
    return {"type": name, "value": value}


def _add_qualifier(qualifiers: list[dict[str, Any]], name: str, value: Any = True) -> None:
    if not any(item.get("type") == name for item in qualifiers):
        qualifiers.append(_qualifier(name, value))


def _event_type(event: dict[str, Any]) -> str:
    primary = _get(event, "type", "primary", default="")
    secondary = set(_get(event, "type", "secondary", default=[]) or [])
    shot = event.get("shot")
    if isinstance(shot, dict):
        if bool(shot.get("isGoal")) or "goal" in secondary:
            return "Goal"
        if shot.get("goalZone") in {"pl", "pr"} or "post" in secondary:
            return "ShotOnPost"
        if bool(shot.get("onTarget")):
            return "SavedShot"
        return "MissedShots"
    if primary in {"pass", "corner", "free_kick", "throw_in", "goal_kick"} and event.get("pass"):
        return "Pass"
    if event.get("carry") and primary in {"touch", "acceleration"}:
        return "Carry"
    if primary == "interception":
        return "Interception" if "recovery" not in secondary else "BallRecovery"
    if primary == "clearance":
        return "Clearance"
    if primary == "infraction":
        return "Foul"
    if primary == "duel":
        if event.get("aerialDuel") is not None or "aerial_duel" in secondary:
            return "Aerial"
        duel = event.get("groundDuel") or {}
        if "dribble" in secondary or duel.get("duelType") == "dribble":
            return "TakeOn"
        if duel.get("duelType") == "defensive_duel" or "defensive_duel" in secondary:
            return "Tackle"
        return "Challenge"
    if primary == "offside":
        return "OffsideGiven"
    return str(primary or "Touch").title().replace("_", "")


def _outcome(event: dict[str, Any], event_type: str) -> str:
    if event_type == "Pass":
        return "Successful" if bool(_get(event, "pass", "accurate", default=False)) else "Unsuccessful"
    if event_type == "Carry":
        return "Successful"
    if event_type == "Aerial":
        secondary = set(_get(event, "type", "secondary", default=[]) or [])
        return "Unsuccessful" if "loss" in secondary else "Successful"
    if event_type in {"TakeOn", "Tackle", "Challenge"}:
        duel = event.get("groundDuel") or {}
        success = any(bool(duel.get(key)) for key in ("keptPossession", "progressedWithBall", "stoppedProgress", "recoveredPossession"))
        return "Successful" if success else "Unsuccessful"
    if event_type == "Foul":
        return "Unsuccessful"
    return "Successful"


def _situation(event: dict[str, Any]) -> str:
    possession_types = set(_get(event, "possession", "types", default=[]) or [])
    primary = _get(event, "type", "primary", default="")
    if primary == "corner" or "corner" in possession_types:
        return "FromCorner"
    if primary == "free_kick" or "free_kick" in possession_types:
        return "DirectFreekick" if event.get("shot") else "SetPiece"
    if "set_piece_attack" in possession_types:
        return "SetPiece"
    return "OpenPlay"


def _base_event(
    event: dict[str, Any],
    *,
    teams: dict[int, dict[str, Any]],
    players: dict[int, dict[str, Any]],
    sides: dict[int, str],
    match_score: str | None,
    match_date: str | None,
) -> dict[str, Any]:
    event_type = _event_type(event)
    team_id = int(_num(_get(event, "team", "id"), -1))
    player_id = int(_num(_get(event, "player", "id"), 0))
    raw_pass = event.get("pass") if isinstance(event.get("pass"), dict) else {}
    raw_shot = event.get("shot") if isinstance(event.get("shot"), dict) else {}
    raw_carry = event.get("carry") if isinstance(event.get("carry"), dict) else {}
    end_location = raw_pass.get("endLocation") or raw_carry.get("endLocation") or event.get("location") or {}
    primary = _get(event, "type", "primary", default="")
    secondary = list(_get(event, "type", "secondary", default=[]) or [])
    qualifiers = [_qualifier(item) for item in secondary]
    if primary == "corner":
        qualifiers.append(_qualifier("CornerTaken"))
    if primary == "free_kick":
        qualifiers.append(_qualifier("FreeKickTaken"))
    if primary == "throw_in":
        qualifiers.append(_qualifier("ThrowIn"))
    if raw_pass.get("height") == "high":
        qualifiers.append(_qualifier("LongBall"))
    if "cross" in secondary:
        qualifiers.append(_qualifier("Cross"))
    if "key_pass" in secondary:
        qualifiers.append(_qualifier("KeyPass"))
    if "shot_assist" in secondary:
        qualifiers.append(_qualifier("ShotAssist"))
    if "assist" in secondary:
        qualifiers.append(_qualifier("IntentionalGoalAssist"))
    if "second_assist" in secondary:
        qualifiers.append(_qualifier("SecondAssist"))
    if "progressive_pass" in secondary:
        qualifiers.append(_qualifier("ProgressivePass"))
    if "opportunity" in secondary:
        qualifiers.append(_qualifier("BigChance"))
    body_part = str(raw_shot.get("bodyPart") or "")
    if body_part == "right_foot":
        qualifiers.append(_qualifier("RightFoot"))
    elif body_part == "left_foot":
        qualifiers.append(_qualifier("LeftFoot"))
    elif body_part == "head":
        qualifiers.append(_qualifier("Head"))

    row = {
        "eventId": event.get("id"),
        "matchId": event.get("matchId"),
        "minute": int(_num(event.get("minute"), 0)),
        "second": int(_num(event.get("second"), 0)),
        "expandedMinute": int(_num(event.get("minute"), 0)),
        "period": _period(event.get("matchPeriod")),
        "teamId": team_id if team_id >= 0 else None,
        "teamName": _get(event, "team", "name", default=teams.get(team_id, {}).get("name", "")),
        "h_a": sides.get(team_id),
        "playerId": player_id,
        "playerName": _player_name(player_id, event.get("player"), players),
        "position": str(_get(event, "player", "position", default="") or "").upper(),
        "type": event_type,
        "outcomeType": _outcome(event, event_type),
        "x": _scale_x(_get(event, "location", "x")),
        "y": _scale_y(_get(event, "location", "y")),
        "endX": _scale_x(end_location.get("x")),
        "endY": _scale_y(end_location.get("y")),
        "relatedEventId": event.get("relatedEventId"),
        "relatedPlayerId": _get(raw_pass, "recipient", "id", default=None),
        "receiver": _get(raw_pass, "recipient", "id", default=None),
        "receiverName": _get(raw_pass, "recipient", "name", default=None),
        "qualifiers": qualifiers,
        "satisfiedEventsTypes": secondary,
        "isShot": bool(raw_shot),
        "isGoal": bool(raw_shot.get("isGoal")) if raw_shot else False,
        "isTouch": event_type not in {"FormationSet", "FormationChange", "SubstitutionOn", "SubstitutionOff"},
        "xG": _num(raw_shot.get("xg"), 0.0) if raw_shot else 0.0,
        "xGOT": _num(raw_shot.get("postShotXg"), 0.0) if raw_shot else 0.0,
        "shotBodyType": body_part,
        "situation": _situation(event),
        "goalMouthY": 34.0,
        "goalMouthZ": 0.0,
        "shotBlocked": bool(raw_shot and not raw_shot.get("onTarget") and raw_shot.get("postShotXg") is None and "blocked" in secondary),
        "shotOnPost": event_type == "ShotOnPost",
        "shotOnTarget": bool(raw_shot.get("onTarget")) if raw_shot else False,
        "goalOwn": "own_goal" in secondary,
        "passCorner": primary == "corner",
        "passCornerAccurate": primary == "corner" and bool(raw_pass.get("accurate")),
        "passCornerInaccurate": primary == "corner" and not bool(raw_pass.get("accurate")),
        "passFreekick": primary == "free_kick",
        "passFreekickAccurate": primary == "free_kick" and bool(raw_pass.get("accurate")),
        "passFreekickInaccurate": primary == "free_kick" and not bool(raw_pass.get("accurate")),
        "throwIn": primary == "throw_in",
        "passAccurate": event_type == "Pass" and bool(raw_pass.get("accurate")),
        "passInaccurate": event_type == "Pass" and not bool(raw_pass.get("accurate")),
        "passCrossAccurate": "cross" in secondary and bool(raw_pass.get("accurate")),
        "passCrossInaccurate": "cross" in secondary and not bool(raw_pass.get("accurate")),
        "passLongBallAccurate": ("long_pass" in secondary or raw_pass.get("height") == "high") and bool(raw_pass.get("accurate")),
        "passLongBallInaccurate": ("long_pass" in secondary or raw_pass.get("height") == "high") and not bool(raw_pass.get("accurate")),
        "passThroughBallAccurate": "through_pass" in secondary and bool(raw_pass.get("accurate")),
        "passThroughBallInaccurate": "through_pass" in secondary and not bool(raw_pass.get("accurate")),
        "passForward": "forward_pass" in secondary,
        "passBack": "back_pass" in secondary,
        "passKey": "key_pass" in secondary or "shot_assist" in secondary,
        "assist": "assist" in secondary,
        "intentionalAssist": "assist" in secondary,
        "bigChanceCreated": "key_pass" in secondary or "shot_assist" in secondary or "assist" in secondary,
        "bigChanceMissed": bool(raw_shot) and "opportunity" in secondary and not raw_shot.get("isGoal"),
        "bigChanceScored": bool(raw_shot) and "opportunity" in secondary and raw_shot.get("isGoal"),
        "interceptionWon": event_type == "Interception",
        "interceptionAll": event_type == "Interception",
        "ballRecovery": event_type == "BallRecovery",
        "clearanceTotal": event_type == "Clearance",
        "clearanceEffective": event_type == "Clearance",
        "tackleWon": event_type == "Tackle" and _outcome(event, event_type) == "Successful",
        "tackleLost": event_type == "Tackle" and _outcome(event, event_type) != "Successful",
        "duelAerialWon": event_type == "Aerial" and _outcome(event, event_type) == "Successful",
        "duelAerialLost": event_type == "Aerial" and _outcome(event, event_type) != "Successful",
        "offensiveDuel": _get(event, "groundDuel", "duelType", default="") in {"offensive_duel", "dribble"},
        "defensiveDuel": _get(event, "groundDuel", "duelType", default="") == "defensive_duel",
        "turnover": event_type in {"TakeOn", "Pass"} and _outcome(event, event_type) == "Unsuccessful",
        "possession_id": _get(event, "possession", "id", default=None),
        "possession_duration": _get(event, "possession", "duration", default=None),
        "startDate": match_date,
        "score": match_score,
        "league": "wyscout-import",
        "season": None,
        "source_provider": "wyscout",
    }
    return row


def _enrich_related_events(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "eventId" not in df.columns:
        return df

    events = df.copy()
    by_event_id = {row.get("eventId"): row for _, row in events.iterrows()}
    shot_ids = set(events.loc[events["isShot"].fillna(False).astype(bool), "eventId"].dropna().tolist())

    for idx, row in events.iterrows():
        event_type = str(row.get("type", ""))
        if event_type not in {"Pass", "Aerial", "TakeOn", "Challenge", "Carry"}:
            continue

        satisfied = str(row.get("satisfiedEventsTypes", ""))
        qualifiers = row.get("qualifiers")
        if not isinstance(qualifiers, list):
            qualifiers = []

        related_id = row.get("relatedEventId")
        related = by_event_id.get(related_id)
        related_is_shot = related_id in shot_ids or (related is not None and bool(related.get("isShot")))
        related_is_goal = related is not None and bool(related.get("isGoal"))

        is_shot_assist = "shot_assist" in satisfied or related_is_shot
        is_key_pass = "key_pass" in satisfied or is_shot_assist
        is_goal_assist = "assist" in satisfied or (related_is_shot and related_is_goal)
        is_second_assist = "second_assist" in satisfied

        if is_shot_assist:
            _add_qualifier(qualifiers, "ShotAssist")
        if is_key_pass:
            _add_qualifier(qualifiers, "KeyPass")
        if is_goal_assist:
            _add_qualifier(qualifiers, "IntentionalGoalAssist")
        if is_second_assist:
            _add_qualifier(qualifiers, "SecondAssist")
        if is_key_pass or is_goal_assist:
            _add_qualifier(qualifiers, "BigChanceCreated")

        events.at[idx, "qualifiers"] = qualifiers
        events.at[idx, "passKey"] = bool(row.get("passKey")) or is_key_pass
        events.at[idx, "assist"] = bool(row.get("assist")) or is_goal_assist
        events.at[idx, "intentionalAssist"] = bool(row.get("intentionalAssist")) or is_goal_assist
        events.at[idx, "bigChanceCreated"] = bool(row.get("bigChanceCreated")) or is_key_pass or is_goal_assist
        if is_shot_assist and related is not None and "xG" in related.index:
            events.at[idx, "xa_target_event_id"] = related.get("eventId")
            events.at[idx, "xa_target_xg"] = _num(related.get("xG"), 0.0)

    return events


def _synthetic_lineup_rows(
    payload: dict[str, Any],
    *,
    teams: dict[int, dict[str, Any]],
    players: dict[int, dict[str, Any]],
    sides: dict[int, str],
    match_id: Any,
    match_score: str | None,
    match_date: str | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    base_event_id = 900000000000
    for team_id_raw, periods in (payload.get("formations") or {}).items():
        team_id = int(_num(team_id_raw, -1))
        if not isinstance(periods, dict):
            continue
        for period_key, starts in periods.items():
            for start_sec_raw, schemes in (starts or {}).items():
                start_sec = int(_num(start_sec_raw, 0))
                minute = start_sec // 60 if period_key != "2H" else 45 + start_sec // 60
                second = start_sec % 60
                for scheme, formation in (schemes or {}).items():
                    players_list = []
                    player_items: list[tuple[int, str, int]] = []
                    formation_id = FORMATION_IDS.get(str(scheme), 0)
                    for player_item in formation.get("players", []):
                        if not isinstance(player_item, dict):
                            continue
                        raw_player = next(iter(player_item.values()), {})
                        pid = int(_num(raw_player.get("playerId"), 0))
                        pos = POSITION_MAP.get(str(raw_player.get("position", "")).lower(), str(raw_player.get("position", "")).upper())
                        slot = FORMATION_SLOT_BY_POSITION.get(formation_id, {}).get(pos, len(player_items) + 1)
                        player_items.append((pid, pos, slot))
                        players_list.append({"playerId": pid, "position": pos, "isFirstEleven": minute == 0})
                    used_slots: set[int] = set()
                    involved_player_ids = []
                    formation_slots = []
                    player_position_codes = []
                    for fallback_slot, (pid, pos, preferred_slot) in enumerate(player_items, start=1):
                        if 1 <= preferred_slot <= 11 and preferred_slot not in used_slots:
                            slot = preferred_slot
                        else:
                            slot = next((candidate for candidate in range(1, 12) if candidate not in used_slots), fallback_slot)
                        used_slots.add(slot)
                        if pid:
                            involved_player_ids.append(str(pid))
                            formation_slots.append(str(slot))
                            player_position_codes.append(str(_position_group_code(pos)))
                    rows.append({
                        "eventId": base_event_id + len(rows),
                        "matchId": match_id,
                        "minute": int(minute),
                        "second": int(second),
                        "expandedMinute": int(minute),
                        "period": _period(period_key),
                        "teamId": team_id,
                        "teamName": teams.get(team_id, {}).get("name", str(team_id)),
                        "h_a": sides.get(team_id),
                        "playerId": 0,
                        "playerName": "",
                        "type": "FormationSet",
                        "outcomeType": "Successful",
                        "x": 0.0,
                        "y": 0.0,
                        "endX": 0.0,
                        "endY": 0.0,
                        "qualifiers": [
                            _qualifier("Formation", scheme),
                            _qualifier("TeamFormation", formation_id),
                            _qualifier("InvolvedPlayers", ",".join(involved_player_ids)),
                            _qualifier("TeamPlayerFormation", ",".join(formation_slots)),
                            _qualifier("PlayerPosition", ",".join(player_position_codes)),
                            _qualifier("Players", json.dumps(players_list)),
                        ],
                        "satisfiedEventsTypes": [],
                        "isShot": False,
                        "isGoal": False,
                        "isTouch": False,
                        "isFirstEleven": False,
                        "formation": scheme,
                        "formation_players": json.dumps(players_list),
                        "xG": 0.0,
                        "xGOT": 0.0,
                        "startDate": match_date,
                        "score": match_score,
                        "league": "wyscout-import",
                        "season": None,
                        "source_provider": "wyscout",
                    })
    for team_id_raw, periods in (payload.get("substitutions") or {}).items():
        team_id = int(_num(team_id_raw, -1))
        for period_key, starts in (periods or {}).items():
            for start_sec_raw, sub_group in (starts or {}).items():
                start_sec = int(_num(start_sec_raw, 0))
                minute = start_sec // 60 if period_key != "2H" else 45 + start_sec // 60
                second = start_sec % 60
                out_players = sub_group.get("out", []) or []
                in_players = sub_group.get("in", []) or []
                max_len = max(len(out_players), len(in_players))
                for pair_index in range(max_len):
                    off_event_id = base_event_id + len(rows)
                    if pair_index < len(out_players):
                        player = out_players[pair_index]
                        pid = int(_num(player.get("playerId"), 0))
                        rows.append({
                            "eventId": off_event_id,
                            "matchId": match_id,
                            "minute": int(minute),
                            "second": int(second),
                            "expandedMinute": int(minute),
                            "period": _period(period_key),
                            "teamId": team_id,
                            "teamName": teams.get(team_id, {}).get("name", str(team_id)),
                            "h_a": sides.get(team_id),
                            "playerId": pid,
                            "playerName": _player_name(pid, None, players),
                            "type": "SubstitutionOff",
                            "outcomeType": "Successful",
                            "x": 0.0,
                            "y": 0.0,
                            "endX": 0.0,
                            "endY": 0.0,
                            "qualifiers": [],
                            "satisfiedEventsTypes": [],
                            "isShot": False,
                            "isGoal": False,
                            "isTouch": False,
                            "xG": 0.0,
                            "xGOT": 0.0,
                            "startDate": match_date,
                            "score": match_score,
                            "league": "wyscout-import",
                            "season": None,
                            "source_provider": "wyscout",
                        })
                    if pair_index < len(in_players):
                        player = in_players[pair_index]
                        pid = int(_num(player.get("playerId"), 0))
                        rows.append({
                            "eventId": base_event_id + len(rows),
                            "matchId": match_id,
                            "minute": int(minute),
                            "second": int(second),
                            "expandedMinute": int(minute),
                            "period": _period(period_key),
                            "teamId": team_id,
                            "teamName": teams.get(team_id, {}).get("name", str(team_id)),
                            "h_a": sides.get(team_id),
                            "playerId": pid,
                            "playerName": _player_name(pid, None, players),
                            "type": "SubstitutionOn",
                            "outcomeType": "Successful",
                            "x": 0.0,
                            "y": 0.0,
                            "endX": 0.0,
                            "endY": 0.0,
                            "qualifiers": [_qualifier("RelatedEventId", off_event_id)] if pair_index < len(out_players) else [],
                            "satisfiedEventsTypes": [],
                            "isShot": False,
                            "isGoal": False,
                            "isTouch": False,
                            "xG": 0.0,
                            "xGOT": 0.0,
                            "startDate": match_date,
                            "score": match_score,
                            "league": "wyscout-import",
                            "season": None,
                            "source_provider": "wyscout",
                        })
    return rows


def _add_derived_columns(df: pd.DataFrame) -> pd.DataFrame:
    events = df.copy()
    events = events.sort_values(["minute", "second", "eventId"], kind="stable").reset_index(drop=True)
    events.insert(0, "index", range(1, len(events) + 1))
    events["cumulative_mins"] = pd.to_numeric(events["minute"], errors="coerce").fillna(0) + (
        pd.to_numeric(events["second"], errors="coerce").fillna(0) / 60.0
    )
    events["qualifiers"] = events["qualifiers"].apply(lambda value: repr(value) if isinstance(value, list) else str(value or ""))
    events["satisfiedEventsTypes"] = events["satisfiedEventsTypes"].apply(
        lambda value: json.dumps(value, ensure_ascii=False) if isinstance(value, list) else str(value or "")
    )
    for column in ("xT", "EPV", "xA", "xPass"):
        if column not in events.columns:
            events[column] = np.nan
    events["prog_pass"] = np.where(
        events["type"].eq("Pass"),
        np.sqrt((PITCH_LENGTH - events["x"]) ** 2 + (34.0 - events["y"]) ** 2)
        - np.sqrt((PITCH_LENGTH - events["endX"]) ** 2 + (34.0 - events["endY"]) ** 2),
        0.0,
    )
    events["prog_carry"] = np.where(
        events["type"].eq("Carry"),
        np.sqrt((PITCH_LENGTH - events["x"]) ** 2 + (34.0 - events["y"]) ** 2)
        - np.sqrt((PITCH_LENGTH - events["endX"]) ** 2 + (34.0 - events["endY"]) ** 2),
        0.0,
    )
    events["pass_or_carry_angle"] = np.degrees(np.arctan2(events["endY"] - events["y"], events["endX"] - events["x"]))
    return events


def _simple_xt_value(x: pd.Series, y: pd.Series) -> pd.Series:
    progress = (pd.to_numeric(x, errors="coerce").fillna(0.0) / PITCH_LENGTH).clip(0.0, 1.0)
    centrality = (1.0 - (pd.to_numeric(y, errors="coerce").fillna(34.0) - 34.0).abs() / 34.0).clip(0.0, 1.0)
    return (progress ** 1.7) * (0.72 + 0.28 * centrality)


def _apply_xt_fallback(df: pd.DataFrame) -> pd.DataFrame:
    events = df.copy()
    if "xT" not in events.columns:
        events["xT"] = np.nan
    current = pd.to_numeric(events["xT"], errors="coerce")
    needs_xt = current.isna() | current.eq(0)
    action = events["type"].astype(str).isin(["Pass", "Carry"])
    successful = events["outcomeType"].astype(str).str.lower().eq("successful")
    mask = needs_xt & action & successful
    if not bool(mask.any()):
        events["xT"] = current.fillna(0.0)
        return events
    start_value = _simple_xt_value(events.loc[mask, "x"], events.loc[mask, "y"])
    end_value = _simple_xt_value(events.loc[mask, "endX"], events.loc[mask, "endY"])
    events.loc[mask, "xT"] = (end_value - start_value).clip(lower=-0.25, upper=0.5)
    events["xT"] = pd.to_numeric(events["xT"], errors="coerce").fillna(0.0)
    return events


def _apply_optional_models(df: pd.DataFrame) -> pd.DataFrame:
    events = df.copy()
    for fn in (apply_epv_values, apply_pass_xa, apply_pass_xpass):
        try:
            events = fn(events)
        except Exception:
            continue
    events = _apply_xt_fallback(events)
    for column in ("xT", "EPV", "xA", "xPass"):
        if column in events.columns:
            events[column] = pd.to_numeric(events[column], errors="coerce").fillna(0.0)
    return events


def normalize_wyscout_match(payload: dict[str, Any]) -> pd.DataFrame:
    if not isinstance(payload, dict):
        raise WyscoutImportError("Wyscout upload must be a JSON object.")
    events = payload.get("events")
    if not isinstance(events, list) or not events:
        raise WyscoutImportError("Wyscout upload must include a non-empty events array.")
    if not isinstance(payload.get("match"), dict):
        raise WyscoutImportError("Wyscout upload must include match metadata.")

    teams = _team_lookup(payload)
    players = _player_lookup(payload)
    _home_id, _away_id, sides, match_score = _home_away(payload, teams)
    match = payload["match"]
    match_date = match.get("dateutc") or match.get("date")
    rows = [
        _base_event(
            event,
            teams=teams,
            players=players,
            sides=sides,
            match_score=match_score,
            match_date=match_date,
        )
        for event in events
        if isinstance(event, dict)
    ]
    rows.extend(
        _synthetic_lineup_rows(
            payload,
            teams=teams,
            players=players,
            sides=sides,
            match_id=match.get("wyId") or (events[0].get("matchId") if events else None),
            match_score=match_score,
            match_date=match_date,
        )
    )
    df = _add_derived_columns(_enrich_related_events(pd.DataFrame(rows)))
    return _apply_optional_models(df)
