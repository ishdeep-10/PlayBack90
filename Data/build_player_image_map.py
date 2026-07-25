"""Build a team-aware player image map from SoccerWiki squad pages.

For every club team in app.domain.TEAM_DICT, finds the SoccerWiki club id,
fetches its squad page once, and joins the squad player ids against the
SoccerWiki player export to produce:

    player_images_map.json   { "<team name>": { "<normalized player name>": "<image url>", ... } }

Run from repo root:  python Data/build_player_image_map.py
"""

from __future__ import annotations

import difflib
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.domain import TEAM_DICT  # noqa: E402

PLAYER_JSON = sorted(ROOT.glob("SoccerWiki*Player Data*.json"))[-1]
CLUB_JSON = sorted(ROOT.glob("SoccerWiki*Club Data*.json"))[-1]
OUT_PATH = ROOT / "player_images_map.json"

SQUAD_URL = "https://en.soccerwiki.org/squad.php?clubid={club_id}"
PLAYER_LINK_RE = re.compile(r'player\.php\?pid=(\d+)"[^>]*>([^<]+)<')

# App team name -> SoccerWiki club name, for names token matching can't bridge.
ALIASES = {
    "Man City": "Manchester City",
    "Man Utd": "Manchester United",
    "Wolves": "Wolverhampton Wanderers",
    "Inter": "Internazionale",
    "Borussia M.Gladbach": "Borussia Monchengladbach",
    "Verona": "Hellas Verona",
    "Parma Calcio": "Parma Calcio 1913",
    "FC Heidenheim": "1. FC Heidenheim 1846",
    "Mainz 05": "1. FSV Mainz 05",
    "St. Pauli": "FC St. Pauli",
    "Brest": "Stade Brestois 29",
    "Reims": "Stade de Reims",
    "Marseille": "Olympique Marseille",
    "Bodo/Glimt": "FK Bodø/Glimt",
    "FC Copenhagen": "FC København",
    "Slavia Prague": "SK Slavia Praha",
    "PSG": "Paris Saint-Germain",
    "Rennes": "Stade Rennais",
}

# National sides (FIFA World Cup) have no SoccerWiki club squad — skipped.
NATIONAL_HINTS = {
    "south africa", "mexico", "south korea", "czechia", "canada", "usa", "paraguay",
    "qatar", "brazil", "morocco", "bosnia", "haiti", "curacao", "israel", "turkiye",
}


def norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.lower().replace(".", " ").replace("-", " ").replace("/", " ").split())


def load_clubs() -> dict[str, int]:
    data = json.loads(CLUB_JSON.read_text())
    nationals = {norm(c["Name"]) for c in data.get("InternationalData", [])}
    index: dict[str, int] = {}
    for club in data["ClubData"]:
        name = norm(club["Name"])
        if name and name not in nationals:
            index.setdefault(name, int(club["ID"]))
    return index


def match_club(team: str, clubs: dict[str, int]) -> int | None:
    if team in ALIASES:
        return clubs.get(norm(ALIASES[team]))
    n = norm(team)
    if n in NATIONAL_HINTS:
        return None
    if n in clubs:
        return clubs[n]
    tokens = set(n.split())
    candidates = [(name, cid) for name, cid in clubs.items() if tokens <= set(name.split())]
    if len({cid for _, cid in candidates}) == 1:
        return candidates[0][1]
    if candidates:
        # Prefer the shortest containing name (e.g. "leeds united" over "leeds united u21")
        candidates.sort(key=lambda item: len(item[0]))
        return candidates[0][1]
    close = difflib.get_close_matches(n, clubs.keys(), n=1, cutoff=0.88)
    if close:
        return clubs[close[0]]
    return None


def main() -> None:
    players = json.loads(PLAYER_JSON.read_text())["PlayerData"]
    url_by_id = {int(p["ID"]): str(p.get("ImageURL") or "") for p in players}
    clubs = load_clubs()

    team_names = sorted(set(TEAM_DICT.values()))
    session = requests.Session()
    session.headers["User-Agent"] = "PlayBack90/1.0 (player image mapper)"

    result: dict[str, dict[str, str]] = {}
    misses: list[str] = []
    for team in team_names:
        club_id = match_club(team, clubs)
        if not club_id:
            misses.append(team)
            continue
        try:
            response = session.get(SQUAD_URL.format(club_id=club_id), timeout=20)
            response.raise_for_status()
        except requests.RequestException as exc:
            print(f"  [WARN] {team}: fetch failed ({exc})")
            continue
        squad: dict[str, str] = {}
        for pid_str, raw_name in PLAYER_LINK_RE.findall(response.text):
            name = norm(raw_name)
            url = url_by_id.get(int(pid_str), "")
            if name and url:
                squad.setdefault(name, url)
        if squad:
            result[team] = squad
            print(f"  {team:<24} club {club_id}: {len(squad)} players")
        else:
            print(f"  [WARN] {team}: no players parsed (club {club_id})")
        time.sleep(0.4)

    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False))
    print(f"\nWrote {OUT_PATH} — {len(result)} teams, "
          f"{sum(len(v) for v in result.values())} player entries")
    if misses:
        print("Unmatched teams (skipped):", ", ".join(misses))


if __name__ == "__main__":
    main()
