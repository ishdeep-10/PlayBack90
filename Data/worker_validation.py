"""Quality gates for stateless remote match ingestion."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re

import pandas as pd

from team_names import team_names_match


class MatchValidationError(ValueError):
    """Raised when a scraped match is unsafe to publish."""


@dataclass(frozen=True)
class MatchValidationReport:
    match_id: str
    event_rows: int
    team_ids: tuple[str, str]
    periods: tuple[str, ...]
    home_team: str | None
    away_team: str | None
    metric_coverage: dict[str, int]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _identifier(value: object) -> str:
    text = str(value).strip()
    try:
        number = float(text)
        return str(int(number)) if number.is_integer() else text
    except (TypeError, ValueError):
        return text


_names_match = team_names_match


def _single_team_name(frame: pd.DataFrame, side: str) -> str | None:
    if "teamName" not in frame.columns:
        return None
    values = frame.loc[
        frame["h_a"].astype(str).str.lower() == side, "teamName"
    ].dropna().astype(str)
    values = values[values.str.strip().ne("") & values.str.lower().ne("nan")]
    return values.iloc[0] if not values.empty else None


def validate_processed_match(
    frame: pd.DataFrame,
    *,
    expected_match_id: str | None = None,
    expected_home: str | None = None,
    expected_away: str | None = None,
    minimum_event_rows: int = 50,
    required_metrics: tuple[str, ...] = ("xT", "epv_added", "xA", "xPass", "xG", "xGOT"),
) -> MatchValidationReport:
    """Validate identity and minimum full-match coverage before R2 publication."""

    if frame is None or frame.empty:
        raise MatchValidationError("The scraper returned no processed events.")
    required = {"matchId", "teamId", "h_a", "startDate", "period", "type", "league", "season"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise MatchValidationError(f"Processed events are missing required columns: {', '.join(missing)}")
    if len(frame.index) < minimum_event_rows:
        raise MatchValidationError(
            f"Processed event coverage is too small ({len(frame.index)} rows; expected at least {minimum_event_rows})."
        )
    missing_metrics = [metric for metric in required_metrics if metric not in frame.columns]
    if missing_metrics:
        raise MatchValidationError(
            f"Processed events are missing enrichment columns: {', '.join(missing_metrics)}"
        )
    metric_coverage = {
        metric: int(pd.to_numeric(frame[metric], errors="coerce").notna().sum())
        for metric in required_metrics
    }
    empty_metrics = [metric for metric, count in metric_coverage.items() if count == 0]
    if empty_metrics:
        raise MatchValidationError(
            f"Processed enrichment columns contain no usable values: {', '.join(empty_metrics)}"
        )

    match_ids = tuple(dict.fromkeys(_identifier(value) for value in frame["matchId"].dropna()))
    if len(match_ids) != 1 or not match_ids[0]:
        raise MatchValidationError("Processed events do not resolve to exactly one match ID.")
    match_id = match_ids[0]
    if expected_match_id and match_id != _identifier(expected_match_id):
        raise MatchValidationError(
            f"Scraped match ID {match_id} does not match expected match ID {_identifier(expected_match_id)}."
        )

    side_values = set(frame["h_a"].dropna().astype(str).str.lower())
    if not {"h", "a"}.issubset(side_values):
        raise MatchValidationError("Processed events do not contain both home and away sides.")
    team_ids = tuple(dict.fromkeys(_identifier(value) for value in frame["teamId"].dropna()))
    if len(team_ids) != 2:
        raise MatchValidationError(f"Expected exactly two teams, found {len(team_ids)}.")

    periods = tuple(dict.fromkeys(frame["period"].dropna().astype(str)))
    normalized_periods = {re.sub(r"[^a-z0-9]", "", period.lower()) for period in periods}
    if not ({"firsthalf", "1"} & normalized_periods) or not ({"secondhalf", "2"} & normalized_periods):
        raise MatchValidationError("Processed events do not contain both regulation halves.")
    if pd.to_datetime(frame["startDate"], errors="coerce").dropna().empty:
        raise MatchValidationError("Processed events do not contain a valid match date.")

    home_team = _single_team_name(frame, "h")
    away_team = _single_team_name(frame, "a")
    if expected_home and (not home_team or not _names_match(expected_home, home_team)):
        raise MatchValidationError(
            f"Scraped home team {home_team or 'Unknown'} does not match expected home team {expected_home}."
        )
    if expected_away and (not away_team or not _names_match(expected_away, away_team)):
        raise MatchValidationError(
            f"Scraped away team {away_team or 'Unknown'} does not match expected away team {expected_away}."
        )

    return MatchValidationReport(
        match_id=match_id,
        event_rows=len(frame.index),
        team_ids=(team_ids[0], team_ids[1]),
        periods=periods,
        home_team=home_team,
        away_team=away_team,
        metric_coverage=metric_coverage,
    )
