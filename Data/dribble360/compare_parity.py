"""Parity harness: Dribble360 (normalized) vs the WhoScored data already in Data/playback90.db.

Run (after fetch_parity_data.py):  python compare_parity.py
Writes parity_by_match.csv and parity_report.md next to this file. Read-only everywhere else.
"""
import sqlite3
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import data_utils  # noqa: E402  (existing carry / cumulative-minute code, reused unchanged)
from normalize import normalize_match  # noqa: E402

CACHE = HERE / "cache"
PERIOD_INT = {"FirstHalf": 1, "SecondHalf": 2, "FirstPeriodOfExtraTime": 3, "SecondPeriodOfExtraTime": 4,
              "PenaltyShootout": 5, "PostGame": 14, "PreMatch": 16}
SHOTS = {"Goal", "MissedShots", "SavedShot", "ShotOnPost"}
WS_COLS = ("eventId,teamId,type,outcomeType,period,minute,second,x,y,endX,endY,isShot,isGoal,shotBodyType,"
           "situation,shotOnTarget,shotBlocked,passKey,assist,passThroughBallAccurate,passThroughBallInaccurate")

matches = pd.read_csv(HERE / "parity_matches.csv", dtype=str)
xwalk = pd.read_csv(HERE / "crosswalk_matches.csv", dtype=str).set_index("ws_match_id")
events = pd.read_parquet(CACHE / "events.parquet")
player_matches = pd.read_parquet(CACHE / "player_matches.parquet")
players = pd.read_parquet(CACHE / "players.parquet", columns=["id", "name", "known_name"]).set_index("id")
names = players["known_name"].fillna(players["name"])
con = sqlite3.connect(f"file:{HERE.parent / 'playback90.db'}?mode=ro", uri=True)


def flag(series):
    return series.fillna(False).astype(float).astype(bool)


rows, shot_rows = [], []
for _, m in matches.iterrows():
    x = xwalk.loc[m.ws_match_id]
    tmap = {int(x.ws_home_team_id): x.d360_home_team_id, int(x.ws_away_team_id): x.d360_away_team_id}
    ev = events[events.match_id == m.d360_match_id]
    # Pro player_matches has no position column; `saves` is only populated for goalkeepers
    gks = set(player_matches[(player_matches.match_id == m.d360_match_id)
                             & player_matches.saves.notna()].player_id)
    norm = normalize_match(ev, home_team_id=x.d360_home_team_id, away_team_id=x.d360_away_team_id,
                           match_id=m.d360_match_id, players=names.to_dict(), goalkeeper_ids=gks)

    ws = pd.read_sql_query(f"select {WS_COLS} from event_data where matchId=? and eventId is not null",
                           con, params=(float(m.ws_match_id),))
    ws["team"] = ws.teamId.astype(int).map(tmap)
    ws_carries = ws[ws.type == "Carry"]
    ws = ws[ws.type != "Carry"].copy()
    ws["eid"] = ws.eventId.astype(int)
    norm["eid"] = norm.eventId.astype(int)
    j = ws.merge(norm, left_on=["team", "eid"], right_on=["teamId", "eid"], suffixes=("_ws", "_n"))

    # carries from the existing pipeline code, run on the normalized frame
    n = norm.copy()
    n["period"] = n.period.map(PERIOD_INT)
    n["cumulative_mins"] = np.nan
    n = data_utils.cumulative_match_mins(n)
    n["qualifiers"] = [[] for _ in range(len(n))]
    carried = data_utils.insert_ball_carries(n, min_carry_length=8, max_carry_length=60,
                                             min_carry_duration=4, max_carry_duration=10)
    ours = carried[carried.type == "Carry"]
    ws_keys = set(zip(ws_carries.team, ws_carries.eventId.astype(float)))
    our_keys_all = set(zip(ours.teamId, ours.eventId.astype(float)))
    # The stored WhoScored carries start only from passes/clearances (empirical, 19 matches); the
    # existing carry code applied to Dribble360 also starts them after recoveries/take-ons/tackles.
    prev_type = {(t, e): ty for t, e, ty in zip(n.teamId, n.eventId.astype(float), n.type)}
    our_keys = {k for k in our_keys_all if prev_type.get((k[0], k[1] - 0.5)) in ("Pass", "Clearance")}

    typed = j[j.type_ws == j.type_n]
    per_ok = (j.period_ws.map(PERIOD_INT) == j.period_n.map(PERIOD_INT))
    s = j[j.type_ws.isin(SHOTS)]
    p = j[j.type_ws == "Pass"]
    pk_ws, pk_n = flag(j.passKey_ws), flag(j.passKey_n)
    rows.append({
        "match": m.ws_match_id, "league": m.league, "why": m.why,
        "ws_events": len(ws), "d360_events_kept": len(norm), "ws_found_in_d360": round(len(j) / len(ws), 4),
        "type_equal": round((j.type_ws == j.type_n).mean(), 4),
        "period_equal": round(per_ok.mean(), 4),
        "outcome_equal_all": round((j.outcomeType_ws == j.outcomeType_n).mean(), 4),
        "x_equal": round(((j.x_ws * 1.05 - j.x_n * 1.05).abs() < 0.1).mean(), 4) if False else
                   round((((j.x_ws - j.x_n * 1.05).abs() < 0.2)).mean(), 4),
        "shots": len(s),
        "on_target_equal": round((flag(s.shotOnTarget_ws) == flag(s.shotOnTarget_n)).mean(), 4) if len(s) else np.nan,
        "blocked_equal": round((flag(s.shotBlocked_ws) == flag(s.shotBlocked_n)).mean(), 4) if len(s) else np.nan,
        "situation_equal": round((s.situation_ws.fillna("none") == s.situation_n.fillna("none")).mean(), 4) if len(s) else np.nan,
        "key_pass_ws": int(pk_ws.sum()), "key_pass_ours": int(pk_n.sum()), "key_pass_both": int((pk_ws & pk_n).sum()),
        "carries_ws": len(ws_keys), "carries_ours": len(our_keys), "carries_same": len(ws_keys & our_keys),
        "carries_ours_unfiltered": len(our_keys_all), "carries_same_unfiltered": len(ws_keys & our_keys_all),
        "passes": len(p),
    })
    for _, r in s.iterrows():
        shot_rows.append({"match": m.ws_match_id, "type": r.type_ws, "ws_on_target": bool(flag(pd.Series([r.shotOnTarget_ws])).iloc[0]),
                          "our_on_target": r.shotOnTarget_n, "ws_blocked": bool(flag(pd.Series([r.shotBlocked_ws])).iloc[0]),
                          "our_blocked": r.shotBlocked_n, "ws_situation": r.situation_ws, "our_situation": r.situation_n})

df = pd.DataFrame(rows)
df.to_csv(HERE / "parity_by_match.csv", index=False)
shots = pd.DataFrame(shot_rows)
shots.to_csv(HERE / "parity_shots.csv", index=False)

tot = df.sum(numeric_only=True)
lines = ["# Dribble360 parity report", "", f"{len(df)} matches, {int(tot.ws_events)} WhoScored events.", "",
         "| check | result |", "|---|---|",
         f"| WhoScored events found in Dribble360 by (team, event_id) | {df.ws_found_in_d360.mean():.2%} |",
         f"| event type identical | {df.type_equal.mean():.2%} |",
         f"| outcome identical (all types) | {df.outcome_equal_all.mean():.2%} |",
         f"| period identical (derived) | {df.period_equal.mean():.2%} |",
         f"| x coordinate identical | {df.x_equal.mean():.2%} |",
         f"| shots on target flag identical | {df.on_target_equal.mean():.2%} over {int(tot.shots)} shots |",
         f"| shots blocked flag identical | {df.blocked_equal.mean():.2%} |",
         f"| shot situation identical | {df.situation_equal.mean():.2%} |",
         f"| key pass recall / precision | {tot.key_pass_both / tot.key_pass_ws:.2%} / {tot.key_pass_both / tot.key_pass_ours:.2%} |",
         f"| carries, existing code unchanged | recall {tot.carries_same_unfiltered / tot.carries_ws:.2%}; produced {int(tot.carries_ours_unfiltered)} vs WhoScored {int(tot.carries_ws)} (+{tot.carries_ours_unfiltered / tot.carries_ws - 1:.0%}) |",
         f"| carries, pass/clearance starts only | recall {tot.carries_same / tot.carries_ws:.2%}; precision {tot.carries_same / tot.carries_ours:.2%}; produced {int(tot.carries_ours)} |",
         ""]
(HERE / "parity_report.md").write_text("\n".join(lines))
print("\n".join(lines))
print(df.drop(columns=["why"]).to_string())
