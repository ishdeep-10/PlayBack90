from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from threading import Lock
from time import monotonic
from typing import Any
import re
import unicodedata

import requests

from app.config import settings


TOP_FIVE_COMPETITION_CODES = {
    "premier-league": "PL",
    "laliga": "PD",
    "bundesliga": "BL1",
    "serie-a": "SA",
    "ligue-1": "FL1",
}

_TEAM_ALIASES = {
    "athletic club": "atletic club",
    "brighton hove albion": "brighton",
    "fc bayern munchen": "bayern munich",
    "bayern munchen": "bayern munich",
    "internazionale": "inter",
    "internazionale milano": "inter",
    "manchester city": "man city",
    "manchester united": "man utd",
    "newcastle united": "newcastle",
    "paris saint germain": "psg",
    "tottenham hotspur": "tottenham",
    "wolverhampton wanderers": "wolves",
}


class StandingsProviderError(RuntimeError):
    pass


def provider_season_year(season: str) -> int:
    match = re.search(r"(?:19|20)\d{2}", season)
    if not match:
        raise ValueError(f"Invalid season: {season}")
    return int(match.group(0))


def _normalized_name(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    normalized = re.sub(r"[^a-z0-9]+", " ", ascii_value.lower()).strip()
    normalized = " ".join(
        token for token in normalized.split() if token not in {"1", "afc", "cf", "fc"}
    )
    return _TEAM_ALIASES.get(normalized, normalized)


def _match_local_team(provider_name: str, local_names: list[str]) -> str | None:
    target = _normalized_name(provider_name)
    normalized_local = {name: _normalized_name(name) for name in local_names}
    for name, normalized in normalized_local.items():
        if normalized == target:
            return name

    best_name = None
    best_score = 0.0
    target_tokens = set(target.split())
    for name, normalized in normalized_local.items():
        local_tokens = set(normalized.split())
        overlap = len(target_tokens & local_tokens) / max(len(target_tokens | local_tokens), 1)
        score = max(overlap, SequenceMatcher(None, target, normalized).ratio())
        smaller, larger = sorted((target_tokens, local_tokens), key=len)
        distinctive_tokens = smaller - {"city", "club", "real", "sporting", "united"}
        if distinctive_tokens and smaller <= larger:
            score = max(score, 0.9)
        if score > best_score:
            best_name, best_score = name, score
    return best_name if best_score >= 0.78 else None


class FootballDataStandingsProvider:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.football-data.org/v4",
        timeout_seconds: float = 10.0,
        session: requests.Session | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()

    def fetch(self, league: str, season: str) -> list[dict[str, Any]]:
        competition_code = TOP_FIVE_COMPETITION_CODES.get(league)
        if not competition_code:
            raise StandingsProviderError("Official standings are not supported for this league.")

        try:
            response = self.session.get(
                f"{self.base_url}/competitions/{competition_code}/standings",
                headers={"X-Auth-Token": self.api_key},
                params={"season": provider_season_year(season)},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise StandingsProviderError("The official standings provider request failed.") from exc

        standings = payload.get("standings", []) if isinstance(payload, dict) else []
        total = next(
            (item for item in standings if isinstance(item, dict) and item.get("type") == "TOTAL"),
            None,
        )
        table = total.get("table", []) if total else []
        if not isinstance(table, list) or not table:
            raise StandingsProviderError("The official standings provider returned no table.")

        rows = []
        for item in table:
            team = item.get("team") or {}
            rows.append(
                {
                    "rank": int(item.get("position", 0)),
                    "team": str(team.get("name", "Unknown")),
                    "provider_team_name": str(team.get("name", "Unknown")),
                    "provider_team_id": team.get("id"),
                    "team_short_name": team.get("shortName"),
                    "team_code": team.get("tla"),
                    "crest": team.get("crest"),
                    "played": int(item.get("playedGames", 0)),
                    "won": int(item.get("won", 0)),
                    "drawn": int(item.get("draw", 0)),
                    "lost": int(item.get("lost", 0)),
                    "gf": int(item.get("goalsFor", 0)),
                    "ga": int(item.get("goalsAgainst", 0)),
                    "gd": int(item.get("goalDifference", 0)),
                    "pts": int(item.get("points", 0)),
                    "form": item.get("form"),
                    "xg": None,
                    "xga": None,
                    "xgd": None,
                }
            )
        return rows


@dataclass
class _CacheEntry:
    rows: list[dict[str, Any]]
    fetched_at: float
    updated_at: datetime


class StandingsService:
    def __init__(
        self,
        provider: FootballDataStandingsProvider | None,
        *,
        cache_ttl_seconds: int = 600,
        stale_ttl_seconds: int = 86_400,
    ) -> None:
        self.provider = provider
        self.cache_ttl_seconds = cache_ttl_seconds
        self.stale_ttl_seconds = stale_ttl_seconds
        self._cache: dict[tuple[str, str], _CacheEntry] = {}
        self._lock = Lock()

    def _official_rows(self, league: str, season: str) -> tuple[list[dict[str, Any]], datetime, bool]:
        if self.provider is None:
            raise StandingsProviderError("The official standings provider is not configured.")

        key = (league, season)
        now = monotonic()
        with self._lock:
            cached = self._cache.get(key)
            if cached and now - cached.fetched_at < self.cache_ttl_seconds:
                return deepcopy(cached.rows), cached.updated_at, False

        try:
            rows = self.provider.fetch(league, season)
        except StandingsProviderError:
            with self._lock:
                cached = self._cache.get(key)
                if cached and now - cached.fetched_at < self.stale_ttl_seconds:
                    return deepcopy(cached.rows), cached.updated_at, True
            raise

        updated_at = datetime.now(timezone.utc)
        with self._lock:
            self._cache[key] = _CacheEntry(deepcopy(rows), now, updated_at)
        return rows, updated_at, False

    def build_payload(
        self,
        league: str,
        season: str,
        local_rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        provider_error: StandingsProviderError | None = None
        if league in TOP_FIVE_COMPETITION_CODES:
            try:
                rows, updated_at, is_stale = self._official_rows(league, season)
                rows = merge_local_analytics(rows, local_rows)
                return {
                    "league": league,
                    "season": season,
                    "source": "football-data",
                    "updated_at": updated_at,
                    "is_official": True,
                    "is_stale": is_stale,
                    "is_complete": True,
                    "warning": (
                        "Showing the most recently cached official table while the provider is unavailable."
                        if is_stale else None
                    ),
                    "rows": rows,
                }
            except StandingsProviderError as exc:
                provider_error = exc

        if not local_rows:
            if provider_error:
                raise provider_error
            raise StandingsProviderError("No standings data is available for this league and season.")

        warning = (
            "Official standings are temporarily unavailable. Showing a table calculated from available match data, which may be incomplete."
            if league in TOP_FIVE_COMPETITION_CODES
            else "Official standings are currently available only for the top five European leagues."
        )
        return {
            "league": league,
            "season": season,
            "source": "calculated",
            "updated_at": datetime.now(timezone.utc),
            "is_official": False,
            "is_stale": False,
            "is_complete": False,
            "warning": warning,
            "rows": local_rows,
        }


def merge_local_analytics(
    official_rows: list[dict[str, Any]],
    local_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    local_names = [str(row.get("team", "")) for row in local_rows if row.get("team")]
    local_by_name = {str(row.get("team")): row for row in local_rows}
    merged = deepcopy(official_rows)
    for row in merged:
        local_name = _match_local_team(str(row.get("provider_team_name") or row["team"]), local_names)
        if not local_name:
            continue
        analytics = local_by_name[local_name]
        row["team"] = local_name
        for metric in ("xg", "xga", "xgd"):
            value = analytics.get(metric)
            row[metric] = float(value) if value is not None else None
    return merged


_provider = (
    FootballDataStandingsProvider(
        settings.football_data_api_key,
        base_url=settings.football_data_base_url,
        timeout_seconds=settings.football_data_timeout_seconds,
    )
    if settings.football_data_api_key
    else None
)
standings_service = StandingsService(
    _provider,
    cache_ttl_seconds=settings.standings_cache_ttl_seconds,
    stale_ttl_seconds=settings.standings_stale_ttl_seconds,
)
