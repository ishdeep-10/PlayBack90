"""Current ages for clubs football-data.org does not cover (MLS, Europa League clubs), from API-Football squads.

    cd social-media && PYTHONPATH=. ~/.local/pipx/venvs/notebook/bin/python ../Data/dribble360/build_player_ages_apifootball.py --league mls

The free plan allows 100 requests a day and `players/squads?team=ID` works on it (it gives a whole-number age, not a birth date;
team listings for the current season do not). Each squad is cached in Data/dribble360/cache/apifootball_squads/ so a re-run costs no
requests. Team ids come from the logo table in apps/web/lib/clubLogos.ts; a club without one is looked up by name (one request).
Writes/updates Data/dribble360/player_ages.csv (d360_player_id, age, as_of, source, name, team). Reads `x-apisports-key` from .env
(never printed). Stops before --max-calls requests so a daily quota is never exhausted.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from datetime import date
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "social-media"))
import pb90.data as data  # noqa: E402

CACHE = ROOT / "Data" / "dribble360" / "cache" / "apifootball_squads"
OUT = ROOT / "Data" / "dribble360" / "player_ages.csv"
SEASONS = {"mls": "2026", "europa-league": "2026/2027", "champions-league": "2026/2027"}
BASE = "https://v3.football.api-sports.io"


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]+", " ", s).strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", default="mls")
    ap.add_argument("--max-calls", type=int, default=45, help="stop after this many API requests (daily quota is 100)")
    ap.add_argument("--only-missing-dob", action="store_true", help="skip clubs whose players already have a birth date")
    args = ap.parse_args()
    env = dict(re.findall(r"^\s*([A-Za-z0-9_-]+)\s*=\s*(.*?)\s*$", (ROOT / ".env").read_text(), re.M))
    headers = {"x-apisports-key": env["x-apisports-key"].strip("\"'")}
    CACHE.mkdir(parents=True, exist_ok=True)
    logos = {k: int(v) for k, v in re.findall(r'"([^"]+)":\s*"https://media\.api-sports\.io/football/teams/(\d+)\.png"', (ROOT / "apps/web/lib/clubLogos.ts").read_text())}
    sys.path.insert(0, str(ROOT / "apps" / "api"))
    from app.domain import TEAM_DICT

    df = data.load_events(args.league, SEASONS[args.league], ["d360_player_id"])
    players = df.dropna(subset=["playerId", "d360_player_id"]).drop_duplicates("playerId")[["d360_player_id", "playerName", "teamId", "teamName"]]
    dob = pd.read_csv(ROOT / "Data/dribble360/player_birthdates.csv") if (ROOT / "Data/dribble360/player_birthdates.csv").exists() else pd.DataFrame(columns=["d360_player_id"])
    known = set(dob["d360_player_id"])
    calls = 0
    rows = []
    for (tid, tname), group in players.groupby(["teamId", "teamName"]):
        if args.only_missing_dob and group["d360_player_id"].isin(known).mean() > 0.5:
            continue
        name = TEAM_DICT.get(int(tid), tname)
        api_id = logos.get(name) or logos.get(tname)
        if api_id is None:
            if calls >= args.max_calls:
                print(f"stopping before the lookup for {name}: call budget reached")
                break
            r = requests.get(f"{BASE}/teams", headers=headers, params={"search": name.split()[0] if len(name.split()) > 1 else name}, timeout=30).json()
            calls += 1
            hits = [t["team"] for t in r.get("response", []) if norm(t["team"]["name"]) == norm(name)]
            api_id = hits[0]["id"] if hits else None
            if api_id is None:
                print(f"no API-Football team found for {name}")
                continue
        f = CACHE / f"{api_id}.json"
        if not f.exists():
            if calls >= args.max_calls:
                print(f"call budget reached ({calls}); re-run later to continue")
                break
            r = requests.get(f"{BASE}/players/squads", headers=headers, params={"team": api_id}, timeout=30).json()
            calls += 1
            if isinstance(r.get("errors"), dict) and "rateLimit" in r["errors"]:     # free plan: 10 requests a minute
                time.sleep(65)
                r = requests.get(f"{BASE}/players/squads", headers=headers, params={"team": api_id}, timeout=30).json()
                calls += 1
            time.sleep(6.5)
            if r.get("errors"):
                print(f"{name}: {r['errors']}")
                break
            f.write_text(json.dumps(r.get("response", [])))
        squad = (json.loads(f.read_text()) or [{}])[0].get("players", [])
        by_key: dict[tuple[str, str], list[dict]] = {}
        for p in squad:
            parts = norm(p["name"]).split()
            if parts:
                by_key.setdefault((parts[0][0], parts[-1]), []).append(p)
        for r in group.itertuples():
            parts = norm(r.playerName).split()
            hits = by_key.get((parts[0][0], parts[-1]), []) if parts else []
            if len(hits) == 1 and isinstance(hits[0].get("age"), int):
                rows.append({"d360_player_id": r.d360_player_id, "age": hits[0]["age"], "as_of": date.today().isoformat(),
                             "source": "api-football", "name": r.playerName, "team": tname})
    new = pd.DataFrame(rows)
    old = pd.read_csv(OUT) if OUT.exists() else pd.DataFrame()
    out = pd.concat([old, new]).drop_duplicates("d360_player_id", keep="last") if len(new) else old
    out.to_csv(OUT, index=False)
    print(f"{args.league}: {len(new)} ages added ({len(out)} total in {OUT.name}); {calls} API requests used")


if __name__ == "__main__":
    main()
