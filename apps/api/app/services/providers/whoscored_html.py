from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd
from bs4 import BeautifulSoup


class WhoScoredHtmlImportError(ValueError):
    """Raised when a saved WhoScored page cannot be imported."""


_CLOUDFLARE_MARKERS = (
    "attention required! | cloudflare",
    "sorry, you have been blocked",
    "cf-chl-",
    "cloudflare ray id",
)

_SUPPLEMENTAL_KEYS = (
    "matchId",
    "matchCentreEventTypeJson",
    "matchCentrePlayerTypeJson",
    "matchCentreTeamTypeJson",
    "playerIdNameDictionary",
    "formationIdNameMappings",
)


def _decode_script_value(script: str, key: str) -> Any | None:
    """Decode a JSON-compatible JS object property or assignment by name."""
    pattern = re.compile(
        rf"(?<![\w$])(?:[\"']{re.escape(key)}[\"']|{re.escape(key)})\s*[:=]\s*"
    )
    decoder = json.JSONDecoder()
    for match in pattern.finditer(script):
        try:
            value, _ = decoder.raw_decode(script, match.end())
            return value
        except json.JSONDecodeError:
            continue
    return None


def parse_whoscored_match_html(html: str) -> dict[str, Any]:
    if not html or not html.strip():
        raise WhoScoredHtmlImportError("The uploaded HTML file is empty.")

    lowered = html.lower()
    if any(marker in lowered for marker in _CLOUDFLARE_MARKERS):
        raise WhoScoredHtmlImportError(
            "This file contains a Cloudflare block page, not a WhoScored Match Centre page. "
            "Open the match successfully in your browser before saving it."
        )

    soup = BeautifulSoup(html, "lxml")
    match_data: dict[str, Any] | None = None
    matched_script = ""

    for script_node in soup.find_all("script"):
        script = script_node.string or script_node.get_text() or ""
        if "matchCentreData" not in script:
            continue
        candidate = _decode_script_value(script, "matchCentreData")
        if isinstance(candidate, dict):
            match_data = dict(candidate)
            matched_script = script
            break

    if match_data is None:
        raise WhoScoredHtmlImportError(
            "No WhoScored match payload was found. Save the Match Centre page after the event timeline has loaded."
        )

    for key in _SUPPLEMENTAL_KEYS:
        value = _decode_script_value(matched_script, key)
        if value is not None:
            match_data[key] = value

    events = match_data.get("events")
    if not isinstance(events, list) or not events:
        raise WhoScoredHtmlImportError(
            "The saved page does not contain match events. Wait for the event timeline to load, then save the page again."
        )
    if match_data.get("matchId") is None:
        raise WhoScoredHtmlImportError("The saved page does not contain a WhoScored match id.")
    if not isinstance(match_data.get("matchCentreEventTypeJson"), dict):
        raise WhoScoredHtmlImportError("The saved page is missing the WhoScored event type dictionary.")
    if not isinstance(match_data.get("playerIdNameDictionary"), dict):
        raise WhoScoredHtmlImportError("The saved page is missing the WhoScored player dictionary.")

    breadcrumb = soup.select_one("#breadcrumb-nav")
    if breadcrumb is not None:
        region_node = breadcrumb.select_one("span")
        competition_node = breadcrumb.select_one("a")
        if region_node and region_node.get_text(strip=True):
            match_data.setdefault("region", region_node.get_text(" ", strip=True))
        if competition_node:
            parts = [part.strip() for part in competition_node.get_text(" ", strip=True).split(" - ")]
            if parts and parts[0]:
                match_data.setdefault("league", parts[0])
            if len(parts) >= 2 and parts[1]:
                match_data.setdefault("season", parts[1])
            match_data.setdefault("competitionType", "Knock Out" if len(parts) >= 3 else "League")
            match_data.setdefault("competitionStage", parts[2] if len(parts) >= 3 else "")

    return match_data


def _load_normalization_functions():
    data_dir = Path(__file__).resolve().parents[5] / "Data"
    data_dir_text = str(data_dir)
    if data_dir_text not in sys.path:
        sys.path.insert(0, data_dir_text)

    from data_utils import data_preprocessing
    from main import createEventsDF

    return createEventsDF, data_preprocessing


def normalize_whoscored_html(html: str) -> pd.DataFrame:
    match_data = parse_whoscored_match_html(html)
    create_events_df, data_preprocessing = _load_normalization_functions()

    try:
        events_df = create_events_df(match_data)
        if events_df is None or events_df.empty:
            raise WhoScoredHtmlImportError("The WhoScored page did not contain usable event rows.")
        processed_df = data_preprocessing(events_df)
    except WhoScoredHtmlImportError:
        raise
    except Exception as exc:
        raise WhoScoredHtmlImportError(
            "The WhoScored payload was found, but its match data could not be processed."
        ) from exc

    processed_df["league"] = match_data.get("league", "Unknown")
    processed_df["country"] = match_data.get("region", "Unknown")
    processed_df["season"] = match_data.get("season", "Unknown")

    try:
        team_names = {
            match_data["home"]["teamId"]: match_data["home"]["name"],
            match_data["away"]["teamId"]: match_data["away"]["name"],
        }
        processed_df["teamName"] = processed_df["teamId"].map(team_names)
    except (KeyError, TypeError):
        pass

    for column in processed_df.columns:
        if processed_df[column].map(type).eq(list).any():
            processed_df[column] = processed_df[column].apply(json.dumps)

    return processed_df
