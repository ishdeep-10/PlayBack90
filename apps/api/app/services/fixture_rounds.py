from __future__ import annotations

from datetime import date, datetime
import json
from pathlib import Path
import re
from threading import Lock
from time import monotonic
from typing import Any

from app.services import r2


MAX_INFERRED_ROUND_SPAN_DAYS = 4
ROUND_INDEX_CACHE_SECONDS = 60
ROUND_MANIFEST_ROOT = Path(__file__).resolve().parents[1] / "data" / "fixture_rounds"
SAFE_MANIFEST_PATH_PART = re.compile(r"^[a-zA-Z0-9_-]+$")
_ROUND_INDEX_CACHE: dict[tuple[str, str], tuple[float, list[dict[str, Any]]]] = {}
_ROUND_INDEX_CACHE_LOCK = Lock()


def _fixture_date(fixture: dict[str, object]) -> date:
    value = fixture.get("start_date")
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value).split("T")[0]).date()


def _round_payload(
    *,
    round_id: str,
    label: str,
    stage: str | None,
    order: int,
    source: str,
    fixtures: list[dict[str, object]],
) -> dict[str, Any]:
    ordered_fixtures = sorted(fixtures, key=lambda item: (_fixture_date(item), str(item.get("match_id", ""))))
    dates = [_fixture_date(fixture) for fixture in ordered_fixtures]
    return {
        "id": round_id,
        "label": label,
        "stage": stage,
        "order": order,
        "start_date": min(dates),
        "end_date": max(dates),
        "match_count": len(ordered_fixtures),
        "metadata_source": source,
        "fixtures": ordered_fixtures,
    }


def _manifest_rounds(
    fixtures: list[dict[str, object]],
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    fixture_by_id = {str(fixture.get("match_id", "")): fixture for fixture in fixtures}
    raw_rounds = manifest.get("rounds")
    if not isinstance(raw_rounds, list):
        return []

    rounds: list[dict[str, Any]] = []
    assigned: set[str] = set()
    round_ids: set[str] = set()
    for index, raw_round in enumerate(raw_rounds, start=1):
        if not isinstance(raw_round, dict):
            continue
        raw_match_ids = raw_round.get("match_ids", raw_round.get("fixtures", []))
        if not isinstance(raw_match_ids, list):
            continue
        match_ids = [
            str(item.get("match_id", "")) if isinstance(item, dict) else str(item)
            for item in raw_match_ids
        ]
        if any(match_id in assigned for match_id in match_ids):
            return []
        round_fixtures = [
            fixture_by_id[match_id]
            for match_id in match_ids
            if match_id in fixture_by_id
        ]
        if not round_fixtures:
            continue
        assigned.update(str(fixture["match_id"]) for fixture in round_fixtures)
        try:
            order = int(raw_round.get("order", index))
        except (TypeError, ValueError):
            return []
        round_id = str(raw_round.get("id") or f"round-{order}")
        if round_id in round_ids:
            return []
        round_ids.add(round_id)
        rounds.append(
            _round_payload(
                round_id=round_id,
                label=str(raw_round.get("label") or f"Round {order}"),
                stage=str(raw_round["stage"]) if raw_round.get("stage") else None,
                order=order,
                source="manifest",
                fixtures=round_fixtures,
            )
        )

    # A partial manifest must not silently hide hosted matches.
    if len(assigned) != len(fixture_by_id):
        return []
    return sorted(rounds, key=lambda item: (item["order"], item["start_date"]), reverse=True)


def infer_fixture_rounds(fixtures: list[dict[str, object]]) -> list[dict[str, Any]]:
    """Build stable legacy rounds from chronology and unique team participation."""
    chronological = sorted(fixtures, key=lambda item: (_fixture_date(item), str(item.get("match_id", ""))))
    grouped: list[list[dict[str, object]]] = []
    current: list[dict[str, object]] = []
    current_teams: set[str] = set()
    current_start: date | None = None

    for fixture in chronological:
        fixture_date = _fixture_date(fixture)
        teams = {str(fixture.get("home_team", "")), str(fixture.get("away_team", ""))}
        exceeds_window = current_start is not None and (fixture_date - current_start).days > MAX_INFERRED_ROUND_SPAN_DAYS
        repeats_team = bool(current_teams.intersection(teams))
        if current and (exceeds_window or repeats_team):
            grouped.append(current)
            current = []
            current_teams = set()
            current_start = None
        if current_start is None:
            current_start = fixture_date
        current.append(fixture)
        current_teams.update(teams)

    if current:
        grouped.append(current)

    rounds = [
        _round_payload(
            round_id=f"round-{index}",
            label=f"Round {index}",
            stage=None,
            order=index,
            source="inferred",
            fixtures=round_fixtures,
        )
        for index, round_fixtures in enumerate(grouped, start=1)
    ]
    return list(reversed(rounds))


def build_fixture_rounds(
    fixtures: list[dict[str, object]],
    manifest: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if manifest:
        rounds = _manifest_rounds(fixtures, manifest)
        if rounds:
            return rounds
    return infer_fixture_rounds(fixtures)


def load_bundled_round_manifest(league: str, season: str) -> dict[str, Any] | None:
    if not SAFE_MANIFEST_PATH_PART.fullmatch(league) or not SAFE_MANIFEST_PATH_PART.fullmatch(season):
        return None
    path = ROUND_MANIFEST_ROOT / league / f"{season}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def list_fixture_rounds(league: str, season: str) -> list[dict[str, Any]]:
    cache_key = (league, season)
    now = monotonic()
    with _ROUND_INDEX_CACHE_LOCK:
        cached = _ROUND_INDEX_CACHE.get(cache_key)
        if cached and now - cached[0] < ROUND_INDEX_CACHE_SECONDS:
            return cached[1]

    fixtures = r2.list_all_fixtures(league, season)
    manifest = load_bundled_round_manifest(league, season)
    if manifest is None:
        manifest = r2.load_round_manifest(league, season)
    rounds = build_fixture_rounds(fixtures, manifest)
    with _ROUND_INDEX_CACHE_LOCK:
        _ROUND_INDEX_CACHE[cache_key] = (now, rounds)
    return rounds
