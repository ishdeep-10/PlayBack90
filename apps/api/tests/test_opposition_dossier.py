from __future__ import annotations

import pandas as pd
from fastapi.testclient import TestClient

from app.main import app
from app.services import opposition_dossier
from app.services.opposition_team_context import ApiFootballCoachProvider


client = TestClient(app)


def _row(
    team: str,
    opponent: str,
    match_id: str,
    date: str,
    *,
    goals: int,
    goals_against: int,
    xg: float,
    xga: float,
    possession: float,
    ppda: float,
) -> dict:
    return {
        "matchId": match_id,
        "date": date,
        "sampleSeason": "2025_2026",
        "teamName": team,
        "opponentName": opponent,
        "homeAway": "h",
        "goals": goals,
        "goals_against": goals_against,
        "xG": xg,
        "xG_against": xga,
        "shots": 12,
        "shots_against": 8,
        "shots_on_target": 5,
        "big_chances": 2,
        "big_chances_against": 1,
        "xG_per_shot": round(xg / 12, 3),
        "possession_pct": possession,
        "pass_accuracy": 84,
        "ppda": ppda,
        "field_tilt_pct": possession,
        "box_entries": 18,
        "long_balls": 28,
        "through_balls": 3,
        "crosses": 16,
    }


def _foundation_payload() -> dict:
    return {
        "league": "premier-league",
        "season": "2026_2027",
        "reference_team": "Arsenal",
        "opponent_team": "Chelsea",
        "sample_size": 5,
        "sample_strategy": "similar_opponent_profile",
        "pool_strategy": "previous_season",
        "pool_seasons": ["2025_2026"],
        "features_used": ["possession_pct", "xG", "xG_against"],
        "similar_teams": [{"team": "Liverpool", "similarity": 91.0, "distance": 0.1, "matches": 38}],
        "sample_matches": [
            {
                "match_id": "che-ars",
                "date": "2026-04-01",
                "season": "2025_2026",
                "team": "Chelsea",
                "opponent": "Arsenal",
                "home_away": "h",
                "result": "W",
                "score": "2-1",
                "xg": 1.8,
                "xga": 1.0,
                "shots": 12,
                "shots_against": 8,
                "sample_reason": "similar_opponent",
            },
            {
                "match_id": "che-liv",
                "date": "2026-03-01",
                "season": "2025_2026",
                "team": "Chelsea",
                "opponent": "Liverpool",
                "home_away": "h",
                "result": "D",
                "score": "1-1",
                "xg": 1.2,
                "xga": 1.1,
                "shots": 12,
                "shots_against": 8,
                "sample_reason": "similar_opponent",
            },
        ],
        "warnings": [],
        "team_match_index": {"team": "Chelsea", "matches": [], "match_count": 0},
    }


def test_build_opposition_dossier_returns_mvp_sections(monkeypatch):
    pool = pd.DataFrame(
        [
            _row("Chelsea", "Arsenal", "che-ars", "2026-04-01", goals=2, goals_against=1, xg=1.8, xga=1.0, possession=48, ppda=10),
            _row("Chelsea", "Liverpool", "che-liv", "2026-03-01", goals=1, goals_against=1, xg=1.2, xga=1.1, possession=47, ppda=11),
            _row("Chelsea", "Brighton", "che-bri", "2026-02-01", goals=0, goals_against=2, xg=0.8, xga=1.9, possession=50, ppda=12),
            _row("Arsenal", "Chelsea", "ars-che", "2026-04-01", goals=1, goals_against=2, xg=1.0, xga=1.8, possession=62, ppda=8),
            _row("Liverpool", "Chelsea", "liv-che", "2026-03-01", goals=1, goals_against=1, xg=1.1, xga=1.2, possession=60, ppda=8.5),
        ]
    )
    players = pd.DataFrame(
        [
            {"teamName": "Chelsea", "playerName": "Forward A", "goals": 4, "xG": 5.2, "xA": 1.1, "shots": 22, "mins_played": 600},
            {"teamName": "Chelsea", "playerName": "Creator B", "goals": 1, "xG": 1.4, "xA": 4.6, "shots": 10, "mins_played": 540},
        ]
    )

    monkeypatch.setattr(opposition_dossier, "build_opposition_foundation", lambda **kwargs: _foundation_payload())
    monkeypatch.setattr(opposition_dossier, "load_analysis_pool", lambda league, season, opponent_team: (pool, "previous_season", ["2025_2026"]))
    monkeypatch.setattr(opposition_dossier.ss, "load_player_season_stats", lambda league, season: players)
    monkeypatch.setattr(
        opposition_dossier,
        "build_lineup_context",
        lambda *args, **kwargs: {
            "available": True,
            "source": "event-data",
            "team": "Chelsea",
            "formation_usage": [{"formation": "4-2-3-1", "count": 2, "pct": 100}],
            "matches": [],
            "player_usage": [],
            "availability_signals": {},
        },
    )
    monkeypatch.setattr(
        opposition_dossier.opposition_team_context_service,
        "build_context",
        lambda *args, **kwargs: {
            "available": True,
            "source": "football-data",
            "teams": {
                "opponent": {
                    "team": "Chelsea",
                    "coach": {"name": "Coach A", "available": True},
                    "coach_change": {"status": "no_change_detected", "label": "No change detected"},
                    "squad_changes": {"new_players": [], "missing_players": [], "current_squad_count": 25, "previous_squad_count": 25},
                }
            },
        },
    )

    payload = opposition_dossier.build_opposition_dossier(
        "premier-league",
        "2026_2027",
        "Chelsea",
        "Arsenal",
        fixture_id="fd-1",
        home_team="Arsenal",
        away_team="Chelsea",
    )

    assert payload["meta"]["persona"] == "neutral opposition analyst"
    assert payload["fixtureContext"]["fixture_id"] == "fd-1"
    assert payload["sampleContext"]["pool_strategy"] == "previous_season"
    assert payload["summary"]["confidence"] == "directional"
    assert payload["teamProfile"]["team"] == "Chelsea"
    assert payload["teamContext"]["teams"]["opponent"]["coach"]["name"] == "Coach A"
    assert payload["lineupContext"]["formation_usage"][0]["formation"] == "4-2-3-1"
    assert payload["recentForm"]["record"] == {"wins": 1, "draws": 1, "losses": 1}
    assert payload["keyPlayers"][0]["player"] == "Forward A"


def test_opposition_dossier_endpoint_uses_camel_case_fixture_context(monkeypatch):
    import app.main as main

    monkeypatch.setattr(
        main,
        "build_opposition_dossier",
        lambda league, season, opponent_team, reference_team, fixture_id=None, home_team=None, away_team=None, sample_size=5: {
            "meta": {
                "league": league,
                "fixture_season": season,
                "analysis_seasons": ["2025_2026"],
                "opponent_team": opponent_team,
                "reference_team": reference_team,
                "generated_at": "2026-07-27T00:00:00+00:00",
                "persona": "neutral opposition analyst",
            },
            "fixtureContext": {
                "fixture_id": fixture_id,
                "home_team": home_team,
                "away_team": away_team,
                "reference_team": reference_team,
                "opponent_team": opponent_team,
            },
            "sampleContext": {
                "requested_sample_size": sample_size,
                "actual_sample_size": 1,
                "sample_strategy": "similar_opponent_profile",
                "pool_strategy": "previous_season",
                "pool_seasons": ["2025_2026"],
                "features_used": ["xG"],
                "warnings": [],
                "sample_matches": [{"match_id": "che-ars"}],
                "similar_teams": [],
            },
            "referenceProfile": {"team": reference_team, "available": True, "metrics": {}, "similar_teams": []},
            "teamContext": {"available": False, "source": "football-data", "teams": {}},
            "lineupContext": {"available": False, "source": "event-data", "matches": [], "formation_usage": [], "player_usage": []},
            "summary": {"bullets": [], "confidence": "directional"},
            "teamProfile": {"team": opponent_team, "metrics": [], "match_count": 1},
            "recentForm": {"window": 5, "matches": [], "averages": {}, "record": {"wins": 0, "draws": 0, "losses": 0}},
            "strengths": [],
            "weaknesses": [],
            "keyPlayers": [],
        },
    )

    response = client.get(
        "/api/leagues/premier-league/seasons/2026_2027/opposition/Chelsea/dossier"
        "?referenceTeam=Arsenal&fixtureId=fd-1&home=Arsenal&away=Chelsea&sampleSize=5"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["fixtureContext"]["fixture_id"] == "fd-1"
    assert payload["fixtureContext"]["home_team"] == "Arsenal"
    assert payload["meta"]["opponent_team"] == "Chelsea"


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, payloads: list[dict]):
        self.payloads = payloads
        self.calls = 0

    def get(self, *args, **kwargs):
        payload = self.payloads[min(self.calls, len(self.payloads) - 1)]
        self.calls += 1
        return _FakeResponse(payload)


class _FakeResolver:
    def resolve(self, team_name: str, league: str | None = None):
        return 40


def test_api_football_transfer_disk_cache_survives_provider_errors(monkeypatch, tmp_path):
    transfer_payload = {
        "response": [
            {
                "player": {"id": 1, "name": "Player In"},
                "transfers": [
                    {
                        "date": "2026-07-01",
                        "type": "Transfer",
                        "teams": {"in": {"id": 40, "name": "Liverpool"}, "out": {"id": 2, "name": "Source FC"}},
                    }
                ],
            }
        ],
        "errors": [],
    }
    quota_payload = {"response": [], "errors": {"requests": "limit"}}
    monkeypatch.setattr("app.services.player_images.resolve_player_image", lambda *args, **kwargs: None)

    provider = ApiFootballCoachProvider(
        "key",
        session=_FakeSession([transfer_payload]),
        team_id_resolver=_FakeResolver(),
        transfer_cache_dir=tmp_path,
    )
    first = provider.transfer_activity_for_season("Liverpool FC", "2026_2027", "premier-league")
    assert first["available"] is True
    assert first["incoming_count"] == 1

    provider_after_restart = ApiFootballCoachProvider(
        "key",
        session=_FakeSession([quota_payload]),
        team_id_resolver=_FakeResolver(),
        transfer_cache_dir=tmp_path,
    )
    cached = provider_after_restart.transfer_activity_for_season("Liverpool FC", "2026_2027", "premier-league")
    assert cached["available"] is True
    assert cached["incoming_count"] == 1
    assert cached["warning"] is None
    assert provider_after_restart.session.calls == 0
