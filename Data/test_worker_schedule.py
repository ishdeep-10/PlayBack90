from datetime import datetime, timedelta, timezone

from worker_schedule import build_schedule_plan, scheduled_ingestion


def fixture(
    fixture_id: str,
    kickoff: str,
    *,
    league: str = "mls",
    state: str = "upcoming",
):
    return {
        "fixture_id": fixture_id,
        "provider_fixture_id": fixture_id,
        "league": league,
        "season": "2026",
        "home_team": f"Home {fixture_id}",
        "away_team": f"Away {fixture_id}",
        "start_date": kickoff,
        "state": state,
    }


def test_due_time_is_three_hours_after_kickoff_in_utc():
    item = scheduled_ingestion(fixture("1", "2026-08-15T19:30:00-04:00"))

    assert item is not None
    assert item.kickoff_utc == datetime(2026, 8, 15, 23, 30, tzinfo=timezone.utc)
    assert item.due_at == datetime(2026, 8, 16, 2, 30, tzinfo=timezone.utc)


def test_absolute_provider_times_remain_correct_across_dst_boundaries():
    before_dst = scheduled_ingestion(
        fixture("pl-before", "2026-03-28T15:00:00+00:00", league="premier-league")
    )
    after_dst = scheduled_ingestion(
        fixture("pl-after", "2026-03-29T16:30:00+01:00", league="premier-league")
    )

    assert before_dst.kickoff_utc == datetime(2026, 3, 28, 15, tzinfo=timezone.utc)
    assert after_dst.kickoff_utc == datetime(2026, 3, 29, 15, 30, tzinfo=timezone.utc)
    assert after_dst.due_at == datetime(2026, 3, 29, 18, 30, tzinfo=timezone.utc)


def test_nearby_matches_are_grouped_and_run_after_latest_due_time():
    fixtures = [
        fixture("1", "2026-08-15T15:00:00Z"),
        fixture("2", "2026-08-15T15:10:00Z"),
        fixture("3", "2026-08-15T15:15:00Z"),
        fixture("4", "2026-08-15T16:00:00Z"),
    ]

    groups = build_schedule_plan(
        fixtures,
        now=datetime(2026, 8, 15, 12, tzinfo=timezone.utc),
    )

    assert [len(group.fixtures) for group in groups] == [3, 1]
    assert groups[0].run_at == datetime(2026, 8, 15, 18, 20, tzinfo=timezone.utc)
    assert groups[1].run_at == datetime(2026, 8, 15, 19, 5, tzinfo=timezone.utc)


def test_postponed_and_cancelled_fixtures_are_not_planned():
    fixtures = [
        fixture("1", "2026-08-15T15:00:00Z", state="postponed"),
        fixture("2", "2026-08-15T15:00:00Z", state="cancelled"),
    ]

    groups = build_schedule_plan(
        fixtures,
        now=datetime(2026, 8, 15, 12, tzinfo=timezone.utc),
    )

    assert groups == []


def test_inactive_fixture_states_are_normalized_for_persistent_queue_updates():
    postponed = scheduled_ingestion(
        fixture("postponed", "2026-08-15T15:00:00Z", state="postponed")
    )
    cancelled = scheduled_ingestion(
        fixture("cancelled", "2026-08-15T15:00:00Z", state="cancelled")
    )

    assert postponed is not None and postponed.provider_state == "postponed"
    assert cancelled is not None and cancelled.provider_state == "cancelled"


def test_overdue_matches_remain_visible_for_three_day_reconciliation_window():
    now = datetime(2026, 8, 18, 12, tzinfo=timezone.utc)
    fixtures = [
        fixture("recent", "2026-08-16T12:00:00Z", state="completed"),
        fixture("old", "2026-08-13T12:00:00Z", state="completed"),
    ]

    groups = build_schedule_plan(fixtures, now=now)

    assert [item.fixture_id for group in groups for item in group.fixtures] == ["recent"]


def test_group_window_is_measured_from_first_due_time_not_chained():
    fixtures = [
        fixture("1", "2026-08-15T15:00:00Z"),
        fixture("2", "2026-08-15T15:25:00Z"),
        fixture("3", "2026-08-15T15:50:00Z"),
    ]

    groups = build_schedule_plan(
        fixtures,
        now=datetime(2026, 8, 15, 12, tzinfo=timezone.utc),
        window=timedelta(minutes=30),
    )

    assert [[item.fixture_id for item in group.fixtures] for group in groups] == [["1", "2"], ["3"]]
