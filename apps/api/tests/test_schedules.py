from __future__ import annotations

from datetime import datetime, timezone

from app.services.schedules import ScheduleProviderError, ScheduleService, current_provider_season_key


class FakeProvider:
    def __init__(self, matches):
        self.matches = matches

    def fetch(self, league: str, season: str):
        return self.matches


class FailingProvider:
    def fetch(self, league: str, season: str):
        raise ScheduleProviderError("provider unavailable")


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
