"""Set-piece analysis: corners, free kicks, throw-ins, and goal kicks."""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.services.matches import _coerce_numeric, _filter_score_state, _filter_time_range

SET_PIECE_TOKENS: dict[str, list[str]] = {
    "corner": ["CornerTaken"],
    "free_kick": ["FreekickTaken", "IndirectFreekickTaken"],
    "throw_in": ["ThrowIn"],
    "goal_kick": ["GoalKick"],
}

SET_PIECE_LABELS = {
    "corner": "Corners",
    "free_kick": "Free Kicks",
    "throw_in": "Throw-Ins",
    "goal_kick": "Goal Kicks",
}

_FOLLOW_EVENTS = 6
_FOLLOW_SECONDS = 20.0

# Shots are attributed to a set piece via the shot's own `situation` tag when
# one exists — the follow-window heuristic alone tags unrelated open-play shots
# (and misses second-phase set-piece goals).
_SITUATION_TOKENS: dict[str, list[str]] = {
    "corner": ["FromCorner"],
    "free_kick": ["SetPiece", "DirectFreekick"],
    "throw_in": ["ThrowinSetPiece"],
}
_ATTRIBUTION_WINDOW_SECONDS: dict[str, float] = {
    "corner": 40.0,
    "free_kick": 40.0,
    "throw_in": 25.0,
    "goal_kick": 20.0,
}
_BOX_X = 88.5
_BOX_Y_LOW = 13.84
_BOX_Y_HIGH = 54.16


def build_set_pieces_view(
    df: pd.DataFrame,
    team: str | None = None,
    score_state: str | None = "all",
    time_range: str | None = "all",
) -> dict[str, Any]:
    if df.empty or "teamName" not in df.columns or "qualifiers" not in df.columns:
        return {"team": team or "", "types": {}}

    events = df.copy().reset_index(drop=True)
    minute = _coerce_numeric(events.get("minute", pd.Series(0, index=events.index))).fillna(0.0)
    second = _coerce_numeric(events.get("second", pd.Series(0, index=events.index))).fillna(0.0)
    events["_abs_seconds"] = minute * 60.0 + second
    events = events.sort_values(["_abs_seconds"]).reset_index(drop=True)

    selected_team = team or str(events["teamName"].dropna().iloc[0])
    qualifiers = events["qualifiers"].astype(str)
    event_team = events["teamName"].astype(str)
    is_shot = events.get("isShot", pd.Series(False, index=events.index)).fillna(False).astype(bool)
    is_goal = events.get("isGoal", pd.Series(False, index=events.index)).fillna(False).astype(bool)
    xg = _coerce_numeric(events.get("xG", pd.Series(0, index=events.index))).fillna(0.0)
    outcome = events.get("outcomeType", pd.Series("", index=events.index)).astype(str).str.lower()

    scoped = events[event_team == selected_team]
    scoped = _filter_score_state(scoped, score_state)
    scoped = _filter_time_range(scoped, time_range)
    scoped_index = set(scoped.index)

    types_payload: dict[str, Any] = {}
    for key, tokens in SET_PIECE_TOKENS.items():
        token_mask = pd.Series(False, index=events.index)
        for token in tokens:
            token_mask = token_mask | qualifiers.str.contains(token, case=False, na=False)
        mask = token_mask & (event_team == selected_team) & events.index.isin(scoped_index)
        set_piece_rows = events[mask]

        deliveries: list[dict[str, Any]] = []
        shots_generated = 0
        goals_generated = 0
        xg_generated = 0.0
        retained = 0
        into_box = 0

        for position, row in set_piece_rows.iterrows():
            start_time = float(row["_abs_seconds"])
            end_x = float(pd.to_numeric(row.get("endX"), errors="coerce") or 0.0)
            end_y = float(pd.to_numeric(row.get("endY"), errors="coerce") or 0.0)
            delivery = {
                "minute": int(start_time // 60),
                "player": str(row.get("playerName") or ""),
                "x": round(float(pd.to_numeric(row.get("x"), errors="coerce") or 0.0), 1),
                "y": round(float(pd.to_numeric(row.get("y"), errors="coerce") or 0.0), 1),
                "end_x": round(end_x, 1),
                "end_y": round(end_y, 1),
                "successful": str(row.get("outcomeType") or "").lower() == "successful",
                "led_to_shot": False,
                "led_to_goal": False,
                "receiver": "",
            }
            if key == "corner":
                # No Inswinger/Outswinger qualifier in the data — infer from the
                # kicking foot × corner side (right-footer from the left corner
                # curls goalward = inswinger, and vice versa).
                qualifier_text = str(row.get("qualifiers") or "")
                foot = "right" if "RightFoot" in qualifier_text else "left" if "LeftFoot" in qualifier_text else ""
                if foot:
                    from_left = delivery["y"] >= 34
                    inswing = (from_left and foot == "right") or (not from_left and foot == "left")
                    delivery["swing"] = "inswinger" if inswing else "outswinger"
                else:
                    delivery["swing"] = "unknown"
            if end_x >= _BOX_X and _BOX_Y_LOW <= end_y <= _BOX_Y_HIGH:
                into_box += 1

            follow = events.iloc[position + 1 : position + 1 + _FOLLOW_EVENTS]
            follow = follow[follow["_abs_seconds"] - start_time <= _FOLLOW_SECONDS]
            if not follow.empty:
                first = follow.iloc[0]
                if str(first.get("teamName")) == selected_team:
                    delivery["receiver"] = str(first.get("playerName") or "")
                    if str(first.get("outcomeType") or "successful").lower() != "unsuccessful":
                        retained += 1
            delivery["_position"] = int(position)
            deliveries.append(delivery)

        # Attribute each qualifying team shot to the most recent delivery of
        # this type (never more than one delivery per shot).
        situation_tokens = _SITUATION_TOKENS.get(key)
        window_seconds = _ATTRIBUTION_WINDOW_SECONDS[key]
        shot_mask = (event_team == selected_team) & is_shot
        if situation_tokens:
            situation = events.get("situation", pd.Series("", index=events.index)).astype(str)
            shot_mask = shot_mask & situation.str.contains("|".join(situation_tokens), case=False, na=False)
        for shot_position in events.index[shot_mask]:
            shot_time = float(events.at[shot_position, "_abs_seconds"])
            candidates = [
                delivery for delivery in deliveries
                if delivery["_position"] < shot_position
                and shot_time - float(events.at[delivery["_position"], "_abs_seconds"]) <= window_seconds
            ]
            if not candidates:
                continue
            delivery = max(candidates, key=lambda item: item["_position"])
            delivery["led_to_shot"] = True
            shots_generated += 1
            xg_generated += float(xg.get(shot_position, 0.0))
            if bool(is_goal.get(shot_position, False)):
                delivery["led_to_goal"] = True
                goals_generated += 1
        for delivery in deliveries:
            delivery.pop("_position", None)

        count = int(len(set_piece_rows))
        completed = int(outcome.reindex(set_piece_rows.index).fillna("").eq("successful").sum())
        types_payload[key] = {
            "label": SET_PIECE_LABELS[key],
            "count": count,
            "completed": completed,
            "completion_pct": round(100.0 * completed / count, 1) if count else 0.0,
            "into_box": into_box,
            "retained": retained,
            "retention_pct": round(100.0 * retained / count, 1) if count else 0.0,
            "shots_generated": shots_generated,
            "goals_generated": goals_generated,
            "xg_generated": round(xg_generated, 2),
            "deliveries": deliveries,
        }

    # How the corners were won: the paired CornerAwarded event with a successful
    # outcome carries the winning player and the spot where it was won.
    if "type" in events.columns and "corner" in types_payload:
        event_kind = events["type"].astype(str)
        won_mask = (
            event_kind.eq("CornerAwarded")
            & (event_team == selected_team)
            & outcome.eq("successful")
            & events.index.isin(scoped_index)
        )
        types_payload["corner"]["won"] = [
            {
                "minute": int(_coerce_numeric(pd.Series([row.get("minute")])).fillna(0).iloc[0]),
                "player": str(row.get("playerName") or ""),
                "x": round(float(pd.to_numeric(row.get("x"), errors="coerce") or 0.0), 1),
                "y": round(float(pd.to_numeric(row.get("y"), errors="coerce") or 0.0), 1),
            }
            for _, row in events[won_mask].iterrows()
        ]

    return {
        "team": selected_team,
        "types": types_payload,
        "score_state": score_state or "all",
        "time_range": time_range or "all",
    }
