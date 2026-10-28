"""Turn cached Dribble360 data for one match into the frame the API reads from R2.

normalize_match -> to_contract -> data_utils.data_preprocessing (carries, xT, EPV, xA, xPass, xG, xGOT)

Run with the API virtualenv (it has xgboost / scikit-learn for the existing models):
    apps/api/.venv/bin/python Data/dribble360/compare_contract.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "apps" / "api"))

import data_utils  # noqa: E402
from normalize import normalize_match, to_contract  # noqa: E402

COUNTRY = {"premier-league": "england", "laliga": "spain", "serie-a": "italy",
           "bundesliga": "germany", "ligue-1": "france", "mls": "usa"}


def load_team_map() -> dict[str, int]:
    teams = pd.read_csv(HERE / "crosswalk_teams.csv", dtype={"ws_team_id": int})
    out = dict(zip(teams.d360_team_id, teams.ws_team_id))
    registry = HERE / "team_registry.csv"   # clubs outside the top 5 / MLS (build_team_registry.py)
    if registry.exists():
        reg = pd.read_csv(registry, dtype={"d360_team_id": str, "numeric_id": int})
        out.update(dict(zip(reg.d360_team_id, reg.numeric_id)))
    return out


def card_types_for(player_matches: pd.DataFrame, match_id: str) -> dict:
    """(player_id, n-th card) -> 'Yellow'|'Red'|'SecondYellow'. Pro only reports per-player totals."""
    out = {}
    pm = player_matches[player_matches.match_id == match_id]
    for r in pm.itertuples():
        yellow = 0 if pd.isna(r.yellow_card) else int(r.yellow_card)
        red = 0 if pd.isna(r.red_card) else int(r.red_card)
        if red and yellow >= 1:
            out[(r.player_id, yellow + red)] = "Red"
        elif red:
            out[(r.player_id, 1)] = "Red"
    return out


def process_match(events: pd.DataFrame, *, match_id: str, league: str, season: str, date: str,
                  home_team_id: str, away_team_id: str, home_score: int, away_score: int,
                  players: dict, goalkeeper_ids: set, team_numeric: dict, card_types: dict,
                  player_minutes: dict | None = None) -> pd.DataFrame:
    norm = normalize_match(events, home_team_id=home_team_id, away_team_id=away_team_id,
                           match_id=match_id, players=players, goalkeeper_ids=goalkeeper_ids)
    score = f"{home_score} : {away_score}"
    meta = {"matchId": match_id, "startDate": f"{date}T00:00:00", "startTime": f"{date}T00:00:00",
            "score": score, "ftScore": score, "htScore": "", "etScore": "", "venueName": "",
            "maxMinute": float(norm.minute.max()), "league": league, "country": COUNTRY.get(league, ""),
            "season": season}
    df = to_contract(norm, meta=meta, team_numeric=team_numeric, card_types=card_types)
    out = data_utils.data_preprocessing(df)
    if player_minutes is not None:
        from lineups import attach_lineups
        out, warnings = attach_lineups(out, player_minutes, goalkeeper_ids)
        out.attrs["lineup_warnings"] = warnings
    return out
