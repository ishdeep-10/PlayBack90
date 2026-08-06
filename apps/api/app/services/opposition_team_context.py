from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from time import monotonic
from typing import Any
import json
import unicodedata

import certifi
import requests
import urllib3

from app.config import settings
from app.services.opposition_foundation import previous_season_key
from app.services.standings import TOP_FIVE_COMPETITION_CODES, _match_local_team, provider_season_year


class TeamContextProviderError(RuntimeError):
    pass


THESPORTSDB_LEAGUE_NAMES = {
    "premier-league": "English Premier League",
    "laliga": "Spanish La Liga",
    "bundesliga": "German Bundesliga",
    "serie-a": "Italian Serie A",
    "ligue-1": "French Ligue 1",
}

API_FOOTBALL_LEAGUE_IDS = {
    "premier-league": 39,
    "laliga": 140,
    "bundesliga": 78,
    "serie-a": 135,
    "ligue-1": 61,
}

API_FOOTBALL_TEAM_ID_OVERRIDES = {
    "premier-league": {
        "afc bournemouth": 35,
        "arsenal": 42,
        "arsenal fc": 42,
        "aston villa": 66,
        "aston villa fc": 66,
        "bournemouth": 35,
        "brentford": 55,
        "brentford fc": 55,
        "brighton": 51,
        "brighton hove albion": 51,
        "brighton & hove albion fc": 51,
        "chelsea": 49,
        "chelsea fc": 49,
        "coventry city": 1346,
        "coventry city fc": 1346,
        "crystal palace": 52,
        "crystal palace fc": 52,
        "everton": 45,
        "everton fc": 45,
        "fulham": 36,
        "fulham fc": 36,
        "hull city": 64,
        "hull city afc": 64,
        "ipswich town": 57,
        "ipswich town fc": 57,
        "leeds united": 63,
        "leeds united fc": 63,
        "liverpool": 40,
        "liverpool fc": 40,
        "man city": 50,
        "manchester city": 50,
        "manchester city fc": 50,
        "man utd": 33,
        "manchester united": 33,
        "manchester united fc": 33,
        "newcastle": 34,
        "newcastle united": 34,
        "newcastle united fc": 34,
        "nottingham forest": 65,
        "nottingham forest fc": 65,
        "nott'm forest": 65,
        "sunderland": 746,
        "sunderland afc": 746,
        "tottenham": 47,
        "tottenham hotspur": 47,
        "tottenham hotspur fc": 47,
    },
}


@dataclass
class _TeamsCacheEntry:
    teams: list[dict[str, Any]]
    fetched_at: float


class FootballDataTeamContextProvider:
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
        self._cache: dict[tuple[str, str], _TeamsCacheEntry] = {}
        self._lock = Lock()
        if not verify_tls:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def fetch_competition_teams(self, league: str, season: str) -> list[dict[str, Any]]:
        competition_code = TOP_FIVE_COMPETITION_CODES.get(league)
        if not competition_code:
            raise TeamContextProviderError("Official team context is available only for configured top-five leagues.")

        key = (league, season)
        now = monotonic()
        with self._lock:
            cached = self._cache.get(key)
            if cached and now - cached.fetched_at < 21_600:
                return deepcopy(cached.teams)

        try:
            response = self.session.get(
                f"{self.base_url}/competitions/{competition_code}/teams",
                headers={"X-Auth-Token": self.api_key},
                params={"season": provider_season_year(season)},
                timeout=self.timeout_seconds,
                verify=certifi.where() if self.verify_tls else False,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise TeamContextProviderError("The official team context provider request failed.") from exc

        teams = payload.get("teams", []) if isinstance(payload, dict) else []
        if not isinstance(teams, list):
            raise TeamContextProviderError("The official team context provider returned no teams.")
        with self._lock:
            self._cache[key] = _TeamsCacheEntry(deepcopy(teams), now)
        return teams


@dataclass
class _ApiFootballCoachCacheEntry:
    coaches: list[dict[str, Any]]
    fetched_at: float


@dataclass
class _ApiFootballTransferCacheEntry:
    transfers: list[dict[str, Any]]
    fetched_at: float


@dataclass
class _TeamIdCacheEntry:
    team_id: int | None
    fetched_at: float


class TheSportsDbApiFootballTeamIdResolver:
    def __init__(self, *, base_url: str = "https://www.thesportsdb.com/api/v1/json/123", timeout_seconds: float = 8.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self._cache: dict[tuple[str | None, str], _TeamIdCacheEntry] = {}
        self._lock = Lock()

    def resolve(self, team_name: str, league: str | None = None) -> int | None:
        key = _normalized_team_key(team_name)
        cache_key = (league, key)
        now = monotonic()
        with self._lock:
            cached = self._cache.get(cache_key)
            if cached and now - cached.fetched_at < 86_400:
                return cached.team_id

        team_id = self._resolve_from_league(team_name, league) if league else None
        if team_id is None:
            team_id = self._resolve_from_search(team_name)

        with self._lock:
            self._cache[cache_key] = _TeamIdCacheEntry(team_id, now)
        return team_id

    def _team_id_from_rows(self, team_name: str, teams: Any) -> int | None:
        if not isinstance(teams, list):
            return None
        provider_names = [
            str(team.get("strTeam") or "")
            for team in teams
            if isinstance(team, dict) and team.get("idAPIfootball")
        ]
        matched = _match_local_team(team_name, provider_names)
        for team in teams:
            if not isinstance(team, dict) or not team.get("idAPIfootball"):
                continue
            if matched and str(team.get("strTeam") or "") == matched:
                return _safe_int(team["idAPIfootball"])
        return None

    def _resolve_from_league(self, team_name: str, league: str | None) -> int | None:
        league_name = THESPORTSDB_LEAGUE_NAMES.get(league or "")
        if not league_name:
            return None
        try:
            response = self.session.get(
                f"{self.base_url}/search_all_teams.php",
                params={"l": league_name},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError):
            return None
        return self._team_id_from_rows(team_name, payload.get("teams", []) if isinstance(payload, dict) else [])

    def _resolve_from_search(self, team_name: str) -> int | None:
        try:
            response = self.session.get(
                f"{self.base_url}/searchteams.php",
                params={"t": team_name},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError):
            payload = {}

        teams = payload.get("teams", []) if isinstance(payload, dict) else []
        return self._team_id_from_rows(team_name, teams)


class ApiFootballCoachProvider:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://v3.football.api-sports.io",
        timeout_seconds: float = 10.0,
        transfer_cache_dir: Path | str | None = None,
        team_id_resolver: TheSportsDbApiFootballTeamIdResolver | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.transfer_cache_dir = Path(transfer_cache_dir) if transfer_cache_dir else None
        self.team_id_resolver = team_id_resolver or TheSportsDbApiFootballTeamIdResolver()
        self.session = session or requests.Session()
        self._cache: dict[int, _ApiFootballCoachCacheEntry] = {}
        self._transfer_cache: dict[int, _ApiFootballTransferCacheEntry] = {}
        self._team_cache: dict[tuple[str, str], _TeamIdCacheEntry] = {}
        self._lock = Lock()

    def _transfer_cache_path(self, team_id: int) -> Path | None:
        if self.transfer_cache_dir is None:
            return None
        return self.transfer_cache_dir / f"{team_id}.json"

    def _read_transfer_disk_cache(self, team_id: int) -> _ApiFootballTransferCacheEntry | None:
        path = self._transfer_cache_path(team_id)
        if path is None or not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            rows = payload.get("response")
            fetched_at_raw = payload.get("fetched_at")
            if not isinstance(rows, list) or not fetched_at_raw:
                return None
            fetched_at_dt = datetime.fromisoformat(str(fetched_at_raw).replace("Z", "+00:00"))
            age_seconds = max(0.0, (datetime.now(timezone.utc) - fetched_at_dt).total_seconds())
        except (OSError, ValueError, TypeError):
            return None
        return _ApiFootballTransferCacheEntry(transfers=rows, fetched_at=monotonic() - age_seconds)

    def _write_transfer_disk_cache(self, team_id: int, rows: list[dict[str, Any]]) -> None:
        path = self._transfer_cache_path(team_id)
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = path.with_suffix(".tmp")
            tmp_path.write_text(
                json.dumps(
                    {
                        "team_id": team_id,
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                        "response": rows,
                    },
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
            tmp_path.replace(path)
        except OSError:
            return

    def _resolve_team_id(self, team_name: str, league: str | None, season: str) -> int | None:
        league_id = API_FOOTBALL_LEAGUE_IDS.get(league or "")
        cache_key = (f"{league or ''}:{season}", _normalized_team_key(team_name))
        now = monotonic()
        with self._lock:
            cached = self._team_cache.get(cache_key)
            if cached and now - cached.fetched_at < 86_400:
                return cached.team_id

        team_id: int | None = API_FOOTBALL_TEAM_ID_OVERRIDES.get(league or "", {}).get(_normalized_team_key(team_name))
        if team_id is None and league_id:
            for provider_season in _api_football_season_candidates(season):
                try:
                    response = self.session.get(
                        f"{self.base_url}/teams",
                        headers={"x-apisports-key": self.api_key},
                        params={"league": league_id, "season": provider_season},
                        timeout=self.timeout_seconds,
                    )
                    response.raise_for_status()
                    payload = response.json()
                except (requests.RequestException, ValueError):
                    continue
                rows = payload.get("response", []) if isinstance(payload, dict) else []
                teams = [row.get("team") for row in rows if isinstance(row, dict) and isinstance(row.get("team"), dict)]
                provider_names = [str(team.get("name") or "") for team in teams if team.get("id")]
                matched = _match_local_team(team_name, provider_names)
                for team in teams:
                    if matched and str(team.get("name") or "") == matched:
                        team_id = _safe_int(team.get("id"))
                        break
                if team_id:
                    break

        if team_id is None:
            team_id = self.team_id_resolver.resolve(team_name, league)

        with self._lock:
            self._team_cache[cache_key] = _TeamIdCacheEntry(team_id, now)
        return team_id

    def fetch_team_coaches(self, team_name: str, league: str | None = None, season: str = "") -> list[dict[str, Any]]:
        team_id = self._resolve_team_id(team_name, league, season)
        if not team_id:
            return []

        now = monotonic()
        with self._lock:
            cached = self._cache.get(team_id)
            if cached and now - cached.fetched_at < 86_400:
                return deepcopy(cached.coaches)

        try:
            response = self.session.get(
                f"{self.base_url}/coachs",
                headers={"x-apisports-key": self.api_key},
                params={"team": team_id},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError):
            coaches: list[dict[str, Any]] = []
        else:
            rows = payload.get("response", []) if isinstance(payload, dict) else []
            coaches = [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []

        with self._lock:
            self._cache[team_id] = _ApiFootballCoachCacheEntry(deepcopy(coaches), now)
        return coaches

    def coach_for_season(self, team_name: str, season: str, league: str | None = None) -> dict[str, Any]:
        team_id = self._resolve_team_id(team_name, league, season)
        if not team_id:
            return _empty_api_football_coach(season, "API-Football team id could not be resolved.")

        coaches = self.fetch_team_coaches(team_name, league, season)
        if not coaches:
            return _empty_api_football_coach(season, "API-Football returned no coach rows for this team.")

        season_start = _season_start(season)
        season_end = _season_end(season)
        selected: tuple[dict[str, Any], dict[str, Any] | None, datetime | None] | None = None
        for coach in coaches:
            career = coach.get("career") if isinstance(coach.get("career"), list) else []
            for stint in career:
                if not isinstance(stint, dict):
                    continue
                stint_team = stint.get("team") if isinstance(stint.get("team"), dict) else {}
                if _safe_int(stint_team.get("id")) != team_id:
                    continue
                if _stint_overlaps_season(stint, season_start, season_end):
                    stint_start = _parse_date(stint.get("start"), datetime.min.replace(tzinfo=timezone.utc))
                    if not selected or (stint_start and (selected[2] is None or stint_start > selected[2])):
                        selected = (coach, stint, stint_start)

        if not selected:
            # The endpoint usually returns the current coach first. Use it as a
            # directional fallback only when no career stint dates overlap.
            selected = (coaches[0], None, None)

        coach, stint, _stint_start = selected
        name = str(coach.get("name") or "").strip()
        return {
            "season": season,
            "name": name or None,
            "nationality": coach.get("nationality"),
            "contract_start": (stint or {}).get("start"),
            "contract_until": (stint or {}).get("end"),
            "source": "api-football",
            "provider_team_id": team_id,
            "photo": coach.get("photo"),
            "available": bool(name),
        }

    def fetch_team_transfers(self, team_name: str, league: str | None = None, season: str = "") -> tuple[int | None, list[dict[str, Any]], str | None]:
        team_id = self._resolve_team_id(team_name, league, season)
        if not team_id:
            return None, [], "API-Football team id could not be resolved."

        now = monotonic()
        with self._lock:
            cached = self._transfer_cache.get(team_id)
            if cached and now - cached.fetched_at < 86_400:
                return team_id, deepcopy(cached.transfers), None
            disk_cached = self._read_transfer_disk_cache(team_id)
            if disk_cached and now - disk_cached.fetched_at < 86_400:
                self._transfer_cache[team_id] = disk_cached
                return team_id, deepcopy(disk_cached.transfers), None

        warning: str | None = None
        try:
            response = self.session.get(
                f"{self.base_url}/transfers",
                headers={"x-apisports-key": self.api_key},
                params={"team": team_id},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError):
            transfers: list[dict[str, Any]] = []
            warning = "API-Football transfer request failed."
        else:
            errors = payload.get("errors") if isinstance(payload, dict) else None
            if errors:
                warning = f"API-Football transfer request returned errors: {errors}"
            rows = payload.get("response", []) if isinstance(payload, dict) else []
            transfers = [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []

        if warning:
            disk_cached = self._read_transfer_disk_cache(team_id)
            if disk_cached:
                with self._lock:
                    self._transfer_cache[team_id] = disk_cached
                return team_id, deepcopy(disk_cached.transfers), f"Serving cached transfers because live request failed: {warning}"

        with self._lock:
            self._transfer_cache[team_id] = _ApiFootballTransferCacheEntry(deepcopy(transfers), now)
        if not warning and transfers:
            self._write_transfer_disk_cache(team_id, transfers)
        return team_id, transfers, warning

    def transfer_activity_for_season(self, team_name: str, season: str, league: str | None = None) -> dict[str, Any]:
        team_id, rows, warning = self.fetch_team_transfers(team_name, league, season)
        if not team_id:
            return _empty_transfer_activity("API-Football team id could not be resolved.")

        window_start = _season_start(season)
        window_end = _season_end(season)
        if not window_start or not window_end:
            return _empty_transfer_activity("The transfer window could not be derived from the fixture season.")

        from app.services.player_images import resolve_player_image

        incomings: list[dict[str, Any]] = []
        outgoings: list[dict[str, Any]] = []
        for row in rows:
            player = row.get("player") if isinstance(row.get("player"), dict) else {}
            player_name = str(player.get("name") or "").strip()
            player_id = player.get("id")
            for transfer in row.get("transfers") if isinstance(row.get("transfers"), list) else []:
                if not isinstance(transfer, dict):
                    continue
                transfer_date = _parse_date(transfer.get("date"), None)
                if not transfer_date or transfer_date < window_start or transfer_date > window_end:
                    continue
                teams = transfer.get("teams") if isinstance(transfer.get("teams"), dict) else {}
                team_in = teams.get("in") if isinstance(teams.get("in"), dict) else {}
                team_out = teams.get("out") if isinstance(teams.get("out"), dict) else {}
                direction = "in" if _safe_int(team_in.get("id")) == team_id else ("out" if _safe_int(team_out.get("id")) == team_id else "")
                if not direction:
                    continue
                transfer_type = transfer.get("type")
                from_team_name = team_out.get("name")
                to_team_name = team_in.get("name")
                if str(transfer_type or "").casefold() == "free agent":
                    if direction == "in" and _safe_int(team_out.get("id")) is None:
                        from_team_name = None
                    if direction == "out" and _safe_int(team_in.get("id")) is None:
                        to_team_name = None
                item = {
                    "player_id": player_id,
                    "player": player_name,
                    "date": str(transfer.get("date") or ""),
                    "type": transfer_type,
                    "from_team": from_team_name,
                    "from_team_id": team_out.get("id"),
                    "from_team_logo": team_out.get("logo"),
                    "to_team": to_team_name,
                    "to_team_id": team_in.get("id"),
                    "to_team_logo": team_in.get("logo"),
                    "image": resolve_player_image(player_name, team_name) or resolve_player_image(player_name),
                    "source": "api-football",
                }
                if direction == "in":
                    incomings.append(item)
                else:
                    outgoings.append(item)

        incomings = _dedupe_transfer_rows(incomings)
        outgoings = _dedupe_transfer_rows(outgoings)
        incomings = _drop_same_window_incomings_with_followup_outgoing(incomings, outgoings)
        outgoings = _drop_superseded_return_rows(outgoings)
        return {
            "available": bool(incomings or outgoings),
            "source": "api-football",
            "warning": warning,
            "team_id": team_id,
            "window_start": window_start.date().isoformat(),
            "window_end": window_end.date().isoformat(),
            "incoming_count": len(incomings),
            "outgoing_count": len(outgoings),
            "incomings": incomings,
            "outgoings": outgoings,
            "note": "Transfer activity from API-Football, filtered to the fixture season window.",
        }


class CoachOverrideProvider:
    def __init__(self) -> None:
        self._payload: dict[str, Any] | None = None
        self._lock = Lock()

    def _load(self) -> dict[str, Any]:
        with self._lock:
            if self._payload is not None:
                return self._payload
            from pathlib import Path

            path = Path(__file__).resolve().parents[1] / "data" / "coach_overrides.json"
            try:
                self._payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self._payload = {}
            return self._payload

    def coach_for_season(self, league: str, season: str, team_names: list[str], *, previous_name: str | None = None) -> dict[str, Any] | None:
        season_rows = ((self._load().get(league) or {}).get(season) or {})
        if not isinstance(season_rows, dict):
            return None
        aliases = {_normalized_team_key(name) for name in team_names if name}
        for raw_name, row in season_rows.items():
            if _normalized_team_key(raw_name) not in aliases or not isinstance(row, dict):
                continue
            name = str(row.get("name") or "").strip()
            if not name:
                return None
            return {
                "season": season,
                "name": name,
                "nationality": row.get("nationality"),
                "contract_start": row.get("contract_start"),
                "contract_until": row.get("contract_until"),
                "source": "coach-overrides",
                "source_url": row.get("source_url"),
                "available": True,
                "previous_name": row.get("previous_name") or previous_name,
            }
        return None


def _coach_payload(team: dict[str, Any] | None, *, season: str) -> dict[str, Any]:
    coach = (team or {}).get("coach") if isinstance((team or {}).get("coach"), dict) else {}
    contract = coach.get("contract") if isinstance(coach.get("contract"), dict) else {}
    name = str(coach.get("name") or "").strip()
    return {
        "season": season,
        "name": name or None,
        "nationality": coach.get("nationality"),
        "contract_start": contract.get("start"),
        "contract_until": contract.get("until"),
        "source": "football-data",
        "available": bool(name),
    }


def _empty_api_football_coach(season: str, reason: str) -> dict[str, Any]:
    return {
        "season": season,
        "name": None,
        "nationality": None,
        "contract_start": None,
        "contract_until": None,
        "source": "api-football",
        "available": False,
        "reason": reason,
    }


def _empty_transfer_activity(reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "source": "api-football",
        "warning": reason,
        "incoming_count": 0,
        "outgoing_count": 0,
        "incomings": [],
        "outgoings": [],
    }


def _dedupe_transfer_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str]] = set()
    unique: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda item: str(item.get("date") or ""), reverse=True):
        key = (
            str(row.get("player_id") or row.get("player") or ""),
            str(row.get("type") or ""),
            str(row.get("from_team_id") or row.get("from_team") or ""),
            str(row.get("to_team_id") or row.get("to_team") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def _drop_same_window_incomings_with_followup_outgoing(incomings: list[dict[str, Any]], outgoings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    outgoing_by_player: dict[str, list[datetime]] = {}
    for row in outgoings:
        player_keys = _transfer_player_keys(row)
        transfer_date = _parse_date(row.get("date"), None)
        if transfer_date:
            for player_key in player_keys:
                outgoing_by_player.setdefault(player_key, []).append(transfer_date)

    filtered: list[dict[str, Any]] = []
    for row in incomings:
        player_keys = _transfer_player_keys(row)
        transfer_date = _parse_date(row.get("date"), None)
        if transfer_date and any(
            out_date >= transfer_date
            for player_key in player_keys
            for out_date in outgoing_by_player.get(player_key, [])
        ):
            continue
        filtered.append(row)
    return filtered


def _drop_superseded_return_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest_non_return_by_player: dict[str, datetime] = {}
    for row in rows:
        transfer_type = str(row.get("type") or "").strip().casefold()
        transfer_date = _parse_date(row.get("date"), None)
        if not transfer_date or transfer_type == "return from loan":
            continue
        for player_key in _transfer_player_keys(row):
            latest = latest_non_return_by_player.get(player_key)
            if latest is None or transfer_date > latest:
                latest_non_return_by_player[player_key] = transfer_date

    filtered: list[dict[str, Any]] = []
    for row in rows:
        transfer_type = str(row.get("type") or "").strip().casefold()
        transfer_date = _parse_date(row.get("date"), None)
        is_superseded_return = transfer_type == "return from loan" and transfer_date and any(
            latest_date >= transfer_date
            for player_key in _transfer_player_keys(row)
            for latest_date in [latest_non_return_by_player.get(player_key)]
            if latest_date
        )
        if not is_superseded_return:
            filtered.append(row)
    return filtered


def _transfer_player_keys(row: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    player_id = row.get("player_id")
    if player_id:
        keys.add(f"id:{player_id}")
    player_name = _normalized_person_key(str(row.get("player") or ""))
    if player_name:
        keys.add(f"name:{player_name}")
    return keys


def _normalized_person_key(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(name or ""))
    ascii_name = "".join(char for char in normalized if not unicodedata.combining(char))
    alpha_numeric_name = "".join(char if char.isalnum() else " " for char in ascii_name)
    return " ".join(alpha_numeric_name.strip().casefold().split())


def _normalized_team_key(team_name: str) -> str:
    return " ".join(str(team_name or "").strip().casefold().split())


def _api_football_season_candidates(season: str) -> list[int]:
    try:
        start_year = provider_season_year(season)
    except ValueError:
        return []
    candidates = [start_year, start_year - 1, start_year - 2]
    return [year for index, year in enumerate(candidates) if year > 0 and year not in candidates[:index]]


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _season_end(season: str) -> datetime | None:
    start = _season_start(season)
    if not start:
        return None
    return datetime(start.year + 1, 6, 30, tzinfo=timezone.utc)


def _parse_date(value: Any, fallback: datetime | None) -> datetime | None:
    if not value:
        return fallback
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return fallback
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _stint_overlaps_season(stint: dict[str, Any], season_start: datetime | None, season_end: datetime | None) -> bool:
    if not season_start or not season_end:
        return False
    stint_start = _parse_date(stint.get("start"), datetime.min.replace(tzinfo=timezone.utc))
    stint_end = _parse_date(stint.get("end"), datetime.max.replace(tzinfo=timezone.utc))
    if not stint_start or not stint_end:
        return False
    return stint_start <= season_end and stint_end >= season_start


def _squad(team: dict[str, Any] | None) -> list[dict[str, Any]]:
    squad = (team or {}).get("squad")
    if not isinstance(squad, list):
        return []
    rows = []
    for player in squad:
        if not isinstance(player, dict) or not player.get("name"):
            continue
        rows.append(
            {
                "id": player.get("id"),
                "name": str(player.get("name")),
                "position": player.get("position"),
                "nationality": player.get("nationality"),
            }
        )
    return rows


def _squad_changes(current_team: dict[str, Any] | None, previous_team: dict[str, Any] | None) -> dict[str, Any]:
    current = _squad(current_team)
    previous = _squad(previous_team)
    current_by_id = {str(player["id"] or player["name"]).casefold(): player for player in current}
    previous_by_id = {str(player["id"] or player["name"]).casefold(): player for player in previous}
    new_keys = [key for key in current_by_id if key not in previous_by_id]
    missing_keys = [key for key in previous_by_id if key not in current_by_id]
    return {
        "current_squad_count": len(current),
        "previous_squad_count": len(previous),
        "current_squad": current,
        "previous_squad": previous,
        "new_players": [current_by_id[key] for key in new_keys[:12]],
        "missing_players": [previous_by_id[key] for key in missing_keys[:12]],
        "note": "Season squad comparison from FootballData. This is not an injury or matchday-availability feed.",
    }


def _season_start(season: str) -> datetime | None:
    try:
        year = provider_season_year(season)
    except ValueError:
        return None
    return datetime(year, 6, 1, tzinfo=timezone.utc)


def _change_status(current: dict[str, Any], previous: dict[str, Any] | None, season: str) -> dict[str, Any]:
    if not current.get("available"):
        return {
            "status": "unknown",
            "label": "Coach not returned by FootballData",
            "reason": "FootballData returned an empty coach object for this team.",
        }
    override_previous_name = str(current.get("previous_name") or "").strip()
    if override_previous_name and override_previous_name != current.get("name"):
        return {
            "status": "changed_from_previous_season",
            "label": "Changed from previous season",
            "reason": f"{override_previous_name} was listed previously; {current.get('name')} is listed now.",
        }
    if previous and previous.get("available") and previous.get("name") != current.get("name"):
        return {
            "status": "changed_from_previous_season",
            "label": "Changed from previous season",
            "reason": f"{previous.get('name')} was listed previously; {current.get('name')} is listed now.",
        }
    start = _season_start(season)
    contract_start = current.get("contract_start")
    if start and contract_start:
        try:
            parsed = datetime.fromisoformat(str(contract_start).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            if parsed >= start:
                return {
                    "status": "started_this_season",
                    "label": "Started this season",
                    "reason": f"Contract start is {contract_start}.",
                }
        except ValueError:
            pass
    return {
        "status": "no_change_detected",
        "label": "No change detected",
        "reason": "No different previous coach or in-season contract start was found in provider data.",
    }


class OppositionTeamContextService:
    def __init__(
        self,
        provider: FootballDataTeamContextProvider | None,
        coach_provider: ApiFootballCoachProvider | None = None,
        override_provider: CoachOverrideProvider | None = None,
    ) -> None:
        self.provider = provider
        self.coach_provider = coach_provider
        self.override_provider = override_provider

    def _find_team(self, teams: list[dict[str, Any]], team_name: str) -> dict[str, Any] | None:
        provider_names = [
            str(team.get("name") or team.get("shortName") or "")
            for team in teams
            if isinstance(team, dict)
        ]
        matched = _match_local_team(team_name, provider_names)
        for team in teams:
            if not isinstance(team, dict):
                continue
            names = {str(team.get("name") or ""), str(team.get("shortName") or ""), str(team.get("tla") or "")}
            if matched and matched in names:
                return team
            if _match_local_team(str(team.get("name") or ""), [team_name]) == team_name:
                return team
        return None

    def build_context(self, league: str, season: str, *, reference_team: str, opponent_team: str) -> dict[str, Any]:
        if self.provider is None or league not in TOP_FIVE_COMPETITION_CODES:
            return {
                "available": False,
                "source": "football-data",
                "warning": "Official coach and squad context is unavailable for this league or provider configuration.",
                "teams": {},
            }

        previous_season = previous_season_key(season)
        try:
            current_teams = self.provider.fetch_competition_teams(league, season)
            previous_teams = self.provider.fetch_competition_teams(league, previous_season) if previous_season else []
        except TeamContextProviderError as exc:
            return {"available": False, "source": "football-data", "warning": str(exc), "teams": {}}

        payload: dict[str, Any] = {
            "available": True,
            "source": "football-data",
            "warning": None,
            "teams": {},
        }
        for role, team_name in (("reference", reference_team), ("opponent", opponent_team)):
            current_team = self._find_team(current_teams, team_name)
            previous_team = self._find_team(previous_teams, team_name)
            current_coach = _coach_payload(current_team, season=season)
            previous_coach = _coach_payload(previous_team, season=previous_season or "")
            coach_lookup_name = str((current_team or previous_team or {}).get("name") or team_name)
            coach_aliases = [
                team_name,
                coach_lookup_name,
                str((current_team or {}).get("shortName") or ""),
                str((previous_team or {}).get("shortName") or ""),
            ]
            if self.override_provider and previous_season:
                override_previous = self.override_provider.coach_for_season(league, previous_season, coach_aliases)
                if override_previous:
                    previous_coach = override_previous
            if self.override_provider:
                override_current = self.override_provider.coach_for_season(
                    league,
                    season,
                    coach_aliases,
                    previous_name=previous_coach.get("name"),
                )
                if override_current:
                    current_coach = override_current
            if self.coach_provider and not current_coach.get("available"):
                api_coach = self.coach_provider.coach_for_season(coach_lookup_name, season, league)
                if api_coach.get("available"):
                    current_coach = api_coach
            if self.coach_provider and previous_season and not previous_coach.get("available"):
                api_previous_coach = self.coach_provider.coach_for_season(coach_lookup_name, previous_season, league)
                if api_previous_coach.get("available"):
                    previous_coach = api_previous_coach
            transfer_activity = (
                self.coach_provider.transfer_activity_for_season(coach_lookup_name, season, league)
                if self.coach_provider
                else _empty_transfer_activity("API-Football is not configured.")
            )
            payload["teams"][role] = {
                "team": team_name,
                "provider_team": current_team.get("name") if current_team else None,
                "crest": current_team.get("crest") if current_team else None,
                "coach": current_coach,
                "previous_coach": previous_coach if previous_coach.get("available") else None,
                "coach_change": _change_status(current_coach, previous_coach, season),
                "transfer_activity": transfer_activity,
                "squad_changes": _squad_changes(current_team, previous_team),
            }
        return payload


team_context_provider = (
    FootballDataTeamContextProvider(
        settings.football_data_api_key,
        base_url=settings.football_data_base_url,
        timeout_seconds=settings.football_data_timeout_seconds,
        verify_tls=settings.should_verify_football_data_tls,
    )
    if settings.football_data_api_key
    else None
)
api_football_coach_provider = (
    ApiFootballCoachProvider(
        settings.api_sports_key,
        base_url=settings.api_sports_base_url,
        timeout_seconds=settings.api_sports_timeout_seconds,
        transfer_cache_dir=settings.api_sports_transfer_cache_dir
        or Path(__file__).resolve().parents[1] / ".cache" / "transfers" / "api-football",
    )
    if settings.api_sports_key
    else None
)
coach_override_provider = CoachOverrideProvider()
opposition_team_context_service = OppositionTeamContextService(
    team_context_provider,
    api_football_coach_provider,
    coach_override_provider,
)
