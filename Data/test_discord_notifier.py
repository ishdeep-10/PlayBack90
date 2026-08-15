from datetime import datetime, timezone

from discord_notifier import notify_ingestion_result


UTC = timezone.utc


class FakeResponse:
    status_code = 204

    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, *, json, timeout):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        return FakeResponse()


class FailingSession:
    def post(self, url, *, json, timeout):
        raise RuntimeError(f"failed to reach {url}")


class RateLimitedResponse(FakeResponse):
    status_code = 429

    def json(self):
        return {"retry_after": 0.25}


class RateLimitedSession(FakeSession):
    def post(self, url, *, json, timeout):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        return RateLimitedResponse() if len(self.calls) == 1 else FakeResponse()


def test_success_notification_contains_match_and_r2_key():
    session = FakeSession()

    sent = notify_ingestion_result(
        fixture_id="match-1",
        league="laliga",
        season="2026/2027",
        home_team="Alaves",
        away_team="Getafe",
        status="uploaded",
        attempt=1,
        r2_key="event_data/laliga/2026_2027/match-1.parquet",
        occurred_at=datetime(2026, 8, 15, 20, 35, tzinfo=UTC),
        webhook_url="https://discord.example/webhook",
        session=session,
    )

    assert sent is True
    embed = session.calls[0]["json"]["embeds"][0]
    assert embed["title"] == "Match ingested successfully"
    assert any(field["name"] == "R2 object" for field in embed["fields"])
    assert session.calls[0]["json"]["allowed_mentions"] == {"parse": []}


def test_failure_notification_contains_retry_and_error():
    session = FakeSession()

    sent = notify_ingestion_result(
        fixture_id="match-2",
        league="mls",
        season="2026",
        home_team="Austin FC",
        away_team="FC Dallas",
        status="retry_scheduled",
        attempt=2,
        retry_at="2026-08-16T04:00:00+00:00",
        error="provider_url_not_found: not published yet",
        webhook_url="https://discord.example/webhook",
        session=session,
    )

    assert sent is True
    fields = session.calls[0]["json"]["embeds"][0]["fields"]
    assert any(field["name"] == "Next retry (UTC)" for field in fields)
    assert any(field["name"] == "Error" for field in fields)


def test_missing_webhook_is_a_no_op(monkeypatch):
    monkeypatch.delenv("PLAYBACK90_DISCORD_WEBHOOK_URL", raising=False)
    session = FakeSession()

    sent = notify_ingestion_result(
        fixture_id="match-3",
        league="mls",
        season="2026",
        home_team="Home",
        away_team="Away",
        status="uploaded",
        attempt=1,
        session=session,
    )

    assert sent is False
    assert session.calls == []


def test_delivery_failure_does_not_raise_or_log_webhook_secret(capsys):
    webhook = "https://discord.example/webhook/super-secret-token"

    sent = notify_ingestion_result(
        fixture_id="match-4",
        league="mls",
        season="2026",
        home_team="Home",
        away_team="Away",
        status="retry_scheduled",
        attempt=1,
        webhook_url=webhook,
        session=FailingSession(),
    )

    assert sent is False
    captured = capsys.readouterr()
    assert "discord_notification_failed" in captured.err
    assert webhook not in captured.err
    assert "super-secret-token" not in captured.err


def test_rate_limit_waits_and_retries_once():
    session = RateLimitedSession()
    sleeps = []

    sent = notify_ingestion_result(
        fixture_id="match-5",
        league="mls",
        season="2026",
        home_team="Home",
        away_team="Away",
        status="uploaded",
        attempt=1,
        webhook_url="https://discord.example/webhook",
        session=session,
        sleeper=sleeps.append,
    )

    assert sent is True
    assert len(session.calls) == 2
    assert sleeps == [0.25]
