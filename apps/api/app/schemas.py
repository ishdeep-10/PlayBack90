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
    match_id: str
    start_date: datetime
    start_date_label: str
    home_team_id: int | None = None
    away_team_id: int | None = None
    home_team: str
    away_team: str
    score: str
    fixture_id: str | None = None
    state: Literal["completed", "upcoming", "postponed", "cancelled", "live", "unknown"] | None = None
    source: Literal["r2", "football-data"] | None = None
    round: str | None = None
    matchday: int | None = None
    post_match_href: str | None = None
    opposition_href: str | None = None
    provider_fixture_id: int | None = None
    provider_status: str | None = None
    home_crest: str | None = None
    away_crest: str | None = None


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


class FixtureHubFixture(BaseModel):
    fixture_id: str
    match_id: str
    state: Literal["completed", "upcoming", "postponed", "cancelled", "live", "unknown"]
    source: Literal["r2", "football-data"]
    league: str
    season: str
    round: str | None = None
    matchday: int | None = None
    start_date: datetime
    start_date_label: str
    home_team: str
    away_team: str
    score: str = ""
    post_match_href: str | None = None
    opposition_href: str | None = None
    provider_fixture_id: int | None = None
    provider_status: str | None = None
    provider_home_team: str | None = None
    provider_away_team: str | None = None
    home_crest: str | None = None
    away_crest: str | None = None


class FixtureHubCounts(BaseModel):
    all: int
    completed: int
    upcoming: int
    postponed: int
    cancelled: int
    live: int
    unknown: int


class FixtureHubResponse(BaseModel):
    league: str
    season: str
    state: Literal["all", "completed", "upcoming", "postponed", "cancelled", "live", "unknown"]
    round_id: str | None = None
    selected_round_id: str | None = None
    source: Literal["r2", "football-data", "hybrid"]
    updated_at: datetime | None = None
    is_stale: bool = False
    warning: str | None = None
    counts: FixtureHubCounts
    rounds: list[FixtureRoundSummary]
    fixtures: list[FixtureHubFixture]


class OppositionSimilarTeam(BaseModel):
    team: str
    similarity: float
    distance: float
    matches: int


class OppositionSampleMatch(BaseModel):
    match_id: str
    date: str
    season: str
    team: str
    opponent: str
    home_away: str
    result: str
    score: str
    xg: float
    xga: float
    shots: int
    shots_against: int
    sample_reason: Literal["similar_opponent", "recent_fallback"]


class OppositionTeamMatchIndexItem(BaseModel):
    match_id: str
    date: str
    home_team: str
    away_team: str
    file_path: str
    score: str


class OppositionTeamMatchIndex(BaseModel):
    team: str
    matches: list[OppositionTeamMatchIndexItem]
    match_count: int


class OppositionFoundationResponse(BaseModel):
    league: str
    season: str
    reference_team: str
    opponent_team: str
    sample_size: int
    sample_strategy: Literal["similar_opponent_profile"]
    pool_strategy: Literal["current_season", "previous_season", "current_plus_previous"]
    pool_seasons: list[str]
    features_used: list[str]
    similar_teams: list[OppositionSimilarTeam]
    sample_matches: list[OppositionSampleMatch]
    warnings: list[str]
    team_match_index: OppositionTeamMatchIndex


class OppositionDossierResponse(BaseModel):
    meta: dict[str, Any]
    fixtureContext: dict[str, Any]
    sampleContext: dict[str, Any]
    referenceProfile: dict[str, Any]
    teamContext: dict[str, Any] | None = None
    lineupContext: dict[str, Any] | None = None
    summary: dict[str, Any]
    teamProfile: dict[str, Any]
    inPossessionProfile: dict[str, Any] | None = None
    recentForm: dict[str, Any]
    strengths: list[dict[str, Any]]
    weaknesses: list[dict[str, Any]]
    keyPlayers: list[dict[str, Any]]


AnalysisSource = Literal["r2", "live", "import"]


class MatchContext(BaseModel):
    match_id: str
    league: str | None = None
    season: str | None = None
    home_team: str
    away_team: str
    score: str | None = None
    source: AnalysisSource
    start_date_label: str | None = None
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
    league: str | None = None
    season: str | None = None
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
    provider: Literal["whoscored", "wyscout", "statsbomb"]
    status: Literal["queued", "running", "completed", "failed"]
    source: Literal["import"] = "import"
    message: str | None = None
    match_id: str | None = None
    context: MatchContext | None = None
    error: str | None = None
