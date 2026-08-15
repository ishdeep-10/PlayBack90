"""Persist official schedules and calculate the remote worker's next UTC wake."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import json
import os
from pathlib import Path
import signal
from threading import Event
from typing import Callable

from worker_schedule import (
    IngestionGroup,
    fetch_official_fixtures,
    group_scheduled_ingestions,
    scheduled_ingestion,
    utc_datetime,
)
from worker_state import WorkerStateStore
from worker_executor import execute_due_batch


DATA_DIR = Path(__file__).resolve().parent
DEFAULT_STATE_PATH = DATA_DIR / ".worker" / "state.db"


class WorkerAlreadyRunningError(RuntimeError):
    pass


@contextmanager
def exclusive_worker_lock(path: Path | str):
    lock_path = Path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise WorkerAlreadyRunningError(
                f"Another ingestion worker holds {lock_path}"
            ) from exc
        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()))
        handle.flush()
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def calculate_next_wake(
    *,
    now: datetime,
    next_action_at: datetime | None,
    last_schedule_sync: datetime,
    schedule_refresh_interval: timedelta = timedelta(hours=6),
    watchdog_interval: timedelta = timedelta(hours=2),
) -> tuple[datetime, str]:
    current = utc_datetime(now)
    candidates = {
        "schedule_refresh": utc_datetime(last_schedule_sync) + schedule_refresh_interval,
        "watchdog": current + watchdog_interval,
    }
    if next_action_at is not None:
        candidates["fixture_or_retry"] = max(current, utc_datetime(next_action_at))
    reason, wake = min(candidates.items(), key=lambda item: (item[1], item[0]))
    return wake, reason


def calculate_wake_deadline(
    *,
    now: datetime,
    next_action_at: datetime | None,
    schedule_refresh_at: datetime,
    watchdog_interval: timedelta = timedelta(hours=2),
) -> tuple[datetime, str]:
    current = utc_datetime(now)
    candidates = {
        "schedule_refresh": max(current, utc_datetime(schedule_refresh_at)),
        "watchdog": current + watchdog_interval,
    }
    if next_action_at is not None:
        candidates["fixture_or_retry"] = max(current, utc_datetime(next_action_at))
    reason, wake = min(candidates.items(), key=lambda item: (item[1], item[0]))
    return wake, reason


def sync_official_schedules(
    state: WorkerStateStore,
    targets: list[tuple[str, str]],
    *,
    now: datetime | None = None,
    fetcher: Callable = fetch_official_fixtures,
) -> list[dict[str, object]]:
    observed = utc_datetime(now or datetime.now(timezone.utc))
    sources: list[dict[str, object]] = []
    for league, season in targets:
        fixtures, metadata = fetcher(league, season)
        scheduled = [
            item for fixture in fixtures
            if (item := scheduled_ingestion(fixture)) is not None
        ]
        state.upsert_schedule(scheduled, seen_at=observed)
        sources.append({**metadata, "fixture_count": len(scheduled)})
    return sources


def build_persisted_plan(
    state: WorkerStateStore,
    *,
    now: datetime | None = None,
    horizon: timedelta = timedelta(days=7),
    overdue_grace: timedelta = timedelta(days=3),
) -> list[IngestionGroup]:
    current = utc_datetime(now or datetime.now(timezone.utc))
    fixtures = state.list_plannable(
        earliest=current - overdue_grace,
        latest=current + horizon,
    )
    return group_scheduled_ingestions(
        [fixture.as_scheduled_ingestion() for fixture in fixtures]
    )


def run_coordinator_loop(
    state: WorkerStateStore,
    targets: list[tuple[str, str]],
    *,
    execute_due: bool,
    batch_limit: int = 8,
    key_prefix: str | None = None,
    days: int = 7,
    schedule_refresh_interval: timedelta = timedelta(hours=6),
    failed_refresh_interval: timedelta = timedelta(minutes=15),
    watchdog_interval: timedelta = timedelta(hours=2),
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    waiter: Callable[[float], bool] | None = None,
    syncer: Callable = sync_official_schedules,
    executor: Callable = execute_due_batch,
    emit: Callable[[dict[str, object]], None] | None = None,
    max_cycles: int | None = None,
) -> int:
    if batch_limit <= 0 or days <= 0:
        raise ValueError("batch_limit and days must be greater than zero")
    stop_event = Event()
    wait = waiter or stop_event.wait
    output = emit or (lambda payload: print(json.dumps(payload, sort_keys=True), flush=True))
    schedule_refresh_at = datetime.min.replace(tzinfo=timezone.utc)
    cycles = 0

    while True:
        now = utc_datetime(clock())
        sources: list[dict[str, object]] = []
        schedule_error = None
        if now >= schedule_refresh_at:
            try:
                sources = syncer(state, targets, now=now)
                schedule_refresh_at = now + schedule_refresh_interval
            except Exception as exc:
                schedule_error = str(exc)
                schedule_refresh_at = now + failed_refresh_interval

        groups = build_persisted_plan(state, now=now, horizon=timedelta(days=days))
        execution = None
        if execute_due and groups and groups[0].run_at <= now:
            execution = executor(
                state,
                now=now,
                limit=batch_limit,
                key_prefix=key_prefix,
            ).to_dict()

        groups = build_persisted_plan(state, now=now, horizon=timedelta(days=days))
        next_group_at = groups[0].run_at if groups else None
        next_wake, wake_reason = calculate_wake_deadline(
            now=now,
            next_action_at=next_group_at,
            schedule_refresh_at=schedule_refresh_at,
            watchdog_interval=watchdog_interval,
        )
        output(
            {
                "generated_at": now.isoformat(),
                "sources": sources,
                "schedule_error": schedule_error,
                "execution": execution,
                "group_count": len(groups),
                "next_wake_at": next_wake.isoformat(),
                "next_wake_reason": wake_reason,
            }
        )
        cycles += 1
        if max_cycles is not None and cycles >= max_cycles:
            return cycles
        if execution and int(execution.get("claimed", 0)) >= batch_limit:
            # Let systemd start a clean Python process after a full soft batch,
            # releasing model and browser memory before claiming more work.
            return cycles
        sleep_seconds = max(0.0, (next_wake - now).total_seconds())
        if wait(sleep_seconds):
            return cycles


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
    parser.add_argument(
        "--state-db",
        default=os.getenv("PLAYBACK90_WORKER_STATE_DB", str(DEFAULT_STATE_PATH)),
    )
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument(
        "--execute-due",
        action="store_true",
        help="Claim and ingest the currently due batch after schedule synchronization",
    )
    parser.add_argument(
        "--run-loop",
        action="store_true",
        help="Remain resident and sleep until fixture, retry, refresh, or watchdog deadlines",
    )
    parser.add_argument("--batch-limit", type=int, default=8)
    parser.add_argument(
        "--fixture-id",
        action="append",
        default=[],
        help="Explicit fixture ID to claim for a one-shot manual retry; repeat as needed",
    )
    parser.add_argument(
        "--lock-file",
        default=os.getenv("PLAYBACK90_WORKER_LOCK", ""),
        help="Execution lock path; defaults beside the worker-state database",
    )
    parser.add_argument(
        "--key-prefix",
        default=os.getenv("PLAYBACK90_R2_KEY_PREFIX", ""),
        help="Optional R2 namespace such as ingestion-test",
    )
    args = parser.parse_args()
    if args.days <= 0 or args.batch_limit <= 0:
        parser.error("--days and --batch-limit must be greater than zero")
    if args.fixture_id and (not args.execute_due or args.run_loop):
        parser.error("--fixture-id requires one-shot --execute-due without --run-loop")

    now = datetime.now(timezone.utc)
    state = WorkerStateStore(args.state_db)
    lock_file = args.lock_file or f"{args.state_db}.lock"
    if args.run_loop:
        stop_event = Event()

        def request_stop(signum, frame):
            stop_event.set()

        signal.signal(signal.SIGTERM, request_stop)
        signal.signal(signal.SIGINT, request_stop)
        with exclusive_worker_lock(lock_file):
            run_coordinator_loop(
                state,
                args.league_season,
                execute_due=args.execute_due,
                batch_limit=args.batch_limit,
                key_prefix=args.key_prefix,
                days=args.days,
                waiter=stop_event.wait,
            )
        return

    sources = sync_official_schedules(state, args.league_season, now=now)
    groups = build_persisted_plan(state, now=now, horizon=timedelta(days=args.days))
    execution = None
    if args.execute_due and args.fixture_id:
        with exclusive_worker_lock(lock_file):
            execution = execute_due_batch(
                state,
                now=now,
                limit=args.batch_limit,
                key_prefix=args.key_prefix,
                fixture_ids=args.fixture_id,
            ).to_dict()
    elif args.execute_due and groups and groups[0].run_at <= now:
        with exclusive_worker_lock(lock_file):
            execution = execute_due_batch(
                state,
                now=now,
                limit=args.batch_limit,
                key_prefix=args.key_prefix,
            ).to_dict()
    groups = build_persisted_plan(state, now=now, horizon=timedelta(days=args.days))
    next_group_at = groups[0].run_at if groups else None
    next_wake, wake_reason = calculate_next_wake(
        now=now,
        next_action_at=next_group_at,
        last_schedule_sync=now,
    )
    print(
        json.dumps(
            {
                "generated_at": now.isoformat(),
                "state_db": str(Path(args.state_db)),
                "sources": sources,
                "execution": execution,
                "group_count": len(groups),
                "groups": [group.to_dict() for group in groups],
                "next_wake_at": next_wake.isoformat(),
                "next_wake_reason": wake_reason,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
