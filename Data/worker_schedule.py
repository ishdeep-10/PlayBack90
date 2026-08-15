"""Build schedule-aware remote ingestion groups from official fixtures."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any, Iterable


ROOT_DIR = Path(__file__).resolve().parents[1]
API_DIR = ROOT_DIR / "apps" / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))


ELIGIBLE_STATES = {"completed", "live", "upcoming", "unknown"}
INACTIVE_STATES = {"cancelled", "postponed"}
KNOWN_STATES = ELIGIBLE_STATES | INACTIVE_STATES


def configured_ingestion_delay() -> timedelta:
    raw = os.getenv("PLAYBACK90_INGESTION_DELAY_HOURS", "3")
    try:
        hours = float(raw)
    except ValueError as exc:
        raise ValueError("PLAYBACK90_INGESTION_DELAY_HOURS must be a number") from exc
    if hours <= 0:
        raise ValueError("PLAYBACK90_INGESTION_DELAY_HOURS must be greater than zero")
    return timedelta(hours=hours)


def utc_datetime(value: datetime | str) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"Naive fixture timestamp is not safe to schedule: {value!r}")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class ScheduledIngestion:
    fixture_id: str
    provider_fixture_id: str
    league: str
    season: str
    home_team: str
    away_team: str
    kickoff_utc: datetime
    due_at: datetime
    provider_state: str

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["kickoff_utc"] = self.kickoff_utc.isoformat()
        payload["due_at"] = self.due_at.isoformat()
        return payload


@dataclass(frozen=True)
class IngestionGroup:
    id: str
    run_at: datetime
    fixtures: tuple[ScheduledIngestion, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "run_at": self.run_at.isoformat(),
            "fixture_count": len(self.fixtures),
            "leagues": sorted({fixture.league for fixture in self.fixtures}),
            "fixtures": [fixture.to_dict() for fixture in self.fixtures],
        }


def scheduled_ingestion(
    fixture: dict[str, Any],
    *,
    delay: timedelta | None = None,
) -> ScheduledIngestion | None:
    state = str(fixture.get("state") or "unknown").lower()
    if state not in KNOWN_STATES:
        return None
    kickoff_raw = fixture.get("start_date")
    if not kickoff_raw:
        return None
    kickoff = utc_datetime(kickoff_raw)
    fixture_id = str(fixture.get("fixture_id") or fixture.get("provider_fixture_id") or "")
    if not fixture_id:
        return None
    ingestion_delay = delay if delay is not None else configured_ingestion_delay()
    return ScheduledIngestion(
        fixture_id=fixture_id,
        provider_fixture_id=str(fixture.get("provider_fixture_id") or fixture_id),
        league=str(fixture.get("league") or ""),
        season=str(fixture.get("season") or ""),
        home_team=str(fixture.get("home_team") or "Unknown"),
        away_team=str(fixture.get("away_team") or "Unknown"),
        kickoff_utc=kickoff,
        due_at=kickoff + ingestion_delay,
        provider_state=state,
    )


def group_scheduled_ingestions(
    fixtures: Iterable[ScheduledIngestion],
    *,
    window: timedelta = timedelta(minutes=30),
    publication_buffer: timedelta = timedelta(minutes=5),
) -> list[IngestionGroup]:
    ordered = sorted(fixtures, key=lambda fixture: (fixture.due_at, fixture.fixture_id))
    groups: list[IngestionGroup] = []
    pending: list[ScheduledIngestion] = []
    group_start: datetime | None = None

    def flush() -> None:
        nonlocal pending, group_start
        if not pending:
            return
        run_at = max(fixture.due_at for fixture in pending) + publication_buffer
        groups.append(
            IngestionGroup(
                id=f"group-{run_at.strftime('%Y%m%dT%H%M%SZ')}",
                run_at=run_at,
                fixtures=tuple(pending),
            )
        )
        pending = []
        group_start = None

    for fixture in ordered:
        if group_start is None:
            group_start = fixture.due_at
        elif fixture.due_at - group_start > window:
            flush()
            group_start = fixture.due_at
        pending.append(fixture)
    flush()
    return groups


def build_schedule_plan(
    fixtures: Iterable[dict[str, Any]],
    *,
    now: datetime | None = None,
    horizon: timedelta = timedelta(days=7),
    overdue_grace: timedelta = timedelta(days=3),
    delay: timedelta = timedelta(hours=3),
    window: timedelta = timedelta(minutes=30),
    publication_buffer: timedelta = timedelta(minutes=5),
) -> list[IngestionGroup]:
    current = utc_datetime(now or datetime.now(timezone.utc))
    earliest = current - overdue_grace
    latest = current + horizon
    scheduled = []
    for fixture in fixtures:
        item = scheduled_ingestion(fixture, delay=delay)
        if item and item.provider_state in ELIGIBLE_STATES and earliest <= item.due_at <= latest:
            scheduled.append(item)
    return group_scheduled_ingestions(
        scheduled,
        window=window,
        publication_buffer=publication_buffer,
    )


def fetch_official_fixtures(league: str, season: str) -> tuple[list[dict[str, Any]], dict[str, object]]:
    from app.services.schedules import schedule_service

    fixtures, updated_at, is_stale, warning = schedule_service.official_fixtures(league, season)
    metadata = {
        "league": league,
        "season": season,
        "updated_at": updated_at.isoformat() if updated_at else None,
        "is_stale": is_stale,
        "warning": warning,
    }
    return fixtures, metadata


def _league_season(value: str) -> tuple[str, str]:
    if ":" not in value:
        raise argparse.ArgumentTypeError("Expected LEAGUE:SEASON, e.g. mls:2026")
    league, season = value.split(":", 1)
    if not league or not season:
        raise argparse.ArgumentTypeError("Both league and season are required")
    return league, season


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--league-season",
        action="append",
        required=True,
        type=_league_season,
        metavar="LEAGUE:SEASON",
    )
    parser.add_argument("--days", type=int, default=7, help="Future planning horizon")
    parser.add_argument(
        "--delay-hours",
        type=float,
        default=configured_ingestion_delay().total_seconds() / 3600,
    )
    parser.add_argument("--group-minutes", type=int, default=30)
    parser.add_argument("--buffer-minutes", type=int, default=5)
    args = parser.parse_args()
    if args.days <= 0 or args.group_minutes < 0 or args.buffer_minutes < 0:
        parser.error("Planning durations must be non-negative and days must be positive")

    all_fixtures: list[dict[str, Any]] = []
    sources = []
    for league, season in args.league_season:
        fixtures, metadata = fetch_official_fixtures(league, season)
        all_fixtures.extend(fixtures)
        sources.append(metadata)
    groups = build_schedule_plan(
        all_fixtures,
        horizon=timedelta(days=args.days),
        delay=timedelta(hours=args.delay_hours),
        window=timedelta(minutes=args.group_minutes),
        publication_buffer=timedelta(minutes=args.buffer_minutes),
    )
    print(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "sources": sources,
                "group_count": len(groups),
                "groups": [group.to_dict() for group in groups],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
