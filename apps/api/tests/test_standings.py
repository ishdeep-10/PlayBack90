from datetime import datetime, timezone

from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app
from app.services.standings import (
    FootballDataStandingsProvider,
    OfficialMlsStandingsProvider,
    StandingsProviderError,
    StandingsService,
    merge_local_analytics,
    provider_season_year,
)


client = TestClient(app)


PROVIDER_PAYLOAD = {
    "standings": [
        {"type": "HOME", "table": [{"position": 1, "team": {"name": "Wrong table"}}]},
        {
            "type": "TOTAL",
            "table": [
                {
                    "position": 1,
                    "team": {
                        "id": 65,
                        "name": "Manchester City FC",
                        "shortName": "Man City",
                        "tla": "MCI",
                        "crest": "https://crests.football-data.org/65.png",
                    },
                    "playedGames": 4,
                    "form": "W,W,D,W",
                    "won": 3,
                    "draw": 1,
                    "lost": 0,
                    "points": 10,
                    "goalsFor": 9,
                    "goalsAgainst": 2,
                    "goalDifference": 7,
                }
            ],
        },
    ]
}


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return PROVIDER_PAYLOAD


class FakeSession:
    def __init__(self):
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse()


class FakeProvider:
    def __init__(self, rows):
        self.rows = rows
        self.calls = 0
        self.error = False

    def fetch(self, league, season):
        self.calls += 1
        if self.error:
            raise StandingsProviderError("provider unavailable")
        return self.rows


def test_provider_converts_app_season_and_normalizes_total_table():
    session = FakeSession()
    provider = FootballDataStandingsProvider("secret", session=session)

    rows = provider.fetch("premier-league", "2025_2026")

    assert provider_season_year("2025/2026") == 2025
    assert session.calls[0][0].endswith("/competitions/PL/standings")
    assert session.calls[0][1]["params"] == {"season": 2025}
    assert session.calls[0][1]["headers"] == {"X-Auth-Token": "secret"}
    assert rows[0]["team"] == "Manchester City FC"
    assert rows[0]["drawn"] == 1
    assert rows[0]["pts"] == 10


def test_mls_provider_returns_separate_official_conference_rows():
    class JsonResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class MlsSession:
        def __init__(self):
            self.calls = []

        def get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            if url.endswith("/seasons"):
                return JsonResponse(
                    {"seasons": [{"season": 2026, "season_id": "MLS-SEA-2026"}]}
                )
            return JsonResponse(
                {
                    "tables": [
                        {
                            "category": "conference",
                            "group": "EASTERN CONFERENCE",
                            "entries": [
                                {
                                    "position": 1,
                                    "team": "Nashville SC",
                                    "team_id": "MLS-CLU-NSH",
                                    "team_three_letter_code": "NSH",
                                    "games_played": 18,
                                    "wins": 12,
                                    "draws": 4,
                                    "losses": 2,
                                    "goals_scored": 35,
                                    "goals_against": 14,
                                    "goals_difference": 21,
                                    "points": 40,
                                }
                            ],
                        },
                        {
                            "category": "conference",
                            "group": "WESTERN CONFERENCE",
                            "entries": [
                                {
                                    "position": 1,
                                    "team": "Vancouver Whitecaps FC",
                                    "team_id": "MLS-CLU-VAN",
                                    "team_three_letter_code": "VAN",
                                    "games_played": 17,
                                    "wins": 10,
                                    "draws": 4,
                                    "losses": 3,
                                    "goals_scored": 38,
                                    "goals_against": 17,
                                    "goals_difference": 21,
                                    "points": 34,
                                }
                            ],
                        },
                    ]
                }
            )

    session = MlsSession()
    rows = OfficialMlsStandingsProvider(session=session).fetch("mls", "2026")

    assert [row["conference"] for row in rows] == [
        "Eastern Conference",
        "Western Conference",
    ]
    assert rows[0]["provider_team_id"] == "MLS-CLU-NSH"
    assert session.calls[1][1]["params"] == {"category": "conference"}


def test_mls_service_builds_two_conference_groups():
    provider = FakeProvider(
        [
            {"rank": 1, "team": "Nashville SC", "provider_team_name": "Nashville SC", "conference": "Eastern Conference"},
            {"rank": 1, "team": "Vancouver Whitecaps FC", "provider_team_name": "Vancouver Whitecaps FC", "conference": "Western Conference"},
        ]
    )

    payload = StandingsService(provider).build_payload("mls", "2026", [])

    assert payload["source"] == "official-mls"
    assert [group["label"] for group in payload["groups"]] == [
        "Eastern Conference",
        "Western Conference",
    ]
    assert payload["groups"][0]["rows"][0]["rank"] == 1


def test_local_team_name_and_analytics_are_merged_into_official_rows():
    official = FootballDataStandingsProvider("secret", session=FakeSession()).fetch(
        "premier-league", "2025_2026"
    )
    local = [{"team": "Man City", "xg": 8.2, "xga": 2.4, "xgd": 5.8}]

    rows = merge_local_analytics(official, local)

    assert rows[0]["team"] == "Man City"
    assert rows[0]["provider_team_name"] == "Manchester City FC"
    assert rows[0]["xgd"] == 5.8


def test_local_team_matching_handles_provider_club_prefixes():
    official = [
        {
            "rank": 1,
            "team": "Olympique de Marseille",
            "provider_team_name": "Olympique de Marseille",
        },
        {
            "rank": 2,
            "team": "SSC Napoli",
            "provider_team_name": "SSC Napoli",
        },
    ]
    local = [
        {"team": "Marseille", "xg": 3.1},
        {"team": "Napoli", "xg": 2.7},
    ]

    rows = merge_local_analytics(official, local)

    assert [row["team"] for row in rows] == ["Marseille", "Napoli"]


def test_service_caches_official_rows_and_uses_stale_copy_on_failure():
    provider = FakeProvider([{"rank": 1, "team": "Arsenal", "provider_team_name": "Arsenal"}])
    service = StandingsService(provider, cache_ttl_seconds=0, stale_ttl_seconds=60)

    first = service.build_payload("premier-league", "2025_2026", [])
    provider.error = True
    stale = service.build_payload("premier-league", "2025_2026", [])

    assert first["source"] == "football-data"
    assert stale["is_stale"] is True
    assert stale["rows"][0]["team"] == "Arsenal"
    assert provider.calls == 2


def test_service_returns_calculated_fallback_when_provider_is_not_configured():
    service = StandingsService(None)
    local = [
        {
            "rank": 1,
            "team": "Arsenal",
            "played": 2,
            "won": 2,
            "drawn": 0,
            "lost": 0,
            "gf": 5,
            "ga": 1,
            "gd": 4,
            "pts": 6,
            "xg": 4.2,
            "xga": 1.3,
            "xgd": 2.9,
        }
    ]

    payload = service.build_payload("premier-league", "2025_2026", local)

    assert payload["source"] == "calculated"
    assert payload["is_official"] is False
    assert payload["is_complete"] is False
    assert "may be incomplete" in payload["warning"]
    assert isinstance(payload["updated_at"], datetime)
    assert payload["updated_at"].tzinfo == timezone.utc


def test_standings_endpoint_exposes_normalized_contract(monkeypatch):
    local_rows = [
        {
            "rank": 1,
            "team": "Arsenal",
            "played": 1,
            "won": 1,
            "drawn": 0,
            "lost": 0,
            "gf": 2,
            "ga": 0,
            "gd": 2,
            "pts": 3,
            "xg": 1.7,
            "xga": 0.4,
            "xgd": 1.3,
        }
    ]
    monkeypatch.setattr(main_module.ss, "load_team_season_stats", lambda league, season: object())
    monkeypatch.setattr(main_module.ss, "build_league_table", lambda frame: local_rows)
    monkeypatch.setattr(
        main_module.standings_service,
        "build_payload",
        lambda league, season, rows: {
            "league": league,
            "season": season,
            "source": "calculated",
            "updated_at": datetime.now(timezone.utc),
            "is_official": False,
            "is_stale": False,
            "is_complete": False,
            "warning": "Fallback",
            "rows": rows,
        },
    )

    response = client.get("/api/leagues/premier-league/seasons/2025_2026/standings")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "calculated"
    assert payload["rows"][0]["team"] == "Arsenal"
    assert payload["rows"][0]["xg"] == 1.7
