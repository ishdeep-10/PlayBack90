from __future__ import annotations

import json
import os
import re
from datetime import datetime
from functools import lru_cache
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
        client_kwargs={"endpoint_url": settings.r2_endpoint_url},
        listings_expiry_time=120,
    )


def get_storage_options() -> dict[str, object]:
    from app.config import settings

    return {
        "key": settings.r2_access_key,
        "secret": settings.r2_secret_key,
        "client_kwargs": {"endpoint_url": settings.r2_endpoint_url},
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
