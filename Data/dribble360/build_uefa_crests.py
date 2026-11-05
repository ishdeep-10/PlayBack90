"""Crest URLs for the Champions League clubs (football-data.org free tier has CL, not the Europa League).

    apps/api/.venv/bin/python Data/dribble360/build_uefa_crests.py

Writes apps/api/app/uefa_crests.json: {club name as the app spells it: crest URL}. The season-analysis export adds
the crest to each team row. Europa League clubs have no free crest source yet (monogram badge in the chart).
Reads FOOTBALL_DATA_API_KEY from .env; the key is never printed.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api"))
from app.services.standings import _match_local_team  # noqa: E402

env = dict(re.findall(r"^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$", (ROOT / ".env").read_text(), re.M))
key = env["FOOTBALL_DATA_API_KEY"].strip("\"'")
teams = requests.get("https://api.football-data.org/v4/competitions/CL/teams", params={"season": 2026},
                     headers={"X-Auth-Token": key}, timeout=30).json()["teams"]
ours = [t["team"] for t in json.loads((ROOT / "Data/dribble360/out/season_agg/champions-league/2026_2027/team_metrics.json").read_text())["teams"]]
MANUAL = {"Sporting Clube de Portugal": "Sporting CP", "SK Slavia Praha": "Slavia Prague", "PAE AEK": "AEK Athens"}
out, unmatched = {}, []
for t in teams:
    name = MANUAL.get(t["name"]) or _match_local_team(t["name"], ours)
    if name and t.get("crest"):
        out[name] = t["crest"]
    else:
        unmatched.append(t["name"])
(ROOT / "apps/api/app/uefa_crests.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
print(f"{len(out)} crests written; unmatched provider names: {unmatched}; clubs without crest: {[n for n in ours if n not in out]}")
