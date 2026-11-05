"""Birth dates for the players in our data, from football-data.org squads (free tier, exact dateOfBirth).

    cd social-media && PYTHONPATH=. ~/.local/pipx/venvs/notebook/bin/python ../Data/dribble360/build_player_birthdates.py

The Dribble `players` table has no birth dates (0 of 91,834), so ages come from here. football-data.org's free plan covers the
Premier League, LaLiga, Serie A, Bundesliga, Ligue 1, Champions League, Eredivisie and Primeira Liga squads, one request per
competition (10 requests a minute). MLS, the Europa League clubs outside those leagues and the other UEFA clubs are not covered.

Writes Data/dribble360/player_birthdates.csv (d360_player_id, date_of_birth, source, name, team); the season-analysis export reads it.
Reads FOOTBALL_DATA_API_KEY from .env (never printed). Names are matched inside the club first, then by full name across all squads
when that is unambiguous; unmatched players are listed at the end.
"""
from __future__ import annotations

import re
import sys
import time
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "social-media"))
sys.path.insert(0, str(ROOT / "apps" / "api"))
import pb90.data as data  # noqa: E402
from app.services.standings import _match_local_team  # noqa: E402

# football-data competition code -> (pb90 league key, season)
COMPETITIONS = {"PL": ("premier-league", "2026/2027"), "PD": ("laliga", "2026/2027"), "SA": ("serie-a", "2026/2027"),
                "BL1": ("bundesliga", "2026/2027"), "FL1": ("ligue-1", "2026/2027"), "CL": ("champions-league", "2026/2027")}
OUR_LEAGUES = [("premier-league", "2026/2027"), ("laliga", "2026/2027"), ("serie-a", "2026/2027"), ("bundesliga", "2026/2027"),
               ("ligue-1", "2026/2027"), ("champions-league", "2026/2027"), ("europa-league", "2026/2027"), ("mls", "2026")]


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]+", " ", s).strip()


def main() -> None:
    env = dict(re.findall(r"^\s*([A-Za-z0-9_-]+)\s*=\s*(.*?)\s*$", (ROOT / ".env").read_text(), re.M))
    headers = {"X-Auth-Token": env["FOOTBALL_DATA_API_KEY"].strip("\"'")}

    squads: dict[str, list[dict]] = {}          # football-data team name -> squad
    for code in COMPETITIONS:
        r = requests.get(f"https://api.football-data.org/v4/competitions/{code}/teams", headers=headers, params={"season": 2026}, timeout=60)
        if r.status_code != 200:
            print(f"{code}: HTTP {r.status_code} ({r.text[:80]})")
            continue
        for t in r.json().get("teams", []):
            squads.setdefault(t["name"], t.get("squad", []))
        print(f"{code}: {len(r.json().get('teams', []))} teams")
        time.sleep(7)                                                    # 10 requests a minute on the free tier

    all_dob = {}                                                        # normalised full name -> [(dob, team)]
    for team, sq in squads.items():
        for p in sq:
            if p.get("dateOfBirth"):
                all_dob.setdefault(norm(p["name"]), []).append((p["dateOfBirth"], team))

    rows, unmatched = [], []
    for league, season in OUR_LEAGUES:
        try:
            df = data.load_events(league, season, ["d360_player_id"])
        except Exception as exc:
            print(f"{league}: {exc}")
            continue
        players = df.dropna(subset=["playerId", "d360_player_id"]).drop_duplicates("playerId")[["d360_player_id", "playerName", "teamName"]]
        for r in players.itertuples():
            fd_team = _match_local_team(r.teamName, list(squads)) if squads else None
            cand = {norm(p["name"]): p for p in squads.get(fd_team, []) if p.get("dateOfBirth")} if fd_team else {}
            me, dob = norm(r.playerName), None
            if me in cand:
                dob = cand[me]["dateOfBirth"]
            else:
                best = max(cand, key=lambda k: SequenceMatcher(None, me, k).ratio(), default=None)
                if best and SequenceMatcher(None, me, best).ratio() >= 0.86:
                    dob = cand[best]["dateOfBirth"]
                elif me in all_dob and len({d for d, _ in all_dob[me]}) == 1:   # same full name everywhere: unambiguous
                    dob = all_dob[me][0][0]
                else:
                    last = me.split()[-1] if me.split() else ""
                    hits = [p for k, p in cand.items() if last and k.split()[-1] == last]
                    if len(hits) == 1:
                        dob = hits[0]["dateOfBirth"]
            if dob:
                rows.append({"d360_player_id": r.d360_player_id, "date_of_birth": dob, "source": "football-data.org", "name": r.playerName, "team": r.teamName})
            else:
                unmatched.append((league, r.playerName, r.teamName))
    out = pd.DataFrame(rows).drop_duplicates("d360_player_id")
    out.to_csv(ROOT / "Data" / "dribble360" / "player_birthdates.csv", index=False)
    print(f"\nbirth dates for {len(out)} players; {len(unmatched)} players unmatched (leagues without a football-data squad, or name differences)")
    by = pd.Series([u[0] for u in unmatched]).value_counts().to_dict()
    print("unmatched by league:", by)


if __name__ == "__main__":
    main()
