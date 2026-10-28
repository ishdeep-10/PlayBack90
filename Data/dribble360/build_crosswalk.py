"""Map local WhoScored matches (Data/playback90.db) to Dribble360 match/team ids.

Usage: python build_crosswalk.py <billing-project-id>
Writes crosswalk_matches.csv next to this file. Read-only on both sides.
"""
import difflib
import re
import sqlite3
import sys
import unicodedata
import warnings
from pathlib import Path

import pandas as pd
from google.cloud import bigquery

warnings.filterwarnings("ignore")

HERE = Path(__file__).resolve().parent
DB = HERE.parent / "playback90.db"
DATASET = "dribble360.football_pro"
MAX_BYTES = int(5e9)

# WhoScored league key -> Dribble360 leagues.id
LEAGUES = {
    "premier-league": "2kwbbcootiqqgmrzs6o5inle5",
    "laliga": "34pl8szyvrbwcmfkuocjm3r6t",
    "serie-a": "1r097lpxe0xn03ihb7wi98kao",
    "bundesliga": "6by3h89i2eykc341oz7lv1ddd",
    "ligue-1": "dm5ka0os1e3dxcp3vh05kmp33",
    "mls": "287tckirbfj9nb8ar2k9r60vn",
    "champions-league": "4oogyu6o156iphvdvphwpck10",
    "europa-league": "4c1nfi2j1m731hcay25fcgndq",
}
NAME_NOISE = {"fc", "cf", "afc", "sc", "ac", "as", "ssc", "us", "rc", "rcd", "1", "04", "05", "1899", "de", "the", "city", "united", "club"}


def norm(name):
    text = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower()
    tokens = [t for t in re.split(r"[^a-z0-9]+", text) if t and t not in NAME_NOISE]
    return " ".join(tokens)


def name_sim(a, b):
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    if a == b or a in b or b in a:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def load_whoscored():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    q = """
        SELECT DISTINCT matchId, league, season, substr(startDate, 1, 10) AS date, ftScore,
               h_a, teamName, teamId
        FROM event_data
        WHERE h_a IN ('h', 'a') AND league IN ({}) AND season IN ('2025/2026', '2026/2027', '2026')
    """.format(",".join("?" * len(LEAGUES)))
    df = pd.read_sql_query(q, con, params=list(LEAGUES))
    df["matchId"] = df["matchId"].astype(float).astype(int).astype(str)
    # raw rows often lack teamName; recover it from any row with the same teamId
    names = pd.read_sql_query(
        "SELECT DISTINCT teamId, teamName FROM event_data WHERE teamName IS NOT NULL AND teamId IS NOT NULL", con
    ).drop_duplicates("teamId").set_index("teamId")["teamName"]
    df["teamName"] = df["teamName"].fillna(df["teamId"].map(names))
    home = df[df.h_a == "h"].drop_duplicates("matchId").set_index("matchId")
    away = df[df.h_a == "a"].drop_duplicates("matchId").set_index("matchId")
    out = home[["league", "season", "date", "ftScore", "teamName", "teamId"]].join(
        away[["teamName", "teamId"]], lsuffix="_home", rsuffix="_away", how="inner"
    )
    scores = out["ftScore"].str.extract(r"(\d+)\s*:\s*(\d+)").astype("float")
    out["home_score"], out["away_score"] = scores[0], scores[1]
    return out.reset_index().rename(columns={"matchId": "ws_match_id"})


def load_dribble360(client):
    sql = f"""
        SELECT m.id AS d360_match_id, m.date, s.name AS season, l.id AS league_id,
               m.home_score, m.away_score,
               th.team_id AS home_team_id, hn.name AS home_name,
               ta.team_id AS away_team_id, an.name AS away_name
        FROM `{DATASET}.matches` m
        JOIN `{DATASET}.seasons` s ON s.id = m.season_id
        JOIN `{DATASET}.leagues` l ON l.id = s.league_id
        JOIN `{DATASET}.team_matches` th ON th.match_id = m.id AND th.side = 'HOME'
        JOIN `{DATASET}.team_matches` ta ON ta.match_id = m.id AND ta.side = 'AWAY'
        JOIN `{DATASET}.teams` hn ON hn.id = th.team_id
        JOIN `{DATASET}.teams` an ON an.id = ta.team_id
        WHERE m.status = 'PLAYED' AND s.start_date >= DATE '2025-01-01'
          AND l.id IN ({",".join(repr(v) for v in LEAGUES.values())})
    """
    cfg = bigquery.QueryJobConfig(maximum_bytes_billed=MAX_BYTES)
    est = client.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True)).total_bytes_processed
    print(f"BigQuery scan ~{est / 1e9:.2f} GB (cap {MAX_BYTES / 1e9:.0f} GB)")
    df = client.query(sql, job_config=cfg).to_dataframe()
    df["date"] = pd.to_datetime(df["date"])
    return df


def main():
    client = bigquery.Client(project=sys.argv[1])
    ws = load_whoscored()
    d3 = load_dribble360(client)
    print(f"WhoScored matches: {len(ws)} | Dribble360 matches: {len(d3)}")

    def candidates(rec):
        day = pd.Timestamp(rec.date)
        return d3[
            (d3.league_id == LEAGUES[rec.league])
            & ((d3.date - day).abs() <= pd.Timedelta(days=1))
            & (d3.home_score == rec.home_score)
            & (d3.away_score == rec.away_score)
        ]

    def sim_of(rec, c):
        return (name_sim(rec.teamName_home, c.home_name) + name_sim(rec.teamName_away, c.away_name)) / 2

    # pass 1: league + date(+-1) + exact score. A single candidate is a match; learn team ids from them.
    team_map = {}
    for rec in ws.itertuples():
        cand = candidates(rec)
        if len(cand) == 1:
            c = next(cand.itertuples())
            team_map.setdefault(int(rec.teamId_home), {}).setdefault(c.home_team_id, 0)
            team_map[int(rec.teamId_home)][c.home_team_id] += 1
            team_map.setdefault(int(rec.teamId_away), {}).setdefault(c.away_team_id, 0)
            team_map[int(rec.teamId_away)][c.away_team_id] += 1
    team_to_d360 = {k: max(v, key=v.get) for k, v in team_map.items()}

    # pass 2: resolve every match, using team ids to break ties between several same-score candidates
    rows = []
    for rec in ws.itertuples():
        cand = candidates(rec)
        best, best_score, status = None, 0.0, "unmatched"
        if len(cand) == 1:
            best = next(cand.itertuples())
            best_score, status = sim_of(rec, best), "matched"
        elif len(cand) > 1:
            by_id = cand[
                (cand.home_team_id == team_to_d360.get(int(rec.teamId_home)))
                & (cand.away_team_id == team_to_d360.get(int(rec.teamId_away)))
            ]
            pool = by_id if len(by_id) == 1 else cand
            ranked = sorted(pool.itertuples(), key=lambda c: -sim_of(rec, c))
            best = ranked[0]
            best_score = sim_of(rec, best)
            status = "matched" if len(by_id) == 1 else ("low_confidence" if best_score >= 0.6 else "ambiguous")
        rows.append({
            "ws_match_id": rec.ws_match_id, "league": rec.league, "season": rec.season, "date": rec.date,
            "ws_home": rec.teamName_home, "ws_away": rec.teamName_away,
            "ws_home_team_id": int(rec.teamId_home), "ws_away_team_id": int(rec.teamId_away),
            "ws_score": f"{rec.home_score:.0f}-{rec.away_score:.0f}" if pd.notna(rec.home_score) else None,
            "d360_match_id": best.d360_match_id if status != "unmatched" else None,
            "d360_home": best.home_name if best is not None else None,
            "d360_away": best.away_name if best is not None else None,
            "d360_home_team_id": best.home_team_id if status != "unmatched" else None,
            "d360_away_team_id": best.away_team_id if status != "unmatched" else None,
            "match_score": round(best_score, 3), "status": status,
        })
    out = pd.DataFrame(rows)
    # a Dribble360 match claimed by two WhoScored matches is ambiguous
    # keep the better name match; the loser has no genuine counterpart in Dribble360
    claimed = out[out.d360_match_id.notna()].sort_values("match_score", ascending=False)
    losers = claimed[claimed.duplicated("d360_match_id", keep="first")].index
    out.loc[losers, ["d360_match_id", "d360_home", "d360_away", "d360_home_team_id", "d360_away_team_id"]] = None
    out.loc[losers, "status"] = "unmatched"
    # team crosswalk: legacy WhoScored numeric team id <-> Dribble360 team id (majority vote)
    d3_names = {**dict(zip(d3.home_team_id, d3.home_name)), **dict(zip(d3.away_team_id, d3.away_name))}
    ws_names = {**dict(zip(ws.teamId_home.astype(int), ws.teamName_home)), **dict(zip(ws.teamId_away.astype(int), ws.teamName_away))}
    team_rows = []
    for ws_id, votes in team_map.items():
        d360_id = max(votes, key=votes.get)
        team_rows.append({"ws_team_id": ws_id, "d360_team_id": d360_id, "ws_name": ws_names.get(ws_id),
                          "d360_name": d3_names.get(d360_id), "votes": votes[d360_id],
                          "conflicting_votes": sum(votes.values()) - votes[d360_id]})
    pd.DataFrame(team_rows).sort_values("d360_name").to_csv(HERE / "crosswalk_teams.csv", index=False)
    print("teams mapped:", len(team_rows))
    path = HERE / "crosswalk_matches.csv"
    out.to_csv(path, index=False)
    print(out.groupby(["league", "status"]).size().unstack(fill_value=0).to_string())
    print("wrote", path)


if __name__ == "__main__":
    main()
