from __future__ import annotations

from datetime import datetime, timezone

from app.services.schedules import (
    OfficialMlsScheduleProvider,
    ScheduleProviderError,
    ScheduleService,
    current_provider_season_key,
)


class FakeProvider:
    def __init__(self, matches):
        self.matches = matches

    def fetch(self, league: str, season: str):
        return self.matches


class FailingProvider:
    def fetch(self, league: str, season: str):
        raise ScheduleProviderError("provider unavailable")


class StubResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class StubMlsSession:
    def __init__(self):
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if url.endswith("/seasons"):
            return StubResponse({"seasons": [{"season": 2026, "season_id": "season-2026"}]})
        page_token = (kwargs.get("params") or {}).get("page_token")
        if page_token:
            return StubResponse({"schedule": [{"match_id": "second"}], "next_page_token": None})
        return StubResponse({"schedule": [{"match_id": "first"}], "next_page_token": "next-token"})


def _provider_match(match_id: int, home: str, away: str, utc_date: str, matchday: int, status: str = "SCHEDULED"):
    return {
        "id": match_id,
        "utcDate": utc_date,
        "status": status,
        "matchday": matchday,
        "homeTeam": {"name": home},
        "awayTeam": {"name": away},
        "score": {"fullTime": {"home": None, "away": None}},
    }


def _official_mls_match(
    match_id: str,
    home: str,
    away: str,
    utc_date: str,
    matchday: int,
    status: str = "scheduled",
):
    return {
        "_provider": "official-mls",
        "match_id": match_id,
        "planned_kickoff_time": utc_date,
        "match_status": status,
        "match_day": matchday,
        "home_team_name": home,
        "away_team_name": away,
        "home_team_three_letter_code": "HOM",
        "away_team_three_letter_code": "AWY",
        "result": "2:1" if status == "finalWhistle" else "0:0",
        "stadium_id": "stadium-1",
        "stadium_name": "Test Stadium",
        "stadium_city": "Test City",
        "stadium_country": "USA",
    }


def test_official_mls_provider_resolves_season_and_paginates():
    session = StubMlsSession()
    provider = OfficialMlsScheduleProvider(base_url="https://official.test", session=session)

    matches = provider.fetch("mls", "2026")

    assert [match["match_id"] for match in matches] == ["first", "second"]
    assert all(match["_provider"] == "official-mls" for match in matches)
    assert session.calls[-1][1]["params"]["page_token"] == "next-token"


def test_fixture_hub_normalizes_official_mls_schedule_metadata(monkeypatch):
    from app.services import r2

    monkeypatch.setattr(r2, "list_all_fixtures", lambda league, season: [])
    service = ScheduleService(
        FakeProvider([_official_mls_match("mls-1", "Atlanta United", "Red Bull New York", "2026-08-15T23:30:00Z", 20)])
    )

    payload = service.build_fixture_hub("mls", "2026")

    assert payload["source"] == "official-mls"
    assert payload["counts"]["upcoming"] == 1
    assert payload["selected_round_id"] == "matchday-20"
    assert payload["fixtures"][0]["provider_fixture_id"] == "mls-1"
    assert payload["fixtures"][0]["venue"] == "Test Stadium"


def test_fixture_hub_merges_mls_completed_match_with_one_day_timezone_shift(monkeypatch):
    from app.services import r2

    completed = {
        "match_id": "local-1",
        "start_date": datetime(2026, 4, 5, tzinfo=timezone.utc),
        "start_date_label": "2026-04-05",
        "home_team": "Atlanta United",
        "away_team": "Columbus Crew",
        "score": "2-1",
    }
    monkeypatch.setattr(r2, "list_all_fixtures", lambda league, season: [completed])
    service = ScheduleService(
        FakeProvider([_official_mls_match("official-1", "Atlanta United", "Columbus Crew", "2026-04-04T23:30:00Z", 6, "finalWhistle")])
    )

    payload = service.build_fixture_hub("mls", "2026")

    assert payload["counts"]["all"] == 1
    assert payload["counts"]["completed"] == 1
    assert payload["fixtures"][0]["source"] == "r2"
    assert payload["fixtures"][0]["provider_fixture_id"] == "official-1"


def test_current_provider_season_key_rolls_in_summer():
    assert current_provider_season_key(datetime(2026, 7, 27, tzinfo=timezone.utc)) == "2026_2027"
    assert current_provider_season_key(datetime(2026, 2, 1, tzinfo=timezone.utc)) == "2025_2026"


def test_fixture_hub_uses_provider_matchdays_and_next_upcoming_round(monkeypatch):
    from app.services import r2

    monkeypatch.setattr(r2, "list_all_fixtures", lambda league, season: [])
    service = ScheduleService(
        FakeProvider(
            [
                _provider_match(1, "Arsenal FC", "Chelsea FC", "2026-08-15T14:00:00Z", 1),
                _provider_match(2, "Liverpool FC", "Everton FC", "2026-08-22T14:00:00Z", 2),
            ]
        )
    )

    payload = service.build_fixture_hub("premier-league", "2026_2027")

    assert payload["counts"]["upcoming"] == 2
    assert payload["selected_round_id"] == "matchday-1"
    assert [round_item["id"] for round_item in payload["rounds"]] == ["matchday-2", "matchday-1"]
    assert [fixture["provider_fixture_id"] for fixture in payload["fixtures"]] == [1]
    assert payload["fixtures"][0]["state"] == "upcoming"
    assert payload["fixtures"][0]["opposition_href"].startswith("/opposition-analysis?")


def test_fixture_hub_prefers_completed_r2_fixture_when_provider_matches(monkeypatch):
    from app.services import r2

    completed = {
        "file_path": "playback90/event_data/premier-league/2026_2027/2026-08-15_abc_13_vs_15_2___1.parquet",
        "match_id": "abc",
        "start_date": datetime(2026, 8, 15, tzinfo=timezone.utc),
        "start_date_label": "2026-08-15",
        "home_team_id": 13,
        "away_team_id": 15,
        "home_team": "Arsenal",
        "away_team": "Chelsea",
        "score": "2-1",
    }
    monkeypatch.setattr(r2, "list_all_fixtures", lambda league, season: [completed])
    service = ScheduleService(
        FakeProvider(
            [
                _provider_match(1, "Arsenal FC", "Chelsea FC", "2026-08-15T14:00:00Z", 1, status="FINISHED"),
                _provider_match(2, "Liverpool FC", "Everton FC", "2026-08-22T14:00:00Z", 2),
            ]
        )
    )

    payload = service.build_fixture_hub("premier-league", "2026_2027", round_id="matchday-1")

    assert payload["counts"]["all"] == 2
    assert payload["counts"]["completed"] == 1
    assert payload["fixtures"][0]["source"] == "r2"
    assert payload["fixtures"][0]["matchday"] == 1
    assert payload["fixtures"][0]["provider_fixture_id"] == 1
    assert "league=premier-league" in payload["fixtures"][0]["post_match_href"]
    assert "season=2026_2027" in payload["fixtures"][0]["post_match_href"]
    assert "filePath" not in payload["fixtures"][0]["post_match_href"]


def test_fixture_hub_splits_provider_matchday_when_team_repeats(monkeypatch):
    from app.services import r2

    monkeypatch.setattr(r2, "list_all_fixtures", lambda league, season: [])
    service = ScheduleService(
        FakeProvider(
            [
                _provider_match(1, "FC Barcelona", "Levante UD", "2026-08-16T17:30:00Z", 1),
                _provider_match(2, "Real Madrid CF", "Real Sociedad de Fútbol", "2026-08-26T19:00:00Z", 1),
                _provider_match(3, "FC Barcelona", "Athletic Club", "2026-08-27T19:00:00Z", 1),
            ]
        )
    )

    payload = service.build_fixture_hub("laliga", "2026_2027")

    assert [round_item["id"] for round_item in payload["rounds"]] == ["matchday-1-2", "matchday-1-1"]
    assert payload["selected_round_id"] == "matchday-1-1"
    teams = [
        team
        for fixture in payload["fixtures"]
        for team in (fixture["home_team"], fixture["away_team"])
    ]
    assert len(teams) == len(set(teams))


def test_fixture_hub_maps_espanyol_without_confusing_barcelona(monkeypatch):
    from app.services import r2

    monkeypatch.setattr(r2, "list_all_fixtures", lambda league, season: [])
    service = ScheduleService(
        FakeProvider(
            [
                _provider_match(1, "RCD Espanyol de Barcelona", "Levante UD", "2026-08-16T17:30:00Z", 1),
                _provider_match(2, "FC Barcelona", "Athletic Club", "2026-08-27T19:00:00Z", 1),
            ]
        )
    )

    payload = service.build_fixture_hub("laliga", "2026_2027", round_id="matchday-1")

    assert payload["selected_round_id"] == "matchday-1"
    assert [fixture["home_team"] for fixture in payload["fixtures"]] == ["Espanyol", "Barcelona"]


def test_fixture_hub_uses_persisted_schedule_cache_when_provider_fails(monkeypatch, tmp_path):
    from app.services import r2

    monkeypatch.setattr(r2, "list_all_fixtures", lambda league, season: [])
    cache_dir = tmp_path / "schedules"
    priming_service = ScheduleService(
        FakeProvider(
            [
                _provider_match(1, "Arsenal FC", "Chelsea FC", "2026-08-15T14:00:00Z", 1),
                _provider_match(2, "Liverpool FC", "Everton FC", "2026-08-15T16:30:00Z", 1),
            ]
        ),
        cache_dir=cache_dir,
    )

    priming_payload = priming_service.build_fixture_hub("premier-league", "2026_2027")
    assert priming_payload["is_stale"] is False
    assert (cache_dir / "premier-league" / "2026_2027.json").exists()

    failing_service = ScheduleService(FailingProvider(), cache_dir=cache_dir)
    stale_payload = failing_service.build_fixture_hub("premier-league", "2026_2027")

    assert stale_payload["is_stale"] is True
    assert "saved official schedule" in stale_payload["warning"]
    assert stale_payload["counts"]["upcoming"] == 2
    assert stale_payload["selected_round_id"] == "matchday-1"
