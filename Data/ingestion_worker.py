"""Scrape, validate, enrich, and publish one match directly to Cloudflare R2.

This worker intentionally does not open the historical analytics SQLite database.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import re
import sys
from typing import Any, Callable

import pandas as pd

from r2_match_store import R2MatchStore, build_event_object_key, match_id_text
from worker_validation import MatchValidationReport, validate_processed_match
from league_sources import LEAGUE_SOURCES


def match_id_from_url(url: str) -> str | None:
    match = re.search(r"/matches/(\d+)(?:/|$)", str(url), flags=re.IGNORECASE)
    return match.group(1) if match else None


@dataclass(frozen=True)
class WorkerResult:
    status: str
    league: str
    season: str
    match_id: str
    key: str
    validation: MatchValidationReport | None
    bytes: int | None = None
    sha256: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        if self.validation is not None:
            payload["validation"] = self.validation.to_dict()
        return payload


def _canonicalize_metadata(frame: pd.DataFrame, league: str, season: str) -> pd.DataFrame:
    canonical = frame.copy()
    canonical["league"] = league
    canonical["season"] = season
    return canonical


def run_match_worker(
    *,
    url: str,
    league: str,
    season: str,
    expected_home: str | None = None,
    expected_away: str | None = None,
    key_prefix: str | None = None,
    dry_run: bool = False,
    scraper: Callable[..., pd.DataFrame | None] | None = None,
    store: R2MatchStore | Any | None = None,
) -> WorkerResult:
    url_match_id = match_id_from_url(url)
    if not url_match_id:
        raise ValueError("The match URL does not contain a numeric /Matches/{id}/ segment.")

    if not dry_run:
        store = store or R2MatchStore.from_env(key_prefix=key_prefix)
        existing_key = store.find_match_key(league, season, url_match_id)
        if existing_key:
            return WorkerResult(
                status="already_exists",
                league=league,
                season=season,
                match_id=url_match_id,
                key=existing_key,
                validation=None,
            )

    if scraper is None:
        from extract_opta_data import extract_single_match_data

        scraper = extract_single_match_data
    source = LEAGUE_SOURCES.get(league)
    frame = scraper(
        url,
        raise_errors=True,
        league=league,
        country=source.country if source else None,
        season=season,
    )
    if frame is None:
        raise RuntimeError("The scraper returned no match dataframe.")
    frame = _canonicalize_metadata(frame, league, season)
    report = validate_processed_match(
        frame,
        expected_match_id=url_match_id,
        expected_home=expected_home,
        expected_away=expected_away,
    )
    match_id = match_id_text(report.match_id)
    key = build_event_object_key(
        frame, league, season, match_id, key_prefix=key_prefix
    )
    if dry_run:
        return WorkerResult(
            status="dry_run",
            league=league,
            season=season,
            match_id=match_id,
            key=key,
            validation=report,
        )

    upload = store.upload_match(
        frame, league=league, season=season, match_id=match_id
    )
    return WorkerResult(
        status=upload.status,
        league=league,
        season=season,
        match_id=match_id,
        key=upload.key,
        validation=report,
        bytes=upload.bytes,
        sha256=upload.sha256,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="WhoScored match-centre URL")
    parser.add_argument("--league", required=True, help="Canonical league key, e.g. mls")
    parser.add_argument("--season", required=True, help="Canonical season key, e.g. 2026")
    parser.add_argument("--expected-home", help="Optional scheduled home-team validation")
    parser.add_argument("--expected-away", help="Optional scheduled away-team validation")
    parser.add_argument(
        "--key-prefix",
        default="",
        help="Optional R2 namespace such as ingestion-test; empty publishes to event_data/",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scrape, enrich, validate, and print the target key without writing R2",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    try:
        result = run_match_worker(
            url=args.url,
            league=args.league,
            season=args.season,
            expected_home=args.expected_home,
            expected_away=args.expected_away,
            key_prefix=args.key_prefix,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        raise SystemExit(1) from exc
    print(json.dumps(result.to_dict(), sort_keys=True))


if __name__ == "__main__":
    main()
