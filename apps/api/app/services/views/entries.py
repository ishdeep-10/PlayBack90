"""Territory entries & penetration: how a team enters the final third / box,
how it breaks lines (methods), build-up exits, and sequence style."""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.services.matches import _coerce_numeric, _filter_time_range, _with_match_dynamics_possessions

FINAL_THIRD_X = 70.0
OWN_THIRD_X = 35.0
BOX_X = 88.5
BOX_Y_LOW = 13.84
BOX_Y_HIGH = 54.16

_DEFENSIVE_ACTION_TYPES = {"Tackle", "Interception", "BallRecovery", "Clearance", "BlockedPass", "Aerial"}

_SET_PIECE_DELIVERY = "CornerTaken|FreekickTaken|IndirectFreekickTaken|ThrowIn|GoalKick|KeeperThrow|KickOff"

# Team-relative coordinates: y=0 is the attacking team's right touchline.
ENTRY_CHANNELS: list[tuple[str, str, float, float]] = [
    ("right", "Right wing", 0.0, 13.84),
    ("right_hs", "Right half-space", 13.84, 24.84),
    ("center", "Centre", 24.84, 43.16),
    ("left_hs", "Left half-space", 43.16, 54.16),
    ("left", "Left wing", 54.16, 68.01),
]


def _channel_key(y_value: float) -> str:
    for key, _, low, high in ENTRY_CHANNELS:
        if low <= y_value < high:
            return key
    return "center"


def _in_box(x_value: float, y_value: float) -> bool:
    return x_value >= BOX_X and BOX_Y_LOW <= y_value <= BOX_Y_HIGH


def build_territory_entries(df: pd.DataFrame, team: str | None = None, time_range: str | None = None) -> dict[str, Any]:
    empty = {"team": team or "", "final_third": [], "box": [], "exits": [], "receptions": [], "sequence": {}, "time_range": time_range or "all"}
    if df.empty or "teamName" not in df.columns or "type" not in df.columns:
        return empty

    events = _with_match_dynamics_possessions(df)
    if time_range and time_range != "all":
        events = _filter_time_range(events, time_range)
    if events.empty:
        return empty
    selected_team = team or str(events["teamName"].dropna().iloc[0])

    event_type = events["type"].astype(str)
    event_team = events["teamName"].astype(str)
    outcome = events.get("outcomeType", pd.Series("", index=events.index)).astype(str).str.lower()
    qualifiers = events.get("qualifiers", pd.Series("", index=events.index)).astype(str)
    x = _coerce_numeric(events.get("x", pd.Series(-1, index=events.index))).fillna(-1)
    y = _coerce_numeric(events.get("y", pd.Series(-1, index=events.index))).fillna(-1)
    end_x = _coerce_numeric(events.get("endX", pd.Series(-1, index=events.index))).fillna(-1)
    end_y = _coerce_numeric(events.get("endY", pd.Series(-1, index=events.index))).fillna(-1)
    minutes = _coerce_numeric(events.get("cumulative_mins", pd.Series(0, index=events.index))).fillna(0.0)
    is_shot = events.get("isShot", pd.Series(False, index=events.index)).fillna(False).astype(bool)
    is_goal = events.get("isGoal", pd.Series(False, index=events.index)).fillna(False).astype(bool)
    possession = events.get("possession_id", pd.Series(pd.NA, index=events.index))

    defending_team_candidates = [t for t in events["teamName"].dropna().astype(str).unique() if t != selected_team]
    defending_team = defending_team_candidates[0] if defending_team_candidates else ""

    team_mask = event_team == selected_team
    on_ball = event_type.isin(["Pass", "Carry"])
    successful = outcome.eq("successful") | outcome.eq("nan") | events.get("outcomeType", pd.Series(index=events.index)).isna()
    open_play = ~qualifiers.str.contains(_SET_PIECE_DELIVERY, case=False, na=False)
    base = team_mask & on_ball & successful & open_play

    # possession_id -> sorted list of (minute, is_shot_index) for shot lookup
    team_shots = events[team_mask & is_shot]
    shots_by_possession: dict[Any, list[tuple[float, Any]]] = {}
    for shot_index, shot_row in team_shots.iterrows():
        shots_by_possession.setdefault(possession.get(shot_index), []).append((float(minutes.get(shot_index, 0.0)), shot_index))

    def shot_after(row_index: Any) -> tuple[bool, bool]:
        """Was there a team shot later in the same possession? (shot, goal)"""
        possession_id = possession.get(row_index)
        if pd.isna(possession_id):
            return False, False
        row_minute = float(minutes.get(row_index, 0.0))
        for shot_minute, shot_index in shots_by_possession.get(possession_id, []):
            if shot_minute >= row_minute:
                return True, bool(is_goal.get(shot_index, False))
        return False, False

    def classify_method(row_index: Any, into_box: bool) -> str:
        if event_type.get(row_index) == "Carry":
            return "carry"
        qualifier_text = qualifiers.get(row_index, "")
        start_x = float(x.get(row_index, 0.0))
        start_y = float(y.get(row_index, 0.0))
        target_x = float(end_x.get(row_index, 0.0))
        if (
            into_box
            and start_x >= 94
            and (start_y < BOX_Y_LOW + 4 or start_y > BOX_Y_HIGH - 4)
            and target_x <= start_x - 1.5
        ):
            return "cutback"
        if "Cross" in qualifier_text:
            return "cross"
        if "Longball" in qualifier_text:
            return "long_ball"
        if "Chipped" in qualifier_text and (target_x - start_x) >= 30:
            return "long_ball"
        return "ground_pass"

    ordered_index = events.sort_values("cumulative_mins", kind="stable").index.to_list()
    position_of = {row_index: position for position, row_index in enumerate(ordered_index)}
    ignore_types = {"SubstitutionOn", "SubstitutionOff", "FormationChange", "FormationSet", "Card", "End", "Start"}

    def last_defender_before(row_index: Any) -> tuple[str, bool]:
        """Scan backward through same possession for the most recent defending-team defensive action.

        Returns (defender_name, uncontested):
          - defender_name: empty string if no defending action found
          - uncontested: True when no defender challenged before the breach
        """
        possession_id = possession.get(row_index)
        row_position = position_of.get(row_index)
        if row_position is None or not defending_team:
            return ("", True)
        for prev_index in reversed(ordered_index[:row_position]):
            prev_possession = possession.get(prev_index)
            if not pd.isna(possession_id) and not pd.isna(prev_possession) and prev_possession != possession_id:
                break
            if str(event_team.get(prev_index, "")) != defending_team:
                continue
            if str(event_type.get(prev_index, "")) in _DEFENSIVE_ACTION_TYPES:
                player = str(events.at[prev_index, "playerName"] or "")
                return (player, False)
        return ("", True)

    def entry_rows(mask: pd.Series, into_box: bool) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for row_index, row in events[mask].iterrows():
            led_shot, led_goal = shot_after(row_index)
            last_def, uncontest = last_defender_before(row_index)
            rows.append({
                "minute": int(_coerce_numeric(pd.Series([row.get("minute")])).fillna(0).iloc[0]),
                "player": str(row.get("playerName") or ""),
                "x": round(float(x.get(row_index, 0.0)), 1),
                "y": round(float(y.get(row_index, 0.0)), 1),
                "end_x": round(float(end_x.get(row_index, 0.0)), 1),
                "end_y": round(float(end_y.get(row_index, 0.0)), 1),
                "method": classify_method(row_index, into_box),
                "channel": _channel_key(float(end_y.get(row_index, 0.0))),
                "led_to_shot": led_shot,
                "led_to_goal": led_goal,
                "last_defender": last_def,
                "uncontested": uncontest,
            })
        return rows

    final_third_mask = base & (x < FINAL_THIRD_X) & (end_x >= FINAL_THIRD_X)
    box_start_outside = ~((x >= BOX_X) & (y >= BOX_Y_LOW) & (y <= BOX_Y_HIGH))
    box_mask = base & box_start_outside & (end_x >= BOX_X) & (end_y >= BOX_Y_LOW) & (end_y <= BOX_Y_HIGH)

    # Build-up exits: leaving the own third.
    exits_mask = base & (x < OWN_THIRD_X) & (end_x >= OWN_THIRD_X)
    exits: list[dict[str, Any]] = []
    for row_index, row in events[exits_mask].iterrows():
        qualifier_text = qualifiers.get(row_index, "")
        method = (
            "carry" if event_type.get(row_index) == "Carry"
            else "long_ball" if "Longball" in qualifier_text or "Chipped" in qualifier_text
            else "ground_pass"
        )
        start_y = float(y.get(row_index, 0.0))
        side = "right" if start_y < 22.67 else "left" if start_y > 45.33 else "center"
        led_shot, led_goal = shot_after(row_index)
        exits.append({
            "minute": int(_coerce_numeric(pd.Series([row.get("minute")])).fillna(0).iloc[0]),
            "player": str(row.get("playerName") or ""),
            "x": round(float(x.get(row_index, 0.0)), 1),
            "y": round(start_y, 1),
            "end_x": round(float(end_x.get(row_index, 0.0)), 1),
            "end_y": round(float(end_y.get(row_index, 0.0)), 1),
            "method": method,
            "channel": side,
            "led_to_shot": led_shot,
            "led_to_goal": led_goal,
        })

    # Final-third pass receptions: who received the ball in dangerous lanes.
    def receiver_of(row_index: Any) -> str:
        position = position_of.get(row_index)
        if position is None:
            return ""
        for next_index in ordered_index[position + 1 : position + 5]:
            if str(event_type.get(next_index)) in ignore_types:
                continue
            if str(event_team.get(next_index)) != selected_team:
                return ""
            return str(events.at[next_index, "playerName"] or "")
        return ""

    reception_mask = team_mask & event_type.eq("Pass") & successful & open_play & (end_x >= FINAL_THIRD_X)
    receptions: list[dict[str, Any]] = []
    for row_index, row in events[reception_mask].iterrows():
        receiver = receiver_of(row_index)
        led_shot, led_goal = shot_after(row_index)
        reception_y = float(end_y.get(row_index, 0.0))
        reception_x = float(end_x.get(row_index, 0.0))
        receptions.append({
            "minute": int(_coerce_numeric(pd.Series([row.get("minute")])).fillna(0).iloc[0]),
            "player": receiver or str(row.get("playerName") or ""),
            "passer": str(row.get("playerName") or ""),
            "x": round(float(x.get(row_index, 0.0)), 1),
            "y": round(float(y.get(row_index, 0.0)), 1),
            "end_x": round(reception_x, 1),
            "end_y": round(reception_y, 1),
            "method": "reception",
            "channel": _channel_key(reception_y),
            "in_box": _in_box(reception_x, reception_y),
            "led_to_shot": led_shot,
            "led_to_goal": led_goal,
        })

    # Sequence style: passes per shot-ending possession vs overall.
    team_events = events[team_mask]
    team_possession = possession[team_mask]
    passes_per_possession = (
        team_events[team_events["type"].astype(str).eq("Pass")]
        .groupby(possession[team_mask & event_type.eq("Pass")])
        .size()
    )
    shot_possessions = {possession_id for possession_id in shots_by_possession if not pd.isna(possession_id)}
    shot_pass_counts = [int(passes_per_possession.get(possession_id, 0)) for possession_id in shot_possessions]
    all_possessions = team_possession.dropna().unique()
    sequence = {
        "shot_possessions": len(shot_possessions),
        "avg_passes_to_shot": round(sum(shot_pass_counts) / len(shot_pass_counts), 1) if shot_pass_counts else 0.0,
        "avg_passes_all": round(float(passes_per_possession.sum()) / max(1, len(all_possessions)), 1),
        "direct_share": round(
            100.0 * sum(1 for count in shot_pass_counts if count <= 4) / len(shot_pass_counts), 0
        ) if shot_pass_counts else 0.0,
    }

    return {
        "team": selected_team,
        "final_third": entry_rows(final_third_mask, into_box=False),
        "box": entry_rows(box_mask, into_box=True),
        "exits": exits,
        "receptions": receptions,
        "sequence": sequence,
        "time_range": time_range or "all",
    }
