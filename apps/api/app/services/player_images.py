"""Resolve player headshot URLs from the SoccerWiki player dataset.

Resolution order:
1. Team-aware map (``player_images_map.json`` built by ``Data/build_player_image_map.py``)
   — exact name, then unique surname match within that team's squad.
2. Global name index — exact full name (only when unambiguous), reversed name
   order, surname + forename-initial, unique surname, mononym forename.
"""

from __future__ import annotations

import json
import logging
import threading
import unicodedata

from app.config import ROOT_DIR

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_INDEX: dict[str, str] | None = None
_SURNAME_INDEX: dict[str, list[tuple[str, str]]] | None = None
_TEAM_MAP: dict[str, dict[str, str]] | None = None


def _normalize(name: str) -> str:
    text = unicodedata.normalize("NFKD", str(name or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.lower().replace("-", " ").split())


def _load_index() -> tuple[dict[str, str], dict[str, list[tuple[str, str]]], dict[str, dict[str, str]]]:
    global _INDEX, _SURNAME_INDEX, _TEAM_MAP
    if _INDEX is not None and _SURNAME_INDEX is not None and _TEAM_MAP is not None:
        return _INDEX, _SURNAME_INDEX, _TEAM_MAP
    with _LOCK:
        if _INDEX is not None and _SURNAME_INDEX is not None and _TEAM_MAP is not None:
            return _INDEX, _SURNAME_INDEX, _TEAM_MAP
        full_index: dict[str, str] = {}
        ambiguous: set[str] = set()
        surname_index: dict[str, list[tuple[str, str]]] = {}
        try:
            candidates = sorted(ROOT_DIR.glob("SoccerWiki*Player Data*.json"))
            if not candidates:
                raise FileNotFoundError("no SoccerWiki player data file in repo root")
            data = json.loads(candidates[-1].read_text())
            for player in data.get("PlayerData", []):
                url = str(player.get("ImageURL") or "").strip()
                if not url:
                    continue
                forename = _normalize(player.get("Forename") or "")
                surname = _normalize(player.get("Surname") or "")
                full = f"{forename} {surname}".strip()
                if full:
                    if full in full_index and full_index[full] != url:
                        ambiguous.add(full)
                    else:
                        full_index[full] = url
                if surname:
                    surname_index.setdefault(surname, []).append((forename, url))
            # A duplicated full name can point at the wrong person — drop it and
            # let the team-aware map (or initials fallback) handle those players.
            for name in ambiguous:
                full_index.pop(name, None)
        except Exception:
            logger.warning("failed to load SoccerWiki player image dataset", exc_info=True)

        team_map: dict[str, dict[str, str]] = {}
        try:
            map_path = ROOT_DIR / "player_images_map.json"
            if map_path.exists():
                raw = json.loads(map_path.read_text())
                team_map = {
                    _normalize(team): {_normalize(name): url for name, url in squad.items()}
                    for team, squad in raw.items()
                }
        except Exception:
            logger.warning("failed to load team-aware player image map", exc_info=True)

        _INDEX, _SURNAME_INDEX, _TEAM_MAP = full_index, surname_index, team_map
        logger.info(
            "player image index loaded: %d full names (%d ambiguous dropped), %d team squads",
            len(full_index), len(ambiguous), len(team_map),
        )
        return _INDEX, _SURNAME_INDEX, _TEAM_MAP


def _resolve_from_squad(wanted: str, squad: dict[str, str]) -> str | None:
    direct = squad.get(wanted)
    if direct:
        return direct
    parts = wanted.split(" ")
    wanted_tokens = set(parts)
    # Unique squad entry sharing the surname (last token) or any name token set overlap.
    surname = parts[-1]
    hits = [url for name, url in squad.items() if surname in name.split(" ")]
    if len(set(hits)) == 1:
        return hits[0]
    token_hits = [url for name, url in squad.items() if wanted_tokens <= set(name.split(" ")) or set(name.split(" ")) <= wanted_tokens]
    if len(set(token_hits)) == 1:
        return token_hits[0]
    partial_hits = [
        url
        for name, url in squad.items()
        if len(wanted_tokens & set(name.split(" "))) >= 2
    ]
    if len(set(partial_hits)) == 1:
        return partial_hits[0]
    return None


def _resolve_partial_full_name(wanted: str, full_index: dict[str, str]) -> str | None:
    wanted_tokens = set(wanted.split(" "))
    if len(wanted_tokens) < 2:
        return None
    hits = {
        url
        for indexed_name, url in full_index.items()
        if len(wanted_tokens & set(indexed_name.split(" "))) >= 2
        and (wanted_tokens <= set(indexed_name.split(" ")) or set(indexed_name.split(" ")) <= wanted_tokens)
    }
    return next(iter(hits)) if len(hits) == 1 else None


def _resolve_leading_name_pair(wanted: str, full_index: dict[str, str]) -> str | None:
    parts = wanted.split(" ")
    if len(parts) < 3:
        return None
    leading_pair = " ".join(parts[:2])
    return full_index.get(leading_pair)


def resolve_player_image(name: str, team: str | None = None) -> str | None:
    full_index, surname_index, team_map = _load_index()
    wanted = _normalize(name)
    if not wanted:
        return None

    if team:
        squad = team_map.get(_normalize(team))
        if squad:
            from_squad = _resolve_from_squad(wanted, squad)
            if from_squad:
                return from_squad

    direct = full_index.get(wanted)
    if direct:
        return direct

    leading_pair = _resolve_leading_name_pair(wanted, full_index)
    if leading_pair:
        return leading_pair

    partial = _resolve_partial_full_name(wanted, full_index)
    if partial:
        return partial

    parts = wanted.split(" ")
    if len(parts) >= 2:
        # Surname-first names ("Hwang Hee-Chan" stored as "Hee-Chan HWANG") and full flips.
        for variant in (" ".join(parts[1:] + parts[:1]), " ".join(reversed(parts))):
            flipped = full_index.get(variant)
            if flipped:
                return flipped

    surname = parts[-1]
    candidates = surname_index.get(surname, [])
    if len(parts) >= 2 and candidates:
        initial = parts[0][0]
        initial_hits = {url for forename, url in candidates if forename.startswith(initial)}
        if len(initial_hits) == 1:
            return next(iter(initial_hits))
    if len({url for _, url in candidates}) == 1 and candidates:
        return candidates[0][1]
    # Mononym (e.g. "Florentino") may be stored as a forename.
    if len(parts) == 1:
        forename_hits = {
            url
            for entries in surname_index.values()
            for forename, url in entries
            if forename == wanted
        }
        if len(forename_hits) == 1:
            return next(iter(forename_hits))
    return None


def resolve_player_images(names: list[str], team: str | None = None) -> dict[str, str | None]:
    return {name: resolve_player_image(name, team) for name in names if str(name).strip()}
