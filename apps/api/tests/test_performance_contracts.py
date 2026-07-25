from fastapi.testclient import TestClient

from app.main import app
from app.services.live_jobs import LiveScrapeJobStore
from app.services.views.player_analysis import _compact_action


def test_large_responses_are_gzipped() -> None:
    response = TestClient(app).get("/openapi.json", headers={"Accept-Encoding": "gzip"})

    assert response.status_code == 200
    assert response.headers["content-encoding"] == "gzip"


def test_player_actions_omit_optional_default_values() -> None:
    action = _compact_action(
        {
            "id": "1",
            "minute": 0,
            "second": 0,
            "team": "Alpha",
            "player": "Player One",
            "player_id": 0,
            "type": "Pass",
            "phase": "in_possession",
            "outcome": "Unsuccessful",
            "is_successful": False,
            "x": 0.0,
            "y": 0.0,
            "end_x": 0.0,
            "end_y": 0.0,
            "pass_cross": False,
            "xA": 0.0,
            "xPass": 0.72,
        }
    )

    assert action["is_successful"] is False
    assert action["x"] == 0.0
    assert action["xPass"] == 0.72
    assert "pass_cross" not in action
    assert "xA" not in action


def test_live_jobs_expire_in_memory() -> None:
    store = LiveScrapeJobStore(ttl_seconds=-1)
    job = store.create_job("https://example.com/match")

    assert store.get_job(job.job_id) is None
