from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from functools import lru_cache
from typing import Any

import requests


STATSBOMB_OPEN_DATA_RAW_BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"


@dataclass(frozen=True)
class StatsBombSampleMatch:
    id: str
    match_id: int
    competition_id: int
    season_id: int
    competition: str
    season: str
    country: str
    match_date: str
    home_team: str
    away_team: str
    score: str
    stage: str

    def to_public_dict(self) -> dict[str, Any]:
        return asdict(self)


STATSBOMB_SAMPLE_MATCHES: tuple[StatsBombSampleMatch, ...] = (
    StatsBombSampleMatch(
        id="euro-2024-final",
        match_id=3943043,
        competition_id=55,
        season_id=282,
        competition="UEFA Euro",
        season="2024",
        country="Europe",
        match_date="2024-07-14",
        home_team="Spain",
        away_team="England",
        score="2-1",
        stage="Final",
    ),
    StatsBombSampleMatch(
        id="copa-america-2024-final",
        match_id=3943077,
        competition_id=223,
        season_id=282,
        competition="Copa America",
        season="2024",
        country="South America",
        match_date="2024-07-15",
        home_team="Argentina",
        away_team="Colombia",
        score="1-0",
        stage="Final",
    ),
    StatsBombSampleMatch(
        id="afcon-2023-final",
        match_id=3923881,
        competition_id=1267,
        season_id=107,
        competition="African Cup of Nations",
        season="2023",
        country="Africa",
        match_date="2024-02-11",
        home_team="Nigeria",
        away_team="Cote d'Ivoire",
        score="1-2",
        stage="Final",
    ),
    StatsBombSampleMatch(
        id="bundesliga-2023-24-leverkusen-augsburg",
        match_id=3895348,
        competition_id=9,
        season_id=281,
        competition="1. Bundesliga",
        season="2023/2024",
        country="Germany",
        match_date="2024-05-18",
        home_team="Bayer Leverkusen",
        away_team="Augsburg",
        score="2-1",
        stage="Regular Season",
    ),
    StatsBombSampleMatch(
        id="ligue-1-2022-23-psg-clermont",
        match_id=3838017,
        competition_id=7,
        season_id=235,
        competition="Ligue 1",
        season="2022/2023",
        country="France",
        match_date="2023-06-03",
        home_team="Paris Saint-Germain",
        away_team="Clermont Foot",
        score="2-3",
        stage="Regular Season",
    ),
    StatsBombSampleMatch(
        id="mls-2023-lafc-inter-miami",
        match_id=3877090,
        competition_id=44,
        season_id=107,
        competition="Major League Soccer",
        season="2023",
        country="United States of America",
        match_date="2023-09-04",
        home_team="LAFC",
        away_team="Inter Miami",
        score="1-3",
        stage="Regular Season",
    ),
    StatsBombSampleMatch(
        id="womens-world-cup-2023-final",
        match_id=3906390,
        competition_id=72,
        season_id=107,
        competition="Women's World Cup",
        season="2023",
        country="International",
        match_date="2023-08-20",
        home_team="Spain Women's",
        away_team="England Women's",
        score="1-0",
        stage="Final",
    ),
    StatsBombSampleMatch(
        id="womens-euro-2025-final",
        match_id=4020846,
        competition_id=53,
        season_id=315,
        competition="UEFA Women's Euro",
        season="2025",
        country="Europe",
        match_date="2025-07-27",
        home_team="England Women's",
        away_team="Spain Women's",
        score="1-1",
        stage="Final",
    ),
    StatsBombSampleMatch(
        id="wsl-2023-24-man-united-chelsea",
        match_id=3913187,
        competition_id=37,
        season_id=281,
        competition="FA Women's Super League",
        season="2023/2024",
        country="England",
        match_date="2024-05-18",
        home_team="Manchester United W",
        away_team="Chelsea FCW",
        score="0-6",
        stage="Regular Season",
    ),
    StatsBombSampleMatch(
        id="liga-f-2023-24-valencia-barcelona",
        match_id=3911643,
        competition_id=182,
        season_id=281,
        competition="Liga F",
        season="2023/2024",
        country="Spain",
        match_date="2024-06-16",
        home_team="Valencia CF",
        away_team="Barcelona WFC",
        score="0-3",
        stage="Regular Season",
    ),
)

_SAMPLE_BY_ID = {sample.id: sample for sample in STATSBOMB_SAMPLE_MATCHES}
_HTTP_TIMEOUT_SECONDS = 20


class StatsBombSampleError(ValueError):
    """Raised when a configured StatsBomb Open Data sample cannot be loaded."""


def list_statsbomb_open_data_samples() -> list[dict[str, Any]]:
    return [sample.to_public_dict() for sample in STATSBOMB_SAMPLE_MATCHES]


def get_statsbomb_open_data_sample(sample_id: str) -> StatsBombSampleMatch:
    sample = _SAMPLE_BY_ID.get(sample_id)
    if not sample:
        raise StatsBombSampleError("StatsBomb sample match not found.")
    return sample


@lru_cache(maxsize=64)
def _fetch_json(path: str) -> Any:
    url = f"{STATSBOMB_OPEN_DATA_RAW_BASE}/{path}"
    try:
        response = requests.get(url, timeout=_HTTP_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise StatsBombSampleError("Unable to fetch StatsBomb Open Data sample.") from exc
    except ValueError as exc:
        raise StatsBombSampleError("StatsBomb Open Data sample returned invalid JSON.") from exc


def fetch_statsbomb_open_data_sample(sample_id: str) -> dict[str, Any]:
    sample = get_statsbomb_open_data_sample(sample_id)
    with ThreadPoolExecutor(max_workers=3) as executor:
        events_future = executor.submit(_fetch_json, f"events/{sample.match_id}.json")
        lineups_future = executor.submit(_fetch_json, f"lineups/{sample.match_id}.json")
        matches_future = executor.submit(_fetch_json, f"matches/{sample.competition_id}/{sample.season_id}.json")
        events = copy.deepcopy(events_future.result())
        lineups = copy.deepcopy(lineups_future.result())
        matches = matches_future.result()
    match = next(
        (item for item in matches if isinstance(item, dict) and item.get("match_id") == sample.match_id),
        None,
    )
    if not isinstance(match, dict):
        raise StatsBombSampleError("StatsBomb Open Data sample match metadata was not found.")
    return {"events": events, "lineups": lineups, "match": copy.deepcopy(match)}
