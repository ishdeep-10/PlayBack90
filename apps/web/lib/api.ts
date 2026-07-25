const PUBLIC_API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api";
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
  file_path: string;
  match_id: string;
  start_date: string;
  start_date_label: string;
  home_team: string;
  away_team: string;
  score: string;
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
    { cache: "force-cache", next: { revalidate: 300 }, authToken },
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

export async function getAnalysis(matchId: string, filePath: string, authToken?: string | null) {
  return request<{
    context: {
      match_id: string;
      home_team: string;
      away_team: string;
      league?: string | null;
      season?: string | null;
      score?: string;
      source: AnalysisSource;
      file_path?: string;
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
  }>(`/analysis/${matchId}?source=r2&file_path=${encodeURIComponent(filePath)}`, { authToken });
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
      file_path?: string;
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
    top_players: Array<{ player: string; goals: number; xg: number; assists: number; mins?: number }>;
    h2h: Array<{ date: string; opponent: string; result: string; goals_for: number; goals_against: number; score?: string }>;
  }>(`/leagues/${league}/seasons/${season}/opposition/${encodeURIComponent(team)}/report`, { authToken });
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
  filePath: string,
  team?: string,
  situation?: string,
  player?: string,
  half?: string,
  duelType?: string,
  transitionType?: string,
  extra?: Record<string, string>
) {
  return _buildAssetUrl(matchId, assetId, "r2", { file_path: filePath }, team, situation, player, half, duelType, transitionType, extra);
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

export function getReportUrl(matchId: string, filePath: string) {
  const url = new URL(`${PUBLIC_API_BASE}/analysis/${matchId}/report.pdf`);
  url.searchParams.set("source", "r2");
  url.searchParams.set("file_path", filePath);
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
