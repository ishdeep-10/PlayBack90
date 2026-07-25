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
FORMATION_IDS = {
    "442": 2,
    "41212": 3,
    "433": 4,
    "451": 5,
    "4411": 6,
    "4141": 7,
    "4231": 8,
    "4321": 9,
    "532": 10,
    "541": 11,
    "352": 12,
    "343": 13,
    "4222": 15,
    "3421": 17,
}

FORMATION_SLOT_POSITIONS = {
    2: {1: "GK", 2: "RB", 3: "LB", 4: "RCM", 5: "RCB", 6: "LCB", 7: "RM", 8: "LCM", 9: "LF", 10: "RF", 11: "LM"},
    3: {1: "GK", 2: "RB", 3: "LB", 4: "CDM", 5: "RCB", 6: "LCB", 7: "RM", 8: "CAM", 9: "LF", 10: "RF", 11: "LM"},
    4: {1: "GK", 2: "RB", 3: "LB", 4: "CM", 5: "RCB", 6: "LCB", 7: "RCM", 8: "LCM", 9: "ST", 10: "RW", 11: "LW"},
    5: {1: "GK", 2: "RB", 3: "LB", 4: "RCM", 5: "RCB", 6: "LCB", 7: "RM", 8: "LCM", 9: "ST", 10: "CM", 11: "LM"},
    6: {1: "GK", 2: "RB", 3: "LB", 4: "RCM", 5: "RCB", 6: "LCB", 7: "RM", 8: "LCM", 9: "ST", 10: "CAM", 11: "LM"},
    7: {1: "GK", 2: "RB", 3: "LB", 4: "CDM", 5: "RCB", 6: "LCB", 7: "RM", 8: "RCM", 9: "ST", 10: "LCM", 11: "LM"},
    8: {1: "GK", 2: "RB", 3: "LB", 4: "RDM", 5: "RCB", 6: "LCB", 7: "RAM", 8: "LDM", 9: "ST", 10: "CAM", 11: "LAM"},
    9: {1: "GK", 2: "RB", 3: "LB", 4: "CM", 5: "RCB", 6: "LCB", 7: "LCM", 8: "RCM", 9: "ST", 10: "RAM", 11: "LAM"},
    10: {1: "GK", 2: "RB", 3: "LB", 4: "LCB", 5: "CB", 6: "RCB", 7: "RCM", 8: "CM", 9: "LF", 10: "RF", 11: "LCM"},
    11: {1: "GK", 2: "RB", 3: "LB", 4: "LCB", 5: "CB", 6: "RCB", 7: "RM", 8: "RCM", 9: "ST", 10: "LCM", 11: "LM"},
    12: {1: "GK", 2: "RM", 3: "LM", 4: "LCB", 5: "CB", 6: "RCB", 7: "RCM", 8: "LCM", 9: "LF", 10: "RF", 11: "CM"},
    13: {1: "GK", 2: "RM", 3: "LM", 4: "LCB", 5: "CB", 6: "RCB", 7: "RCM", 8: "LCM", 9: "ST", 10: "RW", 11: "LW"},
    15: {1: "GK", 2: "RB", 3: "LB", 4: "RDM", 5: "RCB", 6: "LCB", 7: "RCM", 8: "LDM", 9: "LF", 10: "RF", 11: "LCM"},
    17: {1: "GK", 2: "RM", 3: "LM", 4: "LCB", 5: "CB", 6: "RCB", 7: "RCM", 8: "LCM", 9: "ST", 10: "RF", 11: "LF"},
}


class StatsBombImportError(ValueError):
    """Raised when an uploaded StatsBomb payload cannot be normalized."""


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


def _location(value: Any) -> tuple[float, float]:
    if isinstance(value, list) and len(value) >= 2:
        x = _num(value[0]) * (PITCH_LENGTH / 120.0)
        y = PITCH_WIDTH - (_num(value[1]) * (PITCH_WIDTH / 80.0))
        return round(x, 4), round(y, 4)
    return 0.0, 0.0


def _period(value: Any) -> str:
    period = int(_num(value, 0))
    if period == 1:
        return "FirstHalf"
    if period == 2:
        return "SecondHalf"
    if period == 3:
        return "FirstPeriodOfExtraTime"
    if period == 4:
        return "SecondPeriodOfExtraTime"
    return str(value or "")


def _qualifier(name: str, value: Any = True) -> dict[str, Any]:
    return {"type": name, "value": value}


def _add_qualifier(qualifiers: list[dict[str, Any]], name: str, value: Any = True) -> None:
    if not any(item.get("type") == name for item in qualifiers):
        qualifiers.append(_qualifier(name, value))


def _position_group_code(position_name: str) -> int:
    value = position_name.lower()
    if "goalkeeper" in value:
        return 1
    if "back" in value:
        return 2
    if "midfield" in value:
        return 3
    if "wing" in value or "forward" in value or "striker" in value:
        return 4
    return 5


def _position_code(position_name: str) -> str:
    value = " ".join(position_name.lower().replace("-", " ").split())
    mapping = {
        "goalkeeper": "GK",
        "right back": "RB",
        "right wing back": "RB",
        "left back": "LB",
        "left wing back": "LB",
        "right center back": "RCB",
        "right centre back": "RCB",
        "center back": "CB",
        "centre back": "CB",
        "left center back": "LCB",
        "left centre back": "LCB",
        "right defensive midfield": "RDM",
        "right center defensive midfield": "RDM",
        "center defensive midfield": "CDM",
        "centre defensive midfield": "CDM",
        "left defensive midfield": "LDM",
        "left center defensive midfield": "LDM",
        "right center midfield": "RCM",
        "right centre midfield": "RCM",
        "center midfield": "CM",
        "centre midfield": "CM",
        "left center midfield": "LCM",
        "left centre midfield": "LCM",
        "right midfield": "RM",
        "left midfield": "LM",
        "right attacking midfield": "RAM",
        "right center attacking midfield": "RAM",
        "center attacking midfield": "CAM",
        "centre attacking midfield": "CAM",
        "left attacking midfield": "LAM",
        "left center attacking midfield": "LAM",
        "right wing": "RW",
        "left wing": "LW",
        "right center forward": "RF",
        "right centre forward": "RF",
        "center forward": "ST",
        "centre forward": "ST",
        "striker": "ST",
        "left center forward": "LF",
        "left centre forward": "LF",
    }
    return mapping.get(value, "UNK")


def _extract_payload(payload: Any) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    if isinstance(payload, list):
        events = payload
        return [item for item in events if isinstance(item, dict)], {}, []
    if not isinstance(payload, dict):
        raise StatsBombImportError("StatsBomb upload must be a JSON object or events array.")

    events = payload.get("events") or payload.get("event_data")
    if not isinstance(events, list):
        raise StatsBombImportError("StatsBomb upload must include an events array.")
    match = payload.get("match") if isinstance(payload.get("match"), dict) else {}
    lineups = payload.get("lineups") if isinstance(payload.get("lineups"), list) else []
    return [item for item in events if isinstance(item, dict)], match, [item for item in lineups if isinstance(item, dict)]


def _match_metadata(events: list[dict[str, Any]], match: dict[str, Any]) -> dict[str, Any]:
    home_team = _get(match, "home_team", "home_team_name")
    away_team = _get(match, "away_team", "away_team_name")
    home_id = _get(match, "home_team", "home_team_id")
    away_id = _get(match, "away_team", "away_team_id")
    if not home_team or not away_team:
        teams: list[dict[str, Any]] = []
        for event in events:
            team = event.get("team")
            if not isinstance(team, dict) or not team.get("name"):
                continue
            if not any(existing.get("id") == team.get("id") for existing in teams):
                teams.append(team)
            if len(teams) >= 2:
                break
        home_team = home_team or (teams[0].get("name") if teams else None)
        away_team = away_team or (teams[1].get("name") if len(teams) > 1 else None)
        home_id = home_id or (teams[0].get("id") if teams else None)
        away_id = away_id or (teams[1].get("id") if len(teams) > 1 else None)

    match_id = match.get("match_id") or next((event.get("match_id") for event in events if event.get("match_id")), None)
    match_id = match_id or next((event.get("id") for event in events if event.get("id")), "statsbomb-import")
    score = None
    if "home_score" in match and "away_score" in match:
        score = f"{int(_num(match.get('home_score'), 0))}-{int(_num(match.get('away_score'), 0))}"
    league = _get(match, "competition", "competition_name", default="statsbomb-import")
    season = _get(match, "season", "season_name")
    return {
        "match_id": match_id,
        "home_team": str(home_team or "Home"),
        "away_team": str(away_team or "Away"),
        "home_id": int(_num(home_id, -1)),
        "away_id": int(_num(away_id, -1)),
        "score": score,
        "league": str(league or "statsbomb-import"),
        "season": str(season) if season is not None else None,
        "match_date": match.get("match_date"),
    }


def _side(team_id: Any, team_name: str, meta: dict[str, Any]) -> str | None:
    numeric_id = int(_num(team_id, -999999))
    if numeric_id == int(meta.get("home_id", -1)) or team_name == meta.get("home_team"):
        return "h"
    if numeric_id == int(meta.get("away_id", -1)) or team_name == meta.get("away_team"):
        return "a"
    return None


def _event_type(event: dict[str, Any]) -> str:
    raw_type = str(_get(event, "type", "name", default=""))
    if raw_type == "Pass":
        return "Pass"
    if raw_type == "Carry":
        return "Carry"
    if raw_type == "Shot":
        outcome = str(_get(event, "shot", "outcome", "name", default=""))
        if outcome == "Goal":
            return "Goal"
        if outcome in {"Saved", "Saved to Post", "Saved Off Target"}:
            return "SavedShot"
        if outcome in {"Post", "Wayward"}:
            return "ShotOnPost" if outcome == "Post" else "MissedShots"
        return "MissedShots"
    if raw_type == "Interception":
        return "Interception"
    if raw_type == "Ball Recovery":
        return "BallRecovery"
    if raw_type == "Clearance":
        return "Clearance"
    if raw_type == "Dribble":
        return "TakeOn"
    if raw_type == "Duel":
        duel_type = str(_get(event, "duel", "type", "name", default=""))
        if "Aerial" in duel_type:
            return "Aerial"
        return "Tackle"
    if raw_type == "Foul Committed":
        return "Foul"
    if raw_type == "Substitution":
        return "SubstitutionOff"
    if raw_type == "Starting XI":
        return "FormationSet"
    if raw_type in {"Half Start", "Half End"}:
        return "Start" if raw_type == "Half Start" else "End"
    return raw_type.replace(" ", "")


def _outcome(event: dict[str, Any], event_type: str) -> str:
    if event_type == "Pass":
        return "Unsuccessful" if _get(event, "pass", "outcome", "name") else "Successful"
    if event_type == "TakeOn":
        return "Unsuccessful" if _get(event, "dribble", "outcome", "name") == "Incomplete" else "Successful"
    if event_type in {"Tackle", "Aerial"}:
        outcome = str(_get(event, "duel", "outcome", "name", default=""))
        return "Successful" if outcome in {"Won", "Success In Play", "Success Out"} else "Unsuccessful"
    if event_type == "Interception":
        outcome = str(_get(event, "interception", "outcome", "name", default=""))
        return "Unsuccessful" if "Lost" in outcome else "Successful"
    if event_type == "Foul":
        return "Unsuccessful"
    return "Successful"


def _situation(event: dict[str, Any]) -> str:
    shot_type = str(_get(event, "shot", "type", "name", default=""))
    pass_type = str(_get(event, "pass", "type", "name", default=""))
    play_pattern = str(_get(event, "play_pattern", "name", default=""))
    if "Corner" in {shot_type, pass_type} or play_pattern == "From Corner":
        return "FromCorner"
    if "Free Kick" in {shot_type, pass_type} or play_pattern == "From Free Kick":
        return "DirectFreekick" if event.get("shot") else "SetPiece"
    if play_pattern.startswith("From "):
        return "SetPiece"
    return "OpenPlay"


def _base_columns(event: dict[str, Any], meta: dict[str, Any], event_type: str, event_id: int) -> dict[str, Any]:
    team_id = _get(event, "team", "id")
    team_name = str(_get(event, "team", "name", default=""))
    player_id = int(_num(_get(event, "player", "id"), 0))
    start_x, start_y = _location(event.get("location"))
    end_location = _get(event, "pass", "end_location") or _get(event, "carry", "end_location") or event.get("location")
    end_x, end_y = _location(end_location)
    raw_pass = event.get("pass") if isinstance(event.get("pass"), dict) else {}
    raw_shot = event.get("shot") if isinstance(event.get("shot"), dict) else {}
    body_part = str(_get(raw_shot, "body_part", "name", default=""))
    pass_type = str(_get(raw_pass, "type", "name", default=""))
    pass_height = str(_get(raw_pass, "height", "name", default=""))
    shot_outcome = str(_get(raw_shot, "outcome", "name", default=""))
    qualifiers: list[dict[str, Any]] = []

    if pass_type == "Corner":
        qualifiers.append(_qualifier("CornerTaken"))
    if "Free Kick" in pass_type:
        qualifiers.append(_qualifier("FreeKickTaken"))
    if pass_type == "Throw-in":
        qualifiers.append(_qualifier("ThrowIn"))
    if bool(raw_pass.get("cross")):
        qualifiers.append(_qualifier("Cross"))
    if bool(raw_pass.get("through_ball")):
        qualifiers.append(_qualifier("Throughball"))
    if pass_height == "High Pass":
        qualifiers.append(_qualifier("LongBall"))
    if raw_pass.get("shot_assist"):
        qualifiers.append(_qualifier("ShotAssist"))
        qualifiers.append(_qualifier("KeyPass"))
    if raw_pass.get("goal_assist"):
        qualifiers.append(_qualifier("IntentionalGoalAssist"))
    if body_part == "Right Foot":
        qualifiers.append(_qualifier("RightFoot"))
    elif body_part == "Left Foot":
        qualifiers.append(_qualifier("LeftFoot"))
    elif body_part == "Head":
        qualifiers.append(_qualifier("Head"))

    return {
        "eventId": event_id,
        "statsbombEventId": event.get("id"),
        "matchId": event.get("match_id") or meta["match_id"],
        "minute": int(_num(event.get("minute"), 0)),
        "second": int(_num(event.get("second"), 0)),
        "expandedMinute": int(_num(event.get("minute"), 0)),
        "period": _period(event.get("period")),
        "teamId": int(_num(team_id, -1)) if team_id is not None else None,
        "teamName": team_name,
        "h_a": _side(team_id, team_name, meta),
        "playerId": player_id,
        "playerName": str(_get(event, "player", "name", default="")),
        "position": str(_get(event, "position", "name", default="")),
        "type": event_type,
        "outcomeType": _outcome(event, event_type),
        "x": start_x,
        "y": start_y,
        "endX": end_x,
        "endY": end_y,
        "relatedEventId": (event.get("related_events") or [None])[0] if isinstance(event.get("related_events"), list) else None,
        "relatedPlayerId": _get(raw_pass, "recipient", "id", default=None),
        "receiver": _get(raw_pass, "recipient", "id", default=None),
        "receiverName": _get(raw_pass, "recipient", "name", default=None),
        "qualifiers": qualifiers,
        "satisfiedEventsTypes": [],
        "isShot": bool(raw_shot),
        "isGoal": shot_outcome == "Goal",
        "isTouch": event_type not in {"FormationSet", "FormationChange", "SubstitutionOn", "SubstitutionOff", "Start", "End"},
        "xG": _num(raw_shot.get("statsbomb_xg"), 0.0) if raw_shot else 0.0,
        "xGOT": 0.0,
        "shotBodyType": body_part,
        "situation": _situation(event),
        "goalMouthY": 34.0,
        "goalMouthZ": 0.0,
        "shotBlocked": shot_outcome == "Blocked",
        "shotOnPost": shot_outcome == "Post",
        "shotOnTarget": shot_outcome in {"Goal", "Saved", "Saved to Post"},
        "goalOwn": False,
        "passCorner": pass_type == "Corner",
        "passCornerAccurate": pass_type == "Corner" and _outcome(event, event_type) == "Successful",
        "passCornerInaccurate": pass_type == "Corner" and _outcome(event, event_type) != "Successful",
        "passFreekick": "Free Kick" in pass_type,
        "passFreekickAccurate": "Free Kick" in pass_type and _outcome(event, event_type) == "Successful",
        "passFreekickInaccurate": "Free Kick" in pass_type and _outcome(event, event_type) != "Successful",
        "throwIn": pass_type == "Throw-in",
        "passAccurate": event_type == "Pass" and _outcome(event, event_type) == "Successful",
        "passInaccurate": event_type == "Pass" and _outcome(event, event_type) != "Successful",
        "passCrossAccurate": bool(raw_pass.get("cross")) and _outcome(event, event_type) == "Successful",
        "passCrossInaccurate": bool(raw_pass.get("cross")) and _outcome(event, event_type) != "Successful",
        "passLongBallAccurate": pass_height == "High Pass" and _outcome(event, event_type) == "Successful",
        "passLongBallInaccurate": pass_height == "High Pass" and _outcome(event, event_type) != "Successful",
        "passThroughBallAccurate": bool(raw_pass.get("through_ball")) and _outcome(event, event_type) == "Successful",
        "passThroughBallInaccurate": bool(raw_pass.get("through_ball")) and _outcome(event, event_type) != "Successful",
        "passForward": end_x > start_x + 5,
        "passBack": end_x < start_x - 5,
        "passKey": bool(raw_pass.get("shot_assist") or raw_pass.get("goal_assist")),
        "assist": bool(raw_pass.get("goal_assist")),
        "intentionalAssist": bool(raw_pass.get("goal_assist")),
        "bigChanceCreated": bool(raw_pass.get("shot_assist") or raw_pass.get("goal_assist")),
        "bigChanceMissed": bool(raw_shot) and bool(raw_shot.get("one_on_one")) and shot_outcome != "Goal",
        "bigChanceScored": bool(raw_shot) and bool(raw_shot.get("one_on_one")) and shot_outcome == "Goal",
        "interceptionWon": event_type == "Interception" and _outcome(event, event_type) == "Successful",
        "interceptionAll": event_type == "Interception",
        "ballRecovery": event_type == "BallRecovery",
        "clearanceTotal": event_type == "Clearance",
        "clearanceEffective": event_type == "Clearance",
        "tackleWon": event_type == "Tackle" and _outcome(event, event_type) == "Successful",
        "tackleLost": event_type == "Tackle" and _outcome(event, event_type) != "Successful",
        "duelAerialWon": event_type == "Aerial" and _outcome(event, event_type) == "Successful",
        "duelAerialLost": event_type == "Aerial" and _outcome(event, event_type) != "Successful",
        "offensiveDuel": event_type == "TakeOn",
        "defensiveDuel": event_type in {"Tackle", "Aerial"},
        "turnover": event_type in {"Pass", "TakeOn"} and _outcome(event, event_type) == "Unsuccessful",
        "possession_id": event.get("possession"),
        "possession_duration": event.get("duration"),
        "startDate": meta.get("match_date"),
        "score": meta.get("score"),
        "league": meta.get("league") or "statsbomb-import",
        "season": meta.get("season"),
        "source_provider": "statsbomb",
    }


def _formation_string(value: Any) -> str:
    raw = str(value or "")
    if raw.isdigit() and 3 <= len(raw) <= 5:
        return "-".join(raw)
    return raw


def _formation_slot(position_name: str, formation_id: int, fallback_slot: int, used_slots: set[int]) -> int:
    code = _position_code(position_name)
    slots = FORMATION_SLOT_POSITIONS.get(formation_id, {})
    for slot, slot_code in slots.items():
        if slot_code == code and slot not in used_slots:
            return slot
    for slot in range(1, 12):
        if slot not in used_slots:
            return slot
    return fallback_slot


def _lineup_rows_from_events(events: list[dict[str, Any]], meta: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    base_event_id = 800000000000
    for event in events:
        if str(_get(event, "type", "name", default="")) != "Starting XI":
            continue
        team_id = _get(event, "team", "id")
        team_name = str(_get(event, "team", "name", default=""))
        tactics = event.get("tactics") if isinstance(event.get("tactics"), dict) else {}
        formation_raw = tactics.get("formation")
        formation = _formation_string(formation_raw)
        formation_id = FORMATION_IDS.get(str(formation_raw), 0)
        lineup = tactics.get("lineup") if isinstance(tactics.get("lineup"), list) else []
        players = []
        player_ids: list[str] = []
        slots: list[str] = []
        position_codes: list[str] = []
        used_slots: set[int] = set()
        for fallback_slot, item in enumerate(lineup, start=1):
            if not isinstance(item, dict):
                continue
            player_id = int(_num(_get(item, "player", "id"), 0))
            position = str(_get(item, "position", "name", default=""))
            slot = _formation_slot(position, formation_id, fallback_slot, used_slots)
            used_slots.add(slot)
            players.append({
                "playerId": player_id,
                "playerName": str(_get(item, "player", "name", default="")),
                "position": position,
                "positionCode": _position_code(position),
                "isFirstEleven": True,
            })
            if player_id:
                player_ids.append(str(player_id))
                slots.append(str(slot))
                position_codes.append(str(_position_group_code(position)))
        rows.append({
            "eventId": base_event_id + len(rows),
            "statsbombEventId": event.get("id"),
            "matchId": event.get("match_id") or meta["match_id"],
            "minute": 0,
            "second": 0,
            "expandedMinute": 0,
            "period": _period(event.get("period")),
            "teamId": int(_num(team_id, -1)) if team_id is not None else None,
            "teamName": team_name,
            "h_a": _side(team_id, team_name, meta),
            "playerId": 0,
            "playerName": "",
            "type": "FormationSet",
            "outcomeType": "Successful",
            "x": 0.0,
            "y": 0.0,
            "endX": 0.0,
            "endY": 0.0,
            "qualifiers": [
                _qualifier("Formation", formation),
                _qualifier("TeamFormation", formation_id),
                _qualifier("InvolvedPlayers", ",".join(player_ids)),
                _qualifier("TeamPlayerFormation", ",".join(slots)),
                _qualifier("PlayerPosition", ",".join(position_codes)),
                _qualifier("PlayerPositionName", ",".join(player.get("positionCode", "UNK") for player in players)),
                _qualifier("Players", json.dumps(players)),
            ],
            "satisfiedEventsTypes": [],
            "isShot": False,
            "isGoal": False,
            "isTouch": False,
            "isFirstEleven": False,
            "formation": formation,
            "formation_players": json.dumps(players),
            "xG": 0.0,
            "xGOT": 0.0,
            "startDate": meta.get("match_date"),
            "score": meta.get("score"),
            "league": meta.get("league") or "statsbomb-import",
            "season": meta.get("season"),
            "source_provider": "statsbomb",
        })
    return rows


def _lineup_rows_from_lineups(lineups: list[dict[str, Any]], meta: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    base_event_id = 805000000000
    for lineup_team in lineups:
        if not isinstance(lineup_team, dict):
            continue
        team_id = lineup_team.get("team_id")
        team_name = str(lineup_team.get("team_name") or "")
        raw_players = lineup_team.get("lineup") if isinstance(lineup_team.get("lineup"), list) else []
        players: list[dict[str, Any]] = []
        player_ids: list[str] = []
        slots: list[str] = []
        position_codes: list[str] = []
        position_names: list[str] = []
        for slot, item in enumerate(raw_players, start=1):
            if not isinstance(item, dict):
                continue
            positions = item.get("positions") if isinstance(item.get("positions"), list) else []
            first_position = next(
                (
                    position
                    for position in positions
                    if isinstance(position, dict)
                    and (
                        str(position.get("start_reason") or "") == "Starting XI"
                        or str(position.get("from") or "") in {"00:00", "0:00"}
                        or int(_num(position.get("from_period"), 0)) == 1
                    )
                ),
                positions[0] if positions and isinstance(positions[0], dict) else {},
            )
            if not first_position:
                continue
            player_id = int(_num(item.get("player_id"), 0))
            if not player_id:
                continue
            position = str(first_position.get("position") or "")
            position_code = _position_code(position)
            players.append({
                "playerId": player_id,
                "playerName": str(item.get("player_name") or ""),
                "position": position,
                "positionCode": position_code,
                "isFirstEleven": True,
            })
            player_ids.append(str(player_id))
            slots.append(str(slot))
            position_codes.append(str(_position_group_code(position)))
            position_names.append(position_code)
        if not player_ids:
            continue
        rows.append({
            "eventId": base_event_id + len(rows),
            "statsbombEventId": f"lineups-{team_id or team_name}",
            "matchId": meta["match_id"],
            "minute": 0,
            "second": 0,
            "expandedMinute": 0,
            "period": "FirstHalf",
            "teamId": int(_num(team_id, -1)) if team_id is not None else None,
            "teamName": team_name,
            "h_a": _side(team_id, team_name, meta),
            "playerId": 0,
            "playerName": "",
            "type": "FormationSet",
            "outcomeType": "Successful",
            "x": 0.0,
            "y": 0.0,
            "endX": 0.0,
            "endY": 0.0,
            "qualifiers": [
                _qualifier("Formation", "Lineups"),
                _qualifier("TeamFormation", 0),
                _qualifier("InvolvedPlayers", ",".join(player_ids)),
                _qualifier("TeamPlayerFormation", ",".join(slots)),
                _qualifier("PlayerPosition", ",".join(position_codes)),
                _qualifier("PlayerPositionName", ",".join(position_names)),
                _qualifier("Players", json.dumps(players)),
            ],
            "satisfiedEventsTypes": [],
            "isShot": False,
            "isGoal": False,
            "isTouch": False,
            "isFirstEleven": False,
            "formation": "Lineups",
            "formation_players": json.dumps(players),
            "xG": 0.0,
            "xGOT": 0.0,
            "startDate": meta.get("match_date"),
            "score": meta.get("score"),
            "league": meta.get("league") or "statsbomb-import",
            "season": meta.get("season"),
            "source_provider": "statsbomb",
        })
    return rows


def _substitution_rows(events: list[dict[str, Any]], meta: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    base_event_id = 810000000000
    for event in events:
        if str(_get(event, "type", "name", default="")) != "Substitution":
            continue
        team_id = _get(event, "team", "id")
        team_name = str(_get(event, "team", "name", default=""))
        minute = int(_num(event.get("minute"), 0))
        second = int(_num(event.get("second"), 0))
        off_id = int(_num(_get(event, "player", "id"), 0))
        on_id = int(_num(_get(event, "substitution", "replacement", "id"), 0))
        off_event_id = base_event_id + len(rows)
        for event_type, player_id, player_name, event_id in (
            ("SubstitutionOff", off_id, str(_get(event, "player", "name", default="")), off_event_id),
            ("SubstitutionOn", on_id, str(_get(event, "substitution", "replacement", "name", default="")), off_event_id + 1),
        ):
            rows.append({
                "eventId": event_id,
                "statsbombEventId": event.get("id"),
                "matchId": event.get("match_id") or meta["match_id"],
                "minute": minute,
                "second": second,
                "expandedMinute": minute,
                "period": _period(event.get("period")),
                "teamId": int(_num(team_id, -1)) if team_id is not None else None,
                "teamName": team_name,
                "h_a": _side(team_id, team_name, meta),
                "playerId": player_id,
                "playerName": player_name,
                "type": event_type,
                "outcomeType": "Successful",
                "x": 0.0,
                "y": 0.0,
                "endX": 0.0,
                "endY": 0.0,
                "qualifiers": [_qualifier("RelatedEventId", off_event_id)] if event_type == "SubstitutionOn" else [],
                "satisfiedEventsTypes": [],
                "isShot": False,
                "isGoal": False,
                "isTouch": False,
                "xG": 0.0,
                "xGOT": 0.0,
                "startDate": meta.get("match_date"),
                "score": meta.get("score"),
                "league": meta.get("league") or "statsbomb-import",
                "season": meta.get("season"),
                "source_provider": "statsbomb",
            })
    return rows


def _enrich_related_events(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "statsbombEventId" not in df.columns:
        return df
    events = df.copy()
    by_statsbomb_id = {row.get("statsbombEventId"): row for _, row in events.iterrows()}
    for idx, row in events.iterrows():
        if str(row.get("type")) != "Pass":
            continue
        related_ids = row.get("relatedEventId")
        related = by_statsbomb_id.get(related_ids)
        if related is None or not bool(related.get("isShot")):
            continue
        qualifiers = row.get("qualifiers") if isinstance(row.get("qualifiers"), list) else []
        _add_qualifier(qualifiers, "ShotAssist")
        _add_qualifier(qualifiers, "KeyPass")
        if bool(related.get("isGoal")):
            _add_qualifier(qualifiers, "IntentionalGoalAssist")
            events.at[idx, "assist"] = True
            events.at[idx, "intentionalAssist"] = True
        events.at[idx, "qualifiers"] = qualifiers
        events.at[idx, "passKey"] = True
        events.at[idx, "bigChanceCreated"] = True
        events.at[idx, "xa_target_event_id"] = related.get("eventId")
        events.at[idx, "xa_target_xg"] = _num(related.get("xG"), 0.0)
    return events


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


def normalize_statsbomb_match(payload: Any) -> pd.DataFrame:
    events, match, _lineups = _extract_payload(payload)
    if not events:
        raise StatsBombImportError("StatsBomb upload must include a non-empty events array.")

    meta = _match_metadata(events, match)
    rows: list[dict[str, Any]] = []
    for index, event in enumerate(events, start=1):
        event_type = _event_type(event)
        if event_type == "FormationSet":
            continue
        rows.append(_base_columns(event, meta, event_type, index))
    lineup_rows = _lineup_rows_from_events(events, meta)
    if not lineup_rows and _lineups:
        lineup_rows = _lineup_rows_from_lineups(_lineups, meta)
    rows.extend(lineup_rows)
    rows.extend(_substitution_rows(events, meta))
    if not rows:
        raise StatsBombImportError("StatsBomb upload did not contain usable event rows.")
    df = _add_derived_columns(_enrich_related_events(pd.DataFrame(rows)))
    return _apply_optional_models(df)
