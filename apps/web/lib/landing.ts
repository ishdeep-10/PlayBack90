import type { League } from "./api";

export type LandingSequenceEvent = {
  event_id?: string | number | null;
  minute: number;
  second: number;
  team: string;
  player: string;
  type: string;
  outcome: string;
  x: number;
  y: number;
  end_x?: number | null;
  end_y?: number | null;
  xg?: number | null;
  xgot?: number | null;
  xa?: number | null;
  xt?: number | null;
  epv_added?: number | null;
  goal_mouth_y?: number | null;
  goal_mouth_z?: number | null;
};

export type LandingPayload = {
  generated_at: string;
  refresh_key: string;
  featured_match: {
    match_id: string;
    league: string;
    league_name: string;
    season: string;
    date: string;
    home_team: string;
    away_team: string;
    score: string;
    team_colors: Record<string, string>;
    totals: {
      shots: number;
      goals: number;
      xg: number;
      xgot: number;
    };
    selected_shot: LandingSequenceEvent;
  };
  preview_sequence: LandingSequenceEvent[];
  preview_defensive_actions?: Array<{
    minute: number;
    second: number;
    player: string;
    type: string;
    outcome: string;
    x: number;
    y: number;
    zone: string;
  }>;
  preview_pass_network?: {
    team?: string;
    centralization_index?: number;
    nodes?: Array<{
      player_id: number;
      player: string;
      label: string;
      x: number;
      y: number;
      count: number;
      passes_made: number;
      passes_received: number;
      size: number;
    }>;
    edges?: Array<{
      source_id: number;
      target_id: number;
      x0: number;
      y0: number;
      x1: number;
      y1: number;
      pass_count: number;
      total_xt: number;
      width: number;
    }>;
  };
  leagues: Array<
    League & {
      latest_match?: {
        match_id: string;
        home_team: string;
        away_team: string;
        score: string;
        date: string;
      } | null;
    }
  >;
};

export const FALLBACK_LANDING_PAYLOAD: LandingPayload = {
  generated_at: "2026-07-16T00:00:00Z",
  refresh_key: "curated-villarreal-atletico",
  featured_match: {
    match_id: "1914257",
    league: "laliga",
    league_name: "La Liga",
    season: "2025_2026",
    date: "2026-05-24",
    home_team: "Villarreal",
    away_team: "Atletico Madrid",
    score: "5-1",
    team_colors: {
      Villarreal: "#e6c90c",
      "Atletico Madrid": "#c9343d",
    },
    totals: {
      shots: 23,
      goals: 6,
      xg: 4.16,
      xgot: 5.12,
    },
    selected_shot: {
      minute: 39,
      second: 57,
      team: "Villarreal",
      player: "Georges Mikautadze",
      type: "Goal",
      outcome: "Successful",
      x: 89.1,
      y: 52.8,
      end_x: 100,
      end_y: 50,
      xg: 0.597,
      xgot: 0.881,
    },
  },
  preview_sequence: [
    {
      minute: 39,
      second: 54,
      team: "Villarreal",
      player: "Ayoze Perez",
      type: "Pass",
      outcome: "Successful",
      x: 73.2,
      y: 46.8,
      end_x: 84.6,
      end_y: 63.9,
      xa: 0.597,
      xt: 0.082,
      epv_added: 0.074,
    },
    {
      minute: 39,
      second: 56,
      team: "Villarreal",
      player: "Georges Mikautadze",
      type: "TakeOn",
      outcome: "Successful",
      x: 84.6,
      y: 63.9,
      end_x: 89.1,
      end_y: 52.8,
      xt: 0.061,
      epv_added: 0.083,
    },
    {
      minute: 39,
      second: 57,
      team: "Villarreal",
      player: "Georges Mikautadze",
      type: "Goal",
      outcome: "Successful",
      x: 89.1,
      y: 52.8,
      end_x: 100,
      end_y: 50,
      xg: 0.597,
      xgot: 0.881,
      epv_added: 0.21,
    },
  ],
  preview_defensive_actions: [
    { minute: 18, second: 12, player: "Pape Gueye", type: "Tackle", outcome: "Successful", x: 44, y: 61, zone: "Middle Third" },
    { minute: 27, second: 8, player: "Dani Parejo", type: "Interception", outcome: "Successful", x: 53, y: 43, zone: "Middle Third" },
    { minute: 34, second: 31, player: "Juan Foyth", type: "Clearance", outcome: "Successful", x: 22, y: 76, zone: "Defensive Third" },
    { minute: 52, second: 4, player: "Pape Gueye", type: "BallRecovery", outcome: "Successful", x: 61, y: 48, zone: "Middle Third" },
    { minute: 68, second: 39, player: "Logan Costa", type: "BlockedPass", outcome: "Successful", x: 28, y: 35, zone: "Defensive Third" },
  ],
  preview_pass_network: {
    team: "Villarreal",
    centralization_index: 0.31,
    nodes: [
      { player_id: 1, player: "Dani Parejo", label: "DP", x: 48, y: 51, count: 74, passes_made: 42, passes_received: 32, size: 52 },
      { player_id: 2, player: "Pape Gueye", label: "PG", x: 43, y: 38, count: 58, passes_made: 31, passes_received: 27, size: 45 },
      { player_id: 3, player: "Ayoze Perez", label: "AP", x: 70, y: 64, count: 39, passes_made: 18, passes_received: 21, size: 36 },
      { player_id: 4, player: "Juan Foyth", label: "JF", x: 28, y: 72, count: 51, passes_made: 29, passes_received: 22, size: 42 },
    ],
    edges: [
      { source_id: 1, target_id: 2, x0: 48, y0: 51, x1: 43, y1: 38, pass_count: 14, total_xt: 0.12, width: 5 },
      { source_id: 2, target_id: 3, x0: 43, y0: 38, x1: 70, y1: 64, pass_count: 9, total_xt: 0.24, width: 4 },
      { source_id: 4, target_id: 1, x0: 28, y0: 72, x1: 48, y1: 51, pass_count: 12, total_xt: 0.08, width: 4.5 },
    ],
  },
  leagues: [],
};

export function featuredAnalysisUrl(payload: LandingPayload) {
  const match = payload.featured_match;
  const params = new URLSearchParams({
    source: "r2",
    league: match.league,
    season: match.season,
    view: "match-dynamics",
    team: match.home_team,
    situation: "All",
    half: "Full 90",
    duelType: "Total",
    transitionType: "Offensive",
    subWindow: "0",
  });
  return `/analysis/${match.match_id}?${params.toString()}`;
}
