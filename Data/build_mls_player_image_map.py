"""One-off patch: add MLS team squads to player_images_map.json.

Same extraction logic as build_player_image_map.py (SoccerWiki squad page ->
player id -> ImageURL from the SoccerWiki player export), but scoped to the
30 MLS clubs whose SoccerWiki club IDs were sourced manually since MLS
wasn't covered by the bundled Club Data export.

Run from repo root: python Data/build_mls_player_image_map.py
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
PLAYER_JSON = sorted(ROOT.glob("SoccerWiki*Player Data*.json"))[-1]
OUT_PATH = ROOT / "player_images_map.json"

SQUAD_URL = "https://en.soccerwiki.org/squad.php?clubid={club_id}"
PLAYER_LINK_RE = re.compile(r'player\.php\?pid=(\d+)"[^>]*>([^<]+)<')

MLS_CLUB_IDS = {
    "FC Cincinnati": 4243,
    "Atlanta United": 3910,
    "St. Louis City": 5684,
    "Charlotte FC": 5537,
    "DC United": 438,
    "Philadelphia Union": 1572,
    "San Jose Earthquakes": 1212,
    "Sporting Kansas City": 460,
    "Vancouver Whitecaps": 1619,
    "Real Salt Lake": 465,
    "Austin FC": 5288,
    "Minnesota United": 2121,
    "FC Dallas": 459,
    "Toronto FC": 758,
    "Houston Dynamo FC": 464,
    "Chicago Fire FC": 455,
    "Los Angeles FC": 4260,
    "Inter Miami CF": 5228,
    "Nashville SC": 5058,
    "New England Revolution": 463,
    "Orlando City": 2116,
    "Red Bull New York": 462,
    "Portland Timbers": 1654,
    "Columbus Crew": 458,
    "San Diego FC": 6226,
    "CF Montreal": 1790,
    "LA Galaxy": 461,
    "New York City FC": 3210,
    "Seattle Sounders FC": 1336,
    "Colorado Rapids": 457,
}


def norm(value: str) -> str:
    return " ".join(str(value or "").lower().replace(".", " ").replace("-", " ").split())


def main() -> None:
    players = json.loads(PLAYER_JSON.read_text())["PlayerData"]
    url_by_id = {int(p["ID"]): str(p.get("ImageURL") or "") for p in players}

    existing: dict[str, dict[str, str]] = {}
    if OUT_PATH.exists():
        existing = json.loads(OUT_PATH.read_text())

    session = requests.Session()
    session.headers["User-Agent"] = "PlayBack90/1.0 (mls player image mapper)"

    added_teams = 0
    added_players = 0
    misses: list[str] = []
    for team, club_id in MLS_CLUB_IDS.items():
        try:
            response = session.get(SQUAD_URL.format(club_id=club_id), timeout=20)
            response.raise_for_status()
        except requests.RequestException as exc:
            print(f"  [WARN] {team}: fetch failed ({exc})")
            misses.append(team)
            continue

        squad: dict[str, str] = {}
        for pid_str, raw_name in PLAYER_LINK_RE.findall(response.text):
            name = norm(raw_name)
            url = url_by_id.get(int(pid_str), "")
            if name and url:
                squad.setdefault(name, url)

        if squad:
            existing[team] = squad
            added_teams += 1
            added_players += len(squad)
            print(f"  {team:<24} club {club_id}: {len(squad)} players")
        else:
            print(f"  [WARN] {team}: no players parsed (club {club_id})")
            misses.append(team)

        time.sleep(0.4)

    OUT_PATH.write_text(json.dumps(existing, ensure_ascii=False))
    print(f"\nWrote {OUT_PATH} — {added_teams} MLS teams added, {added_players} player entries")
    if misses:
        print("Unmatched teams (skipped):", ", ".join(misses))


if __name__ == "__main__":
    main()
