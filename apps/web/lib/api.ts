export const PUBLIC_API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api";
const INTERNAL_API_BASE = process.env.API_BASE_URL ?? PUBLIC_API_BASE;
export type AnalysisSource = "r2" | "live" | "import";

type AuthTokenGetter = () => Promise<string | null>;

let browserAuthTokenGetter: AuthTokenGetter | null = null;

export function setAuthTokenGetter(getter: AuthTokenGetter | null) {
  browserAuthTokenGetter = getter;
}

function getRequestApiBase() {
  return typeof window === "undefined" ? INTERNAL_API_BASE : PUBLIC_API_BASE;
}

type RequestOptions = RequestInit & { next?: { revalidate?: number } };

async function getAuthToken(): Promise<string | null> {
  if (typeof window === "undefined") return null;
  return browserAuthTokenGetter ? browserAuthTokenGetter() : null;
}

/** For components that fetch directly instead of going through `request()` (e.g. streaming or plain img-batch lookups). */
export async function getAuthHeaders(): Promise<Record<string, string>> {
  const token = await getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(path: string, init?: RequestOptions & { authToken?: string | null }): Promise<T> {
  const { authToken, ...fetchInit } = init ?? {};
  const token = authToken ?? await getAuthToken();
  let response: Response;
  try {
    response = await fetch(`${getRequestApiBase()}${path}`, {
      ...fetchInit,
      cache: fetchInit.cache ?? "no-store",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(fetchInit.headers ?? {})
      }
    });
  } catch {
    throw new Error("Could not reach the PlayBack90 API. Check that the backend is running and try again.");
  }

  if (!response.ok) {
    const message = await response.text();
    try {
      const payload = JSON.parse(message) as { detail?: unknown; error?: unknown; message?: unknown };
      const detail = payload.detail ?? payload.error ?? payload.message;
      if (Array.isArray(detail)) {
        const readable = detail
          .map((item) => {
            if (typeof item === "string") return item;
            if (item && typeof item === "object" && "msg" in item) return String(item.msg);
            return "";
          })
          .filter(Boolean)
          .join(" ");
        if (readable) throw new Error(readable);
      }
      if (typeof detail === "string" && detail.trim()) {
        throw new Error(detail);
      }
    } catch (err) {
      if (err instanceof Error && err.message !== message) {
        throw err;
      }
    }
    throw new Error(message || `Request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export type League = { key: string; name: string };
export type Fixture = {
  match_id: string;
  start_date: string;
  start_date_label: string;
  home_team: string;
  away_team: string;
  score: string;
  fixture_id?: string | null;
  state?: FixtureState | null;
  source?: "r2" | "football-data" | null;
  round?: string | null;
  matchday?: number | null;
  post_match_href?: string | null;
  opposition_href?: string | null;
  provider_fixture_id?: number | null;
  provider_status?: string | null;
  home_crest?: string | null;
  away_crest?: string | null;
};

export type FixtureState = "completed" | "upcoming" | "postponed" | "cancelled" | "live" | "unknown";

export type FixtureHubFixture = {
  fixture_id: string;
  match_id: string;
  state: FixtureState;
  source: "r2" | "football-data";
  league: string;
  season: string;
  round?: string | null;
  matchday?: number | null;
  start_date: string;
  start_date_label: string;
  home_team: string;
  away_team: string;
  score: string;
  post_match_href?: string | null;
  opposition_href?: string | null;
  provider_fixture_id?: number | null;
  provider_status?: string | null;
  provider_home_team?: string | null;
  provider_away_team?: string | null;
  home_crest?: string | null;
  away_crest?: string | null;
};

export type FixtureRound = {
  id: string;
  label: string;
  stage: string | null;
  order: number;
  start_date: string;
  end_date: string;
  match_count: number;
  metadata_source: "manifest" | "inferred";
};

export type FixtureHubResponse = {
  league: string;
  season: string;
  state: "all" | FixtureState;
  round_id?: string | null;
  selected_round_id?: string | null;
  source: "r2" | "football-data" | "hybrid";
  updated_at?: string | null;
  is_stale: boolean;
  warning?: string | null;
  counts: Record<"all" | FixtureState, number>;
  rounds: FixtureRound[];
  fixtures: FixtureHubFixture[];
};

export async function getLeagues(authToken?: string | null) {
  return request<League[]>("/leagues", { cache: "force-cache", next: { revalidate: 3_600 }, authToken });
}

export async function getSeasons(league: string, authToken?: string | null) {
  return request<{ league: string; seasons: string[] }>(`/leagues/${league}/seasons`, {
    cache: "force-cache",
    next: { revalidate: 300 },
    authToken,
  });
}

export async function getFixtures(league: string, season: string, offset = 0, limit = 10, authToken?: string | null) {
  return request<{ league: string; season: string; fixtures: Fixture[]; offset: number; limit: number }>(
    `/leagues/${league}/seasons/${season}/fixtures?offset=${offset}&limit=${limit}`,
    { cache: "no-store", authToken },
  );
}

export async function getFixtureRounds(league: string, season: string, authToken?: string | null) {
  return request<{ league: string; season: string; latest_round_id: string | null; rounds: FixtureRound[] }>(
    `/leagues/${encodeURIComponent(league)}/seasons/${encodeURIComponent(season)}/rounds`,
    { cache: "force-cache", next: { revalidate: 300 }, authToken },
  );
}

export async function getFixtureRound(league: string, season: string, roundId: string, authToken?: string | null) {
  return request<{ league: string; season: string; round: FixtureRound; fixtures: Fixture[] }>(
    `/leagues/${encodeURIComponent(league)}/seasons/${encodeURIComponent(season)}/rounds/${encodeURIComponent(roundId)}`,
    { cache: "force-cache", next: { revalidate: 300 }, authToken },
  );
}

export async function getFixtureHub(
  league: string,
  season: string,
  options: { state?: "all" | FixtureState; round?: string } = {},
  authToken?: string | null,
) {
  const params = new URLSearchParams();
  if (options.state) params.set("state", options.state);
  if (options.round) params.set("round", options.round);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return request<FixtureHubResponse>(
    `/leagues/${encodeURIComponent(league)}/seasons/${encodeURIComponent(season)}/fixture-hub${suffix}`,
    { cache: "force-cache", next: { revalidate: 300 }, authToken },
  );
}

export async function getAnalysis(matchId: string, league: string, season: string, authToken?: string | null) {
  return request<{
    context: {
      match_id: string;
      home_team: string;
      away_team: string;
      league?: string | null;
      season?: string | null;
      score?: string;
      source: AnalysisSource;
      start_date_label?: string | null;
      available_views: string[];
      team_colors?: Record<string, string>;
    };
    summary_cards: Record<string, string | number>;
    team_summaries: Array<{
      team: string;
      goals: number;
      shots: number;
      xg: number;
      completed_passes?: number | null;
      pass_accuracy?: number | null;
    }>;
    available_filters: Record<string, string[]>;
  }>(`/analysis/${matchId}?source=r2&league=${encodeURIComponent(league)}&season=${encodeURIComponent(season)}`, { authToken });
}

export async function getTransientAnalysis(matchId: string, source: Exclude<AnalysisSource, "r2">, jobId: string, authToken?: string | null) {
  return request<{
    context: {
      match_id: string;
      home_team: string;
      away_team: string;
      league?: string | null;
      season?: string | null;
      score?: string;
      source: AnalysisSource;
      start_date_label?: string | null;
      available_views: string[];
      team_colors?: Record<string, string>;
    };
    summary_cards: Record<string, string | number>;
    team_summaries: Array<{
      team: string;
      goals: number;
      shots: number;
      xg: number;
      completed_passes?: number | null;
      pass_accuracy?: number | null;
    }>;
    available_filters: Record<string, string[]>;
  }>(`/analysis/${matchId}?source=${encodeURIComponent(source)}&job_id=${encodeURIComponent(jobId)}`, { authToken });
}

export async function getLiveAnalysis(matchId: string, jobId: string, authToken?: string | null) {
  return getTransientAnalysis(matchId, "live", jobId, authToken);
}

export async function getAnalysisView(viewId: string, body: Record<string, unknown>, authToken?: string | null) {
  return request<{
    view_id: string;
    kind: "table" | "chart" | "asset" | "message";
    payload: Record<string, unknown>;
  }>(`/analysis/views/${viewId}`, {
    method: "POST",
    body: JSON.stringify(body),
    authToken
  });
}

export async function createLiveScrapeJob(url: string) {
  return request<{ job_id: string; status: string; message?: string }>(`/live-scrape-jobs`, {
    method: "POST",
    body: JSON.stringify({ url })
  });
}

export async function getLiveScrapeJob(jobId: string) {
  return request<{
    job_id: string;
    status: string;
    message?: string;
    error?: string;
    context?: { match_id: string; home_team: string; away_team: string; available_views: string[] };
  }>(`/live-scrape-jobs/${jobId}`);
}

export async function createWyscoutImportJob(payload: unknown) {
  return request<{
    job_id: string;
    provider: "wyscout";
    source: "import";
    status: string;
    message?: string;
    match_id?: string | null;
    context?: { match_id: string; home_team: string; away_team: string; available_views: string[] };
    error?: string;
  }>(`/import-jobs/wyscout`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function createStatsBombImportJob(payload: unknown) {
  return request<{
    job_id: string;
    provider: "statsbomb";
    source: "import";
    status: string;
    message?: string;
    match_id?: string | null;
    context?: { match_id: string; home_team: string; away_team: string; available_views: string[] };
    error?: string;
  }>(`/import-jobs/statsbomb`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export type StatsBombSampleMatch = {
  id: string;
  match_id: number;
  competition_id: number;
  season_id: number;
  competition: string;
  season: string;
  country: string;
  match_date: string;
  home_team: string;
  away_team: string;
  score: string;
  stage: string;
};

export async function getStatsBombSampleMatches() {
  return request<{ samples: StatsBombSampleMatch[] }>(`/import-jobs/statsbomb/samples`);
}

export async function createStatsBombSampleImportJob(sampleId: string) {
  return request<{
    job_id: string;
    provider: "statsbomb";
    source: "import";
    status: string;
    message?: string;
    match_id?: string | null;
    context?: { match_id: string; home_team: string; away_team: string; available_views: string[] };
    error?: string;
  }>(`/import-jobs/statsbomb/samples/${encodeURIComponent(sampleId)}`, {
    method: "POST",
    body: JSON.stringify({})
  });
}

export async function getImportJob(jobId: string) {
  return request<{
    job_id: string;
    provider: "wyscout" | "statsbomb";
    source: "import";
    status: string;
    message?: string;
    match_id?: string | null;
    context?: { match_id: string; home_team: string; away_team: string; available_views: string[] };
    error?: string;
  }>(`/import-jobs/${jobId}`);
}

// Season stats endpoints
export type StandingRow = {
  rank: number;
  team: string;
  provider_team_name: string | null;
  provider_team_id: number | null;
  team_short_name: string | null;
  team_code: string | null;
  crest: string | null;
  played: number;
  won: number;
  drawn: number;
  lost: number;
  gf: number;
  ga: number;
  gd: number;
  pts: number;
  form: string | null;
  xg: number | null;
  xga: number | null;
  xgd: number | null;
};

export type StandingsResponse = {
  league: string;
  season: string;
  source: "football-data" | "calculated";
  updated_at: string;
  is_official: boolean;
  is_stale: boolean;
  is_complete: boolean;
  warning: string | null;
  rows: StandingRow[];
};

export async function getLeagueTable(league: string, season: string, authToken?: string | null) {
  return request<StandingsResponse>(
    `/leagues/${encodeURIComponent(league)}/seasons/${encodeURIComponent(season)}/standings`,
    { cache: "force-cache", next: { revalidate: 300 }, authToken },
  );
}

export async function getTeamForm(league: string, season: string, team: string, window = 5, authToken?: string | null) {
  return request<{
    team: string;
    window: number;
    matches: Array<{ date: string; opponent: string; result: string; goals_for: number; goals_against: number; xg_for: number; xg_against: number }>;
  }>(`/leagues/${league}/seasons/${season}/team-form/${encodeURIComponent(team)}?window=${window}`, { authToken });
}

export async function getPlayerLeaderboard(league: string, season: string, sortBy = "xg", minMins = 0, authToken?: string | null) {
  return request<{ rows: Record<string, string | number>[] }>(
    `/leagues/${league}/seasons/${season}/player-leaderboard?sort_by=${sortBy}&min_mins=${minMins}`,
    { authToken }
  );
}

// Opposition analysis
export async function getOppositionReport(league: string, season: string, team: string, authToken?: string | null) {
  return request<{
    team: string;
    strengths: Array<{ metric: string; percentile: number; value: number }>;
    weaknesses: Array<{ metric: string; percentile: number; value: number }>;
    top_players: Array<{ player: string; goals: number; xg: number; xa?: number; mins?: number }>;
    recent_results?: Array<{ date: string; opponent: string; result: string; goals_for: number; goals_against: number; score?: string }>;
    h2h?: Array<{ date: string; opponent: string; result: string; goals_for: number; goals_against: number; score?: string }>;
  }>(`/leagues/${league}/seasons/${season}/opposition/${encodeURIComponent(team)}/report`, { authToken });
}

export type OppositionMetricRow = {
  metric: string;
  label: string;
  category: "style" | "chance_profile" | "defensive_vulnerability" | string;
  value: number;
  league_average: number;
  percentile: number;
  higher_is_better: boolean;
  evaluative?: boolean;
};

export type OppositionSampleMatch = {
  match_id: string;
  date: string;
  season: string;
  team: string;
  opponent: string;
  home_away: string;
  result: "W" | "D" | "L" | string;
  score: string;
  xg: number;
  xga: number;
  shots: number;
  shots_against: number;
  possession_pct?: number;
  ppda?: number;
  sample_reason: "similar_opponent" | "recent_fallback" | string;
};

export type OppositionDossier = {
  meta: {
    league: string;
    fixture_season: string;
    analysis_seasons: string[];
    opponent_team: string;
    reference_team: string;
    generated_at: string;
    persona: string;
  };
  fixtureContext: {
    fixture_id?: string | null;
    home_team?: string | null;
    away_team?: string | null;
    reference_team: string;
    opponent_team: string;
  };
  sampleContext: {
    requested_sample_size: number;
    actual_sample_size: number;
    sample_strategy: string;
    pool_strategy: "current_season" | "previous_season" | "current_plus_previous" | string;
    pool_seasons: string[];
    features_used: string[];
    warnings: string[];
    sample_matches: OppositionSampleMatch[];
    similar_teams: Array<{ team: string; similarity: number; distance: number; matches: number }>;
  };
  referenceProfile: {
    team: string;
    available: boolean;
    metrics: Record<string, number>;
    similar_teams: Array<{ team: string; similarity: number; distance: number; matches: number }>;
  };
  teamContext?: {
    available: boolean;
    source: string;
    warning?: string | null;
    teams: Record<string, {
      team: string;
      provider_team?: string | null;
      crest?: string | null;
      coach?: {
        season?: string;
        name?: string | null;
        nationality?: string | null;
        contract_start?: string | null;
        contract_until?: string | null;
        available?: boolean;
      };
      previous_coach?: {
        season?: string;
        name?: string | null;
        available?: boolean;
      } | null;
      coach_change?: {
        status: string;
        label: string;
        reason?: string;
      };
      transfer_activity?: {
        available: boolean;
        source: string;
        warning?: string;
        team_id?: number | null;
        window_start?: string;
        window_end?: string;
        incoming_count: number;
        outgoing_count: number;
        incomings: Array<{
          player_id?: number | string | null;
          player: string;
          date?: string;
          type?: string | null;
          from_team?: string | null;
          from_team_id?: number | string | null;
          from_team_logo?: string | null;
          to_team?: string | null;
          to_team_id?: number | string | null;
          to_team_logo?: string | null;
          image?: string | null;
          source?: string;
        }>;
        outgoings: Array<{
          player_id?: number | string | null;
          player: string;
          date?: string;
          type?: string | null;
          from_team?: string | null;
          from_team_id?: number | string | null;
          from_team_logo?: string | null;
          to_team?: string | null;
          to_team_id?: number | string | null;
          to_team_logo?: string | null;
          image?: string | null;
          source?: string;
        }>;
        note?: string;
      };
      squad_changes?: {
        current_squad_count: number;
        previous_squad_count: number;
        current_squad?: Array<{ id?: number | string | null; name: string; position?: string | null; nationality?: string | null }>;
        previous_squad?: Array<{ id?: number | string | null; name: string; position?: string | null; nationality?: string | null }>;
        new_players: Array<{ id?: number | string | null; name: string; position?: string | null; nationality?: string | null }>;
        missing_players: Array<{ id?: number | string | null; name: string; position?: string | null; nationality?: string | null }>;
        note?: string;
      };
    }>;
  };
  lineupContext?: {
    available: boolean;
    source: string;
    warning?: string | null;
    team?: string;
    sample_match_count?: number;
    formation_usage?: Array<{ formation: string; count: number; pct: number }>;
    latest_match?: {
      match_id: string;
      date: string;
      opponent: string;
      home_away: string;
      formation: string;
      starters: Array<{ player_id?: number | string | null; player: string; position?: string; jersey?: number | string | null; x?: number | null; y?: number | null; last_seen?: string; started?: boolean }>;
      bench: Array<{ player_id?: number | string | null; player: string; position?: string; jersey?: number | string | null; x?: number | null; y?: number | null; last_seen?: string; started?: boolean }>;
    } | null;
    matches?: Array<{
      match_id: string;
      date: string;
      opponent: string;
      home_away: string;
      formation: string;
      starters: Array<{ player_id?: number | string | null; player: string; position?: string; jersey?: number | string | null; x?: number | null; y?: number | null; last_seen?: string; started?: boolean }>;
      bench: Array<{ player_id?: number | string | null; player: string; position?: string; jersey?: number | string | null; x?: number | null; y?: number | null; last_seen?: string; started?: boolean }>;
    }>;
    player_usage?: Array<{
      player: string;
      primary_position?: string;
      starts: number;
      bench: number;
      appearances: number;
      last_seen: string;
    }>;
    availability_signals?: {
      recently_used_not_current_squad?: Array<{ player: string; primary_position?: string; starts?: number; appearances?: number; last_seen?: string }>;
      current_squad_not_recently_used?: Array<{ id?: number | string | null; name: string; position?: string | null; nationality?: string | null }>;
      note?: string;
    };
    warnings?: string[];
  };
  summary: {
    bullets: string[];
    confidence: "directional" | "moderate" | string;
  };
  teamProfile: {
    team: string;
    metrics: OppositionMetricRow[];
    match_count: number;
  };
  inPossessionProfile?: {
    available: boolean;
    team: string;
    sample_match_count: number;
    identity: Array<{ metric: string; label: string; value: number; unit: string }>;
    possession_identity?: {
      available: boolean;
      label: string;
      quadrants: Array<{
        key: string;
        label: string;
        score: number;
        metrics: Array<{ label: string; value: number | null; unit: string }>;
      }>;
    };
    progression: Array<{ metric: string; label: string; value: number; unit: string }>;
    chance_creation: Array<{ metric: string; label: string; value: number; unit: string }>;
    player_roles: Record<string, Array<{
      player: string;
      goals: number;
      xg: number;
      xa: number;
      shots: number;
      key_passes: number;
      progressive_passes: number;
      progressive_carries: number;
      crosses: number;
      mins: number;
    }>>;
    set_pieces: {
      available: boolean;
      note?: string;
    };
    event_pitch_profile?: {
      available: boolean;
      covered_matches: number;
      requested_matches: number;
      max_matches: number;
      progressive_actions: Array<{
        match_id: string;
        date: string;
        kind: string;
        type: string;
        player: string;
        game_state?: string;
        game_state_label?: string;
        situation?: string;
        situation_label?: string;
        x: number | null;
        y: number | null;
        end_x: number | null;
        end_y: number | null;
        value?: number;
      }>;
	      box_entries: Array<{
	        match_id: string;
	        date: string;
        kind: string;
        type: string;
        player: string;
        game_state?: string;
        game_state_label?: string;
        situation?: string;
        situation_label?: string;
        x: number | null;
        y: number | null;
        end_x: number | null;
	        end_y: number | null;
	        value?: number;
	      }>;
	      build_up_actions: Array<{
	        match_id: string;
	        date: string;
	        kind: string;
	        type: string;
	        player: string;
	        game_state?: string;
	        game_state_label?: string;
	        situation?: string;
	        situation_label?: string;
	        x: number | null;
	        y: number | null;
	        end_x: number | null;
	        end_y: number | null;
	        value?: number;
	      }>;
	      direct_actions: Array<{
	        match_id: string;
	        date: string;
	        kind: string;
	        type: string;
	        player: string;
	        game_state?: string;
	        game_state_label?: string;
	        situation?: string;
	        situation_label?: string;
	        x: number | null;
	        y: number | null;
	        end_x: number | null;
	        end_y: number | null;
	        value?: number;
	      }>;
	      shots: Array<{
        match_id: string;
        date: string;
        kind: string;
        type: string;
        player: string;
        game_state?: string;
        game_state_label?: string;
        situation?: string;
        situation_label?: string;
        x: number | null;
        y: number | null;
        end_x: number | null;
        end_y: number | null;
        value?: number;
        outcome?: string;
      }>;
      chance_sources: Array<{
        match_id: string;
        date: string;
        kind: string;
        type: string;
        player: string;
        game_state?: string;
        game_state_label?: string;
        situation?: string;
        situation_label?: string;
        x: number | null;
        y: number | null;
        end_x: number | null;
        end_y: number | null;
        value?: number;
      }>;
      channels?: Record<string, Array<{ channel: string; count: number; pct: number }>>;
    };
  };
  homeAwaySplit?: {
    available: boolean;
    rows: Array<{
      venue: "h" | "a" | string;
      label: string;
      match_count: number;
      record: { wins: number; draws: number; losses: number };
      metrics: Record<string, number>;
    }>;
    metrics: string[];
    note?: string;
  };
  gameStateProfile?: {
    available: boolean;
    rows: Array<{
      state: "leading" | "level" | "trailing" | string;
      label: string;
      match_count: number;
      shots: number;
      shots_against: number;
      xG: number;
      xGA: number;
      xG_per_match: number;
      xGA_per_match: number;
    }>;
    covered_matches: number;
    requested_matches: number;
    warning?: string | null;
  };
  recentForm: {
    window: number;
    matches: Array<{
      match_id: string;
      date: string;
      season: string;
      opponent: string;
      home_away: string;
      result: "W" | "D" | "L" | string;
      score: string;
      xg: number;
      xga: number;
    }>;
    averages: Record<string, number>;
    record: { wins: number; draws: number; losses: number };
  };
  strengths: OppositionMetricRow[];
  weaknesses: OppositionMetricRow[];
  keyPlayers: Array<{ player: string; goals: number; xg: number; xa: number; shots: number; mins: number }>;
};

export async function getOppositionDossier(
  league: string,
  season: string,
  opponentTeam: string,
  params: {
    referenceTeam: string;
    fixtureId?: string | null;
    home?: string | null;
    away?: string | null;
    sampleSize?: number;
  },
  authToken?: string | null,
) {
  const query = new URLSearchParams({
    referenceTeam: params.referenceTeam,
    sampleSize: String(params.sampleSize ?? 5),
  });
  if (params.fixtureId) query.set("fixtureId", params.fixtureId);
  if (params.home) query.set("home", params.home);
  if (params.away) query.set("away", params.away);

  return request<OppositionDossier>(
    `/leagues/${encodeURIComponent(league)}/seasons/${encodeURIComponent(season)}/opposition/${encodeURIComponent(opponentTeam)}/dossier?${query.toString()}`,
    { authToken },
  );
}

function _buildAssetUrl(
  matchId: string,
  assetId: string,
  source: string,
  sourcePart: Record<string, string>,
  team?: string,
  situation?: string,
  player?: string,
  half?: string,
  duelType?: string,
  transitionType?: string,
  extra?: Record<string, string>
) {
  const url = new URL(`${PUBLIC_API_BASE}/analysis/${matchId}/assets/${assetId}.png`);
  url.searchParams.set("source", source);
  for (const [k, v] of Object.entries(sourcePart)) url.searchParams.set(k, v);
  if (team) url.searchParams.set("team", team);
  if (situation && situation !== "All") url.searchParams.set("situation", situation);
  if (player) url.searchParams.set("player", player);
  if (half && half !== "Full 90") url.searchParams.set("half", half);
  if (duelType) url.searchParams.set("duel_type", duelType);
  if (transitionType) url.searchParams.set("transition_type", transitionType);
  if (extra) for (const [k, v] of Object.entries(extra)) url.searchParams.set(k, v);
  return url.toString();
}

export function getAssetUrl(
  matchId: string,
  assetId: string,
  league: string,
  season: string,
  team?: string,
  situation?: string,
  player?: string,
  half?: string,
  duelType?: string,
  transitionType?: string,
  extra?: Record<string, string>
) {
  return _buildAssetUrl(matchId, assetId, "r2", { league, season }, team, situation, player, half, duelType, transitionType, extra);
}

export function getLiveAssetUrl(
  matchId: string,
  assetId: string,
  jobId: string,
  team?: string,
  situation?: string,
  player?: string,
  half?: string,
  duelType?: string,
  transitionType?: string,
  extra?: Record<string, string>
) {
  return _buildAssetUrl(matchId, assetId, "live", { job_id: jobId }, team, situation, player, half, duelType, transitionType, extra);
}

export function getImportAssetUrl(
  matchId: string,
  assetId: string,
  jobId: string,
  team?: string,
  situation?: string,
  player?: string,
  half?: string,
  duelType?: string,
  transitionType?: string,
  extra?: Record<string, string>
) {
  return _buildAssetUrl(matchId, assetId, "import", { job_id: jobId }, team, situation, player, half, duelType, transitionType, extra);
}

export function getSeasonAssetUrl(league: string, season: string, assetId: string, params?: Record<string, string>) {
  const url = new URL(`${PUBLIC_API_BASE}/leagues/${encodeURIComponent(league)}/seasons/${encodeURIComponent(season)}/season-assets/${assetId}.png`);
  if (params) for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v);
  return url.toString();
}

export function getOppositionAssetUrl(league: string, season: string, team: string, assetId: string) {
  return `${PUBLIC_API_BASE}/leagues/${encodeURIComponent(league)}/seasons/${encodeURIComponent(season)}/opposition/${encodeURIComponent(team)}/assets/${assetId}.png`;
}

export function getReportUrl(matchId: string, league: string, season: string) {
  const url = new URL(`${PUBLIC_API_BASE}/analysis/${matchId}/report.pdf`);
  url.searchParams.set("source", "r2");
  url.searchParams.set("league", league);
  url.searchParams.set("season", season);
  return url.toString();
}

export function getLiveReportUrl(matchId: string, jobId: string) {
  const url = new URL(`${PUBLIC_API_BASE}/analysis/${matchId}/report.pdf`);
  url.searchParams.set("source", "live");
  url.searchParams.set("job_id", jobId);
  return url.toString();
}

export function getImportReportUrl(matchId: string, jobId: string) {
  const url = new URL(`${PUBLIC_API_BASE}/analysis/${matchId}/report.pdf`);
  url.searchParams.set("source", "import");
  url.searchParams.set("job_id", jobId);
  return url.toString();
}
