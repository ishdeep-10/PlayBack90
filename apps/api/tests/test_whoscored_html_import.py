import json

import pandas as pd
from fastapi.testclient import TestClient

import app.main as api_main
from app.main import app
from app.services.providers.whoscored_html import (
    WhoScoredHtmlImportError,
    parse_whoscored_match_html,
)


client = TestClient(app)


def saved_match_html() -> str:
    match_centre_data = {
        "events": [{"id": 1, "minute": 1}],
        "home": {"teamId": 13, "name": "Arsenal"},
        "away": {"teamId": 26, "name": "Liverpool"},
        "score": "2 : 1",
    }
    return f"""
    <!doctype html>
    <html>
      <body>
        <div id="breadcrumb-nav">
          <span>England</span>
          <a>Premier League - 2025/2026</a>
        </div>
        <script>
          require.config.params["args"] = {{
            matchId: 1234567,
            matchCentreData: {json.dumps(match_centre_data)},
            matchCentreEventTypeJson: {{"Pass": 1}},
            playerIdNameDictionary: {{"10": "Example Player"}},
            formationIdNameMappings: {{"1": "4-3-3"}}
          }};
        </script>
      </body>
    </html>
    """


def test_parse_saved_whoscored_html_extracts_payload_and_breadcrumbs():
    payload = parse_whoscored_match_html(saved_match_html())

    assert payload["matchId"] == 1234567
    assert payload["events"][0]["id"] == 1
    assert payload["matchCentreEventTypeJson"] == {"Pass": 1}
    assert payload["playerIdNameDictionary"] == {"10": "Example Player"}
    assert payload["region"] == "England"
    assert payload["league"] == "Premier League"
    assert payload["season"] == "2025/2026"


def test_parse_saved_whoscored_html_rejects_cloudflare_page():
    blocked = "<html><title>Attention Required! | Cloudflare</title><p>Sorry, you have been blocked</p></html>"

    try:
        parse_whoscored_match_html(blocked)
    except WhoScoredHtmlImportError as exc:
        assert "Cloudflare block page" in str(exc)
    else:
        raise AssertionError("Expected a Cloudflare block page to be rejected")


def test_parse_saved_whoscored_html_explains_incomplete_save():
    try:
        parse_whoscored_match_html("<html><body>No match script</body></html>")
    except WhoScoredHtmlImportError as exc:
        assert "No WhoScored match payload" in str(exc)
    else:
        raise AssertionError("Expected an incomplete page to be rejected")


def test_whoscored_html_import_endpoint_creates_transient_analysis_job(monkeypatch):
    normalized = pd.DataFrame(
        [
            {
                "matchId": "1234567",
                "h_a": "h",
                "teamName": "Arsenal",
                "score": "2 : 1",
                "league": "Premier League",
                "season": "2025/2026",
            },
            {
                "matchId": "1234567",
                "h_a": "a",
                "teamName": "Liverpool",
                "score": "2 : 1",
                "league": "Premier League",
                "season": "2025/2026",
            },
        ]
    )
    monkeypatch.setattr(api_main, "normalize_whoscored_html", lambda html: normalized)

    response = client.post(
        "/api/import-jobs/whoscored-html",
        content=saved_match_html(),
        headers={"Content-Type": "text/html; charset=utf-8"},
    )

    assert response.status_code == 200
    job = response.json()
    assert job["status"] == "completed"
    assert job["provider"] == "whoscored"
    assert job["source"] == "import"
    assert job["match_id"] == "1234567"
    assert job["context"]["home_team"] == "Arsenal"
    assert job["context"]["away_team"] == "Liverpool"


def test_whoscored_html_import_endpoint_returns_parser_error(monkeypatch):
    def fail(_: str):
        raise WhoScoredHtmlImportError("Save the Match Centre page after the timeline loads.")

    monkeypatch.setattr(api_main, "normalize_whoscored_html", fail)
    response = client.post(
        "/api/import-jobs/whoscored-html",
        content="<html></html>",
        headers={"Content-Type": "text/html"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert "timeline loads" in response.json()["error"]
