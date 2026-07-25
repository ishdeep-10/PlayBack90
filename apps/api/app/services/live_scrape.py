from __future__ import annotations

import re
import sys
from pathlib import Path

from app.services.live_jobs import job_store

# WhoScored URL slug -> our league key. Country prefixes disambiguate lookalike
# tournament names (e.g. russia-premier-league must not match).
_URL_LEAGUE_TOKENS: list[tuple[str, str]] = [
    ("england-premier-league", "premier-league"),
    ("spain-laliga", "laliga"),
    ("spain-la-liga", "laliga"),
    ("italy-serie-a", "serie-a"),
    ("germany-bundesliga", "bundesliga"),
    ("france-ligue-1", "ligue-1"),
    ("champions-league", "champions-league"),
    ("fifa-world-cup", "fifa-world-cup"),
]


def league_season_from_url(url: str) -> tuple[str | None, str | None]:
    """Parse league + season from a WhoScored match URL slug, e.g.
    .../live/england-premier-league-2025-2026-crystal-palace-arsenal."""
    slug = str(url).lower()
    league = next((key for token, key in _URL_LEAGUE_TOKENS if token in slug), None)
    years = re.search(r"(20\d{2})-(20\d{2})", slug)
    if years:
        season = f"{years.group(1)}/{years.group(2)}"
    else:
        single = re.search(r"(20\d{2})", slug)
        season = single.group(1) if single else None
    return league, season


def _ensure_streamlit_root_on_path() -> None:
    streamlit_root = Path(__file__).resolve().parents[4]
    root_text = str(streamlit_root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)


def run_live_scrape(job_id: str, url: str) -> None:
    job_store.update_job(job_id, status="running", message="Scraping match data")
    try:
        _ensure_streamlit_root_on_path()
        from Data.extract_opta_data import extract_single_match_data

        df = extract_single_match_data(url, raise_errors=True)
        if df is None or df.empty:
            job_store.update_job(
                job_id,
                status="failed",
                error="No match data was returned from the scrape worker.",
            )
            return

        # Tag league/season from the URL slug so season-context baselines can
        # resolve the right season files for imported matches.
        league, season = league_season_from_url(url)
        if league and season:
            df["league"] = league
            df["season"] = season

        match_id = str(df["matchId"].iloc[0]) if "matchId" in df.columns else None
        job_store.update_job(
            job_id,
            status="completed",
            message="Scrape completed",
            match_id=match_id,
            data=df,
        )
    except Exception as exc:
        job_store.update_job(
            job_id,
            status="failed",
            error=str(exc),
        )
