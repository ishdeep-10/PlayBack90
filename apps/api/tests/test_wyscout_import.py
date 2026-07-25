from fastapi.testclient import TestClient

from app.main import app
from app.services.providers.wyscout import normalize_wyscout_match
from app.services.views.pass_network import build_pass_network


client = TestClient(app)


def wyscout_payload():
    return {
        "match": {
            "wyId": 5758824,
            "label": "Al Khaleej - Al Nassr, 0 - 1",
            "dateutc": "2026-03-14 19:00:00",
            "teamsData": {
                "16480": {"teamId": 16480, "side": "home", "score": 0},
                "16470": {"teamId": 16470, "side": "away", "score": 1},
            },
        },
        "teams": {
            "16480": {"team": {"wyId": 16480, "name": "Al Khaleej"}},
            "16470": {"team": {"wyId": 16470, "name": "Al Nassr"}},
        },
        "players": {
            "16480": [{"player": {"wyId": 1, "shortName": "Home Player"}}],
            "16470": [{"player": {"wyId": 2, "shortName": "Away Player"}}],
        },
        "formations": {},
        "substitutions": {},
        "events": [
            {
                "id": 10,
                "matchId": 5758824,
                "matchPeriod": "1H",
                "minute": 1,
                "second": 5,
                "type": {"primary": "pass", "secondary": ["progressive_pass"]},
                "location": {"x": 40, "y": 50},
                "team": {"id": 16480, "name": "Al Khaleej", "formation": "4-4-2"},
                "player": {"id": 1, "name": "Home Player", "position": "CMF"},
                "pass": {
                    "accurate": True,
                    "recipient": {"id": 1, "name": "Home Player", "position": "CMF"},
                    "endLocation": {"x": 70, "y": 55},
                },
                "shot": None,
                "groundDuel": None,
                "aerialDuel": None,
                "infraction": None,
                "carry": None,
                "possession": {"id": 100, "types": ["attack"]},
            },
            {
                "id": 11,
                "matchId": 5758824,
                "matchPeriod": "1H",
                "minute": 2,
                "second": 10,
                "type": {"primary": "shot", "secondary": ["goal", "opportunity"]},
                "location": {"x": 90, "y": 50},
                "team": {"id": 16470, "name": "Al Nassr", "formation": "4-2-3-1"},
                "player": {"id": 2, "name": "Away Player", "position": "CF"},
                "pass": None,
                "shot": {"isGoal": True, "onTarget": True, "xg": 0.42, "postShotXg": 0.66},
                "groundDuel": None,
                "aerialDuel": None,
                "infraction": None,
                "carry": None,
                "possession": {"id": 101, "types": ["attack"], "attack": {"withGoal": True}},
            },
            {
                "id": 12,
                "matchId": 5758824,
                "matchPeriod": "1H",
                "minute": 3,
                "second": 1,
                "type": {"primary": "pass", "secondary": []},
                "location": {"x": 42, "y": 48},
                "team": {"id": 16480, "name": "Al Khaleej", "formation": "4-4-2"},
                "player": {"id": 1, "name": "Home Player", "position": "CMF"},
                "pass": {
                    "accurate": True,
                    "recipient": {"id": 3, "name": "Home Teammate", "position": "AMF"},
                    "endLocation": {"x": 50, "y": 45},
                },
                "shot": None,
                "groundDuel": None,
                "aerialDuel": None,
                "infraction": None,
                "carry": None,
                "possession": {"id": 102, "types": ["attack"]},
            },
            {
                "id": 13,
                "matchId": 5758824,
                "matchPeriod": "1H",
                "minute": 3,
                "second": 8,
                "type": {"primary": "pass", "secondary": []},
                "location": {"x": 50, "y": 45},
                "team": {"id": 16480, "name": "Al Khaleej", "formation": "4-4-2"},
                "player": {"id": 3, "name": "Home Teammate", "position": "AMF"},
                "pass": {
                    "accurate": True,
                    "recipient": {"id": 1, "name": "Home Player", "position": "CMF"},
                    "endLocation": {"x": 44, "y": 50},
                },
                "shot": None,
                "groundDuel": None,
                "aerialDuel": None,
                "infraction": None,
                "carry": None,
                "possession": {"id": 102, "types": ["attack"]},
            },
        ],
    }


def test_normalize_wyscout_match_uses_provider_shot_values():
    df = normalize_wyscout_match(wyscout_payload())

    assert set(["matchId", "eventId", "teamName", "type", "x", "y", "xG", "xGOT"]).issubset(df.columns)
    shot = df[df["isShot"]].iloc[0]
    assert shot["type"] == "Goal"
    assert shot["xG"] == 0.42
    assert shot["xGOT"] == 0.66
    assert shot["x"] == 94.5
    assert shot["y"] == 34.0


def test_wyscout_import_endpoint_feeds_analysis():
    import_response = client.post("/api/import-jobs/wyscout", json=wyscout_payload())
    assert import_response.status_code == 200
    job = import_response.json()
    assert job["status"] == "completed"
    assert job["source"] == "import"
    assert job["context"]["home_team"] == "Al Khaleej"
    assert job["context"]["away_team"] == "Al Nassr"
    assert job["context"]["score"] == "0-1"

    analysis = client.get(f"/api/analysis/5758824?source=import&job_id={job['job_id']}")
    assert analysis.status_code == 200
    payload = analysis.json()
    assert payload["summary_cards"]["shots"] == 1
    assert payload["summary_cards"]["goals"] == 1
    assert payload["summary_cards"]["xg_total"] == 0.42

    baseline = client.post(
        "/api/analysis/views/season-baseline",
        json={"match_id": "5758824", "source": "import", "filters": {"job_id": job["job_id"]}},
    )
    assert baseline.status_code == 200
    assert baseline.json()["kind"] == "message"


def test_wyscout_pass_network_uses_real_pass_participants():
    df = normalize_wyscout_match(wyscout_payload())
    network = build_pass_network(df, team="Al Khaleej")

    assert len(network["nodes"]) == 2
    assert len(network["edges"]) >= 1
    assert {node["player_id"] for node in network["nodes"]} == {1, 3}
