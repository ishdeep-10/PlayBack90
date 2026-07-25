from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import auth as auth_module
from app.main import app


client = TestClient(app)


def test_auth_disabled_allows_api(monkeypatch):
    monkeypatch.setattr(auth_module.settings, "auth_required", False)
    response = client.get("/api/leagues")
    assert response.status_code == 200


def test_auth_required_rejects_missing_bearer(monkeypatch):
    monkeypatch.setattr(auth_module.settings, "auth_required", True)
    monkeypatch.setattr(auth_module.settings, "clerk_jwks_url", "https://example.test/jwks.json")
    monkeypatch.setattr(auth_module.settings, "clerk_issuer", "https://example.test")
    response = client.get("/api/leagues")
    assert response.status_code == 401
    assert response.json()["detail"] == "Missing bearer token."


def test_auth_required_keeps_health_public(monkeypatch):
    monkeypatch.setattr(auth_module.settings, "auth_required", True)
    response = client.get("/health")
    assert response.status_code == 200


def test_allowed_email_check(monkeypatch):
    monkeypatch.setattr(auth_module.settings, "clerk_jwks_url", "https://example.test/jwks.json")
    monkeypatch.setattr(auth_module.settings, "clerk_issuer", "https://example.test")
    monkeypatch.setattr(auth_module.settings, "clerk_audience", None)
    monkeypatch.setattr(auth_module.settings, "auth_allowed_emails", "tester@example.com")
    monkeypatch.setattr(auth_module.settings, "auth_allowed_user_ids", None)

    class FakeJwksClient:
        def get_signing_key_from_jwt(self, token):
            return SimpleNamespace(key="key")

    monkeypatch.setattr(auth_module, "_jwks_client", lambda: FakeJwksClient())
    monkeypatch.setattr(auth_module.jwt, "decode", lambda *args, **kwargs: {"sub": "user_123", "email": "other@example.com"})

    request = SimpleNamespace(headers={"Authorization": "Bearer token"})
    with pytest.raises(HTTPException) as exc:
        auth_module.verify_clerk_request(request)
    assert exc.value.status_code == 403

    monkeypatch.setattr(auth_module.jwt, "decode", lambda *args, **kwargs: {"sub": "user_123", "email": "tester@example.com"})
    user = auth_module.verify_clerk_request(request)
    assert user.email == "tester@example.com"
