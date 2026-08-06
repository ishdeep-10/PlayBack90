from __future__ import annotations

import pandas as pd
from fastapi.testclient import TestClient

from app.main import app
from app.services.opposition_foundation import (
    LOW_SAMPLE_WARNING,
    build_team_style_profiles,
    select_similar_opponent_matches,
    similar_teams,
)


client = TestClient(app)


def _row(
    team: str,
    opponent: str,
    match_id: str,
    *,
    possession: float,
    ppda: float,
    xg: float,
    xga: float,
    date: str = "2026-05-01",
) -> dict:
    return {
        "matchId": match_id,
        "date": date,
        "sampleSeason": "2025_2026",
        "teamName": team,
        "opponentName": opponent,
        "homeAway": "h",
        "goals": 1,
        "goals_against": 1,
        "xG": xg,
        "xG_against": xga,
        "shots": 12,
        "shots_against": 10,
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


def _league_rows() -> list[dict]:
    rows = [
        _row("Arsenal", "Chelsea", "ars-che", possession=61, ppda=8.2, xg=1.8, xga=0.9),
        _row("Liverpool", "Chelsea", "liv-che", possession=60, ppda=8.5, xg=1.75, xga=1.0),
        _row("Man City", "Chelsea", "mci-che", possession=63, ppda=7.9, xg=1.9, xga=0.8),
        _row("Chelsea", "Arsenal", "che-ars", possession=47, ppda=11.1, xg=1.1, xga=1.6, date="2026-04-01"),
        _row("Chelsea", "Liverpool", "che-liv", possession=48, ppda=10.8, xg=1.2, xga=1.5, date="2026-03-01"),
        _row("Chelsea", "Man City", "che-mci", possession=45, ppda=11.5, xg=0.9, xga=1.8, date="2026-02-01"),
        _row("Chelsea", "Burnley", "che-bur", possession=56, ppda=13.5, xg=1.4, xga=0.7, date="2026-01-01"),
    ]
    for index in range(8):
        rows.append(
            _row(
                f"Direct Team {index}",
                "Chelsea",
                f"direct-{index}",
                possession=35 + index,
                ppda=17 + index,
                xg=0.8,
                xga=1.8,
            )
        )
    rows.append(_row("Burnley", "Chelsea", "bur-che", possession=34, ppda=20, xg=0.7, xga=2.0))
    return rows


def test_team_style_profiles_use_available_columns():
    df = pd.DataFrame(_league_rows())

    profiles, features = build_team_style_profiles(df)

    assert "possession_pct" in features
    assert "xG_against" in features
    assert profiles[profiles["teamName"] == "Arsenal"].iloc[0]["matches"] == 1


def test_similar_teams_ranks_style_peers_before_distant_teams():
    df = pd.DataFrame(_league_rows())

    peers = similar_teams(df, "Arsenal", limit=3)

    assert peers[0]["team"] in {"Liverpool", "Man City"}
    assert "Burnley" not in {peer["team"] for peer in peers}


def test_similar_opponent_sample_prefers_reference_and_style_peers():
    df = pd.DataFrame(_league_rows())

    sample = select_similar_opponent_matches(df, "Chelsea", "Arsenal", sample_size=3)

    assert [match["opponent"] for match in sample["matches"]] == ["Arsenal", "Liverpool", "Man City"]
    assert {match["sample_reason"] for match in sample["matches"]} == {"similar_opponent"}
    assert sample["warnings"] == []


def test_similar_opponent_sample_warns_when_recent_fallback_is_needed():
    df = pd.DataFrame(
        [
            _row("Arsenal", "Chelsea", "ars-che", possession=61, ppda=8.2, xg=1.8, xga=0.9),
            _row("Liverpool", "Chelsea", "liv-che", possession=60, ppda=8.5, xg=1.75, xga=1.0),
            _row("Chelsea", "Arsenal", "che-ars", possession=47, ppda=11.1, xg=1.1, xga=1.6, date="2026-04-01"),
            _row("Chelsea", "Burnley", "che-bur", possession=56, ppda=13.5, xg=1.4, xga=0.7, date="2026-03-01"),
        ]
    )

    sample = select_similar_opponent_matches(df, "Chelsea", "Arsenal", sample_size=3)

    assert len(sample["matches"]) == 2
    assert sample["matches"][-1]["sample_reason"] == "recent_fallback"
    assert LOW_SAMPLE_WARNING in sample["warnings"]


def test_opposition_foundation_endpoint_uses_service(monkeypatch):
    import app.main as main

    monkeypatch.setattr(
        main,
        "build_opposition_foundation",
        lambda league, season, opponent_team, reference_team, sample_size=5: {
            "league": league,
            "season": season,
            "reference_team": reference_team,
            "opponent_team": opponent_team,
            "sample_size": sample_size,
            "sample_strategy": "similar_opponent_profile",
            "pool_strategy": "previous_season",
            "pool_seasons": ["2025_2026"],
            "features_used": ["possession_pct", "xG"],
            "similar_teams": [{"team": "Liverpool", "similarity": 91.0, "distance": 0.1, "matches": 38}],
            "sample_matches": [
                {
                    "match_id": "che-ars",
                    "date": "2026-04-01",
                    "season": "2025_2026",
                    "team": "Chelsea",
                    "opponent": "Arsenal",
                    "home_away": "h",
                    "result": "D",
                    "score": "1-1",
                    "xg": 1.1,
                    "xga": 1.6,
                    "shots": 12,
                    "shots_against": 10,
                    "sample_reason": "similar_opponent",
                }
            ],
            "warnings": [],
            "team_match_index": {"team": opponent_team, "matches": [], "match_count": 0},
        },
    )

    response = client.get(
        "/api/leagues/premier-league/seasons/2026_2027/opposition/Chelsea/foundation?reference_team=Arsenal&sample_size=5"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["reference_team"] == "Arsenal"
    assert payload["opponent_team"] == "Chelsea"
    assert payload["pool_strategy"] == "previous_season"
