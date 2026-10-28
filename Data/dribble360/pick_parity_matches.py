"""Choose the 20 matches for the parity harness (deterministic). Writes parity_matches.csv."""
import random
import sqlite3
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
cw = pd.read_csv(HERE / "crosswalk_matches.csv", dtype=str)
cw = cw[(cw.status == "matched") & cw.season.isin(["2025/2026", "2026"])].copy()
con = sqlite3.connect(f"file:{HERE.parent / 'playback90.db'}?mode=ro", uri=True)
ids = ",".join(f"'{int(m)}'" if False else m for m in cw.ws_match_id)
reds = pd.read_sql_query(
    f"SELECT CAST(matchId AS INTEGER) AS m, SUM(redCard) AS reds FROM event_data "
    f"WHERE CAST(matchId AS INTEGER) IN ({ids}) AND redCard=1 GROUP BY 1", con)
cw["reds"] = cw.ws_match_id.astype(int).map(dict(zip(reds.m, reds.reds))).fillna(0).astype(int)
cw[["h", "a"]] = cw.ws_score.str.split("-", expand=True).astype(int)
cw["goals"] = cw.h + cw.a
rng = random.Random(90)
picked = []
def take(df, n, label):
    pool = [i for i in df.index if i not in picked]
    for i in rng.sample(pool, min(n, len(pool))):
        picked.append(i); cw.loc[i, "why"] = label
take(cw[cw.goals == 0], 1, "0-0")
take(cw[cw.goals >= 6], 1, "high-scoring")
take(cw[cw.reds >= 1], 2, "red card")
quota = {"premier-league": 4, "laliga": 3, "serie-a": 3, "bundesliga": 3, "ligue-1": 3, "mls": 3}
for lg, n in quota.items():
    have = sum(cw.loc[i, "league"] == lg for i in picked)
    take(cw[cw.league == lg], max(0, n - have), "random")
out = cw.loc[picked, ["ws_match_id", "d360_match_id", "league", "season", "date", "ws_home", "ws_away", "ws_score", "reds", "why"]]
out.to_csv(HERE / "parity_matches.csv", index=False)
print(len(out), "matches"); print(out.to_string())
