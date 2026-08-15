"""Best-effort Discord notifications for remote match ingestion results."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import sys
import time
from typing import Any

import requests


WEBHOOK_ENV_VAR = "PLAYBACK90_DISCORD_WEBHOOK_URL"
SUCCESS_STATUSES = {"uploaded", "already_exists"}


def _short(value: object, limit: int) -> str:
    text = str(value or "")
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def _payload(
    *,
    fixture_id: str,
    league: str,
    season: str,
    home_team: str,
    away_team: str,
    status: str,
    attempt: int,
    r2_key: str | None,
    retry_at: str | None,
    error: str | None,
    occurred_at: datetime,
) -> dict[str, Any]:
    successful = status in SUCCESS_STATUSES
    if status == "uploaded":
        title = "Match ingested successfully"
        color = 0x2ECC71
    elif status == "already_exists":
        title = "Match already present in R2"
        color = 0x3498DB
    elif status == "needs_attention":
        title = "Match ingestion needs attention"
        color = 0xE74C3C
    else:
        title = "Match ingestion attempt failed"
        color = 0xF39C12

    fields = [
        {"name": "Match", "value": _short(f"{home_team} vs {away_team}", 1024), "inline": False},
        {"name": "League / season", "value": _short(f"{league} · {season}", 1024), "inline": True},
        {"name": "Fixture", "value": _short(fixture_id, 1024), "inline": True},
        {"name": "Attempt", "value": str(attempt), "inline": True},
    ]
    if successful and r2_key:
        fields.append({"name": "R2 object", "value": _short(r2_key, 1024), "inline": False})
    if not successful and retry_at:
        fields.append({"name": "Next retry (UTC)", "value": _short(retry_at, 1024), "inline": False})
    if not successful and error:
        fields.append({"name": "Error", "value": _short(error, 1000), "inline": False})

    return {
        "username": "PlayBack90 Ingestion",
        "allowed_mentions": {"parse": []},
        "embeds": [
            {
                "title": title,
                "color": color,
                "fields": fields,
                "footer": {"text": f"Status: {status}"},
                "timestamp": occurred_at.astimezone(timezone.utc).isoformat(),
            }
        ],
    }


def notify_ingestion_result(
    *,
    fixture_id: str,
    league: str,
    season: str,
    home_team: str,
    away_team: str,
    status: str,
    attempt: int,
    r2_key: str | None = None,
    retry_at: str | None = None,
    error: str | None = None,
    occurred_at: datetime | None = None,
    webhook_url: str | None = None,
    session: Any = requests,
    timeout_seconds: float = 10.0,
    sleeper: Any = time.sleep,
) -> bool:
    """Send one result notification, without allowing Discord to affect ingestion."""

    target = webhook_url if webhook_url is not None else os.getenv(WEBHOOK_ENV_VAR, "")
    if not target.strip():
        return False

    payload = _payload(
        fixture_id=fixture_id,
        league=league,
        season=season,
        home_team=home_team,
        away_team=away_team,
        status=status,
        attempt=attempt,
        r2_key=r2_key,
        retry_at=retry_at,
        error=error,
        occurred_at=occurred_at or datetime.now(timezone.utc),
    )
    try:
        response = session.post(target, json=payload, timeout=timeout_seconds)
        if getattr(response, "status_code", None) == 429:
            try:
                retry_after = float(response.json().get("retry_after", 1.0))
            except (AttributeError, TypeError, ValueError):
                retry_after = 1.0
            sleeper(min(max(retry_after, 0.0), 10.0))
            response = session.post(target, json=payload, timeout=timeout_seconds)
        response.raise_for_status()
    except Exception as exc:
        # Never include the exception text: requests may embed the secret webhook URL.
        print(
            json.dumps(
                {
                    "event": "discord_notification_failed",
                    "fixture_id": fixture_id,
                    "error_type": type(exc).__name__,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
            flush=True,
        )
        return False
    return True
