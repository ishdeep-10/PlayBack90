from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_healthcheck():
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True


def test_list_leagues():
    response = client.get("/api/leagues")
    assert response.status_code == 200
    leagues = response.json()
    assert any(item["key"] == "premier-league" for item in leagues)


def test_list_seasons_merges_provider_schedule_seasons(monkeypatch):
    from app.services import r2
    import app.main as main

    monkeypatch.setattr(r2, "list_league_seasons", lambda league: ["2025_2026"])
    monkeypatch.setattr(main, "provider_season_keys", lambda league: ["2026_2027"])

    response = client.get("/api/leagues/premier-league/seasons")

    assert response.status_code == 200
    assert response.json()["seasons"] == ["2026_2027", "2025_2026"]


def test_fixture_hub_endpoint_uses_schedule_service(monkeypatch):
    import app.main as main

    monkeypatch.setattr(
        main.schedule_service,
        "build_fixture_hub",
        lambda league, season, state="all", round_id=None: {
            "league": league,
            "season": season,
            "state": state,
            "round_id": round_id,
            "selected_round_id": "matchday-1",
            "source": "football-data",
            "updated_at": None,
            "is_stale": False,
            "warning": None,
            "counts": {
                "all": 1,
                "completed": 0,
                "upcoming": 1,
                "postponed": 0,
                "cancelled": 0,
                "live": 0,
                "unknown": 0,
            },
            "rounds": [
                {
                    "id": "matchday-1",
                    "label": "Matchday 1",
                    "stage": "Regular Season",
                    "order": 1,
                    "start_date": "2026-08-15",
                    "end_date": "2026-08-15",
                    "match_count": 1,
                    "metadata_source": "inferred",
                }
            ],
            "fixtures": [
                {
                    "fixture_id": "fd-1",
                    "match_id": "fd-1",
                    "state": "upcoming",
                    "source": "football-data",
                    "league": league,
                    "season": season,
                    "round": "matchday-1",
                    "matchday": 1,
                    "start_date": "2026-08-15T14:00:00Z",
                    "start_date_label": "2026-08-15",
                    "home_team": "Arsenal",
                    "away_team": "Chelsea",
                    "score": "",
                    "file_path": None,
                    "post_match_href": None,
                    "opposition_href": "/opposition-analysis?league=premier-league",
                }
            ],
        },
    )

    response = client.get("/api/leagues/premier-league/seasons/2026_2027/fixture-hub?state=upcoming")

    assert response.status_code == 200
    payload = response.json()
    assert payload["selected_round_id"] == "matchday-1"
    assert payload["counts"]["upcoming"] == 1
    assert payload["fixtures"][0]["state"] == "upcoming"


def test_readiness_reports_missing_deployment_config(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "r2_account_id", None)
    monkeypatch.setattr(settings, "r2_access_key", None)
    monkeypatch.setattr(settings, "r2_secret_key", None)
    monkeypatch.setattr(settings, "r2_bucket", None)
    monkeypatch.setattr(settings, "database_url", None)
    monkeypatch.setattr(settings, "redis_url", "")
    monkeypatch.setattr(settings, "auth_required", False)

    response = client.get("/ready")
    assert response.status_code == 503
    payload = response.json()
    assert payload["ok"] is False
    assert payload["checks"]["r2"] is False
    assert payload["checks"]["database"] is False
    assert payload["checks"]["redis"] is False
    assert payload["checks"]["auth"] is True


def test_readiness_passes_when_deployment_config_is_present(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "r2_account_id", "account")
    monkeypatch.setattr(settings, "r2_access_key", "access")
    monkeypatch.setattr(settings, "r2_secret_key", "secret")
    monkeypatch.setattr(settings, "r2_bucket", "bucket")
    monkeypatch.setattr(settings, "database_url", "postgresql://user:pass@localhost:5432/playback90")
    monkeypatch.setattr(settings, "redis_url", "redis://localhost:6379/0")
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(settings, "clerk_jwks_url", "https://example.clerk.accounts.dev/.well-known/jwks.json")
    monkeypatch.setattr(settings, "clerk_issuer", "https://example.clerk.accounts.dev")
    monkeypatch.setattr(settings, "auth_allowed_emails", "tester@example.com")
    monkeypatch.setattr(settings, "auth_allowed_user_ids", None)

    response = client.get("/ready")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert all(payload["checks"].values())
