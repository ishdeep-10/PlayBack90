"""Match Summary extras: stat breakdowns, per-third windowed series, lineups.

All coordinates are team-relative (each team attacks towards x=105), pitch is
105 x 68 with y=0 on the attacking team's right touchline.
"""

from __future__ import annotations

import ast
import json
import logging
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

THIRD_BANDS = {"defensive": (0.0, 35.0), "middle": (35.0, 70.0), "final": (70.0, 105.001)}
DEF_ACTIONS = {"Interception", "Tackle", "Clearance", "BlockedPass", "BallRecovery", "Challenge"}

FORMATION_ID_NAMES = {
    2: "4-4-2", 3: "4-1-2-1-2", 4: "4-3-3", 5: "4-5-1", 6: "4-4-1-1", 7: "4-1-4-1",
    8: "4-2-3-1", 9: "4-3-2-1", 10: "5-3-2", 11: "5-4-1", 12: "3-5-2", 13: "3-4-3",
    14: "3-1-3-1-2", 15: "4-2-2-2", 16: "3-5-1-1", 17: "3-4-2-1", 18: "3-4-1-2",
    19: "3-1-4-2", 20: "3-1-2-1-3", 21: "4-1-3-2", 22: "4-2-4-0", 23: "4-3-1-2",
    24: "3-2-4-1", 25: "3-3-3-1",
}

# Position codes: pitch coordinates for the formation view (x towards attack, y=0 right side)
_POS = {
    "GK": (6, 34),
    "RB": (22, 9), "RCB": (17, 23), "CB": (15, 34), "LCB": (17, 45), "LB": (22, 59),
    "RDM": (36, 22), "CDM": (34, 34), "LDM": (36, 46),
    "RCM": (52, 22), "CM": (50, 34), "LCM": (52, 46),
    "RM": (54, 9), "LM": (54, 59),
    "RAM": (70, 19), "CAM": (68, 34), "LAM": (70, 49),
    "RW": (80, 11), "LW": (80, 57),
    "RF": (86, 25), "LF": (86, 43), "ST": (91, 34),
    "UNK": (50, 34),
}

# Slot (1-11) -> position code per Opta formation id (adapted from kloppy's
# statsperform formation mapping).
FORMATION_SLOT_POSITIONS: dict[int, dict[int, str]] = {
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
    16: {1: "GK", 2: "RM", 3: "LM", 4: "LCB", 5: "CB", 6: "RCB", 7: "RDM", 8: "LDM", 9: "ST", 10: "CAM", 11: "CDM"},
    17: {1: "GK", 2: "RM", 3: "LM", 4: "LCB", 5: "CB", 6: "RCB", 7: "RCM", 8: "LCM", 9: "ST", 10: "RF", 11: "LF"},
    18: {1: "GK", 2: "RM", 3: "LM", 4: "LCB", 5: "CB", 6: "RCB", 7: "RCM", 8: "LCM", 9: "CAM", 10: "RF", 11: "LF"},
    19: {1: "GK", 2: "RM", 3: "LM", 4: "CB", 5: "RCB", 6: "LCB", 7: "RCM", 8: "CDM", 9: "RF", 10: "LW", 11: "LCM"},
    20: {1: "GK", 2: "RM", 3: "LM", 4: "LCB", 5: "CB", 6: "RCB", 7: "CAM", 8: "CDM", 9: "ST", 10: "RW", 11: "LW"},
    21: {1: "GK", 2: "RB", 3: "LB", 4: "CDM", 5: "RCB", 6: "LCB", 7: "RW", 8: "CAM", 9: "RF", 10: "LF", 11: "LW"},
    22: {1: "GK", 2: "RB", 3: "LB", 4: "RCM", 5: "RCB", 6: "LCB", 7: "RW", 8: "LCM", 9: "RF", 10: "LF", 11: "LW"},
    23: {1: "GK", 2: "RB", 3: "LB", 4: "CM", 5: "RCB", 6: "LCB", 7: "RM", 8: "CAM", 9: "RF", 10: "LF", 11: "LM"},
    24: {1: "GK", 2: "RDM", 3: "LDM", 4: "LCB", 5: "CB", 6: "RCB", 7: "RCM", 8: "LCM", 9: "ST", 10: "RW", 11: "LW"},
    25: {1: "GK", 2: "RDM", 3: "LDM", 4: "LCB", 5: "CB", 6: "RCB", 7: "CAM", 8: "CDM", 9: "ST", 10: "RW", 11: "LW"},
}


def _num(series: pd.Series | None, index: pd.Index) -> pd.Series:
    if series is None:
        return pd.Series(0.0, index=index)
    return pd.to_numeric(series, errors="coerce").fillna(0.0)


def _bool_col(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(False, index=df.index)
    return _num(df[col], df.index) > 0


def _types(df: pd.DataFrame) -> pd.Series:
    if "type" not in df.columns:
        return pd.Series("", index=df.index, dtype=str)
    return df["type"].astype(str)


def _third_of(x: pd.Series) -> pd.Series:
    return pd.cut(x, bins=[-0.001, 35.0, 70.0, 105.001], labels=["defensive", "middle", "final"])


# ── 3.2 stat breakdowns ───────────────────────────────────────────────────────

def build_stat_breakdowns(df: pd.DataFrame, teams: list[str]) -> dict[str, Any]:
    from app.services.matches import _count_corners_taken, _is_shot_on_target, filter_shots

    shot_df = filter_shots(df).copy()
    shot_df["minute"] = _num(shot_df.get("minute"), shot_df.index).astype(int)
    shot_df["xG"] = _num(shot_df.get("xG"), shot_df.index)
    period = df["period"].astype(str) if "period" in df.columns else pd.Series("", index=df.index, dtype=str)

    out: dict[str, Any] = {
        "goals": {}, "xg": {}, "shots": {}, "possession_pct": {}, "pass_accuracy": {},
        "big_chances": {}, "ppda": {}, "turnovers": {}, "corners_taken": {}, "xt": {},
    }

    for team in teams:
        tdf = df[df.get("teamName") == team]
        t_types = _types(tdf)
        t_period = period.loc[tdf.index]
        ts = shot_df[shot_df.get("teamName") == team]
        s_period = ts["period"].astype(str) if "period" in ts.columns else pd.Series("", index=ts.index, dtype=str)
        situation = ts["situation"].astype(str) if "situation" in ts.columns else pd.Series("", index=ts.index, dtype=str)
        is_penalty = _bool_col(ts, "penaltyScored") | _bool_col(ts, "penaltyMissed")

        # Goals: scorer, minute, second, xG
        goal_rows = ts[_types(ts) == "Goal"]
        goals: list[dict[str, Any]] = []
        for _, row in goal_rows.iterrows():
            goals.append({
                "player": str(row.get("playerName", "")),
                "minute": int(float(row.get("minute", 0) or 0)),
                "second": int(float(row.get("second", 0) or 0)),
                "xg": round(float(row.get("xG", 0) or 0), 3),
                "penalty": bool(is_penalty.get(row.name, False)),
                "own_goal": bool(row.get("isOwnGoal")) if pd.notna(row.get("isOwnGoal")) else False,
            })
        # Own goals credited to this team scored by the opposition
        opp_shots = shot_df[shot_df.get("teamName") != team]
        if "isOwnGoal" in opp_shots.columns:
            og = opp_shots[(_types(opp_shots) == "Goal") & opp_shots["isOwnGoal"].fillna(False).astype(bool)]
            for _, row in og.iterrows():
                goals.append({
                    "player": str(row.get("playerName", "")),
                    "minute": int(float(row.get("minute", 0) or 0)),
                    "second": int(float(row.get("second", 0) or 0)),
                    "xg": 0.0,
                    "penalty": False,
                    "own_goal": True,
                })
        out["goals"][team] = sorted(goals, key=lambda g: (g["minute"], g["second"]))

        # xG split
        set_piece_mask = situation.isin(["FromCorner", "SetPiece", "DirectFreekick"]) & ~is_penalty
        open_play_mask = ~set_piece_mask & ~is_penalty
        xg_vals = _num(ts.get("xG"), ts.index)
        out["xg"][team] = {
            "open_play": round(float(xg_vals[open_play_mask].sum()), 2),
            "set_piece": round(float(xg_vals[set_piece_mask].sum()), 2),
            "penalty": round(float(xg_vals[is_penalty].sum()), 2),
            "non_penalty": round(float(xg_vals[~is_penalty].sum()), 2),
            "first_half": round(float(xg_vals[s_period == "FirstHalf"].sum()), 2),
            "second_half": round(float(xg_vals[s_period == "SecondHalf"].sum()), 2),
        }

        # Shots split
        s_types = _types(ts)
        on_target = ts.apply(_is_shot_on_target, axis=1) if not ts.empty else pd.Series(dtype=bool)
        blocked = _bool_col(ts, "shotBlocked")
        woodwork = (s_types == "ShotOnPost") | _bool_col(ts, "shotOnPost")
        out["shots"][team] = {
            "on_target": int(on_target.sum()) if not ts.empty else 0,
            "off_target": int((~on_target & ~blocked & ~woodwork).sum()) if not ts.empty else 0,
            "blocked": int(blocked.sum()),
            "woodwork": int(woodwork.sum()),
            "first_half": int((s_period == "FirstHalf").sum()),
            "second_half": int((s_period == "SecondHalf").sum()),
        }

        # Possession by third: team touches in their third X vs opponent touches in the mirrored third
        opp = df[(df.get("teamName") != team) & df.get("teamName").notna()] if "teamName" in df.columns else df.iloc[0:0]
        touches_t = tdf[_bool_col(tdf, "isTouch")] if "isTouch" in tdf.columns else tdf
        touches_o = opp[_bool_col(opp, "isTouch")] if "isTouch" in opp.columns else opp
        tx = _num(touches_t.get("x"), touches_t.index)
        ox = 105.0 - _num(touches_o.get("x"), touches_o.index)  # mirror to this team's orientation
        poss_thirds: dict[str, float] = {}
        for third, (lo, hi) in THIRD_BANDS.items():
            own_ct = int(((tx >= lo) & (tx < hi)).sum())
            opp_ct = int(((ox >= lo) & (ox < hi)).sum())
            poss_thirds[third] = round(100.0 * own_ct / max(1, own_ct + opp_ct), 1)
        out["possession_pct"][team] = poss_thirds

        # Pass accuracy by third (start location, team-relative)
        passes = tdf[t_types == "Pass"]
        px = _num(passes.get("x"), passes.index)
        succ = passes.get("outcomeType", pd.Series("", index=passes.index)).astype(str).eq("Successful")
        pass_thirds: dict[str, Any] = {}
        for third, (lo, hi) in THIRD_BANDS.items():
            in_band = (px >= lo) & (px < hi)
            attempted = int(in_band.sum())
            completed = int((in_band & succ).sum())
            pass_thirds[third] = {
                "passes": attempted,
                "completed": completed,
                "pct": round(100.0 * completed / attempted, 1) if attempted else 0.0,
            }
        out["pass_accuracy"][team] = pass_thirds

        # Big chances events
        chances: list[dict[str, Any]] = []
        for col, kind in (("bigChanceCreated", "created"), ("bigChanceMissed", "missed"), ("bigChanceScored", "scored")):
            flagged = tdf[_bool_col(tdf, col)]
            for _, row in flagged.iterrows():
                chances.append({
                    "player": str(row.get("playerName", "")),
                    "minute": int(float(row.get("minute", 0) or 0)),
                    "kind": kind,
                })
        out["big_chances"][team] = sorted(chances, key=lambda c: c["minute"])

        # PPDA by half: opposition passes / team defensive actions, within each half
        opp_types = _types(opp)
        ppda_half: dict[str, float] = {}
        for half, label in (("FirstHalf", "first_half"), ("SecondHalf", "second_half")):
            opp_half = opp[period.loc[opp.index] == half]
            team_half = tdf[t_period == half]
            opp_passes = int((_types(opp_half) == "Pass").sum())
            def_actions = int(_types(team_half).isin(DEF_ACTIONS).sum())
            ppda_half[label] = round(opp_passes / def_actions, 2) if def_actions else 0.0
        out["ppda"][team] = ppda_half

        # Turnovers by third + half
        turnover_mask = (_num(tdf.get("turnover"), tdf.index) + _num(tdf.get("dispossessed"), tdf.index)) > 0
        turnovers = tdf[turnover_mask]
        tox = _num(turnovers.get("x"), turnovers.index)
        out["turnovers"][team] = {
            **{third: int(((tox >= lo) & (tox < hi)).sum()) for third, (lo, hi) in THIRD_BANDS.items()},
            "first_half": int((t_period.loc[turnovers.index] == "FirstHalf").sum()),
            "second_half": int((t_period.loc[turnovers.index] == "SecondHalf").sum()),
        }

        # Corners: left/right side + half
        corner_mask = _bool_col(tdf, "passCorner") | _bool_col(tdf, "cornerAwarded")
        if not corner_mask.any() and "qualifiers" in tdf.columns:
            corner_mask = tdf["qualifiers"].astype(str).str.contains("CornerTaken", na=False)
        corners = tdf[corner_mask & (t_types == "Pass")]
        cy = _num(corners.get("y"), corners.index)
        out["corners_taken"][team] = {
            "total": int(_count_corners_taken(tdf)),
            "right": int((cy < 34).sum()),
            "left": int((cy >= 34).sum()),
            "first_half": int((t_period.loc[corners.index] == "FirstHalf").sum()),
            "second_half": int((t_period.loc[corners.index] == "SecondHalf").sum()),
        }

        # xT by third + passes vs carries
        xt_col = "xT" if "xT" in tdf.columns else None
        if xt_col:
            movers = tdf[t_types.isin(["Pass", "Carry"])]
            if "outcomeType" in movers.columns:
                movers = movers[movers["outcomeType"].astype(str) == "Successful"]
            mx = _num(movers.get("x"), movers.index)
            mxt = _num(movers.get(xt_col), movers.index).clip(lower=0.0)
            out["xt"][team] = {
                **{third: round(float(mxt[(mx >= lo) & (mx < hi)].sum()), 2) for third, (lo, hi) in THIRD_BANDS.items()},
                "passes": round(float(mxt[_types(movers) == "Pass"].sum()), 2),
                "carries": round(float(mxt[_types(movers) == "Carry"].sum()), 2),
            }
        else:
            out["xt"][team] = {}

    return out


# ── 3.3 per-third windowed series ─────────────────────────────────────────────

def build_thirds_series(df: pd.DataFrame, teams: list[str], full_time: int) -> list[dict[str, Any]]:
    """Windowed (15') possession/pass-accuracy/PPDA/turnovers per pitch third."""
    minute = _num(df.get("minute"), df.index)
    if "cumulative_mins" in df.columns:
        clock = _num(df["cumulative_mins"], df.index)
    else:
        clock = minute
    types = _types(df)
    team_col = df.get("teamName", pd.Series("", index=df.index)).astype(str)
    x = _num(df.get("x"), df.index)
    is_touch = _bool_col(df, "isTouch") if "isTouch" in df.columns else pd.Series(True, index=df.index)
    succ = df.get("outcomeType", pd.Series("", index=df.index)).astype(str).eq("Successful")
    turnover = (_num(df.get("turnover"), df.index) + _num(df.get("dispossessed"), df.index)) > 0

    rows: list[dict[str, Any]] = []
    for start in range(0, full_time + 1, 15):
        end = min(full_time + 1, start + 15)
        in_window = (clock >= start) & (clock < end)
        for team in teams:
            is_team = team_col == team
            is_opp = ~is_team & team_col.ne("") & team_col.ne("nan")
            for third, (lo, hi) in THIRD_BANDS.items():
                own_band = (x >= lo) & (x < hi)
                mirror_band = ((105.0 - x) >= lo) & ((105.0 - x) < hi)

                own_touches = int((in_window & is_team & is_touch & own_band).sum())
                opp_touches = int((in_window & is_opp & is_touch & mirror_band).sum())
                possession_pct = round(100.0 * own_touches / max(1, own_touches + opp_touches), 2)

                attempted = int((in_window & is_team & (types == "Pass") & own_band).sum())
                completed = int((in_window & is_team & (types == "Pass") & own_band & succ).sum())
                pass_accuracy_pct = round(100.0 * completed / attempted, 2) if attempted else 0.0

                opp_passes = int((in_window & is_opp & (types == "Pass") & mirror_band).sum())
                def_actions = int((in_window & is_team & types.isin(DEF_ACTIONS) & own_band).sum())
                ppda = round(opp_passes / def_actions, 3) if def_actions else 0.0

                turnovers = int((in_window & is_team & turnover & own_band).sum())

                rows.append({
                    "minute": start,
                    "team": team,
                    "third": third,
                    "possession_pct": possession_pct,
                    "pass_accuracy_pct": pass_accuracy_pct,
                    "ppda": ppda,
                    "turnovers": turnovers,
                })
    return rows


# ── 3.6 lineups & substitutions ───────────────────────────────────────────────

def _parse_qualifiers(raw: Any) -> dict[str, str]:
    try:
        items = ast.literal_eval(str(raw))
        return {str(item.get("type")): str(item.get("value", "")) for item in items if isinstance(item, dict)}
    except (ValueError, SyntaxError):
        return {}


def build_lineups(df: pd.DataFrame, teams: list[str]) -> dict[str, Any]:
    types = _types(df)
    player_names: dict[int, str] = {}
    if {"playerId", "playerName"}.issubset(df.columns):
        ids = pd.to_numeric(df["playerId"], errors="coerce")
        for pid, name in zip(ids, df["playerName"].astype(str)):
            if pd.notna(pid) and name and name != "nan":
                player_names.setdefault(int(pid), name)

    # Average touch positions per player (team-relative coordinates)
    avg_positions: dict[str, dict[str, Any]] = {}
    touch_df = df[_bool_col(df, "isTouch")] if "isTouch" in df.columns else df
    if {"playerName", "x", "y"}.issubset(touch_df.columns):
        grouped = touch_df.dropna(subset=["playerName"]).groupby("playerName").agg(
            avg_x=("x", "mean"), avg_y=("y", "mean"), touches=("x", "count")
        )
        for name, row in grouped.iterrows():
            avg_positions[str(name)] = {
                "x": round(float(row["avg_x"]), 2),
                "y": round(float(row["avg_y"]), 2),
                "touches": int(row["touches"]),
            }

    pos_group_map = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD", 5: "SUB"}
    clock_col = "expandedMinute" if "expandedMinute" in df.columns else "minute"
    clock = _num(df.get(clock_col), df.index)
    full_time = int(max(90.0, float(clock.max()) if len(clock) else 90.0))

    def parse_formation_event(row: pd.Series) -> dict[str, Any] | None:
        quals = _parse_qualifiers(row.get("qualifiers"))
        required = {"InvolvedPlayers", "TeamPlayerFormation"}
        if not required.issubset(quals.keys()):
            return None
        try:
            player_ids = [int(v) for v in quals["InvolvedPlayers"].split(",")]
            slots = [int(v) for v in quals["TeamPlayerFormation"].split(",")]
        except ValueError:
            return None
        jerseys = [v.strip() for v in quals.get("JerseyNumber", "").split(",")]
        pos_codes_raw = [v.strip() for v in quals.get("PlayerPosition", "").split(",")]
        pos_names_raw = [v.strip() for v in quals.get("PlayerPositionName", "").split(",")]
        player_name_by_pid: dict[int, str] = {}
        try:
            players_text = quals.get("Players", "[]")
            try:
                players_raw = json.loads(players_text)
            except json.JSONDecodeError:
                players_raw = ast.literal_eval(players_text)
            if isinstance(players_raw, list):
                for item in players_raw:
                    if not isinstance(item, dict):
                        continue
                    pid = int(item.get("playerId") or 0)
                    name = str(item.get("playerName") or "").strip()
                    if pid and name:
                        player_name_by_pid[pid] = name
        except (ValueError, SyntaxError, TypeError):
            player_name_by_pid = {}
        return {
            "minute": float(row.get(clock_col, 0) or 0),
            "formation_id": int(quals.get("TeamFormation", 0) or 0),
            "formation_name": quals.get("Formation", ""),
            "captain_id": int(quals.get("CaptainPlayerId", 0) or 0),
            "slot_by_pid": dict(zip(player_ids, slots)),
            "jersey_by_pid": {pid: jerseys[idx] for idx, pid in enumerate(player_ids) if idx < len(jerseys)},
            "position_by_pid": {pid: pos_names_raw[idx] for idx, pid in enumerate(player_ids) if idx < len(pos_names_raw) and pos_names_raw[idx]},
            "player_name_by_pid": player_name_by_pid,
            "pos_code_by_pid": {
                pid: int(pos_codes_raw[idx]) for idx, pid in enumerate(player_ids)
                if idx < len(pos_codes_raw) and pos_codes_raw[idx].isdigit()
            },
        }

    # Parse per-team formation timeline + substitutions.
    team_states: dict[str, dict[str, Any]] = {}
    substitutions: list[dict[str, Any]] = []
    subs_on = df[types == "SubstitutionOn"]
    subs_off = df[types == "SubstitutionOff"]

    for team in teams:
        formation_rows = df[(df.get("teamName") == team) & (types.isin(["FormationSet", "FormationChange"]))]
        if formation_rows.empty:
            continue
        formation_rows = formation_rows.sort_values(clock_col)
        events = [parse_formation_event(row) for _, row in formation_rows.iterrows()]
        events = [event for event in events if event]
        if not events:
            continue
        initial = events[0]
        # expanded-clock boundary -> display minute (regular match clock) for labels
        boundary_minutes: dict[int, int] = {}

        team_off = subs_off[subs_off.get("teamName") == team]
        off_by_event: dict[int, tuple[int, str]] = {}
        if "eventId" in team_off.columns:
            for _, row in team_off.iterrows():
                eid = pd.to_numeric(pd.Series([row.get("eventId")]), errors="coerce").iloc[0]
                pid = pd.to_numeric(pd.Series([row.get("playerId")]), errors="coerce").iloc[0]
                if pd.notna(eid):
                    off_by_event[int(eid)] = (int(pid) if pd.notna(pid) else 0, str(row.get("playerName", "")))

        team_subs: list[dict[str, Any]] = []
        team_on = subs_on[subs_on.get("teamName") == team].sort_values(clock_col)
        for _, row in team_on.iterrows():
            quals = _parse_qualifiers(row.get("qualifiers"))
            off_pid, off_name = 0, ""
            related = quals.get("RelatedEventId")
            if related and related.isdigit():
                off_pid, off_name = off_by_event.get(int(related), (0, ""))
            on_pid = pd.to_numeric(pd.Series([row.get("playerId")]), errors="coerce").iloc[0]
            minute_val = float(row.get(clock_col, 0) or 0)
            slot_raw = quals.get("FormationSlot", "")
            team_subs.append({
                "minute": minute_val,
                "on_pid": int(on_pid) if pd.notna(on_pid) else 0,
                "off_pid": off_pid,
                "slot": int(slot_raw) if slot_raw.isdigit() else 0,
            })
            substitutions.append({
                "team": team,
                "minute": int(float(row.get("minute", 0) or 0)),
                "player_on": str(row.get("playerName", "")),
                "player_off": off_name,
            })
            boundary_minutes.setdefault(int(round(minute_val)), int(float(row.get("minute", 0) or 0)))

        for event in events[1:]:
            boundary_minutes.setdefault(int(round(event["minute"])), int(event["minute"]))

        team_states[team] = {
            "initial": initial,
            "formation_events": events[1:],
            "subs": team_subs,
            "boundaries": boundary_minutes,
        }

    substitutions.sort(key=lambda s: s["minute"])

    def player_entry(pid: int, slot: int, state: dict[str, Any], formation_id: int, phase_avg: dict[str, Any]) -> dict[str, Any]:
        initial = state["initial"]
        name = player_names.get(pid) or initial["player_name_by_pid"].get(pid, "")
        position = initial["position_by_pid"].get(pid) or (FORMATION_SLOT_POSITIONS.get(formation_id, {}).get(slot, "UNK") if slot > 0 else None)
        coords = _POS.get(position or "UNK", _POS["UNK"])
        return {
            "player_id": pid,
            "player": name,
            "jersey": initial["jersey_by_pid"].get(pid, ""),
            "slot": slot,
            "position": position,
            "position_group": pos_group_map.get(initial["pos_code_by_pid"].get(pid, 5), "SUB"),
            "captain": pid == initial["captain_id"],
            "x": coords[0],
            "y": coords[1],
            "avg": phase_avg.get(name),
        }

    def phase_avg_positions(start: float, end: float) -> dict[str, dict[str, Any]]:
        if not {"playerName", "x", "y"}.issubset(touch_df.columns):
            return {}
        window = touch_df[(clock.loc[touch_df.index] >= start) & (clock.loc[touch_df.index] < end)]
        result: dict[str, dict[str, Any]] = {}
        if window.empty:
            return result
        grouped = window.dropna(subset=["playerName"]).groupby("playerName").agg(
            avg_x=("x", "mean"), avg_y=("y", "mean"), touches=("x", "count")
        )
        for name, row in grouped.iterrows():
            result[str(name)] = {
                "x": round(float(row["avg_x"]), 2),
                "y": round(float(row["avg_y"]), 2),
                "touches": int(row["touches"]),
            }
        return result

    # Per-team phases: each team's timeline is split only at ITS OWN
    # substitutions and formation changes, replayed chronologically.
    display_full_time = int(max(90.0, float(_num(df.get("minute"), df.index).max()) if "minute" in df.columns else 90.0))
    phases: dict[str, list[dict[str, Any]]] = {}
    for team, state in team_states.items():
        team_boundaries: dict[int, int] = state["boundaries"]
        boundaries = sorted(m for m in team_boundaries if 0 < m < full_time)
        merged: list[int] = []
        for minute_val in boundaries:
            if not merged or minute_val - merged[-1] >= 2:
                merged.append(minute_val)
        segments = list(zip([0, *merged], [*merged, full_time]))

        def display_minute(expanded: int) -> int:
            if expanded == 0:
                return 0
            if expanded >= full_time:
                return display_full_time
            return team_boundaries.get(expanded, expanded)

        # Subs sort BEFORE formation events at the same minute: a simultaneous
        # FormationChange is the authoritative post-substitution slot mapping
        # (e.g. sub says "slot 11" but the change reshuffles the XI), so it must
        # be applied last.
        timeline = sorted(
            [("formation", event["minute"], event) for event in state["formation_events"]]
            + [("sub", sub["minute"], sub) for sub in state["subs"]],
            key=lambda item: (item[1], 0 if item[0] == "sub" else 1),
        )

        team_phases: list[dict[str, Any]] = []
        for start, end in segments:
            phase_avg = phase_avg_positions(float(start), float(end))
            slot_by_pid = dict(state["initial"]["slot_by_pid"])
            formation_id = state["initial"]["formation_id"]
            assigned_seq: dict[int, int] = {}
            seq = 0
            for kind, minute_val, payload in timeline:
                if minute_val >= start + 1:
                    break
                if kind == "formation":
                    for pid, slot in payload["slot_by_pid"].items():
                        slot_by_pid[pid] = slot
                        if slot > 0:
                            seq += 1
                            assigned_seq[pid] = seq
                    formation_id = payload["formation_id"] or formation_id
                else:
                    slot = payload["slot"] or slot_by_pid.get(payload["off_pid"], 0)
                    if payload["off_pid"] in slot_by_pid:
                        slot_by_pid[payload["off_pid"]] = 0
                    if payload["on_pid"]:
                        if not slot:
                            # No slot info at all: take any currently free slot so the XI stays at 11.
                            used = {value for value in slot_by_pid.values() if value > 0}
                            slot = next((candidate for candidate in range(1, 12) if candidate not in used), 0)
                        slot_by_pid[payload["on_pid"]] = slot
                        seq += 1
                        assigned_seq[payload["on_pid"]] = seq
            # Normalize: a sub qualifier can point at an occupied slot when no
            # FormationChange accompanies it — keep the most recent assignee on
            # the contested slot and move earlier occupants to free slots.
            by_slot: dict[int, list[int]] = {}
            for pid, slot in slot_by_pid.items():
                if slot > 0:
                    by_slot.setdefault(slot, []).append(pid)
            free_slots = [slot for slot in range(1, 12) if slot not in by_slot]
            for slot, pids in sorted(by_slot.items()):
                if len(pids) <= 1:
                    continue
                pids.sort(key=lambda pid: assigned_seq.get(pid, 0), reverse=True)
                for pid in pids[1:]:
                    slot_by_pid[pid] = free_slots.pop(0) if free_slots else 0
            players = [
                player_entry(pid, slot, state, formation_id, phase_avg)
                for pid, slot in sorted(slot_by_pid.items(), key=lambda item: item[1])
                if slot > 0
            ]
            team_phases.append({
                "start": int(start),
                "end": int(end),
                "label": f"{display_minute(int(start))}'–{display_minute(int(end))}'",
                "formation_id": formation_id,
                "formation": FORMATION_ID_NAMES.get(formation_id, state["initial"].get("formation_name", "")),
                "players": players,
            })
        phases[team] = team_phases

    # Backwards-compatible starting lineups payload (phase 0 + bench).
    lineups: dict[str, Any] = {}
    for team, state in team_states.items():
        initial = state["initial"]
        starters = [
            player_entry(pid, slot, state, initial["formation_id"], {})
            for pid, slot in sorted(initial["slot_by_pid"].items(), key=lambda item: item[1])
            if slot > 0
        ]
        for entry in starters:
            entry["avg"] = avg_positions.get(entry["player"])
        bench = [
            player_entry(pid, 0, state, initial["formation_id"], {})
            for pid, slot in initial["slot_by_pid"].items()
            if slot == 0
        ]
        for entry in bench:
            entry["avg"] = avg_positions.get(entry["player"])
        lineups[team] = {
            "formation_id": initial["formation_id"],
            "formation": FORMATION_ID_NAMES.get(initial["formation_id"], initial.get("formation_name", "")),
            "starters": starters,
            "bench": bench,
        }

    return {"teams": lineups, "substitutions": substitutions, "phases": phases, "full_time": full_time}


def player_position_timeline(df: pd.DataFrame, teams: list[str]) -> dict[str, dict[str, Any]]:
    """Per-player position history derived from build_lineups()'s per-team phases.

    Returns, for each player name that appeared in at least one phase:
      primary_position / primary_position_group: the position held for the most minutes
      position_group: alias of primary_position_group (top-level convenience field)
      positions: unique positions played, ordered by first occurrence
      timeline: [{position, position_group, start, end}] with consecutive
                same-position phases collapsed into one entry
    """
    lineups = build_lineups(df, teams)
    phases_by_team: dict[str, list[dict[str, Any]]] = lineups.get("phases", {})

    raw: dict[str, list[dict[str, Any]]] = {}
    for team_phases in phases_by_team.values():
        for phase in team_phases:
            start, end = int(phase.get("start", 0)), int(phase.get("end", 0))
            for player in phase.get("players", []):
                name = str(player.get("player") or "").strip()
                if not name:
                    continue
                position = player.get("position") or "UNK"
                position_group = player.get("position_group") or "SUB"
                raw.setdefault(name, []).append({
                    "position": position,
                    "position_group": position_group,
                    "start": start,
                    "end": end,
                })

    result: dict[str, dict[str, Any]] = {}
    for name, entries in raw.items():
        entries.sort(key=lambda item: item["start"])
        collapsed: list[dict[str, Any]] = []
        for entry in entries:
            if collapsed and collapsed[-1]["position"] == entry["position"] and collapsed[-1]["end"] >= entry["start"]:
                collapsed[-1]["end"] = max(collapsed[-1]["end"], entry["end"])
            else:
                collapsed.append(dict(entry))

        minutes_by_position: dict[str, int] = {}
        for entry in collapsed:
            minutes_by_position[entry["position"]] = minutes_by_position.get(entry["position"], 0) + max(0, entry["end"] - entry["start"])
        primary_position = max(minutes_by_position, key=lambda key: minutes_by_position[key]) if minutes_by_position else "UNK"
        primary_group = next((entry["position_group"] for entry in collapsed if entry["position"] == primary_position), "SUB")
        positions_ordered: list[str] = []
        for entry in collapsed:
            if entry["position"] not in positions_ordered:
                positions_ordered.append(entry["position"])

        result[name] = {
            "primary_position": primary_position,
            "primary_position_group": primary_group,
            "position_group": primary_group,
            "positions": positions_ordered,
            "timeline": collapsed,
        }
    return result


def position_at_minute(timeline: list[dict[str, Any]], minute: float) -> str | None:
    """Look up the position active at a given match minute from a player's timeline."""
    for entry in timeline:
        if entry["start"] <= minute < entry["end"]:
            return str(entry["position"])
    if timeline:
        last = timeline[-1]
        if minute >= last["end"]:
            return str(last["position"])
        first = timeline[0]
        if minute < first["start"]:
            return str(first["position"])
    return None
