from datetime import datetime, timedelta, timezone

from ingestion_worker import WorkerResult
from provider_match_resolver import ResolutionBatch, resolve_fixture_urls
from worker_executor import execute_due_batch
from worker_schedule import ScheduledIngestion
from worker_state import WorkerStateStore


UTC = timezone.utc


def scheduled(
    fixture_id: str,
    *,
    league: str = "mls",
    season: str = "2026",
    home: str = "Inter Miami CF",
    away: str = "Orlando City",
    kickoff: datetime = datetime(2026, 8, 15, 23, 30, tzinfo=UTC),
) -> ScheduledIngestion:
    return ScheduledIngestion(
        fixture_id=fixture_id,
        provider_fixture_id=fixture_id,
        league=league,
        season=season,
        home_team=home,
        away_team=away,
        kickoff_utc=kickoff,
        due_at=kickoff + timedelta(hours=3),
        provider_state="completed",
    )


def persisted(tmp_path, fixtures):
    state = WorkerStateStore(tmp_path / "state.db")
    state.upsert_schedule(fixtures)
    return state


def test_resolver_matches_team_names_and_adjacent_provider_date(tmp_path):
    state = persisted(
        tmp_path,
        [
            scheduled(
                "mls-1",
                home="Red Bull New York",
                away="DC United",
                kickoff=datetime(2026, 8, 16, 0, 30, tzinfo=UTC),
            )
        ],
    )
    fixture = state.get("mls-1")

    result = resolve_fixture_urls(
        [fixture],
        discoverer=lambda league, season: [
            {
                "date": "Saturday, Aug 15 2026",
                "home": "New York Red Bulls",
                "away": "D.C. United",
                "url": "/matches/1953001/live/usa-major-league-soccer-test",
            }
        ],
    )

    assert result.urls == {
        "mls-1": "https://1xbet.whoscored.com/matches/1953001/live/usa-major-league-soccer-test"
    }
    assert result.errors == {}


def test_resolver_refuses_ambiguous_candidates(tmp_path):
    state = persisted(tmp_path, [scheduled("mls-1")])
    fixture = state.get("mls-1")
    rows = [
        {
            "date": "Saturday, Aug 15 2026",
            "home": "Inter Miami",
            "away": "Orlando City SC",
            "url": f"/matches/{match_id}/live/usa-major-league-soccer-test",
        }
        for match_id in (1953001, 1953002)
    ]

    result = resolve_fixture_urls([fixture], discoverer=lambda league, season: rows)

    assert result.urls == {}
    assert "ambiguously" in result.errors["mls-1"]


def test_executor_discovers_once_per_league_and_ingests_sequentially(tmp_path):
    fixtures = [
        scheduled("mls-1"),
        scheduled("mls-2", home="Austin FC", away="FC Dallas"),
        scheduled(
            "pl-1",
            league="premier-league",
            season="2026/2027",
            home="Arsenal",
            away="Chelsea",
        ),
    ]
    state = persisted(tmp_path, fixtures)
    now = fixtures[0].due_at + timedelta(minutes=5)
    resolver_calls = []
    worker_calls = []

    def resolver(group):
        group = list(group)
        resolver_calls.append((group[0].league, [item.fixture_id for item in group]))
        return ResolutionBatch(
            urls={
                item.fixture_id: f"https://example.com/Matches/{index}/Live/test"
                for index, item in enumerate(group, start=100001 + len(resolver_calls) * 100)
            },
            errors={},
            candidate_count=len(group),
        )

    def worker(**kwargs):
        worker_calls.append(kwargs)
        match_id = kwargs["url"].split("/Matches/")[1].split("/")[0]
        return WorkerResult(
            status="uploaded",
            league=kwargs["league"],
            season=kwargs["season"],
            match_id=match_id,
            key=f"event_data/{kwargs['league']}/{kwargs['season']}/{match_id}.parquet",
            validation=None,
        )

    report = execute_due_batch(state, now=now, resolver=resolver, worker=worker)

    assert resolver_calls == [
        ("mls", ["mls-1", "mls-2"]),
        ("premier-league", ["pl-1"]),
    ]
    assert [call["expected_home"] for call in worker_calls] == [
        "Inter Miami CF",
        "Austin FC",
        "Arsenal",
    ]
    assert report.to_dict()["uploaded"] == 3
    assert all(state.get(item.fixture_id).status == "uploaded" for item in fixtures)


def test_executor_schedules_retry_for_unresolved_url_and_ingestion_failure(tmp_path):
    fixtures = [scheduled("missing"), scheduled("failed", home="Austin FC", away="FC Dallas")]
    state = persisted(tmp_path, fixtures)
    now = fixtures[0].due_at + timedelta(minutes=5)

    def resolver(group):
        return ResolutionBatch(
            urls={"failed": "https://example.com/Matches/100001/Live/test"},
            errors={"missing": "not published yet"},
            candidate_count=0,
        )

    def worker(**kwargs):
        raise RuntimeError("timeline incomplete")

    report = execute_due_batch(state, now=now, resolver=resolver, worker=worker)

    assert report.to_dict()["retry_scheduled"] == 2
    assert state.get("missing").last_error.startswith("provider_url_not_found:")
    assert state.get("failed").last_error == "ingestion: timeline incomplete"
    assert state.get("missing").next_retry_at == now + timedelta(hours=1)


def test_executor_notifies_for_each_success_and_failed_attempt(tmp_path):
    fixtures = [scheduled("success"), scheduled("missing", home="Austin FC", away="FC Dallas")]
    state = persisted(tmp_path, fixtures)
    now = fixtures[0].due_at + timedelta(minutes=5)
    notifications = []

    def resolver(group):
        return ResolutionBatch(
            urls={"success": "https://example.com/Matches/100001/Live/test"},
            errors={"missing": "not published yet"},
            candidate_count=1,
        )

    def worker(**kwargs):
        return WorkerResult(
            status="uploaded",
            league=kwargs["league"],
            season=kwargs["season"],
            match_id="100001",
            key="event_data/mls/2026/100001.parquet",
            validation=None,
        )

    report = execute_due_batch(
        state,
        now=now,
        resolver=resolver,
        worker=worker,
        notifier=lambda **kwargs: notifications.append(kwargs),
    )

    assert report.to_dict()["uploaded"] == 1
    assert report.to_dict()["retry_scheduled"] == 1
    by_fixture = {item["fixture_id"]: item for item in notifications}
    assert by_fixture["success"]["status"] == "uploaded"
    assert by_fixture["success"]["r2_key"] == "event_data/mls/2026/100001.parquet"
    assert by_fixture["missing"]["status"] == "retry_scheduled"
    assert by_fixture["missing"]["attempt"] == 1
    assert by_fixture["missing"]["retry_at"] == (now + timedelta(hours=1)).isoformat()


def test_executor_can_retry_one_selected_fixture_before_retry_deadline(tmp_path):
    fixtures = [scheduled("selected"), scheduled("other", home="Austin FC", away="FC Dallas")]
    state = persisted(tmp_path, fixtures)
    failed_at = fixtures[0].due_at + timedelta(minutes=1)
    state.schedule_retry("selected", "browser failed", now=failed_at)
    calls = []

    def resolver(group):
        group = list(group)
        calls.extend(item.fixture_id for item in group)
        return ResolutionBatch(
            urls={"selected": "https://example.com/Matches/100001/Live/test"},
            errors={},
            candidate_count=1,
        )

    def worker(**kwargs):
        return WorkerResult(
            status="uploaded",
            league=kwargs["league"],
            season=kwargs["season"],
            match_id="100001",
            key="event_data/mls/2026/100001.parquet",
            validation=None,
        )

    report = execute_due_batch(
        state,
        now=failed_at + timedelta(minutes=5),
        fixture_ids=["selected"],
        resolver=resolver,
        worker=worker,
        notifier=lambda **kwargs: None,
    )

    assert report.to_dict()["uploaded"] == 1
    assert calls == ["selected"]
    assert state.get("selected").status == "uploaded"
    assert state.get("other").status == "scheduled"


def test_selected_fixture_can_use_supplied_url_without_discovery(tmp_path):
    fixture = scheduled("selected")
    state = persisted(tmp_path, [fixture])
    source_url = "https://1xbet.whoscored.com/matches/1993897/live/test"
    worker_calls = []

    def resolver(group):
        raise AssertionError("resolver must not run when the source URL is supplied")

    def worker(**kwargs):
        worker_calls.append(kwargs)
        return WorkerResult(
            status="uploaded",
            league=kwargs["league"],
            season=kwargs["season"],
            match_id="1993897",
            key="event_data/laliga/2026_2027/1993897.parquet",
            validation=None,
        )

    report = execute_due_batch(
        state,
        now=fixture.due_at + timedelta(minutes=5),
        fixture_ids=[fixture.fixture_id],
        source_urls={fixture.fixture_id: source_url},
        resolver=resolver,
        worker=worker,
        notifier=lambda **kwargs: None,
    )

    assert report.to_dict()["uploaded"] == 1
    assert worker_calls[0]["url"] == source_url
    assert state.get(fixture.fixture_id).source_url == source_url
