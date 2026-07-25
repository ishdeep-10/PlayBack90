from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class LeagueSummary(BaseModel):
    key: str
    name: str


class SeasonList(BaseModel):
    league: str
    seasons: list[str]


class StandingRow(BaseModel):
    rank: int
    team: str
    provider_team_name: str | None = None
    provider_team_id: int | None = None
    team_short_name: str | None = None
    team_code: str | None = None
    crest: str | None = None
    played: int
    won: int
    drawn: int
    lost: int
    gf: int
    ga: int
    gd: int
    pts: int
    form: str | None = None
    xg: float | None = None
    xga: float | None = None
    xgd: float | None = None


class StandingsResponse(BaseModel):
    league: str
    season: str
    source: Literal["football-data", "calculated"]
    updated_at: datetime
    is_official: bool
    is_stale: bool = False
    is_complete: bool
    warning: str | None = None
    rows: list[StandingRow]


class FixtureSummary(BaseModel):
    file_path: str
    match_id: str
    start_date: datetime
    start_date_label: str
    home_team_id: int
    away_team_id: int
    home_team: str
    away_team: str
    score: str


class FixtureListResponse(BaseModel):
    league: str
    season: str
    offset: int
    limit: int
    fixtures: list[FixtureSummary]


class FixtureRoundSummary(BaseModel):
    id: str
    label: str
    stage: str | None = None
    order: int
    start_date: date
    end_date: date
    match_count: int
    metadata_source: Literal["manifest", "inferred"]


class FixtureRoundListResponse(BaseModel):
    league: str
    season: str
    latest_round_id: str | None = None
    rounds: list[FixtureRoundSummary]


class FixtureRoundResponse(BaseModel):
    league: str
    season: str
    round: FixtureRoundSummary
    fixtures: list[FixtureSummary]


AnalysisSource = Literal["r2", "live", "import"]


class MatchContext(BaseModel):
    match_id: str
    league: str | None = None
    season: str | None = None
    home_team: str
    away_team: str
    score: str | None = None
    source: AnalysisSource
    file_path: str | None = None
    available_views: list[str]
    team_colors: dict[str, str] | None = None


class MatchByFileResponse(BaseModel):
    context: MatchContext
    event_count: int
    columns: list[str]
    preview_rows: list[dict[str, Any]]


class TeamSummary(BaseModel):
    team: str
    goals: int
    shots: int
    xg: float
    xgot: float = 0.0
    completed_passes: int | None = None
    pass_accuracy: float | None = None


class AnalysisResponse(BaseModel):
    context: MatchContext
    summary_cards: dict[str, Any]
    team_summaries: list[TeamSummary]
    available_filters: dict[str, list[str]]


class AnalysisViewFilters(BaseModel):
    """Validated filter set for analysis views; unknown keys are ignored."""

    model_config = ConfigDict(extra="ignore")

    team: str | None = None
    situation: str | None = None
    player: str | None = None
    players: list[str] | None = None
    subWindow: str | int | None = None
    third: str | None = None
    playerB: str | None = None
    gameState: str | None = None
    timeRange: str | None = None
    duelType: str | None = None
    transitionType: str | None = None
    job_id: str | None = None

    def get(self, key: str, default: Any = None) -> Any:
        value = getattr(self, key, None)
        return default if value is None else value


class AnalysisViewRequest(BaseModel):
    match_id: str
    file_path: str | None = None
    source: AnalysisSource = "r2"
    filters: AnalysisViewFilters = Field(default_factory=AnalysisViewFilters)


class AnalysisViewResponse(BaseModel):
    view_id: str
    context: MatchContext
    kind: Literal["table", "chart", "asset", "message"]
    payload: dict[str, Any]


class LiveScrapeJobCreate(BaseModel):
    url: HttpUrl


class LiveScrapeJobResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "completed", "failed"]
    source: Literal["live"] = "live"
    message: str | None = None
    match_id: str | None = None
    context: MatchContext | None = None
    error: str | None = None


class ImportJobResponse(BaseModel):
    job_id: str
    provider: Literal["wyscout", "statsbomb"]
    status: Literal["queued", "running", "completed", "failed"]
    source: Literal["import"] = "import"
    message: str | None = None
    match_id: str | None = None
    context: MatchContext | None = None
    error: str | None = None
