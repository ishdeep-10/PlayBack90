"""
generate_season_stats.py
------------------------
Reads match events, computes per-match team and player aggregations, then
uploads three compact Parquet files per (league, season) to Cloudflare R2:

  season_stats/{league}/{season}/team_match_stats.parquet
  season_stats/{league}/{season}/player_match_stats.parquet
  season_stats/{league}/{season}/event_locations.parquet

Default source is HYBRID: the full match list comes from the local SQLite
database (R2 event_data/ is only a partial archive), but any match that has
an enriched R2 event parquet is read from R2 instead — model backfills
(xG v2, xA, xGOT, xpass, EPV) write into those parquets only, so this is the
only way season stats carry the backfilled metrics without losing coverage.
SQLite events are deduplicated (some matches contain repeated scrapes).

Run manually after scraping AND after model backfills.
Usage:
  python generate_season_stats.py                              # hybrid, all leagues/seasons
  python generate_season_stats.py --league ligue-1             # hybrid, one league
  python generate_season_stats.py --source sqlite --season 2025/2026
"""

import os
import io
import sys
import re
import json
import sqlite3
import argparse
from datetime import datetime, timezone

import boto3
import numpy as np
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
R2_ACCESS_KEY  = os.getenv("R2_ACCESS_KEY")
R2_SECRET_KEY  = os.getenv("R2_SECRET_KEY")
R2_BUCKET      = os.getenv("R2_BUCKET")
ENDPOINT_URL   = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

DB_PATH = os.path.join(os.path.dirname(__file__), "playback90.db")

# The raw DB has NULL teamName for some teams (mostly national sides); the API
# backfills them from TEAM_DICT, so do the same here.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))
try:
    from app.domain import TEAM_DICT
    from app.services.views.match_summary import build_lineups
except Exception:
    TEAM_DICT = {}
    build_lineups = None


def _backfill_team_names(match_df: pd.DataFrame) -> pd.DataFrame:
    if "teamName" not in match_df.columns or "teamId" not in match_df.columns or not TEAM_DICT:
        return match_df
    # R2 parquets serialize missing names as the string "None"; SQLite stores NULL.
    names = match_df["teamName"].astype(str).str.strip()
    missing = match_df["teamName"].isna() | names.isin(["None", "nan", ""])
    if missing.any():
        team_ids = pd.to_numeric(match_df.loc[missing, "teamId"], errors="coerce")
        match_df.loc[missing, "teamName"] = team_ids.map(lambda tid: TEAM_DICT.get(int(tid)) if pd.notna(tid) else None)
    # Numeric team names (ids stored in the name column) also map through TEAM_DICT.
    numeric_names = pd.to_numeric(match_df["teamName"], errors="coerce")
    mappable = numeric_names.notna()
    if mappable.any():
        match_df.loc[mappable, "teamName"] = numeric_names[mappable].map(lambda tid: TEAM_DICT.get(int(tid), str(int(tid))))
    return match_df

# Defensive action event types used for PPDA
_DEF_TYPES  = {"Tackle", "Interception", "Challenge", "BlockedPass"}
# All shot subtypes
_SHOT_TYPES = {"Goal", "SavedShot", "MissedShots", "ShotOnPost"}

# Goalkeeper event types — must match apps/api/app/services/views/goalkeeper.py
_KEEPER_EVENT_TYPES = {"Save", "KeeperSave", "KeeperPickup", "Claim", "Punch", "Smother", "KeeperSweeper"}
_SHOT_ON_TARGET_TYPES = {"Goal", "SavedShot"}
_GK_LONG_PASS_DISTANCE = 32.0

# Bump when row-level definitions change so the API can detect stale files.
SCHEMA_VERSION = 5

# Duel composition — must match apps/api/app/services/views/common.py
_GROUND_DUEL_TYPES = {"TakeOn", "GoodSkill", "ShieldBallOpp", "Foul", "Tackle", "Challenge"}
# Defensive-action set — must match DEFENSIVE_ACTION_TYPES in services/matches.py
_DEF_ACTION_TYPES = {"Aerial", "BallRecovery", "BlockedPass", "Challenge", "Clearance",
                     "Error", "Foul", "Interception", "Tackle"}

# Pitch constants — Opta 0-100 coords, must match apps/api/app/services/views/entries.py
_FINAL_THIRD_X = 70.0
_BOX_X = 88.5
_BOX_Y_LOW = 13.84
_BOX_Y_HIGH = 54.16


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_key(val: str) -> str:
    """Make a string safe for use in an S3/R2 key."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(val))


def _norm_match_id(val) -> str:
    """SQLite stores matchId as REAL; normalize '1903350.0' -> '1903350'."""
    s = str(val)
    return s[:-2] if s.endswith(".0") else s


def _safe_sum(series, default=0):
    try:
        return series.sum()
    except Exception:
        return default


def _type_filter(df, type_val):
    """Filter rows where the 'type' column equals type_val (str) or a boolean column named type_val is True."""
    if "type" in df.columns:
        return df[df["type"] == type_val]
    elif type_val in df.columns:
        return df[df[type_val] == True]
    return pd.DataFrame(columns=df.columns)


def _type_filter_set(df, type_set):
    """Filter rows where type is in a set of strings."""
    if "type" in df.columns:
        return df[df["type"].isin(type_set)]
    # Fallback: OR together any matching boolean columns
    mask = pd.Series(False, index=df.index)
    for t in type_set:
        if t in df.columns:
            mask = mask | (df[t] == True)
    return df[mask]


def _numcol(df, col):
    if col not in df.columns:
        return pd.Series(0.0, index=df.index)
    return pd.to_numeric(df[col], errors="coerce").fillna(0.0)


def _successful_mask(df):
    if "outcomeType" not in df.columns:
        return pd.Series(False, index=df.index)
    return df["outcomeType"].astype(str).str.contains("Successful", na=False)


def _bool_col_true(df, col):
    if col not in df.columns:
        return pd.Series(False, index=df.index)
    return pd.to_numeric(df[col], errors="coerce").fillna(0) > 0


def _duel_frames(dfp):
    """(all duels, won duels) for a player's events — mirrors the duels view."""
    if "type" not in dfp.columns:
        empty = dfp.iloc[0:0]
        return empty, empty
    types = dfp["type"].astype(str)
    aerial = _bool_col_true(dfp, "duelAerialWon") | _bool_col_true(dfp, "duelAerialLost") | types.eq("Aerial")
    ground = types.isin(_GROUND_DUEL_TYPES)
    duels = dfp[aerial | ground]
    aerial_won = _bool_col_true(duels, "duelAerialWon")
    aerial_lost = _bool_col_true(duels, "duelAerialLost")
    outcome = duels["outcomeType"].astype(str).str.lower() if "outcomeType" in duels.columns else pd.Series("", index=duels.index)
    other_won = outcome.isin(["successful", "nan", ""]) | duels["outcomeType"].isna() if "outcomeType" in duels.columns else pd.Series(True, index=duels.index)
    won = duels[aerial_won | (~aerial_lost & other_won)]
    return duels, won


def _def_action_frame(dfp):
    """Successful defensive actions — mirrors _defensive_action_mask in the API."""
    if "type" not in dfp.columns:
        return dfp.iloc[0:0]
    types = dfp["type"].astype(str)
    mask = types.isin(_DEF_ACTION_TYPES)
    if "qualifiers" in dfp.columns:
        mask = mask & ((types != "Aerial") | dfp["qualifiers"].astype(str).str.contains("Defensive", case=False, na=False))
    if "outcomeType" in dfp.columns:
        outcome = dfp["outcomeType"].astype(str).str.lower()
        mask = mask & (outcome.eq("successful") | outcome.eq("nan") | dfp["outcomeType"].isna())
    return dfp[mask]


def _pass_receiver_series(match_df):
    """Receiver of each successful pass = next event's player when same team."""
    df = match_df.sort_index()
    types = df["type"].astype(str) if "type" in df.columns else pd.Series("", index=df.index)
    outcome = df["outcomeType"].astype(str) if "outcomeType" in df.columns else pd.Series("", index=df.index)
    next_player = df["playerName"].shift(-1) if "playerName" in df.columns else pd.Series(index=df.index, dtype=object)
    next_team = df["teamName"].shift(-1) if "teamName" in df.columns else pd.Series(index=df.index, dtype=object)
    ok = types.eq("Pass") & outcome.str.contains("Successful", na=False) & (next_team == df.get("teamName"))
    return pd.Series(np.where(ok, next_player, None), index=df.index)


def _pass_carry_value_sum(df, col, clip_negative=False):
    """Sum a value column over successful passes/carries (xT / EPV convention in the API)."""
    if col not in df.columns or "type" not in df.columns:
        return 0.0
    pc = df[df["type"].isin(["Pass", "Carry"]) & _successful_mask(df)]
    series = pd.to_numeric(pc[col], errors="coerce").fillna(0.0)
    if clip_negative:
        series = series.clip(lower=0.0)
    return float(series.sum())


def _identify_match_keepers(match_df):
    """{teamName: keeper playerName} — mirrors _identify_keeper in goalkeeper.py."""
    keepers = {}
    if "teamName" not in match_df.columns or "type" not in match_df.columns:
        return keepers
    types = match_df["type"].astype(str)
    keeper_events = match_df[types.isin(_KEEPER_EVENT_TYPES)]
    for team, team_events in keeper_events.groupby("teamName"):
        names = team_events["playerName"].dropna().astype(str)
        if not names.empty:
            keepers[str(team)] = names.mode().iloc[0]
    return keepers


def _compute_gk_match_stats(dfp, match_df, team):
    """GK shot-stopping/distribution/sweeping for one player-match — mirrors goalkeeper.py."""
    if "teamName" not in match_df.columns or "type" not in match_df.columns:
        return {}
    opponent_mask = match_df["teamName"].astype(str) != str(team)
    opp = match_df[opponent_mask]
    opp_types = opp["type"].astype(str) if "type" in opp.columns else pd.Series(dtype=str)
    is_shot = opp_types.isin(_SHOT_TYPES)
    own_goal = _bool_col_true(opp, "goalOwn") if "goalOwn" in opp.columns else pd.Series(False, index=opp.index)
    shots = opp[is_shot & ~own_goal]
    shot_types = shots["type"].astype(str) if "type" in shots.columns else pd.Series(dtype=str)
    on_target = shots[shot_types.isin(_SHOT_ON_TARGET_TYPES)]
    goals_conceded = int((shot_types == "Goal").sum())
    sot_faced = int(len(on_target))
    xg_on_target = float(_numcol(on_target, "xG").sum()) if "xG" in on_target.columns else 0.0
    xgot_faced = float(_numcol(on_target, "xGOT").sum()) if "xGOT" in on_target.columns else 0.0
    saves = max(0, sot_faced - goals_conceded)

    types_p = dfp["type"].astype(str) if "type" in dfp.columns else pd.Series(dtype=str)
    passes = dfp[types_p == "Pass"]
    outcome = passes["outcomeType"].astype(str).str.lower() if "outcomeType" in passes.columns else pd.Series("", index=passes.index)
    completed_mask = outcome.eq("successful")
    x = _numcol(passes, "x")
    y = _numcol(passes, "y")
    end_x = _numcol(passes, "endX")
    end_y = _numcol(passes, "endY")
    length = ((end_x - x) ** 2 + (end_y - y) ** 2) ** 0.5
    long_mask = length >= _GK_LONG_PASS_DISTANCE
    pass_count = int(len(passes))

    claims = int(types_p.isin({"Claim", "Punch"}).sum())
    pickups = int((types_p == "KeeperPickup").sum())
    sweeper_actions = int((types_p == "KeeperSweeper").sum())

    return {
        "gk_sot_faced": sot_faced,
        "gk_goals_conceded": goals_conceded,
        "gk_saves": saves,
        "gk_save_pct": round(100.0 * saves / sot_faced, 1) if sot_faced else 0.0,
        "gk_xg_on_target_faced": round(xg_on_target, 2),
        "gk_xgot_faced": round(xgot_faced, 2),
        "gk_goals_prevented": round(xgot_faced - goals_conceded, 2),
        "gk_claims": claims,
        "gk_pickups": pickups,
        "gk_sweeper_actions": sweeper_actions,
        "gk_pass_completion_pct": round(100.0 * float(completed_mask.mean()), 1) if pass_count else 0.0,
        "gk_long_pass_pct": round(100.0 * float(long_mask.mean()), 1) if pass_count else 0.0,
        "gk_avg_pass_length": round(float(length.mean()), 1) if pass_count else 0.0,
    }


# ---------------------------------------------------------------------------
# Per-match team aggregation
# ---------------------------------------------------------------------------

def _compute_team_match_stats(match_df: pd.DataFrame) -> list[dict]:
    """Return a list of two dicts (one per team) for a single match."""
    rows = []
    teams = match_df["teamName"].dropna().unique().tolist()
    if len(teams) == 0:
        return rows

    match_id = _norm_match_id(match_df["matchId"].iloc[0])
    date     = str(match_df["startDate"].iloc[0])[:10] if "startDate" in match_df.columns else ""
    league   = str(match_df["league"].iloc[0]) if "league" in match_df.columns else ""
    season   = str(match_df["season"].iloc[0]) if "season" in match_df.columns else ""
    ft_score = (
        str(match_df["ftScore"].dropna().iloc[0])
        if "ftScore" in match_df.columns and not match_df["ftScore"].dropna().empty
        else ""
    )

    for team in teams:
        t   = match_df[match_df["teamName"] == team]
        opp_name = next((x for x in teams if x != team), "")
        opp = match_df[match_df["teamName"] == opp_name] if opp_name else pd.DataFrame(columns=match_df.columns)

        h_a = str(t["h_a"].iloc[0]) if "h_a" in t.columns and len(t) > 0 else ""

        # --- Goals & xG ---
        goals         = len(_type_filter(t, "Goal"))
        goals_against = len(_type_filter(opp, "Goal")) if len(opp) > 0 else 0
        xg            = round(float(_safe_sum(t["xG"])), 3)  if "xG"  in t.columns else 0.0
        xg_against    = round(float(_safe_sum(opp["xG"])), 3) if "xG" in opp.columns and len(opp) > 0 else 0.0

        # --- Shots ---
        shots_df        = _type_filter_set(t, _SHOT_TYPES)
        shots           = len(shots_df)
        shots_on_target = len(_type_filter_set(shots_df, {"Goal", "SavedShot"}))
        shots_against   = len(_type_filter_set(opp, _SHOT_TYPES)) if len(opp) > 0 else 0

        # --- Passes & pass accuracy ---
        passes_df    = _type_filter(t, "Pass")
        passes       = len(passes_df)
        pass_accuracy = 0.0
        if passes > 0 and "outcomeType" in passes_df.columns:
            successful = passes_df["outcomeType"].str.contains("Successful", na=False).sum()
            pass_accuracy = round(float(successful) / passes * 100, 1)

        # --- Possession % (share of all events) ---
        total_events  = len(match_df)
        possession_pct = round(len(t) / total_events * 100, 1) if total_events > 0 else 0.0

        # --- PPDA: opponent passes / team defensive actions ---
        team_def   = len(_type_filter_set(t, _DEF_TYPES))
        opp_passes = len(_type_filter(opp, "Pass")) if len(opp) > 0 else 0
        ppda       = round(opp_passes / max(1, team_def), 2)

        # --- Turnovers ---
        turnovers = len(_type_filter_set(t, {"Turnover", "Dispossessed"}))

        # --- Big chances (xG > 0.35) ---
        big_chances = (
            int(shots_df[shots_df["xG"] > 0.35].shape[0])
            if "xG" in shots_df.columns and len(shots_df) > 0 else 0
        )
        opp_shots_df = _type_filter_set(opp, _SHOT_TYPES) if len(opp) > 0 else pd.DataFrame()
        big_chances_against = (
            int(opp_shots_df[opp_shots_df["xG"] > 0.35].shape[0])
            if "xG" in opp_shots_df.columns and len(opp_shots_df) > 0 else 0
        )
        shot_accuracy = round(shots_on_target / max(1, shots) * 100, 1)
        xg_per_shot   = round(xg / max(1, shots), 3)

        # --- Passing details (qualifier-based) ---
        crosses     = 0
        through_balls = 0
        long_balls  = 0
        if "qualifiers" in passes_df.columns and len(passes_df) > 0:
            crosses       = int(passes_df["qualifiers"].str.contains("Cross",       na=False).sum())
            through_balls = int(passes_df["qualifiers"].str.contains("Throughball", na=False).sum())
            long_balls    = int(passes_df["qualifiers"].str.contains("Longball",    na=False).sum())

        # --- Dribbles (TakeOn) ---
        takeons_df        = _type_filter(t, "TakeOn")
        dribbles_attempted = len(takeons_df)
        dribbles_won      = (
            int(takeons_df["outcomeType"].str.contains("Successful", na=False).sum())
            if "outcomeType" in takeons_df.columns and len(takeons_df) > 0 else 0
        )

        # --- Other defensive / disciplinary ---
        clearances     = len(_type_filter(t, "Clearance"))
        fouls_committed= len(_type_filter(t, "Foul"))
        aerials_df     = _type_filter(t, "Aerial")
        aerial_total   = len(aerials_df)
        aerial_won     = (
            int(aerials_df["outcomeType"].str.contains("Successful", na=False).sum())
            if "outcomeType" in aerials_df.columns and len(aerials_df) > 0 else 0
        )

        # --- Cards ---
        yellow_cards = 0
        red_cards    = 0
        if "cardType" in t.columns:
            yellow_cards = int(t["cardType"].astype(str).str.contains("Yellow|SecondYellow", na=False).sum())
            red_cards    = int(t["cardType"].astype(str).str.contains("(?<![Ss]econd)Red|SecondYellow", na=False, regex=True).sum())

        # --- Advanced metrics (only present when the source was backfilled) ---
        extra = {}
        if "xGOT" in t.columns:
            extra["xGOT"] = round(float(_numcol(t, "xGOT").sum()), 3)
            extra["xGOT_against"] = round(float(_numcol(opp, "xGOT").sum()), 3) if len(opp) > 0 else 0.0
        if "xT" in t.columns:
            extra["xT"] = round(_pass_carry_value_sum(t, "xT", clip_negative=True), 3)
        if "epv_added" in t.columns:
            extra["epv_added"] = round(_pass_carry_value_sum(t, "epv_added"), 3)
        if "prog_pass" in t.columns:
            extra["prog_passes"] = int(_numcol(t, "prog_pass").gt(0).sum())
        if "prog_carry" in t.columns:
            extra["prog_carries"] = int(_numcol(t, "prog_carry").gt(0).sum())
        if "type" in t.columns and "endX" in t.columns:
            pc = t[t["type"].isin(["Pass", "Carry"]) & _successful_mask(t)]
            sx, sy = _numcol(pc, "x"), _numcol(pc, "y")
            ex, ey = _numcol(pc, "endX"), _numcol(pc, "endY")
            start_outside = ~((sx >= _BOX_X) & (sy >= _BOX_Y_LOW) & (sy <= _BOX_Y_HIGH))
            extra["box_entries"] = int((start_outside & (ex >= _BOX_X) & (ey >= _BOX_Y_LOW) & (ey <= _BOX_Y_HIGH)).sum())
        if "isTouch" in match_df.columns and "x" in match_df.columns:
            touch = match_df[match_df["isTouch"] == True]
            ft = touch[pd.to_numeric(touch["x"], errors="coerce").fillna(0.0) >= _FINAL_THIRD_X]
            extra["field_tilt_pct"] = round(int((ft["teamName"] == team).sum()) / len(ft) * 100, 1) if len(ft) else 0.0
            team_seq = touch["teamName"].dropna()
            extra["possessions"] = int(((team_seq != team_seq.shift()) & (team_seq == team)).sum())
        if "xPass" in t.columns and passes > 0:
            xp = pd.to_numeric(passes_df["xPass"], errors="coerce")
            extra["passes_completed"] = int(_successful_mask(passes_df).sum())
            extra["xpass_exp_completed"] = round(float(xp.dropna().sum()), 2)

        rows.append({
            "matchId":             match_id,
            "date":                date,
            "league":              league,
            "season":              season,
            "teamName":            team,
            "opponentName":        opp_name,
            "homeAway":            h_a,
            "goals":               goals,
            "goals_against":       goals_against,
            "xG":                  xg,
            "xG_against":          xg_against,
            "shots":               shots,
            "shots_on_target":     shots_on_target,
            "shots_against":       shots_against,
            "big_chances":         big_chances,
            "big_chances_against": big_chances_against,
            "shot_accuracy":       shot_accuracy,
            "xG_per_shot":         xg_per_shot,
            "passes":              passes,
            "pass_accuracy":       pass_accuracy,
            "crosses":             crosses,
            "through_balls":       through_balls,
            "long_balls":          long_balls,
            "ppda":                ppda,
            "turnovers":           turnovers,
            "possession_pct":      possession_pct,
            "dribbles_attempted":  dribbles_attempted,
            "dribbles_won":        dribbles_won,
            "clearances":          clearances,
            "fouls_committed":     fouls_committed,
            "aerial_duels_total":  aerial_total,
            "aerial_duels_won":    aerial_won,
            "yellow_cards":        yellow_cards,
            "red_cards":           red_cards,
            "ft_score":            ft_score,
            **extra,
        })
    return rows


def _json_compact(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _compute_team_history(match_df: pd.DataFrame, team_match_rows: list[dict] | None = None) -> list[dict]:
    """One row per team-match for opposition timeline/history features."""
    if build_lineups is None or "teamName" not in match_df.columns:
        return []

    teams = [str(team) for team in match_df["teamName"].dropna().unique().tolist()]
    if not teams:
        return []

    match_id = _norm_match_id(match_df["matchId"].iloc[0])
    date = str(match_df["startDate"].iloc[0])[:10] if "startDate" in match_df.columns else ""
    league = str(match_df["league"].iloc[0]) if "league" in match_df.columns else ""
    season = str(match_df["season"].iloc[0]) if "season" in match_df.columns else ""
    ft_score = (
        str(match_df["ftScore"].dropna().iloc[0])
        if "ftScore" in match_df.columns and not match_df["ftScore"].dropna().empty
        else ""
    )

    try:
        lineup_payload = build_lineups(match_df, teams)
    except Exception:
        return []

    lineups = lineup_payload.get("teams", {}) if isinstance(lineup_payload, dict) else {}
    substitutions = lineup_payload.get("substitutions", []) if isinstance(lineup_payload, dict) else []
    phases = lineup_payload.get("phases", {}) if isinstance(lineup_payload, dict) else {}
    stats_by_team = {
        str(row.get("teamName") or ""): row
        for row in (team_match_rows or [])
        if isinstance(row, dict) and row.get("teamName")
    }
    metric_columns = [
        "goals", "goals_against", "xG", "xG_against", "shots", "shots_on_target", "shots_against",
        "big_chances", "big_chances_against", "shot_accuracy", "xG_per_shot", "passes", "passes_completed",
        "pass_accuracy", "xpass_exp_completed", "crosses", "through_balls", "long_balls", "ppda", "turnovers",
        "possession_pct", "field_tilt_pct", "box_entries", "prog_passes", "prog_carries", "xT", "epv_added",
        "xGOT", "xGOT_against", "dribbles_attempted", "dribbles_won", "clearances", "fouls_committed",
        "aerial_duels_total", "aerial_duels_won", "yellow_cards", "red_cards", "possessions",
    ]
    rows = []
    for team in teams:
        lineup = lineups.get(team, {}) if isinstance(lineups, dict) else {}
        team_events = match_df[match_df["teamName"] == team]
        opponent = next((item for item in teams if item != team), "")
        stats = stats_by_team.get(team, {})
        goals = int(float(stats.get("goals", 0) or 0))
        goals_against = int(float(stats.get("goals_against", 0) or 0))
        result = "W" if goals > goals_against else ("D" if goals == goals_against else "L")
        metric_values = {column: stats[column] for column in metric_columns if column in stats}
        rows.append(
            {
                "matchId": match_id,
                "date": date,
                "league": league,
                "season": season,
                "teamName": team,
                "opponentName": opponent,
                "homeAway": str(team_events["h_a"].iloc[0]) if "h_a" in team_events.columns and not team_events.empty else "",
                "score": ft_score,
                "result": result,
                "formation_id": lineup.get("formation_id"),
                "formation": lineup.get("formation", ""),
                "starters_json": _json_compact(lineup.get("starters", [])),
                "starter_ids_json": _json_compact([player.get("player_id") for player in lineup.get("starters", []) if isinstance(player, dict)]),
                "starter_names_json": _json_compact([player.get("player") for player in lineup.get("starters", []) if isinstance(player, dict)]),
                "bench_json": _json_compact(lineup.get("bench", [])),
                "substitutions_json": _json_compact([sub for sub in substitutions if sub.get("team") == team]),
                "phase_lineups_json": _json_compact(phases.get(team, []) if isinstance(phases, dict) else []),
                "lineup_available": bool(lineup.get("starters")),
                "history_schema_version": 1,
                **metric_values,
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Per-match player aggregation
# ---------------------------------------------------------------------------

def _compute_player_match_stats(match_df: pd.DataFrame) -> list[dict]:
    """Return a list of dicts (one per player) for a single match."""
    rows = []
    match_id = _norm_match_id(match_df["matchId"].iloc[0])
    receivers = _pass_receiver_series(match_df)
    received_prog = receivers[_bool_col_true(match_df, "prog_pass")] if "prog_pass" in match_df.columns else pd.Series(dtype=object)
    received_counts = receivers.dropna().value_counts()
    received_prog_counts = received_prog.dropna().value_counts()
    match_keepers = _identify_match_keepers(match_df)
    date     = str(match_df["startDate"].iloc[0])[:10] if "startDate" in match_df.columns else ""
    league   = str(match_df["league"].iloc[0]) if "league" in match_df.columns else ""
    season   = str(match_df["season"].iloc[0]) if "season" in match_df.columns else ""

    for player in match_df["playerName"].dropna().unique():
        dfp  = match_df[match_df["playerName"] == player]
        team = str(dfp["teamName"].iloc[0]) if "teamName" in dfp.columns and len(dfp) > 0 else ""

        # --- Minutes played (reuse compute_player_match_stats logic) ---
        if "cumulative_mins" in dfp.columns and len(dfp) > 0:
            first_min = float(dfp["cumulative_mins"].min())
            last_min  = float(dfp["cumulative_mins"].max())
            start_min = 0.0 if first_min < 5.0 else first_min
            mins_played = max(1, round(last_min - start_min))
        elif "minute" in dfp.columns and len(dfp) > 0:
            first_min  = int(dfp["minute"].min())
            last_min   = int(dfp["minute"].max())
            start_min  = 0 if first_min < 5 else first_min
            mins_played = max(1, last_min - start_min)
        else:
            mins_played = 0

        # --- Goals & xG ---
        goals = len(_type_filter(dfp, "Goal"))
        xg    = round(float(_safe_sum(dfp["xG"])), 3) if "xG" in dfp.columns else 0.0

        # --- Shots ---
        shots_df        = _type_filter_set(dfp, _SHOT_TYPES)
        shots           = len(shots_df)
        shots_on_target = len(_type_filter_set(shots_df, {"Goal", "SavedShot"}))

        # --- Key passes & xA ---
        xA_val = round(float(_safe_sum(dfp["xA"])), 3) if "xA" in dfp.columns else 0.0
        passes_dfp = _type_filter(dfp, "Pass")
        # passKey is the Opta flag; the xA>0 fallback only works on data where
        # xA was never model-backfilled onto every pass.
        if "passKey" in dfp.columns:
            key_passes = int(_numcol(dfp, "passKey").gt(0).sum())
        else:
            key_passes = (
                int(passes_dfp["xA"].gt(0).sum())
                if "xA" in passes_dfp.columns and len(passes_dfp) > 0
                else 0
            )

        # --- Progressive passes ---
        prog_passes = (
            int(dfp["prog_pass"].gt(0).sum())
            if "prog_pass" in dfp.columns
            else 0
        )

        # --- xT ---
        xT_val = round(float(_safe_sum(dfp["xT"])), 3) if "xT" in dfp.columns else 0.0

        # --- Tackles, interceptions & defensive ---
        tackles         = len(_type_filter(dfp, "Tackle"))
        interceptions   = len(_type_filter(dfp, "Interception"))
        clearances      = len(_type_filter(dfp, "Clearance"))
        fouls_committed = len(_type_filter(dfp, "Foul"))
        recoveries      = len(_type_filter(dfp, "BallRecovery"))
        blocked_passes  = len(_type_filter(dfp, "BlockedPass"))
        # Challenge = unsuccessful attempt to tackle (dribbled past)
        dribbled_past   = len(_type_filter(dfp, "Challenge"))
        aerials_dfp     = _type_filter(dfp, "Aerial")
        aerial_total    = len(aerials_dfp)
        aerial_won      = (
            int(aerials_dfp["outcomeType"].str.contains("Successful", na=False).sum())
            if "outcomeType" in aerials_dfp.columns and len(aerials_dfp) > 0 else 0
        )

        # --- Dribbles ---
        takeons_dfp        = _type_filter(dfp, "TakeOn")
        dribbles_attempted = len(takeons_dfp)
        dribbles_won       = (
            int(takeons_dfp["outcomeType"].str.contains("Successful", na=False).sum())
            if "outcomeType" in takeons_dfp.columns and len(takeons_dfp) > 0 else 0
        )

        # --- Big chances & shot quality ---
        big_chances   = (
            int(shots_df[shots_df["xG"] > 0.35].shape[0])
            if "xG" in shots_df.columns and len(shots_df) > 0 else 0
        )
        shot_accuracy = round(shots_on_target / max(1, shots) * 100, 1)
        xg_per_shot   = round(float(xg) / max(1, shots), 3)

        # --- Passing details ---
        passes_dfp    = _type_filter(dfp, "Pass")
        crosses       = 0
        through_balls = 0
        long_balls    = 0
        if "qualifiers" in passes_dfp.columns and len(passes_dfp) > 0:
            crosses       = int(passes_dfp["qualifiers"].str.contains("Cross",       na=False).sum())
            through_balls = int(passes_dfp["qualifiers"].str.contains("Throughball", na=False).sum())
            long_balls    = int(passes_dfp["qualifiers"].str.contains("Longball",    na=False).sum())

        # --- Cards ---
        yellow_cards = 0
        red_cards    = 0
        if "cardType" in dfp.columns:
            yellow_cards = int(dfp["cardType"].astype(str).str.contains("Yellow|SecondYellow", na=False).sum())
            red_cards    = int(dfp["cardType"].astype(str).str.contains("(?<![Ss]econd)Red|SecondYellow", na=False, regex=True).sum())

        # --- Table-parity metrics (mirror the analysis-view definitions) ---
        passes_attempted = len(passes_dfp)
        completed_mask = (
            passes_dfp["outcomeType"].astype(str).str.contains("Successful", na=False)
            if "outcomeType" in passes_dfp.columns and len(passes_dfp) > 0
            else pd.Series(False, index=passes_dfp.index)
        )
        completed_dfp = passes_dfp[completed_mask]
        pass_accuracy = round(len(completed_dfp) / passes_attempted * 100, 1) if passes_attempted else 0.0
        if len(completed_dfp) > 0 and "endX" in completed_dfp.columns:
            dist = ((_numcol(completed_dfp, "endX") - _numcol(completed_dfp, "x")) ** 2
                    + (_numcol(completed_dfp, "endY") - _numcol(completed_dfp, "y")) ** 2) ** 0.5
            avg_pass_distance = round(float(dist.mean()), 1)
        else:
            avg_pass_distance = 0.0
        end_x = _numcol(completed_dfp, "endX")
        end_y = _numcol(completed_dfp, "endY")
        final_third_passes = int((end_x > 75).sum())
        box_passes = int(((end_x >= 88.5) & end_y.between(13.6, 54.4)).sum())
        turnovers = len(_type_filter_set(dfp, {"Turnover", "Dispossessed"}))

        duels_df, duels_won_df = _duel_frames(dfp)
        duel_types = duels_df["type"].astype(str) if "type" in duels_df.columns else pd.Series("", index=duels_df.index)
        ground_duels = int(duel_types.isin(_GROUND_DUEL_TYPES).sum())

        def_df = _def_action_frame(dfp)
        def_x = _numcol(def_df, "x")

        extra = {
            "passes_attempted":        passes_attempted,
            "passes_received":         int(received_counts.get(player, 0)),
            "prog_passes_received":    int(received_prog_counts.get(player, 0)),
            "pass_accuracy":           pass_accuracy,
            "avg_pass_distance":       avg_pass_distance,
            "final_third_passes":      final_third_passes,
            "box_passes":              box_passes,
            "turnovers":               turnovers,
            "duels_total":             int(len(duels_df)),
            "duels_won":               int(len(duels_won_df)),
            "ground_duels":            ground_duels,
            "def_actions_total":       int(len(def_df)),
            "def_actions_def_third":   int((def_x < 35).sum()),
            "def_actions_mid_third":   int(((def_x >= 35) & (def_x < 70)).sum()),
            "def_actions_att_third":   int((def_x >= 70).sum()),
        }

        # --- Advanced metrics (only present when the source was backfilled) ---
        if "xGOT" in dfp.columns:
            extra["xGOT"] = round(float(_numcol(dfp, "xGOT").sum()), 3)
        if "epv_added" in dfp.columns:
            extra["epv_added"] = round(_pass_carry_value_sum(dfp, "epv_added"), 3)
        if "isTouch" in dfp.columns:
            extra["touches"] = int((dfp["isTouch"] == True).sum())
        if "type" in dfp.columns:
            extra["carries"] = len(_type_filter(dfp, "Carry"))
        if "prog_carry" in dfp.columns:
            extra["prog_carries"] = int(_numcol(dfp, "prog_carry").gt(0).sum())
        if "xG" in dfp.columns and "qualifiers" in shots_df.columns and len(shots_df) > 0:
            shots_q = shots_df["qualifiers"].astype(str)
            pen_mask = shots_q.str.contains("Penalty", na=False) & ~shots_q.str.contains("PenaltyShootout", na=False)
            pen_xg = float(pd.to_numeric(shots_df.loc[pen_mask, "xG"], errors="coerce").fillna(0).sum())
            extra["npxG"] = round(float(xg) - pen_xg, 3)
        elif "xG" in dfp.columns:
            extra["npxG"] = float(xg)
        if "xPass" in dfp.columns and len(passes_dfp) > 0:
            xp = pd.to_numeric(passes_dfp["xPass"], errors="coerce")
            extra["passes_completed"] = int(_successful_mask(passes_dfp).sum())
            extra["xpass_exp_completed"] = round(float(xp.dropna().sum()), 2)

        # --- Goalkeeper metrics (only for the team's identified keeper) ---
        if match_keepers.get(team) == player:
            extra.update(_compute_gk_match_stats(dfp, match_df, team))

        rows.append({
            "matchId":           match_id,
            "date":              date,
            "league":            league,
            "season":            season,
            "playerName":        player,
            "teamName":          team,
            "mins_played":       mins_played,
            "goals":             goals,
            "xG":                xg,
            "shots":             shots,
            "shots_on_target":   shots_on_target,
            "big_chances":       big_chances,
            "shot_accuracy":     shot_accuracy,
            "xG_per_shot":       xg_per_shot,
            "key_passes":        key_passes,
            "xA":                xA_val,
            "crosses":           crosses,
            "through_balls":     through_balls,
            "long_balls":        long_balls,
            "prog_passes":       prog_passes,
            "xT":                xT_val,
            "tackles":           tackles,
            "interceptions":     interceptions,
            "clearances":        clearances,
            "fouls_committed":   fouls_committed,
            "recoveries":        recoveries,
            "blocked_passes":    blocked_passes,
            "dribbled_past":     dribbled_past,
            "aerial_duels_total": aerial_total,
            "aerial_duels_won":  aerial_won,
            "dribbles_attempted": dribbles_attempted,
            "dribbles_won":      dribbles_won,
            "yellow_cards":      yellow_cards,
            "red_cards":         red_cards,
            **extra,
        })
    return rows


# ---------------------------------------------------------------------------
# Event locations extraction
# ---------------------------------------------------------------------------

_LOCATION_TYPES = {
    # Shots
    "Goal", "SavedShot", "MissedShots", "ShotOnPost",
    # Build-up
    "Pass", "Carry", "TakeOn",
    # Defensive
    "Tackle", "Interception", "Challenge", "Clearance",
    "BallRecovery", "BlockedPass", "Aerial", "Foul",
}

_LOC_KEEP_COLS = [
    "matchId", "startDate", "league", "season",
    "teamName", "playerName",
    "type", "outcomeType", "isGoal",
    "x", "y", "endX", "endY",
    "xG", "xA", "xT",
    "qualifiers", "period", "minute",
]


def _compute_event_locations(match_df: pd.DataFrame) -> pd.DataFrame:
    """Return a filtered DataFrame of trackable events with coordinate columns."""
    if "type" in match_df.columns:
        loc_df = match_df[match_df["type"].isin(_LOCATION_TYPES)].copy()
    else:
        # Fallback: boolean column union
        mask = pd.Series(False, index=match_df.index)
        for t in _LOCATION_TYPES:
            if t in match_df.columns:
                mask = mask | (match_df[t] == True)
        loc_df = match_df[mask].copy()

    # Keep only columns that exist
    keep = [c for c in _LOC_KEEP_COLS if c in loc_df.columns]
    loc_df = loc_df[keep].copy()

    # Rename startDate → date for consistency
    if "startDate" in loc_df.columns:
        loc_df["date"] = loc_df["startDate"].astype(str).str[:10]
        loc_df = loc_df.drop(columns=["startDate"])

    # Ensure numeric coordinate columns exist and are float
    for col in ["x", "y", "endX", "endY", "xG", "xA", "xT"]:
        if col not in loc_df.columns:
            loc_df[col] = 0.0
        else:
            loc_df[col] = pd.to_numeric(loc_df[col], errors="coerce").fillna(0.0)

    # Ensure bool isGoal
    if "isGoal" in loc_df.columns:
        loc_df["isGoal"] = loc_df["isGoal"].fillna(False).astype(bool)
    else:
        loc_df["isGoal"] = False

    # Hybrid source mixes float (SQLite) and str/int (R2) matchIds — a mixed
    # object column breaks the parquet write, so normalize to str here.
    if "matchId" in loc_df.columns:
        loc_df["matchId"] = loc_df["matchId"].map(_norm_match_id)

    return loc_df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Verification summary
# ---------------------------------------------------------------------------

def _print_verification(team_df: pd.DataFrame, player_df: pd.DataFrame, events_df: pd.DataFrame = None):
    """Print a quick sanity-check summary of the generated data."""
    print("\n  --- Verification ---")

    # Team stats
    if not team_df.empty:
        total_matches = team_df["matchId"].nunique()
        total_teams   = team_df["teamName"].nunique()
        print(f"  team_match_stats : {len(team_df)} rows | {total_matches} matches | {total_teams} teams")
        top_xg = team_df.groupby("teamName")["xG"].sum().nlargest(5).round(1)
        print("  Top 5 teams by xG:")
        for team, val in top_xg.items():
            print(f"    {team:<28} {val}")
    else:
        print("  team_match_stats : empty")

    # Player stats
    if not player_df.empty:
        total_players = player_df["playerName"].nunique()
        print(f"  player_match_stats: {len(player_df)} rows | {total_players} players")
        top_xg_p = player_df.groupby("playerName")["xG"].sum().nlargest(5).round(2)
        print("  Top 5 players by xG:")
        for player, val in top_xg_p.items():
            print(f"    {player:<28} {val}")
        top_goals = player_df.groupby("playerName")["goals"].sum().nlargest(5)
        print("  Top 5 players by goals:")
        for player, val in top_goals.items():
            print(f"    {player:<28} {int(val)}")
    else:
        print("  player_match_stats: empty")

    # Event locations
    if events_df is not None and not events_df.empty:
        print(f"  event_locations   : {len(events_df)} rows")
        if "type" in events_df.columns:
            type_counts = events_df["type"].value_counts().head(8)
            print("  Event type breakdown:")
            for etype, cnt in type_counts.items():
                print(f"    {etype:<28} {cnt}")
    else:
        print("  event_locations   : empty")

    print("  --------------------\n")


# ---------------------------------------------------------------------------
# R2 upload
# ---------------------------------------------------------------------------

def _upload_df(s3_client, df: pd.DataFrame, bucket: str, key: str):
    buf = io.BytesIO()
    df.to_parquet(buf, index=False)
    size_kb = buf.tell() // 1024
    buf.seek(0)
    s3_client.upload_fileobj(buf, bucket, key)
    print(f"  ✅ Uploaded s3://{bucket}/{key}  ({len(df)} rows, {size_kb} KB)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _dedupe_events(match_df: pd.DataFrame) -> pd.DataFrame:
    """Some SQLite matches contain the same events appended multiple times
    (e.g. re-scrapes) which inflates every counting stat. Drop exact repeats."""
    if "eventId" in match_df.columns:
        return match_df.drop_duplicates(subset=["eventId", "teamId"], keep="first")
    subset = [c for c in ("minute", "second", "teamId", "playerId", "type", "x", "y", "endX", "endY") if c in match_df.columns]
    if subset:
        return match_df.drop_duplicates(subset=subset, keep="first")
    return match_df


def _r2_match_id_from_key(key: str):
    """event_data keys look like {date}_{matchId}_{home}_vs_{away}_{score}.parquet."""
    name = key.rsplit("/", 1)[-1]
    parts = name.split("_")
    return parts[1] if len(parts) > 1 else None


def _list_r2_combos(s3, league_filter=None, season_filter=None):
    """Return [(league, season_key, [parquet keys])] discovered under event_data/."""
    paginator = s3.get_paginator("list_objects_v2")

    def child_prefixes(prefix):
        names = []
        for page in paginator.paginate(Bucket=R2_BUCKET, Prefix=prefix, Delimiter="/"):
            for cp in page.get("CommonPrefixes", []):
                names.append(cp["Prefix"].rstrip("/").split("/")[-1])
        return names

    combos = []
    for league in child_prefixes("event_data/"):
        if league_filter and league != league_filter:
            continue
        for season_key in child_prefixes(f"event_data/{league}/"):
            if season_filter and season_key != _clean_key(season_filter):
                continue
            keys = []
            for page in paginator.paginate(Bucket=R2_BUCKET, Prefix=f"event_data/{league}/{season_key}/"):
                for obj in page.get("Contents", []):
                    if obj["Key"].endswith(".parquet"):
                        keys.append(obj["Key"])
            if keys:
                combos.append((league, season_key, keys))
    return combos


def main():
    parser = argparse.ArgumentParser(description="Generate season summary stats and upload to R2.")
    parser.add_argument("--source", choices=["hybrid", "r2", "sqlite"], default="hybrid",
                        help="Event source: hybrid (default — full SQLite match list, enriched R2 parquet used per match "
                             "when one exists), r2 only (partial archive!), or sqlite only (no backfilled metrics)")
    parser.add_argument("--league",  help="Filter to a specific league slug, e.g. ligue-1")
    parser.add_argument("--season",  help="Filter to a specific season, e.g. 2025/2026 (or 2025_2026 with --source r2)")
    parser.add_argument("--dry-run", action="store_true", help="Compute but do not upload to R2")
    args = parser.parse_args()

    s3 = boto3.client(
        "s3",
        endpoint_url=ENDPOINT_URL,
        region_name="auto",
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
    )

    conn = None
    # Each combo yields (league, season_label, match count, iterator of (ref, DataFrame)).
    if args.source == "r2":
        r2_combos = _list_r2_combos(s3, args.league, args.season)
        print(f"Found {len(r2_combos)} (league, season) combinations in R2.\n")

        def combo_iter():
            for league, season_key, keys in r2_combos:
                def match_iter(keys=keys):
                    for key in keys:
                        obj = s3.get_object(Bucket=R2_BUCKET, Key=key)
                        yield key.rsplit("/", 1)[-1], pd.read_parquet(io.BytesIO(obj["Body"].read()))
                yield league, season_key, len(keys), match_iter()
    else:
        conn = sqlite3.connect(DB_PATH)
        print(f"Connected to {DB_PATH}")

        # Build query for distinct (league, season) combos
        query  = "SELECT DISTINCT league, season FROM event_data WHERE league IS NOT NULL AND season IS NOT NULL"
        params = []
        if args.league:
            query += " AND league = ?"
            params.append(args.league)
        if args.season:
            query += " AND season = ?"
            params.append(args.season)

        combos = pd.read_sql_query(query, conn, params=params)
        print(f"Found {len(combos)} (league, season) combinations to process.\n")

        # hybrid: map (league, season_key) -> {matchId: R2 key} so enriched
        # parquets replace the SQLite events for matches that have them.
        r2_keys_by_combo = {}
        if args.source == "hybrid":
            for league, season_key, keys in _list_r2_combos(s3, args.league, args.season):
                r2_keys_by_combo[(league, season_key)] = {
                    mid: key for key in keys if (mid := _r2_match_id_from_key(key))
                }

        def combo_iter():
            for _, row in combos.iterrows():
                league = row["league"]
                season = row["season"]
                match_ids = pd.read_sql_query(
                    "SELECT DISTINCT matchId FROM event_data WHERE league=? AND season=?",
                    conn, params=(league, season)
                )["matchId"].tolist()
                r2_keys = r2_keys_by_combo.get((_clean_key(league), _clean_key(season)), {})
                if r2_keys:
                    print(f"  [{league} {season}] {len(r2_keys)} of {len(match_ids)} matches have enriched R2 parquets")

                def match_iter(match_ids=match_ids, r2_keys=r2_keys):
                    for match_id in match_ids:
                        # SQLite stores matchId as REAL — str() yields "1903350.0"
                        mid = str(match_id)
                        if mid.endswith(".0"):
                            mid = mid[:-2]
                        r2_key = r2_keys.get(mid)
                        if r2_key:
                            obj = s3.get_object(Bucket=R2_BUCKET, Key=r2_key)
                            yield r2_key.rsplit("/", 1)[-1], pd.read_parquet(io.BytesIO(obj["Body"].read()))
                        else:
                            yield f"matchId={match_id}", pd.read_sql_query(
                                "SELECT * FROM event_data WHERE matchId=?",
                                conn, params=(match_id,)
                            )
                yield league, season, len(match_ids), match_iter()

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    for league, season, n_matches, matches in combo_iter():
        league_clean = _clean_key(league)
        season_clean = _clean_key(season)

        print(f"{'='*60}")
        print(f"League: {league}  |  Season: {season}  |  Source: {args.source}")
        print(f"  Matches: {n_matches}")

        team_rows    = []
        player_rows  = []
        history_rows = []
        event_frames = []
        failed       = 0

        for match_ref, match_df in matches:
            try:
                if match_df.empty:
                    continue
                match_df = _dedupe_events(match_df)
                match_df = _backfill_team_names(match_df)
                team_match_rows = _compute_team_match_stats(match_df)
                team_rows.extend(team_match_rows)
                player_rows.extend(_compute_player_match_stats(match_df))
                history_rows.extend(_compute_team_history(match_df, team_match_rows))
                event_frames.append(_compute_event_locations(match_df))
            except Exception as exc:
                failed += 1
                print(f"  [WARN] {match_ref}: {exc}")

        if failed:
            print(f"  {failed} match(es) skipped due to errors")

        if not team_rows:
            print("  No data — skipping upload")
            continue

        team_df     = pd.DataFrame(team_rows)
        player_df   = pd.DataFrame(player_rows)
        history_df  = pd.DataFrame(history_rows)
        events_df   = pd.concat(event_frames, ignore_index=True) if event_frames else pd.DataFrame()
        for df_out in (team_df, player_df, history_df):
            if df_out.empty:
                continue
            df_out["source"] = args.source
            df_out["generated_at"] = generated_at
            df_out["schema_version"] = SCHEMA_VERSION
        print(f"  team_match_stats shape:   {team_df.shape}")
        print(f"  player_match_stats shape: {player_df.shape}")
        print(f"  team_history shape:       {history_df.shape}")
        print(f"  event_locations shape:    {events_df.shape}")

        if args.dry_run:
            # Save locally so you can inspect the output
            local_dir = os.path.join(os.path.dirname(__file__), "season_stats", league_clean, season_clean)
            os.makedirs(local_dir, exist_ok=True)
            team_path   = os.path.join(local_dir, "team_match_stats.parquet")
            player_path = os.path.join(local_dir, "player_match_stats.parquet")
            history_path = os.path.join(local_dir, "team_history.parquet")
            events_path = os.path.join(local_dir, "event_locations.parquet")
            team_df.to_parquet(team_path,   index=False)
            player_df.to_parquet(player_path, index=False)
            if not history_df.empty:
                history_df.to_parquet(history_path, index=False)
            if not events_df.empty:
                events_df.to_parquet(events_path, index=False)
            print(f"  [dry-run] Saved locally:")
            print(f"    {team_path}")
            print(f"    {player_path}")
            print(f"    {history_path}  ({len(history_df)} rows)")
            print(f"    {events_path}  ({len(events_df)} rows)")
            _print_verification(team_df, player_df, events_df)
            continue

        team_key    = f"season_stats/{league_clean}/{season_clean}/team_match_stats.parquet"
        player_key  = f"season_stats/{league_clean}/{season_clean}/player_match_stats.parquet"
        history_key = f"season_stats/{league_clean}/{season_clean}/team_history.parquet"
        events_key  = f"season_stats/{league_clean}/{season_clean}/event_locations.parquet"
        _upload_df(s3, team_df,   R2_BUCKET, team_key)
        _upload_df(s3, player_df, R2_BUCKET, player_key)
        if not history_df.empty:
            _upload_df(s3, history_df, R2_BUCKET, history_key)
        if not events_df.empty:
            _upload_df(s3, events_df, R2_BUCKET, events_key)

    if conn is not None:
        conn.close()
    print("\nAll done.")


if __name__ == "__main__":
    main()
