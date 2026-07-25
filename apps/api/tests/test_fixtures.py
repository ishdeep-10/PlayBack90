from datetime import datetime

from fastapi.testclient import TestClient

from app.main import app
from app.services import fixture_rounds
from app.services.r2 import parse_fixture_filename


client = TestClient(app)


def _fixture(match_id: str, date: str, home: str, away: str) -> dict[str, object]:
    return {
        "file_path": f"bucket/event_data/league/season/{date}_{match_id}_1_vs_2_1___0.parquet",
        "match_id": match_id,
        "start_date": datetime.fromisoformat(date),
        "start_date_label": date,
        "home_team_id": 1,
        "away_team_id": 2,
        "home_team": home,
        "away_team": away,
        "score": "1-0",
    }


def test_parse_fixture_filename_extracts_metadata():
    result = parse_fixture_filename(
        "bucket/event_data/premier-league/2024_25/2025-05-03_1821387_31_vs_165_2___2.parquet"
    )

    assert result is not None
    assert result["match_id"] == "1821387"
    assert result["home_team_id"] == 31
    assert result["away_team_id"] == 165
    assert result["home_team"] == "Everton"
    assert result["away_team"] == "Ipswich"
    assert result["score"] == "2-2"


def test_infer_fixture_rounds_keeps_each_team_to_one_match_per_round():
    fixtures = [
        _fixture("1", "2025-08-09", "Alpha", "Bravo"),
        _fixture("2", "2025-08-10", "Charlie", "Delta"),
        _fixture("3", "2025-08-16", "Alpha", "Charlie"),
        _fixture("4", "2025-08-17", "Bravo", "Delta"),
    ]

    rounds = fixture_rounds.build_fixture_rounds(fixtures)

    assert [item["id"] for item in rounds] == ["round-2", "round-1"]
    assert [item["match_count"] for item in rounds] == [2, 2]
    assert all(item["metadata_source"] == "inferred" for item in rounds)


def test_complete_manifest_provides_authoritative_round_labels():
    fixtures = [
        _fixture("1", "2025-08-09", "Alpha", "Bravo"),
        _fixture("2", "2025-08-16", "Alpha", "Charlie"),
    ]
    manifest = {
        "version": 1,
        "rounds": [
            {
                "id": "matchweek-1",
                "label": "Matchweek 1",
                "stage": "Regular season",
                "order": 1,
                "match_ids": ["1"],
            },
            {
                "id": "matchweek-2",
                "label": "Matchweek 2",
                "stage": "Regular season",
                "order": 2,
                "match_ids": ["2"],
            },
        ],
    }

    rounds = fixture_rounds.build_fixture_rounds(fixtures, manifest)

    assert [item["id"] for item in rounds] == ["matchweek-2", "matchweek-1"]
    assert all(item["metadata_source"] == "manifest" for item in rounds)
    assert rounds[0]["stage"] == "Regular season"


def test_partial_manifest_falls_back_without_hiding_matches():
    fixtures = [
        _fixture("1", "2025-08-09", "Alpha", "Bravo"),
        _fixture("2", "2025-08-16", "Alpha", "Charlie"),
    ]
    manifest = {
        "rounds": [
            {"id": "matchweek-1", "label": "Matchweek 1", "order": 1, "match_ids": ["1"]},
        ],
    }

    rounds = fixture_rounds.build_fixture_rounds(fixtures, manifest)

    assert sum(item["match_count"] for item in rounds) == 2
    assert all(item["metadata_source"] == "inferred" for item in rounds)


def test_round_endpoints_return_navigation_and_selected_fixtures(monkeypatch):
    fixtures = [_fixture("1", "2025-08-09", "Alpha", "Bravo")]
    rounds = fixture_rounds.build_fixture_rounds(fixtures)
    monkeypatch.setattr(fixture_rounds, "list_fixture_rounds", lambda league, season: rounds)

    list_response = client.get("/api/leagues/test-league/seasons/2025_2026/rounds")
    assert list_response.status_code == 200
    assert list_response.json()["latest_round_id"] == "round-1"
    assert list_response.json()["rounds"][0]["metadata_source"] == "inferred"

    detail_response = client.get("/api/leagues/test-league/seasons/2025_2026/rounds/round-1")
    assert detail_response.status_code == 200
    assert detail_response.json()["round"]["label"] == "Round 1"
    assert detail_response.json()["fixtures"][0]["match_id"] == "1"

    missing_response = client.get("/api/leagues/test-league/seasons/2025_2026/rounds/missing")
    assert missing_response.status_code == 404


def test_round_index_reuses_recent_r2_listing(monkeypatch):
    calls = {"fixtures": 0, "manifest": 0}

    def list_all_fixtures(league, season):
        calls["fixtures"] += 1
        return [_fixture("cached-1", "2025-08-09", "Alpha", "Bravo")]

    def load_round_manifest(league, season):
        calls["manifest"] += 1
        return None

    fixture_rounds._ROUND_INDEX_CACHE.clear()
    monkeypatch.setattr(fixture_rounds.r2, "list_all_fixtures", list_all_fixtures)
    monkeypatch.setattr(fixture_rounds.r2, "load_round_manifest", load_round_manifest)

    first = fixture_rounds.list_fixture_rounds("cache-league", "cache-season")
    second = fixture_rounds.list_fixture_rounds("cache-league", "cache-season")

    assert first is second
    assert calls == {"fixtures": 1, "manifest": 1}


def test_bundled_premier_league_manifest_preserves_official_matchweeks():
    manifest = fixture_rounds.load_bundled_round_manifest("premier-league", "2025_2026")

    assert manifest is not None
    dates = {
        "matchweek-36": "2026-05-09",
        "matchweek-37": "2026-05-17",
        "matchweek-38": "2026-05-24",
    }
    fixtures = [
        _fixture(
            str(match_id),
            dates[str(round_data["id"])],
            f"Home {match_id}",
            f"Away {match_id}",
        )
        for round_data in manifest["rounds"]
        for match_id in round_data["match_ids"]
    ]

    rounds = fixture_rounds.build_fixture_rounds(fixtures, manifest)

    assert [item["id"] for item in rounds] == ["matchweek-38", "matchweek-37", "matchweek-36"]
    assert [item["match_count"] for item in rounds] == [10, 10, 11]
    matchweek_36_ids = {fixture["match_id"] for fixture in rounds[2]["fixtures"]}
    matchweek_37_ids = {fixture["match_id"] for fixture in rounds[1]["fixtures"]}
    assert "1903466" in matchweek_36_ids
    assert "1903446" in matchweek_37_ids
    assert all(item["metadata_source"] == "manifest" for item in rounds)


def test_bundled_manifest_path_rejects_traversal():
    assert fixture_rounds.load_bundled_round_manifest("../premier-league", "2025_2026") is None
