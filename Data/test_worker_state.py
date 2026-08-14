from datetime import datetime, timedelta, timezone

import pytest

from worker_coordinator import (
    WorkerAlreadyRunningError,
    calculate_next_wake,
    calculate_wake_deadline,
    exclusive_worker_lock,
    run_coordinator_loop,
    sync_official_schedules,
)
from worker_schedule import ScheduledIngestion, utc_datetime
from worker_state import WorkerStateStore


UTC = timezone.utc


def scheduled(
    fixture_id: str = "fixture-1",
    *,
    kickoff: datetime = datetime(2026, 8, 15, 23, 30, tzinfo=UTC),
    provider_state: str = "upcoming",
) -> ScheduledIngestion:
    return ScheduledIngestion(
        fixture_id=fixture_id,
        provider_fixture_id=fixture_id,
        league="mls",
        season="2026",
        home_team="Inter Miami CF",
        away_team="Orlando City",
        kickoff_utc=kickoff,
        due_at=kickoff + timedelta(hours=3),
        provider_state=provider_state,
    )


def test_naive_timestamps_are_rejected_instead_of_assuming_a_league_timezone():
    with pytest.raises(ValueError, match="Naive fixture timestamp"):
        utc_datetime(datetime(2026, 8, 15, 19, 30))


def test_absolute_offsets_handle_different_mls_venue_timezones():
    new_york = utc_datetime("2026-08-15T19:30:00-04:00")
    los_angeles = utc_datetime("2026-08-15T19:30:00-07:00")

    assert new_york == datetime(2026, 8, 15, 23, 30, tzinfo=UTC)
    assert los_angeles == datetime(2026, 8, 16, 2, 30, tzinfo=UTC)


def test_schedule_upsert_persists_utc_and_resets_a_changed_kickoff(tmp_path):
    state = WorkerStateStore(tmp_path / "state.db")
    original = scheduled()
    state.upsert_schedule([original], seen_at=datetime(2026, 8, 14, tzinfo=UTC))
    state.schedule_retry(
        original.fixture_id,
        "not published",
        now=datetime(2026, 8, 16, 3, tzinfo=UTC),
    )
    moved = scheduled(kickoff=original.kickoff_utc + timedelta(days=1))

    state.upsert_schedule([moved], seen_at=datetime(2026, 8, 16, 4, tzinfo=UTC))
    row = state.get(original.fixture_id)

    assert row is not None
    assert row.kickoff_utc == moved.kickoff_utc
    assert row.due_at == moved.due_at
    assert row.status == "scheduled"
    assert row.next_retry_at is None
    assert row.last_error is None


def test_postponed_fixture_is_not_claimed_until_rescheduled(tmp_path):
    state = WorkerStateStore(tmp_path / "state.db")
    fixture = scheduled(provider_state="postponed")
    state.upsert_schedule([fixture])

    assert state.claim_due(now=fixture.due_at + timedelta(hours=1)) == []
    assert state.get(fixture.fixture_id).status == "postponed"

    restored = scheduled(kickoff=fixture.kickoff_utc + timedelta(days=2))
    state.upsert_schedule([restored])
    assert state.get(fixture.fixture_id).status == "scheduled"


def test_schedule_sync_applies_provider_postponement_to_existing_queue(tmp_path):
    state = WorkerStateStore(tmp_path / "state.db")
    fixture = scheduled()
    state.upsert_schedule([fixture])

    def fetcher(league, season):
        return [
            {
                "fixture_id": fixture.fixture_id,
                "provider_fixture_id": fixture.provider_fixture_id,
                "league": league,
                "season": season,
                "home_team": fixture.home_team,
                "away_team": fixture.away_team,
                "start_date": fixture.kickoff_utc.isoformat(),
                "state": "postponed",
            }
        ], {"league": league, "season": season}

    sync_official_schedules(state, [("mls", "2026")], fetcher=fetcher)

    assert state.get(fixture.fixture_id).status == "postponed"
    assert state.claim_due(now=fixture.due_at + timedelta(hours=1)) == []


def test_due_claims_are_leased_and_limited(tmp_path):
    state = WorkerStateStore(tmp_path / "state.db")
    fixtures = [scheduled(str(index)) for index in range(10)]
    state.upsert_schedule(fixtures)
    now = fixtures[0].due_at + timedelta(minutes=1)

    first = state.claim_due(now=now, limit=8)
    second = state.claim_due(now=now, limit=8)

    assert len(first) == 8
    assert len(second) == 2
    assert not ({item.fixture_id for item in first} & {item.fixture_id for item in second})


def test_due_claims_can_ignore_matches_before_reconciliation_window(tmp_path):
    state = WorkerStateStore(tmp_path / "state.db")
    now = datetime(2026, 8, 14, 12, tzinfo=UTC)
    old = scheduled("old", kickoff=now - timedelta(days=10))
    recent = scheduled("recent", kickoff=now - timedelta(hours=4))
    state.upsert_schedule([old, recent], seen_at=now)

    claimed = state.claim_due(now=now, earliest=now - timedelta(days=3))

    assert [item.fixture_id for item in claimed] == ["recent"]
    assert state.get("old").status == "scheduled"


def test_failed_claim_uses_retry_schedule_and_uploaded_state_is_terminal(tmp_path):
    state = WorkerStateStore(tmp_path / "state.db")
    fixture = scheduled()
    state.upsert_schedule([fixture])
    claimed = state.claim_due(now=fixture.due_at + timedelta(minutes=1))[0]
    failed_at = fixture.due_at + timedelta(minutes=2)

    retry_at = state.schedule_retry(claimed.fixture_id, "source unavailable", now=failed_at)

    assert retry_at == failed_at + timedelta(hours=1)
    assert state.get(fixture.fixture_id).status == "retry_scheduled"
    assert state.claim_due(now=retry_at - timedelta(seconds=1)) == []
    assert len(state.claim_due(now=retry_at)) == 1

    state.mark_uploaded(
        fixture.fixture_id,
        r2_key="event_data/mls/2026/test.parquet",
        source_match_id="123",
        source_url="https://example.com/Matches/123/Live/test",
        now=retry_at,
    )
    state.upsert_schedule([fixture], seen_at=retry_at + timedelta(hours=1))
    assert state.get(fixture.fixture_id).status == "uploaded"


def test_next_wake_uses_absolute_utc_action_before_watchdog():
    now = datetime(2026, 8, 14, 12, tzinfo=UTC)
    wake, reason = calculate_next_wake(
        now=now,
        next_action_at=now + timedelta(minutes=40),
        last_schedule_sync=now,
    )

    assert wake == now + timedelta(minutes=40)
    assert reason == "fixture_or_retry"


def test_next_wake_clamps_overdue_action_to_now():
    now = datetime(2026, 8, 14, 12, tzinfo=UTC)
    wake, reason = calculate_next_wake(
        now=now,
        next_action_at=now - timedelta(hours=1),
        last_schedule_sync=now,
    )

    assert wake == now
    assert reason == "fixture_or_retry"


def test_next_action_ignores_fixtures_before_reconciliation_window(tmp_path):
    state = WorkerStateStore(tmp_path / "state.db")
    now = datetime(2026, 8, 14, 12, tzinfo=UTC)
    old = scheduled("old", kickoff=now - timedelta(days=10))
    upcoming = scheduled("upcoming", kickoff=now + timedelta(days=1))
    state.upsert_schedule([old, upcoming], seen_at=now)

    assert state.next_action_at() == old.due_at
    assert state.next_action_at(earliest=now - timedelta(days=3)) == upcoming.due_at


def test_worker_process_lock_prevents_concurrent_firefox_batches(tmp_path):
    lock_path = tmp_path / "worker.lock"

    with exclusive_worker_lock(lock_path):
        with pytest.raises(WorkerAlreadyRunningError, match="Another ingestion worker"):
            with exclusive_worker_lock(lock_path):
                pass

    with exclusive_worker_lock(lock_path):
        assert lock_path.read_text().strip()


def test_coordinator_loop_sleeps_to_watchdog_without_repolling_schedule(tmp_path):
    state = WorkerStateStore(tmp_path / "state.db")
    current = [datetime(2026, 8, 14, 12, tzinfo=UTC)]
    sync_calls = []
    waits = []
    emitted = []

    def syncer(state_store, targets, *, now):
        sync_calls.append(now)
        return [{"league": "mls", "season": "2026", "fixture_count": 0}]

    def waiter(seconds):
        waits.append(seconds)
        current[0] += timedelta(seconds=seconds)
        return False

    cycles = run_coordinator_loop(
        state,
        [("mls", "2026")],
        execute_due=False,
        clock=lambda: current[0],
        waiter=waiter,
        syncer=syncer,
        emit=emitted.append,
        max_cycles=2,
    )

    assert cycles == 2
    assert len(sync_calls) == 1
    assert waits == [7200.0]
    assert emitted[0]["next_wake_reason"] == "watchdog"


def test_failed_schedule_refresh_retries_in_fifteen_minutes():
    now = datetime(2026, 8, 14, 12, tzinfo=UTC)
    wake, reason = calculate_wake_deadline(
        now=now,
        next_action_at=None,
        schedule_refresh_at=now + timedelta(minutes=15),
    )

    assert wake == now + timedelta(minutes=15)
    assert reason == "schedule_refresh"


def test_coordinator_waits_for_group_publication_buffer_before_execution(tmp_path):
    state = WorkerStateStore(tmp_path / "state.db")
    fixture = scheduled(kickoff=datetime(2026, 8, 15, 9, tzinfo=UTC))
    state.upsert_schedule([fixture])
    now = fixture.due_at
    executor_calls = []
    emitted = []

    def executor(*args, **kwargs):
        executor_calls.append(kwargs["now"])
        raise AssertionError("executor must not run before the group buffer")

    run_coordinator_loop(
        state,
        [("mls", "2026")],
        execute_due=True,
        clock=lambda: now,
        syncer=lambda state_store, targets, now: [],
        executor=executor,
        emit=emitted.append,
        max_cycles=1,
    )

    assert executor_calls == []
    assert emitted[0]["next_wake_at"] == (fixture.due_at + timedelta(minutes=5)).isoformat()
    assert emitted[0]["next_wake_reason"] == "fixture_or_retry"
