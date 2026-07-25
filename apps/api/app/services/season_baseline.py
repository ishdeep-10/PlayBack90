"""Season-baseline view: a team's/player's match performance vs their season.

Match values are computed with the same metric definitions as
Data/generate_season_stats.py so they are directly comparable to the
per-match rows stored in season_stats/{league}/{season}/*.parquet.
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np
import pandas as pd

from app.schemas import MatchContext
from app.services import season_stats as ss
from app.services.opposition import _percentile

# Small-sample thresholds surfaced to the frontend via meta.
TEAM_MATCHES_MIN = 4
PLAYER_MINS_MIN = 450
MATCH_MINS_MIN = 20

_DEF_TYPES = {"Tackle", "Interception", "Challenge", "BlockedPass"}
_SHOT_TYPES = {"Goal", "SavedShot", "MissedShots", "ShotOnPost"}

# season column, frontend key, label, lower-is-better
_TEAM_METRICS: list[tuple[str, str, str, bool]] = [
    ("goals", "goals", "Goals", False),
    ("xG", "xg", "xG", False),
    ("shots", "shots", "Shots", False),
    ("shots_on_target", "shots_on_target", "Shots on Target", False),
    ("possession_pct", "possession_pct", "Possession %", False),
    ("pass_accuracy", "pass_accuracy", "Pass Accuracy", False),
    ("big_chances", "big_chances_created", "Big Chances", False),
    ("ppda", "ppda", "PPDA", True),
    ("turnovers", "turnovers", "Turnovers", True),
    ("crosses", "crosses", "Crosses", False),
    ("dribbles_won", "dribbles_won", "Dribbles Won", False),
    # Phase 4 columns — skipped automatically until present in season parquet.
    ("xGOT", "xgot", "xGOT", False),
    ("xT", "xt", "xT", False),
    ("epv_added", "epv_added", "EPV", False),
]

_PLAYER_METRICS: list[tuple[str, str, str, bool]] = [
    ("goals", "goals", "Goals", False),
    ("shots", "shots", "Shots", False),
    ("shots_on_target", "shots_on_target", "Shots on Target", False),
    ("big_chances", "big_chances", "Big Chances", False),
    ("key_passes", "key_passes", "Key Passes", False),
    ("xA", "xa", "xA", False),
    ("xG", "xg", "xG", False),
    ("xT", "xt", "xT", False),
    ("prog_passes", "progressive_passes", "Progressive Passes", False),
    ("crosses", "crosses", "Crosses", False),
    ("through_balls", "through_balls", "Through Balls", False),
    ("long_balls", "long_balls", "Long Balls", False),
    ("tackles", "tackles", "Tackles", False),
    ("interceptions", "interceptions", "Interceptions", False),
    ("clearances", "clearances", "Clearances", False),
    ("fouls_committed", "fouls_committed", "Fouls", True),
    ("recoveries", "recoveries", "Ball Recoveries", False),
    ("blocked_passes", "blocked_passes", "Blocked Passes", False),
    ("dribbled_past", "dribbled_past", "Dribbled Past", True),
    ("dribbles_attempted", "take_ons", "Take Ons", False),
    ("dribbles_won", "take_ons_won", "Take Ons Won", False),
    ("aerial_duels_total", "aerial_duels", "Aerial Duels", False),
    ("aerial_duels_won", "aerial_duels_won", "Aerials Won", False),
    # Schema-v2 columns — skipped automatically until present.
    ("xGOT", "xgot", "xGOT", False),
    ("npxG", "npxg", "npxG", False),
    ("epv_added", "epv_added", "EPV", False),
    ("touches", "touches", "Touches", False),
    ("carries", "carries", "Carries", False),
    ("prog_carries", "prog_carries", "Progressive Carries", False),
    ("passes_completed", "passes_completed", "Passes Completed", False),
    # Schema-v4 table-parity columns.
    ("passes_attempted", "passes_attempted", "Passes Attempted", False),
    ("passes_received", "passes_received", "Passes Received", False),
    ("prog_passes_received", "progressive_passes_received", "Prog Passes Received", False),
    ("pass_accuracy", "pass_accuracy", "Pass Accuracy", False),
    ("avg_pass_distance", "avg_pass_distance", "Avg Pass Distance", False),
    ("final_third_passes", "final_third_passes", "Final Third Passes", False),
    ("box_passes", "box_passes", "Box Passes", False),
    ("turnovers", "turnovers", "Turnovers", True),
    ("duels_total", "duels", "Duels", False),
    ("duels_won", "duels_won", "Duels Won", False),
    ("duels_lost", "duels_lost", "Duels Lost", True),
    ("duel_win_pct", "duel_win_pct", "Duel Win %", False),
    ("ground_duels", "ground_duels", "Ground Duels", False),
    ("def_actions_total", "def_actions_total", "Def Actions", False),
    ("def_actions_def_third", "def_actions_def_third", "Def 3rd Actions", False),
    ("def_actions_mid_third", "def_actions_mid_third", "Mid 3rd Actions", False),
    ("def_actions_att_third", "def_actions_att_third", "Att 3rd Actions", False),
]

# Rate/average metrics: per-90 scaling is meaningless — chips and baselines
# compare the value directly.
_RATE_COLS = {"pass_accuracy", "avg_pass_distance", "duel_win_pct"}

# Phase tabs for the Season Context panel — one selector drives both the
# match-vs-season dumbbell strips and the percentile radar.
_METRIC_GROUPS = [
    {"id": "in_possession", "label": "In Possession",
     "keys": ["touches", "passes_completed", "key_passes", "xa", "xt", "epv_added",
              "progressive_passes", "carries", "prog_carries", "crosses", "through_balls", "long_balls"]},
    {"id": "duels", "label": "Duels",
     "keys": ["duels", "duels_won", "ground_duels", "take_ons", "take_ons_won",
              "aerial_duels", "aerial_duels_won", "tackles", "fouls_committed"]},
    {"id": "shots", "label": "Shots",
     "keys": ["goals", "shots", "shots_on_target", "big_chances", "xg", "npxg", "xgot"]},
    {"id": "out_of_possession", "label": "Out of Possession",
     "keys": ["def_actions_total", "tackles", "interceptions", "recoveries", "blocked_passes",
              "clearances", "dribbled_past", "aerial_duels_won"]},
]


# ── season parquet cache ──────────────────────────────────────────────────────

_CACHE: dict[tuple[str, str], tuple[float, pd.DataFrame, pd.DataFrame]] = {}
_CACHE_TTL_SECONDS = 900
_CACHE_MAX_ITEMS = 16


def _norm_match_id(value: Any) -> str:
    """Season parquets store matchId as '1903353.0'; contexts use '1903353'."""
    s = str(value)
    return s[:-2] if s.endswith(".0") else s


def _exclude_current_match(df: pd.DataFrame, match_id: str) -> pd.DataFrame:
    if df.empty or "matchId" not in df.columns:
        return df
    return df[df["matchId"].map(_norm_match_id) != _norm_match_id(match_id)]


def _load_cached_season_dfs(league: str, season: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    key = (league, season)
    now = time.monotonic()
    cached = _CACHE.get(key)
    if cached is not None and (now - cached[0]) < _CACHE_TTL_SECONDS:
        return cached[1], cached[2]

    team_df = ss.load_team_season_stats(league, season)
    player_df = ss.load_player_season_stats(league, season)

    if len(_CACHE) >= _CACHE_MAX_ITEMS:
        oldest = min(_CACHE, key=lambda k: _CACHE[k][0])
        _CACHE.pop(oldest, None)
    _CACHE[key] = (now, team_df, player_df)
    return team_df, player_df


# ── match-value computation (mirrors generate_season_stats definitions) ──────

def _types(df: pd.DataFrame) -> pd.Series:
    if "type" in df.columns:
        return df["type"].astype(str)
    return pd.Series("", index=df.index, dtype=str)


def _qualifier_count(passes: pd.DataFrame, token: str) -> int:
    if "qualifiers" not in passes.columns or passes.empty:
        return 0
    return int(passes["qualifiers"].astype(str).str.contains(token, na=False).sum())


def _successful_count(df: pd.DataFrame) -> int:
    if "outcomeType" not in df.columns or df.empty:
        return 0
    return int(df["outcomeType"].astype(str).str.contains("Successful", na=False).sum())


def _num(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(df[col], errors="coerce").fillna(0.0)


def compute_team_match_values(match_df: pd.DataFrame, team: str) -> dict[str, float]:
    t = match_df[match_df.get("teamName") == team]
    opp = match_df[(match_df.get("teamName") != team) & match_df.get("teamName").notna()]
    types_t = _types(t)

    shots_df = t[types_t.isin(_SHOT_TYPES)]
    shots = len(shots_df)
    shots_on_target = int(_types(shots_df).isin({"Goal", "SavedShot"}).sum())

    passes_df = t[types_t == "Pass"]
    passes = len(passes_df)
    pass_accuracy = round(_successful_count(passes_df) / passes * 100, 1) if passes else 0.0

    team_def = int(types_t.isin(_DEF_TYPES).sum())
    opp_passes = int((_types(opp) == "Pass").sum())
    ppda = round(opp_passes / max(1, team_def), 2)

    total_events = len(match_df)
    possession_pct = round(len(t) / total_events * 100, 1) if total_events else 0.0

    xg_series = _num(shots_df, "xG")
    takeons = t[types_t == "TakeOn"]

    values: dict[str, float] = {
        "goals": float((types_t == "Goal").sum()),
        "xG": round(float(_num(t, "xG").sum()), 3),
        "shots": float(shots),
        "shots_on_target": float(shots_on_target),
        "possession_pct": possession_pct,
        "pass_accuracy": pass_accuracy,
        "big_chances": float((xg_series > 0.35).sum()) if not xg_series.empty else 0.0,
        "ppda": ppda,
        "turnovers": float(types_t.isin({"Turnover", "Dispossessed"}).sum()),
        "crosses": float(_qualifier_count(passes_df, "Cross")),
        "dribbles_won": float(_successful_count(takeons)),
    }
    if "xGOT" in t.columns:
        values["xGOT"] = round(float(_num(t, "xGOT").sum()), 3)
    if "xT" in t.columns:
        xt_df = t[types_t.isin(["Pass", "Carry"])]
        if "outcomeType" in xt_df.columns:
            xt_df = xt_df[xt_df["outcomeType"].astype(str) == "Successful"]
        values["xT"] = round(float(_num(xt_df, "xT").clip(lower=0.0).sum()), 3)
    if "epv_added" in t.columns:
        epv_df = t[types_t.isin(["Pass", "Carry"])]
        if "outcomeType" in epv_df.columns:
            epv_df = epv_df[epv_df["outcomeType"].astype(str) == "Successful"]
        values["epv_added"] = round(float(_num(epv_df, "epv_added").sum()), 3)
    return values


def _player_minutes(dfp: pd.DataFrame) -> int:
    if "cumulative_mins" in dfp.columns and len(dfp) > 0:
        mins = pd.to_numeric(dfp["cumulative_mins"], errors="coerce").dropna()
        if not mins.empty:
            first_min = float(mins.min())
            last_min = float(mins.max())
            start_min = 0.0 if first_min < 5.0 else first_min
            return max(1, round(last_min - start_min))
    if "minute" in dfp.columns and len(dfp) > 0:
        mins = pd.to_numeric(dfp["minute"], errors="coerce").dropna()
        if not mins.empty:
            first_min = int(mins.min())
            last_min = int(mins.max())
            start_min = 0 if first_min < 5 else first_min
            return max(1, last_min - start_min)
    return 0


_GROUND_DUEL_TYPES = {"TakeOn", "GoodSkill", "ShieldBallOpp", "Foul", "Tackle", "Challenge"}
_DEF_ACTION_TYPES = {"Aerial", "BallRecovery", "BlockedPass", "Challenge", "Clearance",
                     "Error", "Foul", "Interception", "Tackle"}


def _bool_col_true(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(False, index=df.index)
    return pd.to_numeric(df[col], errors="coerce").fillna(0) > 0


def _player_duels(dfp: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Mirrors _duel_frames in Data/generate_season_stats.py."""
    types = _types(dfp)
    aerial = _bool_col_true(dfp, "duelAerialWon") | _bool_col_true(dfp, "duelAerialLost") | types.eq("Aerial")
    ground = types.isin(_GROUND_DUEL_TYPES)
    duels = dfp[aerial | ground]
    aerial_won = _bool_col_true(duels, "duelAerialWon")
    aerial_lost = _bool_col_true(duels, "duelAerialLost")
    if "outcomeType" in duels.columns:
        outcome = duels["outcomeType"].astype(str).str.lower()
        other_won = outcome.isin(["successful", "nan", ""]) | duels["outcomeType"].isna()
    else:
        other_won = pd.Series(True, index=duels.index)
    return duels, duels[aerial_won | (~aerial_lost & other_won)]


def _player_def_actions(dfp: pd.DataFrame) -> pd.DataFrame:
    """Mirrors _def_action_frame in Data/generate_season_stats.py."""
    types = _types(dfp)
    mask = types.isin(_DEF_ACTION_TYPES)
    if "qualifiers" in dfp.columns:
        mask = mask & ((types != "Aerial") | dfp["qualifiers"].astype(str).str.contains("Defensive", case=False, na=False))
    if "outcomeType" in dfp.columns:
        outcome = dfp["outcomeType"].astype(str).str.lower()
        mask = mask & (outcome.eq("successful") | outcome.eq("nan") | dfp["outcomeType"].isna())
    return dfp[mask]


def _pass_receiver_series(match_df: pd.DataFrame) -> pd.Series:
    """Receiver of each successful pass = next event's player when same team."""
    df = match_df.sort_index()
    types = _types(df)
    outcome = df["outcomeType"].astype(str) if "outcomeType" in df.columns else pd.Series("", index=df.index)
    next_player = df["playerName"].shift(-1) if "playerName" in df.columns else pd.Series(index=df.index, dtype=object)
    next_team = df["teamName"].shift(-1) if "teamName" in df.columns else pd.Series(index=df.index, dtype=object)
    ok = types.eq("Pass") & outcome.str.contains("Successful", na=False) & (next_team == df.get("teamName"))
    return pd.Series(np.where(ok, next_player, None), index=df.index)


def compute_player_match_values(
    dfp: pd.DataFrame,
    passes_received: int = 0,
    prog_passes_received: int = 0,
) -> tuple[dict[str, float], int]:
    types_p = _types(dfp)
    shots_df = dfp[types_p.isin(_SHOT_TYPES)]
    passes_dfp = dfp[types_p == "Pass"]
    takeons = dfp[types_p == "TakeOn"]
    aerials = dfp[types_p == "Aerial"]

    # passKey is the Opta flag; xA>0 only works on un-backfilled data where xA
    # existed solely on direct shot assists.
    key_passes = 0
    if "passKey" in dfp.columns:
        key_passes = int(pd.to_numeric(dfp["passKey"], errors="coerce").fillna(0).gt(0).sum())
    elif "xA" in passes_dfp.columns and len(passes_dfp) > 0:
        key_passes = int(pd.to_numeric(passes_dfp["xA"], errors="coerce").fillna(0).gt(0).sum())

    prog_passes = 0
    if "prog_pass" in dfp.columns:
        prog_passes = int(pd.to_numeric(dfp["prog_pass"], errors="coerce").fillna(0).gt(0).sum())

    xg_total = round(float(_num(dfp, "xG").sum()), 3)
    shot_xg = _num(shots_df, "xG")

    values: dict[str, float] = {
        "goals": float((types_p == "Goal").sum()),
        "shots": float(len(shots_df)),
        "shots_on_target": float(_types(shots_df).isin({"Goal", "SavedShot"}).sum()),
        "big_chances": float((shot_xg > 0.35).sum()) if not shot_xg.empty else 0.0,
        "key_passes": float(key_passes),
        "xA": round(float(_num(dfp, "xA").sum()), 3),
        "xG": xg_total,
        "xT": round(float(_num(dfp, "xT").sum()), 3),
        "prog_passes": float(prog_passes),
        "crosses": float(_qualifier_count(passes_dfp, "Cross")),
        "through_balls": float(_qualifier_count(passes_dfp, "Throughball")),
        "long_balls": float(_qualifier_count(passes_dfp, "Longball")),
        "tackles": float((types_p == "Tackle").sum()),
        "interceptions": float((types_p == "Interception").sum()),
        "clearances": float((types_p == "Clearance").sum()),
        "fouls_committed": float((types_p == "Foul").sum()),
        "recoveries": float((types_p == "BallRecovery").sum()),
        "blocked_passes": float((types_p == "BlockedPass").sum()),
        "dribbled_past": float((types_p == "Challenge").sum()),
        "dribbles_attempted": float(len(takeons)),
        "dribbles_won": float(_successful_count(takeons)),
        "aerial_duels_total": float(len(aerials)),
        "aerial_duels_won": float(_successful_count(aerials)),
        "passes_completed": float(_successful_count(passes_dfp)),
        "carries": float((types_p == "Carry").sum()),
    }
    if "qualifiers" in shots_df.columns and len(shots_df) > 0:
        shots_q = shots_df["qualifiers"].astype(str)
        pen_mask = shots_q.str.contains("Penalty", na=False) & ~shots_q.str.contains("PenaltyShootout", na=False)
        pen_xg = float(pd.to_numeric(shots_df.loc[pen_mask, "xG"], errors="coerce").fillna(0).sum())
        values["npxG"] = round(xg_total - pen_xg, 3)
    else:
        values["npxG"] = xg_total
    # Table-parity metrics (mirror the analysis-view definitions).
    completed_dfp = (
        passes_dfp[passes_dfp["outcomeType"].astype(str).str.contains("Successful", na=False)]
        if "outcomeType" in passes_dfp.columns
        else passes_dfp.iloc[0:0]
    )
    passes_attempted = len(passes_dfp)
    values["passes_attempted"] = float(passes_attempted)
    values["pass_accuracy"] = round(len(completed_dfp) / passes_attempted * 100, 1) if passes_attempted else 0.0
    if len(completed_dfp) > 0 and "endX" in completed_dfp.columns:
        dist = ((_num(completed_dfp, "endX") - _num(completed_dfp, "x")) ** 2
                + (_num(completed_dfp, "endY") - _num(completed_dfp, "y")) ** 2) ** 0.5
        values["avg_pass_distance"] = round(float(dist.mean()), 1)
    else:
        values["avg_pass_distance"] = 0.0
    end_x = _num(completed_dfp, "endX")
    end_y = _num(completed_dfp, "endY")
    values["final_third_passes"] = float((end_x > 75).sum())
    values["box_passes"] = float(((end_x >= 88.5) & end_y.between(13.6, 54.4)).sum())
    values["turnovers"] = float(types_p.isin({"Turnover", "Dispossessed"}).sum())
    values["passes_received"] = float(passes_received)
    values["prog_passes_received"] = float(prog_passes_received)

    duels_df, duels_won_df = _player_duels(dfp)
    values["duels_total"] = float(len(duels_df))
    values["duels_won"] = float(len(duels_won_df))
    values["duels_lost"] = float(len(duels_df) - len(duels_won_df))
    values["duel_win_pct"] = round(len(duels_won_df) / len(duels_df) * 100, 1) if len(duels_df) else 0.0
    values["ground_duels"] = float(_types(duels_df).isin(_GROUND_DUEL_TYPES).sum())

    def_df = _player_def_actions(dfp)
    def_x = _num(def_df, "x")
    values["def_actions_total"] = float(len(def_df))
    values["def_actions_def_third"] = float((def_x < 35).sum())
    values["def_actions_mid_third"] = float(((def_x >= 35) & (def_x < 70)).sum())
    values["def_actions_att_third"] = float((def_x >= 70).sum())

    if "isTouch" in dfp.columns:
        values["touches"] = float((dfp["isTouch"] == True).sum())  # noqa: E712
    if "prog_carry" in dfp.columns:
        values["prog_carries"] = float(pd.to_numeric(dfp["prog_carry"], errors="coerce").fillna(0).gt(0).sum())
    if "xGOT" in dfp.columns:
        values["xGOT"] = round(float(_num(dfp, "xGOT").sum()), 3)
    if "epv_added" in dfp.columns:
        epv_df = dfp[types_p.isin(["Pass", "Carry"])]
        if "outcomeType" in epv_df.columns:
            epv_df = epv_df[epv_df["outcomeType"].astype(str) == "Successful"]
        values["epv_added"] = round(float(_num(epv_df, "epv_added").sum()), 3)
    return values, _player_minutes(dfp)


# ── baseline builders ─────────────────────────────────────────────────────────

def _round(value: float, digits: int = 2) -> float:
    return round(float(value), digits)


def _metric_entry(
    key: str,
    label: str,
    lower_is_better: bool,
    match_value: float,
    own_series: pd.Series,
    league_series: pd.Series,
    last5_series: pd.Series,
) -> dict[str, Any]:
    own = pd.to_numeric(own_series, errors="coerce").dropna()
    n_matches = int(len(own))
    entry: dict[str, Any] = {
        "key": key,
        "label": label,
        "lowerIsBetter": lower_is_better,
        "matchValue": _round(match_value),
        "nMatches": n_matches,
    }
    if n_matches == 0:
        return entry

    mean = float(own.mean())
    std = float(own.std(ddof=0))
    # gameRank: 1 = best performance of the season (counting this match)
    if lower_is_better:
        worse_count = int((own < match_value).sum())
    else:
        worse_count = int((own > match_value).sum())
    game_rank = worse_count + 1

    entry.update({
        "seasonAvg": _round(mean),
        "seasonMedian": _round(float(own.median())),
        "p25": _round(float(own.quantile(0.25))),
        "p75": _round(float(own.quantile(0.75))),
        "min": _round(float(own.min())),
        "max": _round(float(own.max())),
        "delta": _round(match_value - mean),
        "zScore": _round((match_value - mean) / std) if std > 1e-9 else 0.0,
        "pctOfOwnMatches": _round(_percentile(own, match_value, not lower_is_better), 1),
        "gameRank": game_rank,
    })
    league = pd.to_numeric(league_series, errors="coerce").dropna()
    if not league.empty:
        entry["leaguePercentile"] = _round(_percentile(league, match_value, not lower_is_better), 1)
    last5 = pd.to_numeric(last5_series, errors="coerce").dropna()
    if not last5.empty:
        entry["last5Avg"] = _round(float(last5.mean()))
    return entry


def build_team_season_baseline(
    match_df: pd.DataFrame,
    context: MatchContext,
    team_season_df: pd.DataFrame,
) -> dict[str, Any]:
    teams: dict[str, Any] = {}
    if team_season_df.empty or "teamName" not in team_season_df.columns:
        return teams

    season_df = _exclude_current_match(team_season_df, context.match_id)

    for team in (context.home_team, context.away_team):
        opponent = context.away_team if team == context.home_team else context.home_team
        t_season = season_df[season_df["teamName"] == team]
        if len(t_season) < TEAM_MATCHES_MIN:
            teams[team] = {"matchesPlayed": int(len(t_season)), "lowSample": True, "metrics": [], "matches": []}
            continue
        t_recent = t_season.sort_values("date", ascending=False).head(5)
        # What all teams have managed AGAINST tonight's opponent this season.
        vs_opp = season_df[season_df.get("opponentName", pd.Series(dtype=object)) == opponent]
        match_values = compute_team_match_values(match_df, team)
        metrics = []
        for col, key, label, lower in _TEAM_METRICS:
            if col not in t_season.columns or col not in match_values:
                continue
            entry = _metric_entry(
                key, label, lower,
                match_values[col],
                t_season[col],
                season_df[col],
                t_recent[col],
            )
            if col in vs_opp.columns and len(vs_opp) >= TEAM_MATCHES_MIN:
                pool = pd.to_numeric(vs_opp[col], errors="coerce").dropna()
                if not pool.empty:
                    entry["vsOpponentAvg"] = _round(float(pool.mean()))
                    entry["vsOpponentMedian"] = _round(float(pool.median()))
                    entry["vsOpponentP25"] = _round(float(pool.quantile(0.25)))
                    entry["vsOpponentP75"] = _round(float(pool.quantile(0.75)))
                    entry["vsOpponentMin"] = _round(float(pool.min()))
                    entry["vsOpponentMax"] = _round(float(pool.max()))
                    entry["nVsOpponent"] = int(len(pool))
            metrics.append(entry)

        # Per-match season rows for the scatter and rolling-form visuals.
        season_matches = []
        for _, row in t_season.sort_values("date").iterrows():
            goals = int(pd.to_numeric(row.get("goals"), errors="coerce") or 0)
            goals_against = int(pd.to_numeric(row.get("goals_against"), errors="coerce") or 0)
            season_matches.append({
                "matchId": _norm_match_id(row.get("matchId")),
                "date": str(row.get("date", "")),
                "opponent": str(row.get("opponentName", "")),
                "homeAway": str(row.get("homeAway", "")),
                "result": "W" if goals > goals_against else ("D" if goals == goals_against else "L"),
                "goals": goals,
                "goalsAgainst": goals_against,
                "xg": _round(float(pd.to_numeric(row.get("xG"), errors="coerce") or 0.0)),
                "xga": _round(float(pd.to_numeric(row.get("xG_against"), errors="coerce") or 0.0)),
            })

        teams[team] = {
            "matchesPlayed": int(len(t_season)),
            "lowSample": False,
            "metrics": metrics,
            "matches": season_matches,
        }
    return teams


def build_player_season_baseline(
    match_df: pd.DataFrame,
    context: MatchContext,
    player_season_df: pd.DataFrame,
) -> dict[str, Any]:
    players: dict[str, Any] = {}
    if (
        match_df.empty
        or "playerName" not in match_df.columns
        or player_season_df.empty
        or "playerName" not in player_season_df.columns
    ):
        return players

    season_df = _exclude_current_match(player_season_df, context.match_id).copy()
    # Derived duel columns (the parquet stores totals and wins only).
    if {"duels_total", "duels_won"} <= set(season_df.columns):
        totals = pd.to_numeric(season_df["duels_total"], errors="coerce").fillna(0)
        wins = pd.to_numeric(season_df["duels_won"], errors="coerce").fillna(0)
        season_df["duels_lost"] = totals - wins
        season_df["duel_win_pct"] = (wins / totals.clip(lower=1) * 100).round(1)
    season_mins = pd.to_numeric(season_df.get("mins_played", pd.Series(dtype=float)), errors="coerce").fillna(0)

    # League per-90 pool for percentiles: season totals per player, minutes-gated.
    # Rate metrics are averaged, not summed.
    count_cols = [col for col, *_ in _PLAYER_METRICS if col in season_df.columns and col not in _RATE_COLS]
    agg_cols: dict[str, str] = {col: "sum" for col in count_cols}
    agg_cols["mins_played"] = "sum"
    league_agg = season_df.groupby("playerName").agg(agg_cols)
    league_agg = league_agg[league_agg["mins_played"] >= PLAYER_MINS_MIN]
    league_per90 = league_agg.drop(columns=["mins_played"]).div(
        league_agg["mins_played"].clip(lower=1), axis=0
    ) * 90
    rate_cols = [col for col, *_ in _PLAYER_METRICS if col in season_df.columns and col in _RATE_COLS]
    league_rates = (
        season_df[season_df["playerName"].isin(league_agg.index)]
        .groupby("playerName")[rate_cols]
        .mean()
        if rate_cols
        else pd.DataFrame()
    )

    # Receiver counts need the whole match frame, not just the player's rows.
    receivers = _pass_receiver_series(match_df)
    received_counts = receivers.dropna().value_counts()
    prog_received = (
        receivers[pd.to_numeric(match_df.get("prog_pass", pd.Series(dtype=float)), errors="coerce").fillna(0) > 0]
        if "prog_pass" in match_df.columns
        else pd.Series(dtype=object)
    )
    prog_received_counts = prog_received.dropna().value_counts()

    for player in match_df["playerName"].dropna().unique():
        dfp = match_df[match_df["playerName"] == player]
        team = str(dfp["teamName"].iloc[0]) if "teamName" in dfp.columns and len(dfp) else ""
        p_season = season_df[season_df["playerName"] == player]
        if p_season.empty:
            continue

        p_mins_season = float(season_mins.loc[p_season.index].sum())
        match_values, match_mins = compute_player_match_values(
            dfp,
            passes_received=int(received_counts.get(player, 0)),
            prog_passes_received=int(prog_received_counts.get(player, 0)),
        )
        low_sample = p_mins_season < PLAYER_MINS_MIN or match_mins < MATCH_MINS_MIN
        p_recent = p_season.sort_values("date", ascending=False).head(5)
        p_season_mins_sum = max(1.0, p_mins_season)

        metrics = []
        for col, key, label, lower in _PLAYER_METRICS:
            if col not in p_season.columns or col not in match_values:
                continue
            entry = _metric_entry(
                key, label, lower,
                match_values[col],
                p_season[col],
                pd.Series(dtype=float),  # league percentile handled below
                p_recent[col],
            )
            is_rate = col in _RATE_COLS
            entry["kind"] = "rate" if is_rate else "count"
            if is_rate:
                # Rates compare directly; reuse the per-90 fields so the chips
                # and charts have one code path (the values are just the rates).
                entry["seasonPer90"] = entry.get("seasonAvg", _round(float(pd.to_numeric(p_season[col], errors="coerce").mean() or 0)))
                if match_mins >= MATCH_MINS_MIN:
                    entry["matchValuePer90"] = _round(match_values[col])
                if not league_rates.empty and col in league_rates.columns:
                    pool = league_rates[col].dropna()
                    if len(pool) >= 10:
                        entry["leagueMeanPer90"] = _round(float(pool.mean()))
                        entry["leagueStdPer90"] = _round(float(pool.std(ddof=0)), 3)
                    if not low_sample and player in league_rates.index:
                        entry["leaguePercentilePer90"] = _round(
                            _percentile(pool, float(league_rates.at[player, col]), not lower), 1
                        )
            else:
                season_total = float(pd.to_numeric(p_season[col], errors="coerce").fillna(0).sum())
                entry["seasonPer90"] = _round(season_total / p_season_mins_sum * 90)
                if match_mins >= MATCH_MINS_MIN:
                    entry["matchValuePer90"] = _round(match_values[col] / max(1, match_mins) * 90)
                if col in league_per90.columns:
                    pool = league_per90[col].dropna()
                    if len(pool) >= 10:
                        entry["leagueMeanPer90"] = _round(float(pool.mean()))
                        entry["leagueStdPer90"] = _round(float(pool.std(ddof=0)), 3)
                if not low_sample and col in league_per90.columns and player in league_per90.index:
                    entry["leaguePercentilePer90"] = _round(
                        _percentile(league_per90[col], float(league_per90.at[player, col]), not lower), 1
                    )
            metrics.append(entry)

        players[str(player)] = {
            "team": team,
            "minsSeason": int(p_mins_season),
            "matchesPlayed": int(len(p_season)),
            "matchMins": int(match_mins),
            "lowSample": bool(low_sample),
            "positionGroup": None,
            "metrics": metrics,
        }
    return players


def build_season_baseline_view(match_df: pd.DataFrame, context: MatchContext) -> dict[str, Any]:
    league = context.league
    season = context.season
    if not league or not season:
        return {"available": False, "reason": "League/season unknown for this match."}

    team_season_df, player_season_df = _load_cached_season_dfs(league, season)
    if team_season_df.empty:
        return {"available": False, "reason": f"No season stats found for {league} {season}."}

    source = (
        str(team_season_df["source"].iloc[0])
        if "source" in team_season_df.columns and len(team_season_df)
        else "sqlite"
    )
    return {
        "available": True,
        "meta": {
            "league": league,
            "season": season,
            "source": source,
            "teamMatchesMin": TEAM_MATCHES_MIN,
            "playerMinsMin": PLAYER_MINS_MIN,
            "matchMinsMin": MATCH_MINS_MIN,
            "metricGroups": _METRIC_GROUPS,
        },
        "teams": build_team_season_baseline(match_df, context, team_season_df),
        "players": build_player_season_baseline(match_df, context, player_season_df),
    }
