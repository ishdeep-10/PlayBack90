from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from jwt import PyJWKClient
from jwt.exceptions import InvalidTokenError, PyJWKClientError

from app.config import settings


@dataclass(frozen=True)
class AuthUser:
    user_id: str
    email: str | None
    claims: dict[str, Any]


PUBLIC_API_PATHS = {
    "/health",
    "/ready",
}

PUBLIC_API_PREFIXES = (
    "/docs",
    "/redoc",
    "/openapi.json",
)

PUBLIC_ASSET_PATH_MARKERS = (
    "/assets/",
    "/players/image-proxy",
)


def _split_csv(value: str | None) -> set[str]:
    if not value:
        return set()
    return {item.strip().lower() for item in value.split(",") if item.strip()}


@lru_cache(maxsize=1)
def _jwks_client() -> PyJWKClient:
    if not settings.clerk_jwks_url:
        raise RuntimeError("CLERK_JWKS_URL is not configured.")
    return PyJWKClient(settings.clerk_jwks_url)


def auth_enabled() -> bool:
    return bool(settings.auth_required)


def is_public_path(path: str, method: str = "GET") -> bool:
    if method.upper() == "OPTIONS":
        return True
    if path in PUBLIC_API_PATHS:
        return True
    if any(path.startswith(prefix) for prefix in PUBLIC_API_PREFIXES):
        return True
    if path.startswith(settings.api_prefix) and any(marker in path for marker in PUBLIC_ASSET_PATH_MARKERS):
        return True
    return False


def _extract_bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        return token.strip()
    return None


def _claim_email(claims: dict[str, Any]) -> str | None:
    for key in ("email", "primary_email", "primary_email_address", "user_email"):
        value = claims.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    return None


def verify_clerk_request(request: Request) -> AuthUser:
    if not settings.clerk_jwks_url or not settings.clerk_issuer:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is enabled but Clerk is not configured.",
        )

    token = _extract_bearer_token(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token.")

    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        decode_kwargs: dict[str, Any] = {
            "algorithms": ["RS256"],
            "issuer": settings.clerk_issuer,
        }
        if settings.clerk_audience:
            decode_kwargs["audience"] = settings.clerk_audience
        else:
            decode_kwargs["options"] = {"verify_aud": False}
        claims = jwt.decode(token, signing_key.key, **decode_kwargs)
    except (InvalidTokenError, PyJWKClientError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid auth token.") from exc

    user_id = str(claims.get("sub") or "").strip()
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid auth subject.")

    email = _claim_email(claims)
    allowed_emails = _split_csv(settings.auth_allowed_emails)
    allowed_user_ids = _split_csv(settings.auth_allowed_user_ids)

    if allowed_emails or allowed_user_ids:
        email_allowed = bool(email and email.lower() in allowed_emails)
        user_allowed = user_id.lower() in allowed_user_ids
        if not email_allowed and not user_allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not allowed for this beta.")

    return AuthUser(user_id=user_id, email=email, claims=claims)


async def require_auth_middleware(request: Request, call_next):
    if auth_enabled() and not is_public_path(request.url.path, request.method):
        try:
            request.state.auth_user = verify_clerk_request(request)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return await call_next(request)
