"""Claim due fixtures, resolve provider URLs once per league, and ingest sequentially."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from itertools import groupby
from typing import Callable, Iterable

from discord_notifier import notify_ingestion_result
from ingestion_worker import WorkerResult, run_match_worker
from provider_match_resolver import ResolutionBatch, resolve_fixture_urls
from worker_schedule import utc_datetime
from worker_state import WorkerFixture, WorkerStateStore


@dataclass(frozen=True)
class ExecutionItem:
    fixture_id: str
    league: str
    status: str
    source_url: str | None = None
    r2_key: str | None = None
    retry_at: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class ExecutionReport:
    started_at: str
    claimed: int
    items: tuple[ExecutionItem, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "started_at": self.started_at,
            "claimed": self.claimed,
            "uploaded": sum(item.status in {"uploaded", "already_exists"} for item in self.items),
            "retry_scheduled": sum(item.status == "retry_scheduled" for item in self.items),
            "items": [asdict(item) for item in self.items],
        }


def _groups(fixtures: Iterable[WorkerFixture]) -> list[list[WorkerFixture]]:
    ordered = sorted(fixtures, key=lambda item: (item.league, item.season, item.due_at, item.fixture_id))
    return [
        list(group)
        for _, group in groupby(ordered, key=lambda item: (item.league, item.season))
    ]


def execute_due_batch(
    state: WorkerStateStore,
    *,
    now: datetime | None = None,
    limit: int = 8,
    overdue_grace: timedelta = timedelta(days=3),
    key_prefix: str | None = None,
    resolver: Callable[[Iterable[WorkerFixture]], ResolutionBatch] = resolve_fixture_urls,
    worker: Callable[..., WorkerResult] = run_match_worker,
    notifier: Callable[..., object] = notify_ingestion_result,
    fixture_ids: Iterable[str] | None = None,
    source_urls: dict[str, str] | None = None,
) -> ExecutionReport:
    current = utc_datetime(now or datetime.now(timezone.utc))
    if fixture_ids is None:
        claimed = state.claim_due(
            now=current,
            earliest=current - overdue_grace,
            limit=limit,
        )
    else:
        selected = list(dict.fromkeys(str(value) for value in fixture_ids))[:limit]
        claimed = state.claim_selected(selected, now=current)
    results: list[ExecutionItem] = []

    def record(fixture: WorkerFixture, item: ExecutionItem) -> None:
        results.append(item)
        try:
            notifier(
                fixture_id=fixture.fixture_id,
                league=fixture.league,
                season=fixture.season,
                home_team=fixture.home_team,
                away_team=fixture.away_team,
                status=item.status,
                attempt=fixture.attempt_count + 1,
                r2_key=item.r2_key,
                retry_at=item.retry_at,
                error=item.error,
                occurred_at=current,
            )
        except Exception as exc:
            # Custom notifiers must remain best-effort just like the Discord sender.
            import json
            import sys

            print(
                json.dumps(
                    {
                        "event": "ingestion_notification_failed",
                        "fixture_id": fixture.fixture_id,
                        "error_type": type(exc).__name__,
                    },
                    sort_keys=True,
                ),
                file=sys.stderr,
                flush=True,
            )

    for fixtures in _groups(claimed):
        supplied_urls = {
            fixture.fixture_id: source_urls[fixture.fixture_id]
            for fixture in fixtures
            if source_urls and fixture.fixture_id in source_urls
        }
        discovery_fixtures = [
            fixture for fixture in fixtures if fixture.fixture_id not in supplied_urls
        ]
        if discovery_fixtures:
            try:
                discovered = resolver(discovery_fixtures)
            except Exception as exc:
                import sys
                import traceback

                print(
                    f"provider_discovery traceback for {[f.fixture_id for f in discovery_fixtures]}:",
                    file=sys.stderr,
                )
                traceback.print_exc(file=sys.stderr)
                sys.stderr.flush()
                for fixture in discovery_fixtures:
                    error = f"provider_discovery: {exc}"
                    retry_at = state.schedule_retry(fixture.fixture_id, error, now=current)
                    record(
                        fixture,
                        ExecutionItem(
                            fixture_id=fixture.fixture_id,
                            league=fixture.league,
                            status="retry_scheduled",
                            retry_at=retry_at.isoformat(),
                            error=error,
                        )
                    )
                discovery_fixtures = []
                discovered = ResolutionBatch(urls={}, errors={}, candidate_count=0)
            resolution = ResolutionBatch(
                urls={**supplied_urls, **discovered.urls},
                errors=discovered.errors,
                candidate_count=discovered.candidate_count,
            )
        else:
            resolution = ResolutionBatch(
                urls=supplied_urls,
                errors={},
                candidate_count=len(supplied_urls),
            )

        for fixture in fixtures:
            if any(item.fixture_id == fixture.fixture_id for item in results):
                continue
            source_url = resolution.urls.get(fixture.fixture_id)
            if source_url is None:
                detail = resolution.errors.get(fixture.fixture_id, "Provider URL was not resolved")
                error = f"provider_url_not_found: {detail}"
                retry_at = state.schedule_retry(fixture.fixture_id, error, now=current)
                record(
                    fixture,
                    ExecutionItem(
                        fixture_id=fixture.fixture_id,
                        league=fixture.league,
                        status="retry_scheduled",
                        retry_at=retry_at.isoformat(),
                        error=error,
                    )
                )
                continue

            try:
                worker_result = worker(
                    url=source_url,
                    league=fixture.league,
                    season=fixture.season,
                    expected_home=fixture.home_team,
                    expected_away=fixture.away_team,
                    key_prefix=key_prefix,
                )
                state.mark_uploaded(
                    fixture.fixture_id,
                    r2_key=worker_result.key,
                    source_match_id=worker_result.match_id,
                    source_url=source_url,
                    now=current,
                )
                record(
                    fixture,
                    ExecutionItem(
                        fixture_id=fixture.fixture_id,
                        league=fixture.league,
                        status=worker_result.status,
                        source_url=source_url,
                        r2_key=worker_result.key,
                    )
                )
            except Exception as exc:
                error = f"ingestion: {exc}"
                retry_at = state.schedule_retry(fixture.fixture_id, error, now=current)
                record(
                    fixture,
                    ExecutionItem(
                        fixture_id=fixture.fixture_id,
                        league=fixture.league,
                        status="retry_scheduled",
                        source_url=source_url,
                        retry_at=retry_at.isoformat(),
                        error=error,
                    )
                )

    return ExecutionReport(
        started_at=current.isoformat(),
        claimed=len(claimed),
        items=tuple(results),
    )
