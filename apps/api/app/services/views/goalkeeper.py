"""Goalkeeper analysis: shot-stopping, distribution, and sweeping."""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.services.matches import _coerce_numeric, _opponent_team_name

KEEPER_EVENT_TYPES = {"Save", "KeeperSave", "KeeperPickup", "Claim", "Punch", "Smother", "KeeperSweeper"}
SHOT_ON_TARGET_TYPES = {"Goal", "SavedShot"}
_LONG_PASS_DISTANCE = 32.0


def _identify_keeper(team_events: pd.DataFrame) -> str | None:
    event_type = team_events.get("type", pd.Series("", index=team_events.index)).astype(str)
    keeper_events = team_events[event_type.isin(KEEPER_EVENT_TYPES)]
    if keeper_events.empty:
        return None
    names = keeper_events["playerName"].dropna().astype(str)
    if names.empty:
        return None
    return names.mode().iloc[0]


def build_goalkeeper_view(df: pd.DataFrame, team: str | None = None) -> dict[str, Any]:
    empty = {"team": team or "", "keeper": None, "available": False}
    if df.empty or "teamName" not in df.columns:
        return empty

    selected_team = team or str(df["teamName"].dropna().iloc[0])
    team_events = df[df["teamName"].astype(str) == selected_team]
    keeper = _identify_keeper(team_events)
    if not keeper:
        return {**empty, "team": selected_team}

    opponent = _opponent_team_name(df, selected_team)
    event_type = df.get("type", pd.Series("", index=df.index)).astype(str)
    is_shot = df.get("isShot", pd.Series(False, index=df.index)).fillna(False).astype(bool)
    is_goal = df.get("isGoal", pd.Series(False, index=df.index)).fillna(False).astype(bool)
    xg = _coerce_numeric(df.get("xG", pd.Series(0, index=df.index))).fillna(0.0)
    xgot = _coerce_numeric(df.get("xGOT", pd.Series(0, index=df.index))).fillna(0.0)
    own_goal = df.get("goalOwn", pd.Series(False, index=df.index)).fillna(False).astype(bool) if "goalOwn" in df.columns else pd.Series(False, index=df.index)

    # ── Shot stopping (opponent shots on target) ────────────────────────────
    opp_mask = df["teamName"].astype(str).eq(opponent) & is_shot & ~own_goal
    on_target = opp_mask & event_type.isin(SHOT_ON_TARGET_TYPES)
    goals_conceded = int((opp_mask & is_goal).sum())
    sot_faced = int(on_target.sum())
    xg_on_target = float(xg[on_target].sum())
    xgot_faced = float(xgot[on_target].sum())
    saves = max(0, sot_faced - goals_conceded)

    # ── Distribution (keeper passes) ────────────────────────────────────────
    keeper_events = df[(df["playerName"].astype(str) == keeper) & df["teamName"].astype(str).eq(selected_team)]
    keeper_type = keeper_events.get("type", pd.Series("", index=keeper_events.index)).astype(str)
    passes = keeper_events[keeper_type.eq("Pass")].copy()
    outcome = passes.get("outcomeType", pd.Series("", index=passes.index)).astype(str).str.lower()
    x = _coerce_numeric(passes.get("x", pd.Series(0, index=passes.index))).fillna(0.0)
    y = _coerce_numeric(passes.get("y", pd.Series(0, index=passes.index))).fillna(0.0)
    end_x = _coerce_numeric(passes.get("endX", pd.Series(0, index=passes.index))).fillna(0.0)
    end_y = _coerce_numeric(passes.get("endY", pd.Series(0, index=passes.index))).fillna(0.0)
    length = (((end_x - x) ** 2 + (end_y - y) ** 2) ** 0.5)
    completed_mask = outcome.eq("successful")
    long_mask = length >= _LONG_PASS_DISTANCE
    pass_count = int(len(passes))

    pass_map = [
        {
            "x": round(float(row_x), 1),
            "y": round(float(row_y), 1),
            "end_x": round(float(row_ex), 1),
            "end_y": round(float(row_ey), 1),
            "successful": bool(row_ok),
            "long": bool(row_long),
        }
        for row_x, row_y, row_ex, row_ey, row_ok, row_long in zip(x, y, end_x, end_y, completed_mask, long_mask)
    ][:80]

    # ── Sweeping / claims ───────────────────────────────────────────────────
    claims = int(keeper_type.isin({"Claim", "Punch"}).sum())
    pickups = int(keeper_type.eq("KeeperPickup").sum())
    keeper_x = _coerce_numeric(keeper_events.get("x", pd.Series(0, index=keeper_events.index))).fillna(0.0)
    sweeper_actions = int((keeper_x > 16.5).sum())

    return {
        "team": selected_team,
        "keeper": keeper,
        "available": True,
        "shot_stopping": {
            "sot_faced": sot_faced,
            "goals_conceded": goals_conceded,
            "saves": saves,
            "save_pct": round(100.0 * saves / sot_faced, 1) if sot_faced else 0.0,
            "xg_on_target_faced": round(xg_on_target, 2),
            "xgot_faced": round(xgot_faced, 2),
            "goals_prevented": round(xgot_faced - goals_conceded, 2),
            "goals_prevented_proxy": round(xgot_faced - goals_conceded, 2),
        },
        "distribution": {
            "passes": pass_count,
            "completed": int(completed_mask.sum()),
            "completion_pct": round(100.0 * float(completed_mask.mean()), 1) if pass_count else 0.0,
            "long_passes": int(long_mask.sum()),
            "long_completed": int((long_mask & completed_mask).sum()),
            "long_pct": round(100.0 * float(long_mask.mean()), 1) if pass_count else 0.0,
            "avg_length": round(float(length.mean()), 1) if pass_count else 0.0,
        },
        "sweeping": {
            "claims": claims,
            "pickups": pickups,
            "actions_outside_box": sweeper_actions,
        },
        "pass_map": pass_map,
    }
