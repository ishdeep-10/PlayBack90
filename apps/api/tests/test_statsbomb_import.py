from fastapi.testclient import TestClient

from app.main import app
from app.services.providers.statsbomb import normalize_statsbomb_match
from app.services.views.match_summary import build_lineups
from app.services.views.pass_network import build_pass_network


client = TestClient(app)


def statsbomb_payload():
    return {
        "match": {
            "match_id": 22912,
            "match_date": "2019-06-01",
            "competition": {"competition_name": "Champions League"},
            "season": {"season_name": "2018/2019"},
            "home_team": {"home_team_id": 38, "home_team_name": "Tottenham Hotspur"},
            "away_team": {"away_team_id": 24, "away_team_name": "Liverpool"},
            "home_score": 0,
            "away_score": 2,
        },
        "events": [
            {
                "id": "start-home",
                "index": 1,
                "period": 1,
                "minute": 0,
                "second": 0,
                "type": {"id": 35, "name": "Starting XI"},
                "team": {"id": 38, "name": "Tottenham Hotspur"},
                "tactics": {
                    "formation": 4231,
                    "lineup": [
                        {"player": {"id": 1, "name": "Home GK"}, "position": {"id": 1, "name": "Goalkeeper"}},
                        {"player": {"id": 2, "name": "Home CM"}, "position": {"id": 13, "name": "Right Center Midfield"}},
                    ],
                },
            },
            {
                "id": "start-away",
                "index": 2,
                "period": 1,
                "minute": 0,
                "second": 0,
                "type": {"id": 35, "name": "Starting XI"},
                "team": {"id": 24, "name": "Liverpool"},
                "tactics": {
                    "formation": 433,
                    "lineup": [
                        {"player": {"id": 3, "name": "Away CB"}, "position": {"id": 3, "name": "Right Center Back"}},
                        {"player": {"id": 4, "name": "Away FW"}, "position": {"id": 23, "name": "Center Forward"}},
                    ],
                },
            },
            {
                "id": "pass-1",
                "index": 3,
                "period": 1,
                "minute": 1,
                "second": 4,
                "type": {"id": 30, "name": "Pass"},
                "team": {"id": 24, "name": "Liverpool"},
                "player": {"id": 3, "name": "Away CB"},
                "position": {"id": 3, "name": "Right Center Back"},
                "location": [40.0, 42.0],
                "pass": {
                    "recipient": {"id": 4, "name": "Away FW"},
                    "end_location": [70.0, 38.0],
                    "height": {"id": 1, "name": "Ground Pass"},
                },
                "related_events": ["receipt-1"],
                "possession": 2,
                "play_pattern": {"id": 1, "name": "Regular Play"},
            },
            {
                "id": "pass-2",
                "index": 4,
                "period": 1,
                "minute": 1,
                "second": 10,
                "type": {"id": 30, "name": "Pass"},
                "team": {"id": 24, "name": "Liverpool"},
                "player": {"id": 4, "name": "Away FW"},
                "position": {"id": 23, "name": "Center Forward"},
                "location": [70.0, 38.0],
                "pass": {
                    "recipient": {"id": 3, "name": "Away CB"},
                    "end_location": [62.0, 44.0],
                    "height": {"id": 1, "name": "Ground Pass"},
                },
                "possession": 2,
                "play_pattern": {"id": 1, "name": "Regular Play"},
            },
            {
                "id": "shot-1",
                "index": 5,
                "period": 1,
                "minute": 2,
                "second": 1,
                "type": {"id": 16, "name": "Shot"},
                "team": {"id": 24, "name": "Liverpool"},
                "player": {"id": 4, "name": "Away FW"},
                "position": {"id": 23, "name": "Center Forward"},
                "location": [104.0, 40.0],
                "shot": {
                    "statsbomb_xg": 0.31,
                    "outcome": {"id": 97, "name": "Goal"},
                    "body_part": {"id": 40, "name": "Right Foot"},
                    "type": {"id": 87, "name": "Open Play"},
                },
                "possession": 2,
                "play_pattern": {"id": 1, "name": "Regular Play"},
            },
        ],
    }


def test_normalize_statsbomb_match_uses_provider_xg_and_match_metadata():
    df = normalize_statsbomb_match(statsbomb_payload())

    assert {"matchId", "teamName", "type", "x", "y", "xG", "h_a"}.issubset(df.columns)
    shot = df[df["isShot"]].iloc[0]
    assert shot["type"] == "Goal"
    assert shot["xG"] == 0.31
    assert shot["h_a"] == "a"
    assert shot["x"] == 91.0
    assert shot["y"] == 34.0


def test_normalize_statsbomb_match_flips_y_axis_to_app_convention():
    payload = statsbomb_payload()
    payload["events"][2]["location"] = [40.0, 10.0]
    payload["events"][2]["pass"]["end_location"] = [70.0, 70.0]

    df = normalize_statsbomb_match(payload)
    row = df[df["statsbombEventId"].eq("pass-1")].iloc[0]

    assert row["y"] == 59.5
    assert row["endY"] == 8.5


def test_statsbomb_starting_xi_positions_drive_formation_slots():
    payload = statsbomb_payload()
    payload["events"][1]["tactics"] = {
        "formation": 433,
        "lineup": [
            {"player": {"id": 10, "name": "Away LW"}, "position": {"id": 21, "name": "Left Wing"}},
            {"player": {"id": 11, "name": "Away RW"}, "position": {"id": 17, "name": "Right Wing"}},
            {"player": {"id": 12, "name": "Away GK"}, "position": {"id": 1, "name": "Goalkeeper"}},
        ],
    }

    df = normalize_statsbomb_match(payload)
    lineups = build_lineups(df, ["Tottenham Hotspur", "Liverpool"])
    players = {player["player_id"]: player for player in lineups["teams"]["Liverpool"]["starters"]}

    assert lineups["teams"]["Tottenham Hotspur"]["formation"] == "4-2-3-1"
    assert players[11]["position"] == "RW"
    assert players[10]["position"] == "LW"
    assert players[11]["y"] < players[10]["y"]


def test_statsbomb_lineups_file_fills_lineups_when_starting_xi_events_missing():
    payload = statsbomb_payload()
    payload["events"] = [event for event in payload["events"] if event["type"]["name"] != "Starting XI"]
    payload["lineups"] = [
        {
            "team_id": 38,
            "team_name": "Tottenham Hotspur",
            "lineup": [
                {
                    "player_id": 1,
                    "player_name": "Home GK",
                    "positions": [{"position": "Goalkeeper", "from": "00:00", "start_reason": "Starting XI"}],
                },
                {
                    "player_id": 2,
                    "player_name": "Home RB",
                    "positions": [{"position": "Right Back", "from": "00:00", "start_reason": "Starting XI"}],
                },
            ],
        },
        {
            "team_id": 24,
            "team_name": "Liverpool",
            "lineup": [
                {
                    "player_id": 10,
                    "player_name": "Away LW",
                    "positions": [{"position": "Left Wing", "from": "00:00", "start_reason": "Starting XI"}],
                },
                {
                    "player_id": 11,
                    "player_name": "Away RW",
                    "positions": [{"position": "Right Wing", "from": "00:00", "start_reason": "Starting XI"}],
                },
            ],
        },
    ]

    df = normalize_statsbomb_match(payload)
    lineups = build_lineups(df, ["Tottenham Hotspur", "Liverpool"])
    players = {player["player_id"]: player for player in lineups["teams"]["Liverpool"]["starters"]}

    assert lineups["teams"]["Liverpool"]["formation"] == "Lineups"
    assert players[10]["player"] == "Away LW"
    assert players[10]["position"] == "LW"
    assert players[11]["player"] == "Away RW"
    assert players[11]["position"] == "RW"


def test_statsbomb_import_endpoint_feeds_analysis_and_pass_network():
    import_response = client.post("/api/import-jobs/statsbomb", json=statsbomb_payload())
    assert import_response.status_code == 200
    job = import_response.json()
    assert job["status"] == "completed"
    assert job["provider"] == "statsbomb"
    assert job["context"]["home_team"] == "Tottenham Hotspur"
    assert job["context"]["away_team"] == "Liverpool"
    assert job["context"]["score"] == "0-2"

    analysis = client.get(f"/api/analysis/22912?source=import&job_id={job['job_id']}")
    assert analysis.status_code == 200
    payload = analysis.json()
    assert payload["summary_cards"]["shots"] == 1
    assert payload["summary_cards"]["goals"] == 1
    assert payload["summary_cards"]["xg_total"] == 0.31

    network = build_pass_network(normalize_statsbomb_match(statsbomb_payload()), team="Liverpool")
    assert len(network["nodes"]) == 2
    assert len(network["edges"]) >= 1


def test_statsbomb_import_accepts_raw_events_array():
    import_response = client.post("/api/import-jobs/statsbomb", json=statsbomb_payload()["events"])

    assert import_response.status_code == 200
    job = import_response.json()
    assert job["status"] == "completed"
    assert job["provider"] == "statsbomb"
    assert job["context"]["match_id"] != "unknown"


def test_statsbomb_sample_catalogue_lists_configured_open_data_matches():
    response = client.get("/api/import-jobs/statsbomb/samples")

    assert response.status_code == 200
    samples = response.json()["samples"]
    assert len(samples) == 10
    assert samples[0]["id"] == "euro-2024-final"
    assert {"match_id", "competition", "season", "home_team", "away_team", "score"}.issubset(samples[0])


def test_statsbomb_sample_import_endpoint_uses_configured_payload(monkeypatch):
    from app import main as main_module

    def fake_fetch(sample_id: str):
        assert sample_id == "euro-2024-final"
        return statsbomb_payload()

    monkeypatch.setattr(main_module, "fetch_statsbomb_open_data_sample", fake_fetch)

    response = client.post("/api/import-jobs/statsbomb/samples/euro-2024-final")

    assert response.status_code == 200
    job = response.json()
    assert job["status"] == "completed"
    assert job["message"] == "StatsBomb Open Data sample imported"
    assert job["context"]["home_team"] == "Tottenham Hotspur"
