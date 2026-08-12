from __future__ import annotations

import json
import os
import re
from datetime import datetime
from functools import lru_cache
from time import monotonic
from typing import Any

import pandas as pd

from app.domain import TEAM_DICT


FIXTURE_FILENAME_PATTERN = re.compile(
    r"(\d{4}-\d{2}-\d{2})_(.+?)_(\d+)_vs_(\d+)_(.+)\.parquet"
)


@lru_cache(maxsize=1)
def make_fs():
    import s3fs
    from app.config import settings

    return s3fs.S3FileSystem(
        key=settings.r2_access_key,
        secret=settings.r2_secret_key,
        client_kwargs={"endpoint_url": settings.r2_endpoint_url, "region_name": "auto"},
        listings_expiry_time=120,
    )


def get_storage_options() -> dict[str, object]:
    from app.config import settings

    return {
        "key": settings.r2_access_key,
        "secret": settings.r2_secret_key,
        "client_kwargs": {"endpoint_url": settings.r2_endpoint_url, "region_name": "auto"},
        "use_listings_cache": False,
    }


def parse_fixture_filename(file_path: str) -> dict[str, object] | None:
    filename = os.path.basename(file_path)
    match = FIXTURE_FILENAME_PATTERN.match(filename)
    if not match:
        return None

    start_date_str, match_id, home_team_id, away_team_id, ft_score = match.groups()
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
    score = re.sub(r"_+", "-", ft_score)
    home_id = int(home_team_id)
    away_id = int(away_team_id)

    return {
        "file_path": file_path,
        "match_id": match_id,
        "start_date": start_date,
        "start_date_label": start_date_str,
        "home_team_id": home_id,
        "away_team_id": away_id,
        "home_team": TEAM_DICT.get(home_id, str(home_id)),
        "away_team": TEAM_DICT.get(away_id, str(away_id)),
        "score": score,
    }


def list_league_seasons(league: str) -> list[str]:
    from app.config import settings

    fs = make_fs()
    prefix = f"{settings.r2_bucket}/event_data/{league}/"
    try:
        season_dirs = fs.ls(prefix)
    except Exception:
        return []
    seasons = [path.rstrip("/").split("/")[-1] for path in season_dirs]
    return sorted(set(seasons), reverse=True)


def list_all_fixtures(league: str, season: str) -> list[dict[str, object]]:
    from app.config import settings

    fs = make_fs()
    prefix = f"{settings.r2_bucket}/event_data/{league}/{season}/"
    files = fs.glob(f"{prefix}*.parquet")
    fixtures = [parsed for file in files if (parsed := parse_fixture_filename(file))]
    fixtures.sort(key=lambda item: item["start_date"], reverse=True)
    return fixtures


_FILE_PATH_CACHE: dict[tuple[str, str, str], tuple[float, str | None]] = {}
_FILE_PATH_CACHE_TTL_SECONDS = 15 * 60
_FILE_PATH_CACHE_MAX_ITEMS = 256


def find_file_path(league: str, season: str, match_id: str) -> str | None:
    """Resolve a match's R2 object path server-side so clients only need league+season+match_id,
    never the internal storage path itself.

    A single analysis tab load fans out into several concurrent view requests (see
    AnalysisContent in the web app), each of which resolves the same league/season/match_id
    independently. Without this cache every one of those requests re-globs and re-parses the
    whole season's fixture list. TTL matches _MATCH_DF_CACHE in matches.py since a resolved
    file_path is exactly as stable as the dataframe it points to.
    """
    key = (league, season, str(match_id))
    now = monotonic()
    cached = _FILE_PATH_CACHE.get(key)
    if cached is not None and (now - cached[0]) < _FILE_PATH_CACHE_TTL_SECONDS:
        return cached[1]

    file_path: str | None = None
    for fixture in list_all_fixtures(league, season):
        if str(fixture.get("match_id")) == str(match_id):
            file_path = str(fixture["file_path"])
            break

    if len(_FILE_PATH_CACHE) >= _FILE_PATH_CACHE_MAX_ITEMS:
        oldest_key = min(_FILE_PATH_CACHE, key=lambda k: _FILE_PATH_CACHE[k][0])
        _FILE_PATH_CACHE.pop(oldest_key, None)
    _FILE_PATH_CACHE[key] = (now, file_path)
    return file_path


def list_fixtures(league: str, season: str, limit: int, offset: int) -> list[dict[str, object]]:
    fixtures = list_all_fixtures(league, season)
    return fixtures[offset : offset + limit]


def load_round_manifest(league: str, season: str) -> dict[str, Any] | None:
    """Load optional provider-maintained round metadata stored beside a season."""
    from app.config import settings

    fs = make_fs()
    path = f"{settings.r2_bucket}/event_data/{league}/{season}/rounds.json"
    try:
        if not fs.exists(path):
            return None
        with fs.open(path, "r") as handle:
            payload = json.load(handle)
    except (OSError, ValueError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def load_match_dataframe(file_path: str) -> pd.DataFrame:
    fs = make_fs()
    try:
        with fs.open(file_path, "rb") as handle:
            return pd.read_parquet(handle)
    except (FileNotFoundError, OSError):
        return pd.DataFrame()
