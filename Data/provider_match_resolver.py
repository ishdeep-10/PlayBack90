"""Resolve official fixtures to completed WhoScored match-centre URLs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import json
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urljoin

from ingestion_worker import match_id_from_url
from league_sources import LEAGUE_SOURCES
from team_names import team_name_similarity
from worker_state import WorkerFixture


DATA_DIR = Path(__file__).resolve().parent
LEAGUE_URLS_PATH = DATA_DIR / "league_urls_updated.json"
PROVIDER_BASE_URL = "https://1xbet.whoscored.com/"
_DATE_FORMATS = ("%A, %b %d %Y", "%a, %b %d %Y", "%b %d %Y", "%Y-%m-%d")


@dataclass(frozen=True)
class ProviderMatch:
    match_id: str
    url: str
    home_team: str
    away_team: str
    match_date: date | None


@dataclass(frozen=True)
class ResolutionBatch:
    urls: dict[str, str]
    errors: dict[str, str]
    candidate_count: int


_team_similarity = team_name_similarity


def _provider_date(value: object) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.date()
    except ValueError:
        pass
    for date_format in _DATE_FORMATS:
        try:
            return datetime.strptime(text, date_format).date()
        except ValueError:
            continue
    return None


def provider_matches(rows: Iterable[dict[str, object]]) -> list[ProviderMatch]:
    matches: list[ProviderMatch] = []
    seen: set[str] = set()
    for row in rows:
        raw_url = str(row.get("url") or "")
        url = urljoin(PROVIDER_BASE_URL, raw_url)
        match_id = str(row.get("matchId") or match_id_from_url(url) or "")
        if not match_id or match_id in seen:
            continue
        seen.add(match_id)
        matches.append(
            ProviderMatch(
                match_id=match_id,
                url=url,
                home_team=str(row.get("home") or row.get("home_team") or ""),
                away_team=str(row.get("away") or row.get("away_team") or ""),
                match_date=_provider_date(row.get("startDate") or row.get("date")),
            )
        )
    return matches


def discover_completed_matches(league: str, season: str) -> list[dict[str, object]]:
    """Open one league page and return its completed match links for a season."""
    source = LEAGUE_SOURCES.get(league)
    if source is None:
        raise ValueError(f"No WhoScored competition mapping configured for league {league!r}")
    with LEAGUE_URLS_PATH.open() as handle:
        competition_urls = json.load(handle)
    if source.provider_competition not in competition_urls:
        raise ValueError(
            f"WhoScored competition URL is missing for {source.provider_competition!r}"
        )

    # Imported lazily so unit tests and sleeping coordinator processes do not
    # import Selenium or start Firefox.
    from main import getMatchUrls

    return getMatchUrls(
        comp_urls=competition_urls,
        competition=source.provider_competition,
        season=season,
    ) or []


def resolve_fixture_urls(
    fixtures: Iterable[WorkerFixture],
    *,
    discoverer: Callable[[str, str], list[dict[str, object]]] = discover_completed_matches,
    minimum_team_score: float = 0.72,
    ambiguity_margin: float = 0.04,
) -> ResolutionBatch:
    fixture_list = list(fixtures)
    if not fixture_list:
        return ResolutionBatch(urls={}, errors={}, candidate_count=0)
    targets = {(fixture.league, fixture.season) for fixture in fixture_list}
    if len(targets) != 1:
        raise ValueError("URL discovery batches must contain exactly one league and season")
    league, season = next(iter(targets))
    candidates = provider_matches(discoverer(league, season))
    available = {candidate.match_id: candidate for candidate in candidates}
    urls: dict[str, str] = {}
    errors: dict[str, str] = {}

    for fixture in sorted(fixture_list, key=lambda item: (item.kickoff_utc, item.fixture_id)):
        fixture_date = fixture.kickoff_utc.date()
        ranked: list[tuple[float, ProviderMatch]] = []
        for candidate in available.values():
            if candidate.match_date is not None:
                day_distance = abs((candidate.match_date - fixture_date).days)
                if day_distance > 1:
                    continue
            home_score = _team_similarity(fixture.home_team, candidate.home_team)
            away_score = _team_similarity(fixture.away_team, candidate.away_team)
            if min(home_score, away_score) < minimum_team_score:
                continue
            date_bonus = 0.08 if candidate.match_date == fixture_date else 0.0
            ranked.append(((home_score + away_score) / 2 + date_bonus, candidate))

        ranked.sort(key=lambda item: (-item[0], item[1].match_id))
        if not ranked:
            errors[fixture.fixture_id] = "No completed provider match matched the scheduled teams/date"
            continue
        if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < ambiguity_margin:
            errors[fixture.fixture_id] = "Multiple provider matches ambiguously matched the scheduled teams/date"
            continue
        selected = ranked[0][1]
        urls[fixture.fixture_id] = selected.url
        available.pop(selected.match_id, None)

    return ResolutionBatch(urls=urls, errors=errors, candidate_count=len(candidates))
