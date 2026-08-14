from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
from pathlib import Path
from threading import Lock
from time import monotonic
from typing import Any, Literal, Protocol

import certifi
import requests
import urllib3

from app.config import ROOT_DIR, settings
from app.domain import TEAM_DICT
from app.services import r2
from app.services.fixture_rounds import build_fixture_rounds, infer_fixture_rounds
from app.services.standings import TOP_FIVE_COMPETITION_CODES, _match_local_team, provider_season_year


FixtureState = Literal["completed", "upcoming", "postponed", "cancelled", "live", "unknown"]


_PROVIDER_STATUS_TO_STATE: dict[str, FixtureState] = {
    "FINISHED": "completed",
    "AWARDED": "completed",
    "SCHEDULED": "upcoming",
    "TIMED": "upcoming",
    "POSTPONED": "postponed",
    "CANCELLED": "cancelled",
    "SUSPENDED": "unknown",
    "IN_PLAY": "live",
    "PAUSED": "live",
}

_MLS_STATUS_TO_PROVIDER_STATUS = {
    "finalwhistle": "FINISHED",
    "scheduled": "SCHEDULED",
    "postponed": "POSTPONED",
    "cancelled": "CANCELLED",
    "canceled": "CANCELLED",
    "suspended": "SUSPENDED",
    "inprogress": "IN_PLAY",
    "firsthalf": "IN_PLAY",
    "halftime": "PAUSED",
    "secondhalf": "IN_PLAY",
}

MLS_COMPETITION_ID = "MLS-COM-000001"


class ScheduleProviderError(RuntimeError):
    pass


class ScheduleProvider(Protocol):
    def fetch(self, league: str, season: str) -> list[dict[str, Any]]: ...


def current_provider_season_key(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    start_year = current.year if current.month >= 6 else current.year - 1
    return f"{start_year}_{start_year + 1}"


def provider_season_keys(league: str) -> list[str]:
    if league == "mls":
        return [str(datetime.now(timezone.utc).year)]
    if league not in TOP_FIVE_COMPETITION_CODES or not settings.football_data_api_key:
        return []
    return [current_provider_season_key()]


def _date_label(value: datetime) -> str:
    return value.date().isoformat()


def _provider_team_name(raw_team: dict[str, Any]) -> str:
    return str(
        raw_team.get("name")
        or raw_team.get("shortName")
        or raw_team.get("tla")
        or "Unknown"
    )


def _score_label(match: dict[str, Any]) -> str:
    full_time = (match.get("score") or {}).get("fullTime") or {}
    home = full_time.get("home")
    away = full_time.get("away")
    if home is None or away is None:
        return ""
    return f"{home}-{away}"


def _fixture_identity(value: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(value.get("start_date_label") or str(value.get("start_date", "")).split("T")[0]),
        str(value.get("home_team") or "").casefold(),
        str(value.get("away_team") or "").casefold(),
    )


def _fixture_date(value: dict[str, Any]) -> date:
    raw = value.get("start_date")
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).date()


def _round_summary_from_fixtures(
    matchday: int,
    fixtures: list[dict[str, Any]],
    *,
    part: int | None = None,
) -> dict[str, Any]:
    ordered = sorted(fixtures, key=lambda item: (str(item.get("start_date")), str(item.get("fixture_id"))))
    dates = [_fixture_date(fixture) for fixture in ordered]
    round_id = f"matchday-{matchday}" if part is None else f"matchday-{matchday}-{part}"
    label = f"Matchday {matchday}" if part is None else f"Matchday {matchday} · Part {part}"
    return {
        "id": round_id,
        "label": label,
        "stage": f"Matchday {matchday}" if part is not None else "Regular Season",
        "order": matchday * 100 + (part or 0),
        "start_date": min(dates),
        "end_date": max(dates),
        "match_count": len(ordered),
        "metadata_source": "inferred",
        "fixtures": ordered,
    }


def _has_team_conflict(fixtures: list[dict[str, Any]]) -> bool:
    seen: set[str] = set()
    for fixture in fixtures:
        for team_key in ("home_team", "away_team"):
            team = str(fixture.get(team_key) or "").casefold()
            if not team:
                continue
            if team in seen:
                return True
            seen.add(team)
    return False


def _build_hub_rounds(fixtures: list[dict[str, Any]], *, league: str | None = None) -> list[dict[str, Any]]:
    if league == "mls":
        completed = [fixture for fixture in fixtures if fixture.get("state") == "completed"]
        remaining = [fixture for fixture in fixtures if fixture.get("state") != "completed"]
        completed_rounds = build_fixture_rounds(completed, merge_orphan_rounds=True) if completed else []
        remaining_rounds = _build_hub_rounds(remaining) if remaining else []
        remaining_rounds.sort(key=lambda item: (item["start_date"], item["end_date"]), reverse=True)
        return remaining_rounds + completed_rounds

    matchday_groups: dict[int, list[dict[str, Any]]] = {}
    for fixture in fixtures:
        matchday = fixture.get("matchday")
        if isinstance(matchday, int):
            matchday_groups.setdefault(matchday, []).append(fixture)
    if matchday_groups and sum(len(items) for items in matchday_groups.values()) == len(fixtures):
        rounds: list[dict[str, Any]] = []
        for matchday, round_fixtures in sorted(matchday_groups.items(), reverse=True):
            if not _has_team_conflict(round_fixtures):
                rounds.append(_round_summary_from_fixtures(matchday, round_fixtures))
                continue

            split_rounds = infer_fixture_rounds(round_fixtures)
            part_count = len(split_rounds)
            for index, split_round in enumerate(split_rounds, start=1):
                # infer_fixture_rounds returns latest first; keep that display order
                # while assigning part numbers chronologically.
                part = part_count - index + 1
                rounds.append(_round_summary_from_fixtures(matchday, split_round["fixtures"], part=part))
        return rounds
    return build_fixture_rounds(fixtures, merge_orphan_rounds=league == "mls")


def _opposition_href(
    *,
    league: str,
    season: str,
    fixture_id: str,
    home_team: str,
    away_team: str,
) -> str:
    from urllib.parse import urlencode

    return "/opposition-analysis?" + urlencode(
        {
            "league": league,
            "season": season,
            "fixtureId": fixture_id,
            "home": home_team,
            "away": away_team,
            "referenceTeam": home_team,
            "opponentTeam": away_team,
        }
    )


class FootballDataScheduleProvider:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.football-data.org/v4",
        timeout_seconds: float = 10.0,
        verify_tls: bool = True,
        session: requests.Session | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.verify_tls = verify_tls
        self.session = session or requests.Session()
        if not verify_tls:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def fetch(self, league: str, season: str) -> list[dict[str, Any]]:
        competition_code = TOP_FIVE_COMPETITION_CODES.get(league)
        if not competition_code:
            raise ScheduleProviderError("Official schedules are not supported for this league.")

        try:
            response = self.session.get(
                f"{self.base_url}/competitions/{competition_code}/matches",
                headers={"X-Auth-Token": self.api_key},
                params={"season": provider_season_year(season)},
                timeout=self.timeout_seconds,
                verify=certifi.where() if self.verify_tls else False,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise ScheduleProviderError("The official schedule provider request failed.") from exc

        matches = payload.get("matches", []) if isinstance(payload, dict) else []
        if not isinstance(matches, list):
            raise ScheduleProviderError("The official schedule provider returned no matches.")
        return matches


class OfficialMlsScheduleProvider:
    def __init__(
        self,
        *,
        base_url: str = "https://stats-api.mlssoccer.com",
        timeout_seconds: float = 15.0,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()
        self._season_ids: dict[int, str] = {}

    def _season_id(self, season_year: int) -> str:
        cached = self._season_ids.get(season_year)
        if cached:
            return cached
        try:
            response = self.session.get(
                f"{self.base_url}/competitions/{MLS_COMPETITION_ID}/seasons",
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise ScheduleProviderError("The official MLS seasons request failed.") from exc
        seasons = payload.get("seasons", []) if isinstance(payload, dict) else []
        match = next(
            (
                item for item in seasons
                if isinstance(item, dict) and item.get("season") == season_year and item.get("season_id")
            ),
            None,
        )
        if not match:
            raise ScheduleProviderError(f"The official MLS feed has no season metadata for {season_year}.")
        season_id = str(match["season_id"])
        self._season_ids[season_year] = season_id
        return season_id

    def fetch(self, league: str, season: str) -> list[dict[str, Any]]:
        if league != "mls":
            raise ScheduleProviderError("The official MLS schedule provider only supports MLS.")
        season_year = provider_season_year(season)
        season_id = self._season_id(season_year)
        base_params: dict[str, Any] = {
            "match_date[gte]": f"{season_year}-01-01",
            "match_date[lte]": f"{season_year}-12-31",
            "competition_id": MLS_COMPETITION_ID,
            "per_page": 1000,
            "sort": "planned_kickoff_time:asc,home_team_name:asc",
        }
        matches: list[dict[str, Any]] = []
        page_token: str | None = None
        seen_tokens: set[str] = set()
        for _ in range(10):
            params = dict(base_params)
            if page_token:
                params["page_token"] = page_token
            try:
                response = self.session.get(
                    f"{self.base_url}/matches/seasons/{season_id}",
                    params=params,
                    timeout=self.timeout_seconds,
                )
                response.raise_for_status()
                payload = response.json()
            except (requests.RequestException, ValueError) as exc:
                raise ScheduleProviderError("The official MLS schedule request failed.") from exc
            rows = payload.get("schedule", []) if isinstance(payload, dict) else []
            if not isinstance(rows, list):
                raise ScheduleProviderError("The official MLS schedule returned an invalid payload.")
            matches.extend({**row, "_provider": "official-mls"} for row in rows if isinstance(row, dict))
            next_token = payload.get("next_page_token") if isinstance(payload, dict) else None
            if not next_token:
                break
            page_token = str(next_token)
            if page_token in seen_tokens:
                raise ScheduleProviderError("The official MLS schedule pagination repeated a page token.")
            seen_tokens.add(page_token)
        else:
            raise ScheduleProviderError("The official MLS schedule exceeded the pagination limit.")
        if not matches:
            raise ScheduleProviderError("The official MLS schedule returned no matches.")
        return matches


class ScheduleProviderRouter:
    def __init__(
        self,
        football_data: FootballDataScheduleProvider | None,
        official_mls: OfficialMlsScheduleProvider,
    ) -> None:
        self.football_data = football_data
        self.official_mls = official_mls

    def fetch(self, league: str, season: str) -> list[dict[str, Any]]:
        if league == "mls":
            return self.official_mls.fetch(league, season)
        if self.football_data is None:
            raise ScheduleProviderError("The official schedule provider is not configured.")
        return self.football_data.fetch(league, season)


@dataclass
class _ScheduleCacheEntry:
    fixtures: list[dict[str, Any]]
    fetched_at: float
    updated_at: datetime


class ScheduleService:
    def __init__(
        self,
        provider: ScheduleProvider | None,
        *,
        cache_ttl_seconds: int = 21_600,
        stale_ttl_seconds: int = 86_400,
        cache_dir: Path | str | None = None,
    ) -> None:
        self.provider = provider
        self.cache_ttl_seconds = cache_ttl_seconds
        self.stale_ttl_seconds = stale_ttl_seconds
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self._cache: dict[tuple[str, str], _ScheduleCacheEntry] = {}
        self._lock = Lock()

    def _cache_path(self, league: str, season: str) -> Path | None:
        if self.cache_dir is None:
            return None
        return self.cache_dir / league / f"{season}.json"

    def _serialize_fixture(self, fixture: dict[str, Any]) -> dict[str, Any]:
        payload = dict(fixture)
        start_date = payload.get("start_date")
        if isinstance(start_date, datetime):
            payload["start_date"] = start_date.isoformat()
        elif isinstance(start_date, date):
            payload["start_date"] = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc).isoformat()
        return payload

    def _deserialize_fixture(self, fixture: dict[str, Any]) -> dict[str, Any]:
        payload = dict(fixture)
        start_date = payload.get("start_date")
        if isinstance(start_date, str) and start_date:
            try:
                payload["start_date"] = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            except ValueError:
                pass
        return payload

    def _write_persisted_cache(
        self,
        league: str,
        season: str,
        fixtures: list[dict[str, Any]],
        updated_at: datetime,
    ) -> None:
        path = self._cache_path(league, season)
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = path.with_suffix(".tmp")
            tmp_path.write_text(
                json.dumps(
                    {
                        "league": league,
                        "season": season,
                        "updated_at": updated_at.isoformat(),
                        "fixtures": [self._serialize_fixture(fixture) for fixture in fixtures],
                    },
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
            tmp_path.replace(path)
        except OSError:
            return

    def _read_persisted_cache(self, league: str, season: str) -> _ScheduleCacheEntry | None:
        path = self._cache_path(league, season)
        if path is None or not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            fixtures_raw = payload.get("fixtures")
            updated_at_raw = payload.get("updated_at")
            if not isinstance(fixtures_raw, list) or not updated_at_raw:
                return None
            updated_at = datetime.fromisoformat(str(updated_at_raw).replace("Z", "+00:00"))
            fixtures = [self._deserialize_fixture(fixture) for fixture in fixtures_raw if isinstance(fixture, dict)]
        except (OSError, ValueError, TypeError):
            return None
        return _ScheduleCacheEntry(fixtures=fixtures, fetched_at=monotonic(), updated_at=updated_at)

    def _local_team_names(self, completed: list[dict[str, Any]]) -> list[str]:
        names = set(str(name) for name in TEAM_DICT.values())
        for fixture in completed:
            for key in ("home_team", "away_team"):
                if fixture.get(key):
                    names.add(str(fixture[key]))
        return sorted(names)

    def _normalize_provider_fixture(
        self,
        match: dict[str, Any],
        *,
        league: str,
        season: str,
        local_names: list[str],
    ) -> dict[str, Any]:
        is_official_mls = match.get("_provider") == "official-mls"
        utc_date_raw = str(match.get("planned_kickoff_time") if is_official_mls else match.get("utcDate") or "")
        try:
            start_date = datetime.fromisoformat(utc_date_raw.replace("Z", "+00:00"))
        except ValueError:
            start_date = datetime.now(timezone.utc)

        home_team_raw = (
            {"name": match.get("home_team_name"), "tla": match.get("home_team_three_letter_code")}
            if is_official_mls else match.get("homeTeam") or {}
        )
        away_team_raw = (
            {"name": match.get("away_team_name"), "tla": match.get("away_team_three_letter_code")}
            if is_official_mls else match.get("awayTeam") or {}
        )
        provider_home = _provider_team_name(home_team_raw)
        provider_away = _provider_team_name(away_team_raw)
        home_team = _match_local_team(provider_home, local_names) or provider_home
        away_team = _match_local_team(provider_away, local_names) or provider_away
        status = (
            _MLS_STATUS_TO_PROVIDER_STATUS.get(str(match.get("match_status") or "").replace("_", "").casefold(), "UNKNOWN")
            if is_official_mls else str(match.get("status") or "UNKNOWN").upper()
        )
        state = _PROVIDER_STATUS_TO_STATE.get(status, "unknown")
        provider_fixture_id = match.get("match_id") if is_official_mls else match.get("id")
        fixture_source = "official-mls" if is_official_mls else "football-data"
        fixture_id = f"mls-{provider_fixture_id}" if is_official_mls else f"fd-{provider_fixture_id}"
        score = (
            str(match.get("result") or "").replace(":", "-") if state == "completed" and is_official_mls
            else _score_label(match)
        )
        matchday = match.get("match_day") if is_official_mls else match.get("matchday")
        return {
            "fixture_id": fixture_id,
            "match_id": fixture_id,
            "state": state,
            "source": fixture_source,
            "league": league,
            "season": season,
            "round": f"matchday-{matchday}" if matchday else None,
            "matchday": matchday,
            "start_date": start_date,
            "start_date_label": _date_label(start_date),
            "home_team": home_team,
            "away_team": away_team,
            "provider_home_team": provider_home,
            "provider_away_team": provider_away,
            "home_crest": home_team_raw.get("crest"),
            "away_crest": away_team_raw.get("crest"),
            "provider_fixture_id": provider_fixture_id,
            "provider_status": status,
            "score": score,
            "venue_id": match.get("stadium_id") if is_official_mls else None,
            "venue": match.get("stadium_name") if is_official_mls else None,
            "venue_city": match.get("stadium_city") if is_official_mls else None,
            "venue_country": match.get("stadium_country") if is_official_mls else None,
            "post_match_href": None,
            "opposition_href": _opposition_href(
                league=league,
                season=season,
                fixture_id=fixture_id,
                home_team=home_team,
                away_team=away_team,
            ),
        }

    def _provider_fixtures(
        self,
        league: str,
        season: str,
        completed: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], datetime | None, bool, str | None]:
        if self.provider is None:
            return [], None, False, "The official schedule provider is not configured."
        if league not in TOP_FIVE_COMPETITION_CODES and league != "mls":
            return [], None, False, (
                "Official future fixtures are not configured for this league."
            )

        key = (league, season)
        now = monotonic()
        with self._lock:
            cached = self._cache.get(key)
            if cached and now - cached.fetched_at < self.cache_ttl_seconds:
                return deepcopy(cached.fixtures), cached.updated_at, False, None

        try:
            raw_matches = self.provider.fetch(league, season)
            local_names = self._local_team_names(completed)
            fixtures = [
                self._normalize_provider_fixture(match, league=league, season=season, local_names=local_names)
                for match in raw_matches
            ]
        except ScheduleProviderError:
            with self._lock:
                cached = self._cache.get(key)
                if cached and now - cached.fetched_at < self.stale_ttl_seconds:
                    return (
                        deepcopy(cached.fixtures),
                        cached.updated_at,
                        True,
                        "Showing the most recently cached official schedule while the provider is unavailable.",
                    )
                persisted = self._read_persisted_cache(league, season)
                if persisted:
                    self._cache[key] = _ScheduleCacheEntry(
                        deepcopy(persisted.fixtures),
                        now,
                        persisted.updated_at,
                    )
                    return (
                        deepcopy(persisted.fixtures),
                        persisted.updated_at,
                        True,
                        "Showing the most recently saved official schedule while the provider is unavailable.",
                    )
            return [], None, False, "Official schedule data is unavailable right now."

        updated_at = datetime.now(timezone.utc)
        with self._lock:
            self._cache[key] = _ScheduleCacheEntry(deepcopy(fixtures), now, updated_at)
        self._write_persisted_cache(league, season, fixtures, updated_at)
        return fixtures, updated_at, False, None

    def official_fixtures(
        self,
        league: str,
        season: str,
    ) -> tuple[list[dict[str, Any]], datetime | None, bool, str | None]:
        """Return normalized provider fixtures without requiring an R2 archive.

        Remote ingestion workers use this boundary to plan future work while
        keeping match-storage reconciliation separate from schedule fetching.
        """

        return self._provider_fixtures(league, season, [])

    def _completed_fixture(self, fixture: dict[str, Any], *, league: str, season: str) -> dict[str, Any]:
        from urllib.parse import urlencode

        match_id = str(fixture.get("match_id") or "")
        post_match_href = f"/analysis/{match_id}?" + urlencode({"source": "r2", "league": league, "season": season})
        return {
            "fixture_id": f"r2-{match_id}",
            "match_id": match_id,
            "state": "completed",
            "source": "r2",
            "league": league,
            "season": season,
            "round": None,
            "matchday": None,
            "start_date": fixture.get("start_date"),
            "start_date_label": fixture.get("start_date_label"),
            "home_team_id": fixture.get("home_team_id"),
            "away_team_id": fixture.get("away_team_id"),
            "home_team": fixture.get("home_team"),
            "away_team": fixture.get("away_team"),
            "provider_home_team": None,
            "provider_away_team": None,
            "provider_fixture_id": None,
            "provider_status": None,
            "home_crest": None,
            "away_crest": None,
            "score": fixture.get("score") or "",
            "post_match_href": post_match_href,
            "opposition_href": None,
        }

    def _merge_fixtures(
        self,
        completed: list[dict[str, Any]],
        provider: list[dict[str, Any]],
        *,
        league: str,
        season: str,
    ) -> list[dict[str, Any]]:
        completed_normalized = [self._completed_fixture(fixture, league=league, season=season) for fixture in completed]
        completed_by_identity = {_fixture_identity(fixture): fixture for fixture in completed_normalized}
        completed_by_teams: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for fixture in completed_normalized:
            teams = (str(fixture.get("home_team") or "").casefold(), str(fixture.get("away_team") or "").casefold())
            completed_by_teams.setdefault(teams, []).append(fixture)
        merged = list(completed_normalized)
        for fixture in provider:
            identity = _fixture_identity(fixture)
            completed_match = completed_by_identity.get(identity)
            if completed_match is None and league == "mls":
                teams = (str(fixture.get("home_team") or "").casefold(), str(fixture.get("away_team") or "").casefold())
                nearby = [
                    candidate for candidate in completed_by_teams.get(teams, [])
                    if abs((_fixture_date(candidate) - _fixture_date(fixture)).days) <= 1
                ]
                if nearby:
                    completed_match = min(
                        nearby,
                        key=lambda candidate: abs((_fixture_date(candidate) - _fixture_date(fixture)).days),
                    )
            if completed_match is not None:
                completed_match.update(
                    {
                        "round": fixture.get("round"),
                        "matchday": fixture.get("matchday"),
                        "provider_home_team": fixture.get("provider_home_team"),
                        "provider_away_team": fixture.get("provider_away_team"),
                        "home_crest": fixture.get("home_crest"),
                        "away_crest": fixture.get("away_crest"),
                        "provider_fixture_id": fixture.get("provider_fixture_id"),
                        "provider_status": fixture.get("provider_status"),
                        "venue_id": fixture.get("venue_id"),
                        "venue": fixture.get("venue"),
                        "venue_city": fixture.get("venue_city"),
                        "venue_country": fixture.get("venue_country"),
                    }
                )
                continue
            merged.append(fixture)
        return sorted(merged, key=lambda item: (str(item.get("start_date")), str(item.get("fixture_id"))))

    def build_fixture_hub(self, league: str, season: str, *, state: str = "all", round_id: str | None = None) -> dict[str, Any]:
        completed = r2.list_all_fixtures(league, season)
        provider, updated_at, is_stale, warning = self._provider_fixtures(league, season, completed)
        fixtures = self._merge_fixtures(completed, provider, league=league, season=season)
        rounds = _build_hub_rounds(fixtures, league=league)
        if round_id:
            selected_round = next((round_item for round_item in rounds if round_item["id"] == round_id), None)
            if selected_round is None:
                selected_round = next((round_item for round_item in reversed(rounds) if str(round_item["id"]).startswith(f"{round_id}-")), None)
        else:
            upcoming_rounds = [
                round_item for round_item in rounds
                if any(f.get("state") == "upcoming" for f in round_item["fixtures"])
            ]
            selected_round = min(upcoming_rounds, key=lambda item: item["start_date"]) if upcoming_rounds else None
            if selected_round is None and rounds:
                selected_round = rounds[0]

        visible = selected_round["fixtures"] if selected_round else fixtures
        if state != "all":
            visible = [fixture for fixture in visible if fixture.get("state") == state]

        summaries = [{key: value for key, value in item.items() if key != "fixtures"} for item in rounds]
        provider_source = str(provider[0].get("source") or "football-data") if provider else "r2"
        return {
            "league": league,
            "season": season,
            "state": state,
            "round_id": round_id,
            "selected_round_id": str(selected_round["id"]) if selected_round else None,
            "source": "hybrid" if provider and completed else provider_source,
            "updated_at": updated_at,
            "is_stale": is_stale,
            "warning": warning,
            "counts": {
                "all": len(fixtures),
                "completed": sum(1 for fixture in fixtures if fixture.get("state") == "completed"),
                "upcoming": sum(1 for fixture in fixtures if fixture.get("state") == "upcoming"),
                "postponed": sum(1 for fixture in fixtures if fixture.get("state") == "postponed"),
                "cancelled": sum(1 for fixture in fixtures if fixture.get("state") == "cancelled"),
                "live": sum(1 for fixture in fixtures if fixture.get("state") == "live"),
                "unknown": sum(1 for fixture in fixtures if fixture.get("state") == "unknown"),
            },
            "rounds": summaries,
            "fixtures": visible,
        }


football_data_schedule_provider = (
    FootballDataScheduleProvider(
        settings.football_data_api_key,
        base_url=settings.football_data_base_url,
        timeout_seconds=settings.football_data_timeout_seconds,
        verify_tls=settings.should_verify_football_data_tls,
    )
    if settings.football_data_api_key
    else None
)
schedule_provider = ScheduleProviderRouter(
    football_data_schedule_provider,
    OfficialMlsScheduleProvider(
        base_url=settings.official_mls_schedule_base_url,
        timeout_seconds=settings.official_mls_schedule_timeout_seconds,
    ),
)
schedule_service = ScheduleService(
    schedule_provider,
    cache_dir=settings.football_data_schedule_cache_dir or ROOT_DIR / "apps" / "api" / ".cache" / "schedules",
)
