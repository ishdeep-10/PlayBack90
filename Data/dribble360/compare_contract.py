"""Run the 19 parity matches through the full chain and compare every API-read column with the
stored WhoScored frame. Writes contract_report.md / contract_columns.csv.

Run with:  apps/api/.venv/bin/python Data/dribble360/compare_contract.py
"""
import sqlite3
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
from process_match import card_types_for, load_team_map, process_match  # noqa: E402

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"


def read_parquet(path, columns=None):
    # BigQuery DATE columns carry a pandas 'dbdate' dtype the API venv's pandas cannot parse
    import pyarrow.parquet as pq
    return pq.read_table(path, columns=columns).to_pandas(ignore_metadata=True)


events = read_parquet(CACHE / "events.parquet")
pmatch = read_parquet(CACHE / "player_matches.parquet")
names_df = read_parquet(CACHE / "players.parquet", columns=["id", "name", "known_name"]).set_index("id")
names = names_df["known_name"].fillna(names_df["name"]).to_dict()
d3 = read_parquet(CACHE / "matches.parquet", columns=["id", "home_score", "away_score"]).set_index("id")
team_map = load_team_map()
parity = pd.read_csv(HERE / "parity_matches.csv", dtype=str)
xw = pd.read_csv(HERE / "crosswalk_matches.csv", dtype=str).set_index("ws_match_id")
con = sqlite3.connect(f"file:{HERE.parent / 'playback90.db'}?mode=ro", uri=True)

API_COLS = ["index", "eventId", "minute", "second", "teamId", "x", "y", "expandedMinute", "period", "type", "outcomeType",
            "qualifiers", "isTouch", "playerId", "endX", "endY", "goalMouthZ", "goalMouthY", "isShot", "isGoal", "cardType",
            "isOwnGoal", "cumulative_mins", "playerName", "h_a", "matchId", "score", "shotBodyType", "situation", "shotCounter",
            "shotOffTarget", "shotOnPost", "shotBlocked", "penaltyScored", "goalOwn", "passCorner", "passFreekick",
            "keyPassCross", "keyPassCorner", "keyPassThroughball", "keyPassFreekick", "keyPassThrowin", "assistCross",
            "assistCorner", "assistThroughball", "assistFreekick", "assistThrowin", "foulGiven", "foulCommitted", "turnover",
            "dispossessed", "touches", "cornerAwarded", "passKey", "passChipped", "passCrossAccurate", "passCrossInaccurate",
            "passLongBallAccurate", "passLongBallInaccurate", "passThroughBallAccurate", "passThroughBallInaccurate",
            "penaltyMissed", "duelAerialWon", "duelAerialLost", "bigChanceMissed", "bigChanceScored", "bigChanceCreated",
            "throwIn", "xT", "teamName", "prog_pass", "prog_carry", "xA", "xG", "league", "season", "xGOT"]
BOOL_COLS = [c for c in API_COLS if c in {
    "isTouch", "isShot", "isGoal", "isOwnGoal", "shotCounter", "shotOffTarget", "shotOnPost", "shotBlocked", "penaltyScored",
    "goalOwn", "passCorner", "passFreekick", "keyPassCross", "keyPassCorner", "keyPassThroughball", "keyPassFreekick",
    "keyPassThrowin", "assistCross", "assistCorner", "assistThroughball", "assistFreekick", "assistThrowin", "foulGiven",
    "foulCommitted", "turnover", "dispossessed", "touches", "cornerAwarded", "passKey", "passChipped", "passCrossAccurate",
    "passCrossInaccurate", "passLongBallAccurate", "passLongBallInaccurate", "passThroughBallAccurate",
    "passThroughBallInaccurate", "penaltyMissed", "duelAerialWon", "duelAerialLost", "bigChanceMissed", "bigChanceScored",
    "bigChanceCreated", "throwIn"}]
NUM_COLS = ["x", "y", "endX", "endY", "cumulative_mins", "xT", "prog_pass", "prog_carry", "xA", "xG", "xGOT"]


def tf(s):
    return s.fillna(False).astype(str).isin(["1", "1.0", "True", "true"])


boolstats = {c: [0, 0, 0, 0] for c in BOOL_COLS}      # tp, fp, fn, tn
numdiff = {c: [] for c in NUM_COLS}
missing_cols, per_match, errors = set(), [], []
for _, m in parity.iterrows():
    x = xw.loc[m.ws_match_id]
    ev = events[events.match_id == m.d360_match_id]
    gks = set(pmatch[(pmatch.match_id == m.d360_match_id) & pmatch.saves.notna()].player_id)
    try:
        ours = process_match(ev, match_id=m.d360_match_id, league=m.league, season=m.season, date=m.date,
                             home_team_id=x.d360_home_team_id, away_team_id=x.d360_away_team_id,
                             home_score=int(d3.loc[m.d360_match_id].home_score), away_score=int(d3.loc[m.d360_match_id].away_score),
                             players=names, goalkeeper_ids=gks, team_numeric=team_map,
                             card_types=card_types_for(pmatch, m.d360_match_id))
    except Exception as exc:  # report, keep going
        import traceback
        errors.append((m.ws_match_id, repr(exc)[:200]))
        if len(errors) == 1:
            traceback.print_exc()
        continue
    ws = pd.read_sql_query("select * from event_data where CAST(matchId AS INTEGER)=?", con, params=(int(m.ws_match_id),))
    missing_cols |= {c for c in API_COLS if c not in ours.columns}
    ours["k"] = list(zip(ours.teamId.astype(float), ours.eventId.astype(float)))
    ws["k"] = list(zip(ws.teamId.astype(float), ws.eventId.astype(float)))
    j = ws.drop_duplicates("k").merge(ours.drop_duplicates("k"), on="k", suffixes=("_w", "_o"))
    for c in BOOL_COLS:
        if f"{c}_w" in j and f"{c}_o" in j:
            w, o = tf(j[f"{c}_w"]), tf(j[f"{c}_o"])
            s = boolstats[c]
            s[0] += int((w & o).sum()); s[1] += int((~w & o).sum()); s[2] += int((w & ~o).sum()); s[3] += int((~w & ~o).sum())
    for c in NUM_COLS:
        if f"{c}_w" in j and f"{c}_o" in j:
            a, b = pd.to_numeric(j[f"{c}_w"], errors="coerce"), pd.to_numeric(j[f"{c}_o"], errors="coerce")
            ok = a.notna() & b.notna()
            numdiff[c].append(pd.DataFrame({"w": a[ok], "o": b[ok]}))
    per_match.append({"match": m.ws_match_id, "xG_ws": round(pd.to_numeric(ws.xG, errors="coerce").sum(), 2),
                      "xG_ours": round(pd.to_numeric(ours.xG, errors="coerce").sum(), 2),
                      "xT_ws": round(pd.to_numeric(ws.xT, errors="coerce").sum(), 2),
                      "xT_ours": round(pd.to_numeric(ours.xT, errors="coerce").sum(), 2),
                      "rows_ws": len(ws), "rows_ours": len(ours)})

rows = []
for c, (tp, fp, fn, tn) in boolstats.items():
    pos = tp + fn
    rows.append({"column": c, "ws_true": pos, "ours_true": tp + fp, "recall": tp / pos if pos else np.nan,
                 "precision": tp / (tp + fp) if tp + fp else np.nan, "agree": (tp + tn) / max(1, tp + fp + fn + tn)})
bdf = pd.DataFrame(rows).round(3)
nrows = []
for c, parts in numdiff.items():
    if not parts:
        continue
    d = pd.concat(parts)
    nrows.append({"column": c, "n": len(d), "corr": round(float(np.corrcoef(d.w, d.o)[0, 1]), 4) if d.w.std() and d.o.std() else np.nan,
                  "mean_abs_diff": round(float((d.w - d.o).abs().mean()), 4), "within_1pct": round(float(((d.w - d.o).abs() <= 0.01 * d.w.abs().clip(lower=1e-9)).mean()), 3)})
ndf = pd.DataFrame(nrows)
bdf.to_csv(HERE / "contract_columns.csv", index=False)
print("errors:", errors)
print("API columns missing from our frame:", sorted(missing_cols))
print("\nBOOLEAN FLAGS (aligned on team+eventId)"); print(bdf.to_string(index=False))
print("\nNUMERIC COLUMNS"); print(ndf.to_string(index=False))
pm = pd.DataFrame(per_match); print("\nPER-MATCH TOTALS"); print(pm.to_string(index=False))
if len(pm):
    print("\nxG total ws/ours:", pm.xG_ws.sum().round(1), pm.xG_ours.sum().round(1), "| xT total ws/ours:", pm.xT_ws.sum().round(1), pm.xT_ours.sum().round(1))
