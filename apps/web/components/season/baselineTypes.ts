export type BaselineMetric = {
  key: string;
  label: string;
  lowerIsBetter: boolean;
  matchValue: number;
  nMatches: number;
  seasonAvg?: number;
  seasonMedian?: number;
  p25?: number;
  p75?: number;
  min?: number;
  max?: number;
  delta?: number;
  zScore?: number;
  pctOfOwnMatches?: number;
  gameRank?: number;
  leaguePercentile?: number;
  last5Avg?: number;
  seasonPer90?: number;
  matchValuePer90?: number;
  leaguePercentilePer90?: number;
  leagueMeanPer90?: number;
  leagueStdPer90?: number;
  /** "rate" metrics (pass %, win %, avg distance) compare directly, not per-90. */
  kind?: "count" | "rate";
  vsOpponentAvg?: number;
  vsOpponentMedian?: number;
  vsOpponentP25?: number;
  vsOpponentP75?: number;
  vsOpponentMin?: number;
  vsOpponentMax?: number;
  nVsOpponent?: number;
};

export type TeamSeasonMatch = {
  matchId: string;
  date: string;
  opponent: string;
  homeAway: string;
  result: "W" | "D" | "L";
  goals: number;
  goalsAgainst: number;
  xg: number;
  xga: number;
};

export type MetricGroup = {
  id: string;
  label: string;
  keys: string[];
};

export type TeamBaseline = {
  matchesPlayed: number;
  lowSample?: boolean;
  metrics: BaselineMetric[];
  matches?: TeamSeasonMatch[];
};

export type PlayerBaseline = {
  team: string;
  minsSeason: number;
  matchesPlayed: number;
  matchMins: number;
  lowSample: boolean;
  positionGroup: string | null;
  metrics: BaselineMetric[];
};

export type SeasonBaselinePayload = {
  available: boolean;
  reason?: string;
  meta?: {
    league: string;
    season: string;
    source: string;
    teamMatchesMin: number;
    playerMinsMin: number;
    matchMinsMin: number;
    radarGroups?: Record<string, string[]>;
    metricGroups?: MetricGroup[];
  };
  teams?: Record<string, TeamBaseline>;
  players?: Record<string, PlayerBaseline>;
};

export function metricByKey(baseline: TeamBaseline | PlayerBaseline | undefined, key: string): BaselineMetric | undefined {
  return baseline?.metrics.find((m) => m.key === key);
}
