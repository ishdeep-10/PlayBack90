import type { LandingPayload, LandingSequenceEvent } from "./landing";
import { FALLBACK_LANDING_PAYLOAD } from "./landing";

export type ChapterTreatment =
  | "momentum"
  | "shots"
  | "pass-network"
  | "defensive-shape"
  | "duels"
  | "player-focus";

// All values in Opta 0-100 pitch space. span = pitch-length units visible
// across the viewport width; tiltDeg 0 = top-down, ~50 = broadcast camera.
// screenOffsetX shifts the framed action horizontally (fraction of viewport
// width) so the replay stays clear of the overlay card on the opposite side.
export type CameraFraming = {
  center: [number, number];
  span: number;
  tiltDeg: number;
  yawDeg?: number;
  screenOffsetX?: number;
};

export type DefensiveAction = NonNullable<
  LandingPayload["preview_defensive_actions"]
>[number];

// One cell of the 6x5 duel-map grid: duels won by each side in that zone,
// rendered as a split rect (home share left, away share right) like the
// Duels & Transitions tab.
export type DuelZoneCount = {
  col: number;
  row: number;
  home: number;
  away: number;
};

// Vertical pitch third with its share of ball recoveries.
export type ZoneShare = {
  label: string;
  x0: number;
  x1: number;
  share: number; // 0-1
};

// Juego-de-posicion zone (col/row into the 6x5 grid from lib/pitch.ts)
// with its share of the team's defensive actions, in percent.
export type DefensiveZone = {
  col: number;
  row: number;
  share: number;
};

// A single contested duel; transitionTo marks the duel that sprang a
// counter and where the resulting move ended.
export type DuelAction = {
  minute: number;
  player: string;
  team: string;
  kind: "aerial" | "ground";
  won: boolean;
  x: number;
  y: number;
  transitionTo?: [number, number];
};

// Season-average player position with a relative involvement size.
export type AveragePosition = {
  player: string;
  team: string;
  x: number;
  y: number;
  size: number; // relative involvement (touches), ~30-60
};

// A single in-possession action for the player-analysis chapter.
export type InPossessionAction = {
  type: string;
  minute: number;
  x: number;
  y: number;
  end_x: number;
  end_y: number;
  xt?: number;
};

export type ChapterSequence = {
  id: ChapterTreatment;
  matchId: string;
  homeTeam: string;
  awayTeam: string;
  teamColors: Record<string, string>;
  events: LandingSequenceEvent[];
  focusPlayer?: string;
  passNetwork?: LandingPayload["preview_pass_network"];
  defensiveActions?: DefensiveAction[];
  duelZoneCounts?: DuelZoneCount[];
  duelActions?: DuelAction[];
  zoneShares?: ZoneShare[];
  defensiveZoneGrid?: DefensiveZone[];
  averagePositions?: AveragePosition[];
  heatTouches?: Array<[number, number]>; // Opta 0-100 touch locations
  inPossessionActions?: InPossessionAction[];
  playerImages?: Record<string, string>;
  avatarScale?: number; // multiplier on player marker size for this chapter
  metrics: Array<{ label: string; value: string }>;
};

// Curated editorial sequences, one per journey chapter. The shots chapter uses
// the real Villarreal-Atletico preview sequence from FALLBACK_LANDING_PAYLOAD;
// the rest are curated from the featured matches. Re-curate with
// apps/api/scripts/export_landing_sequences.py and paste the JSON here.
export const CHAPTER_SEQUENCES: Record<ChapterTreatment, ChapterSequence> = {
  momentum: {
    id: "momentum",
    matchId: "1903353",
    homeTeam: "Crystal Palace",
    awayTeam: "Arsenal",
    teamColors: { "Crystal Palace": "#1b458f", Arsenal: "#ef0107" },
    // no event replay here: the visual is both teams' average positions
    // partitioned by a Voronoi control map
    events: [],
    averagePositions: [
      { player: "Chris Richards", team: "Crystal Palace", x: 22, y: 30, size: 44 },
      { player: "Maxence Lacroix", team: "Crystal Palace", x: 20, y: 52, size: 46 },
      { player: "Chadi Riad", team: "Crystal Palace", x: 22, y: 74, size: 40 },
      { player: "Daniel Munoz", team: "Crystal Palace", x: 38, y: 14, size: 48 },
      { player: "Borna Sosa", team: "Crystal Palace", x: 36, y: 86, size: 42 },
      { player: "Adam Wharton", team: "Crystal Palace", x: 40, y: 44, size: 52 },
      { player: "Cheick Doucoure", team: "Crystal Palace", x: 44, y: 60, size: 46 },
      { player: "Daichi Kamada", team: "Crystal Palace", x: 52, y: 30, size: 40 },
      { player: "Ismaila Sarr", team: "Crystal Palace", x: 58, y: 74, size: 38 },
      { player: "Jean Philippe Mateta", team: "Crystal Palace", x: 60, y: 50, size: 36 },
      { player: "Jurrien Timber", team: "Arsenal", x: 80, y: 16, size: 44 },
      { player: "Gabriel Magalhaes", team: "Arsenal", x: 82, y: 45, size: 46 },
      { player: "Riccardo Calafiori", team: "Arsenal", x: 80, y: 70, size: 42 },
      { player: "Martin Zubimendi", team: "Arsenal", x: 64, y: 55, size: 50 },
      { player: "Declan Rice", team: "Arsenal", x: 60, y: 38, size: 54 },
      { player: "Martin Odegaard", team: "Arsenal", x: 55, y: 62, size: 50 },
      { player: "Bukayo Saka", team: "Arsenal", x: 48, y: 18, size: 46 },
      { player: "Gabriel Martinelli", team: "Arsenal", x: 50, y: 82, size: 40 },
      { player: "Kai Havertz", team: "Arsenal", x: 44, y: 48, size: 42 },
    ],
    playerImages: {
      "Chris Richards": "https://cdn.soccerwiki.org/images/player/96656.png",
      "Maxence Lacroix": "https://cdn.soccerwiki.org/images/player/98346.png",
      "Chadi Riad": "https://cdn.soccerwiki.org/images/player/123504.png",
      "Daniel Munoz": "https://cdn.soccerwiki.org/images/player/95517.png",
      "Borna Sosa": "https://cdn.soccerwiki.org/images/player/80189.png",
      "Adam Wharton": "https://cdn.soccerwiki.org/images/player/127251.png",
      "Cheick Doucoure": "https://cdn.soccerwiki.org/images/player/98429.png",
      "Daichi Kamada": "https://cdn.soccerwiki.org/images/player/85931.png",
      "Ismaila Sarr": "https://cdn.soccerwiki.org/images/player/87576.png",
      "Jean Philippe Mateta": "https://cdn.soccerwiki.org/images/player/87889.png",
      "Jurrien Timber": "https://cdn.soccerwiki.org/images/player/100881.png",
      "Gabriel Magalhaes": "https://cdn.soccerwiki.org/images/player/89344.png",
      "Riccardo Calafiori": "https://cdn.soccerwiki.org/images/player/107765.png",
      "Martin Zubimendi": "https://cdn.soccerwiki.org/images/player/104827.png",
      "Declan Rice": "https://cdn.soccerwiki.org/images/player/90916.png",
      "Martin Odegaard": "https://cdn.soccerwiki.org/images/player/73424.png",
      "Bukayo Saka": "https://cdn.soccerwiki.org/images/player/99607.png",
      "Gabriel Martinelli": "https://cdn.soccerwiki.org/images/player/100768.png",
      "Kai Havertz": "https://cdn.soccerwiki.org/images/player/88054.png",
    },
    metrics: [
      { label: "xG swing", value: "+0.94" },
      { label: "PPDA", value: "9.8" },
      { label: "Big chances", value: "5" },
    ],
  },
  shots: {
    id: "shots",
    matchId: "1914257",
    homeTeam: "Villarreal",
    awayTeam: "Atletico Madrid",
    teamColors: FALLBACK_LANDING_PAYLOAD.featured_match.team_colors,
    // full SCA chain behind the Mikautadze goal: 4 players, pass -> carry ->
    // take-on -> shot (last three events are the real preview_sequence values)
    events: [
      { minute: 39, second: 46, team: "Villarreal", player: "Juan Foyth", type: "Pass", outcome: "Successful", x: 34, y: 56, end_x: 52, end_y: 40, xt: 0.012 },
      { minute: 39, second: 49, team: "Villarreal", player: "Nicolas Pepe", type: "Carry", outcome: "Successful", x: 52, y: 40, end_x: 64, end_y: 34, xt: 0.024 },
      { minute: 39, second: 52, team: "Villarreal", player: "Nicolas Pepe", type: "Pass", outcome: "Successful", x: 64, y: 34, end_x: 73.2, end_y: 46.8, xt: 0.038 },
      { minute: 39, second: 54, team: "Villarreal", player: "Ayoze Perez", type: "Pass", outcome: "Successful", x: 73.2, y: 46.8, end_x: 84.6, end_y: 63.9, xa: 0.597, xt: 0.082, epv_added: 0.074 },
      { minute: 39, second: 56, team: "Villarreal", player: "Georges Mikautadze", type: "TakeOn", outcome: "Successful", x: 84.6, y: 63.9, end_x: 89.1, end_y: 52.8, xt: 0.061, epv_added: 0.083 },
      { minute: 39, second: 57, team: "Villarreal", player: "Georges Mikautadze", type: "Goal", outcome: "Successful", x: 89.1, y: 52.8, end_x: 100, end_y: 50, xg: 0.597, xgot: 0.881, epv_added: 0.21 },
    ],
    playerImages: {
      "Juan Foyth": "https://cdn.soccerwiki.org/images/player/90317.png",
      "Nicolas Pepe": "https://cdn.soccerwiki.org/images/player/81586.png",
      "Ayoze Perez": "https://cdn.soccerwiki.org/images/player/68710.png",
      "Georges Mikautadze": "https://cdn.soccerwiki.org/images/player/109701.png",
      "Jan Oblak": "https://cdn.soccerwiki.org/images/player/41018.png",
    },
    avatarScale: 1.45,
    metrics: [
      { label: "SCA chain", value: "4 players" },
      { label: "xG", value: "0.60" },
      { label: "xGOT", value: "0.88" },
    ],
  },
  "pass-network": {
    id: "pass-network",
    matchId: "1910895",
    homeTeam: "Bayern Munich",
    awayTeam: "FC Koln",
    teamColors: { "Bayern Munich": "#dc052d", "FC Koln": "#ed1c24" },
    // no replay: the chapter shows only the full passing network
    events: [],
    passNetwork: {
      team: "Bayern Munich",
      centralization_index: 0.27,
      nodes: [
        { player_id: 1, player: "Joshua Kimmich", label: "JK", x: 44, y: 56, count: 96, passes_made: 54, passes_received: 42, size: 56 },
        { player_id: 2, player: "Aleksandar Pavlovic", label: "AP", x: 40, y: 40, count: 78, passes_made: 44, passes_received: 34, size: 48 },
        { player_id: 3, player: "Jamal Musiala", label: "JM", x: 66, y: 44, count: 62, passes_made: 30, passes_received: 32, size: 44 },
        { player_id: 4, player: "Michael Olise", label: "MO", x: 66, y: 68, count: 58, passes_made: 28, passes_received: 30, size: 42 },
        { player_id: 5, player: "Harry Kane", label: "HK", x: 76, y: 50, count: 47, passes_made: 21, passes_received: 26, size: 40 },
        { player_id: 6, player: "Dayot Upamecano", label: "DU", x: 33, y: 62, count: 64, passes_made: 38, passes_received: 26, size: 44 },
        { player_id: 7, player: "Jonathan Tah", label: "JT", x: 33, y: 38, count: 59, passes_made: 35, passes_received: 24, size: 42 },
        { player_id: 8, player: "Alphonso Davies", label: "AD", x: 44, y: 72, count: 55, passes_made: 27, passes_received: 28, size: 40 },
      ],
      edges: [
        { source_id: 1, target_id: 2, x0: 44, y0: 56, x1: 40, y1: 40, pass_count: 21, total_xt: 0.14, width: 5.5 },
        { source_id: 1, target_id: 4, x0: 44, y0: 56, x1: 66, y1: 68, pass_count: 14, total_xt: 0.22, width: 4.5 },
        { source_id: 2, target_id: 3, x0: 40, y0: 40, x1: 66, y1: 44, pass_count: 12, total_xt: 0.19, width: 4 },
        { source_id: 3, target_id: 5, x0: 66, y0: 44, x1: 76, y1: 50, pass_count: 9, total_xt: 0.27, width: 3.5 },
        { source_id: 4, target_id: 5, x0: 66, y0: 68, x1: 76, y1: 50, pass_count: 8, total_xt: 0.24, width: 3.5 },
        { source_id: 6, target_id: 1, x0: 33, y0: 62, x1: 44, y1: 56, pass_count: 18, total_xt: 0.09, width: 5 },
        { source_id: 7, target_id: 2, x0: 33, y0: 38, x1: 40, y1: 40, pass_count: 16, total_xt: 0.08, width: 4.5 },
        { source_id: 6, target_id: 7, x0: 33, y0: 62, x1: 33, y1: 38, pass_count: 15, total_xt: 0.03, width: 4.5 },
        { source_id: 6, target_id: 2, x0: 33, y0: 62, x1: 40, y1: 40, pass_count: 13, total_xt: 0.05, width: 4.2 },
        { source_id: 8, target_id: 4, x0: 44, y0: 72, x1: 66, y1: 68, pass_count: 11, total_xt: 0.12, width: 4 },
        { source_id: 1, target_id: 3, x0: 44, y0: 56, x1: 66, y1: 44, pass_count: 10, total_xt: 0.17, width: 4 },
      ],
    },
    playerImages: {
      "Joshua Kimmich": "https://cdn.soccerwiki.org/images/player/70860.png",
      "Dayot Upamecano": "https://cdn.soccerwiki.org/images/player/82312.png",
      "Jonathan Tah": "https://cdn.soccerwiki.org/images/player/68027.png",
      "Alphonso Davies": "https://cdn.soccerwiki.org/images/player/85954.png",
      "Michael Olise": "https://cdn.soccerwiki.org/images/player/101780.png",
      "Jamal Musiala": "https://cdn.soccerwiki.org/images/player/104640.png",
      "Harry Kane": "https://cdn.soccerwiki.org/images/player/49590.png",
      "Aleksandar Pavlovic": "https://cdn.soccerwiki.org/images/player/135567.png",
    },
    metrics: [
      { label: "Passes", value: "612" },
      { label: "Centralization", value: "0.27" },
      { label: "Field tilt", value: "71%" },
    ],
  },
  "defensive-shape": {
    id: "defensive-shape",
    matchId: "1901418",
    homeTeam: "Napoli",
    awayTeam: "Bologna",
    teamColors: { Napoli: "#12a0d7", Bologna: "#a21c26" },
    // no player markers here: the zonal pitch is the visual, transforming
    // into the labeled action pitch as the chapter scrolls
    events: [],
    defensiveZoneGrid: [
      { col: 0, row: 1, share: 6 }, { col: 0, row: 2, share: 9 }, { col: 0, row: 3, share: 7 },
      { col: 1, row: 0, share: 4 }, { col: 1, row: 1, share: 8 }, { col: 1, row: 2, share: 11 },
      { col: 1, row: 3, share: 8 }, { col: 1, row: 4, share: 5 },
      { col: 2, row: 0, share: 3 }, { col: 2, row: 1, share: 7 }, { col: 2, row: 2, share: 10 },
      { col: 2, row: 3, share: 6 }, { col: 2, row: 4, share: 3 },
      { col: 3, row: 1, share: 3 }, { col: 3, row: 2, share: 5 },
      { col: 4, row: 2, share: 3 }, { col: 4, row: 3, share: 2 },
    ],
    defensiveActions: [
      { minute: 18, second: 40, player: "Stanislav Lobotka", type: "Interception", outcome: "Successful", x: 46, y: 52, zone: "Middle Third" },
      { minute: 24, second: 12, player: "Frank Anguissa", type: "Tackle", outcome: "Successful", x: 52, y: 34, zone: "Middle Third" },
      { minute: 31, second: 55, player: "Giovanni Di Lorenzo", type: "BallRecovery", outcome: "Successful", x: 38, y: 18, zone: "Defensive Third" },
      { minute: 47, second: 21, player: "Amir Rrahmani", type: "Clearance", outcome: "Successful", x: 16, y: 48, zone: "Defensive Third" },
      { minute: 58, second: 3, player: "Alessandro Buongiorno", type: "BlockedPass", outcome: "Successful", x: 22, y: 64, zone: "Defensive Third" },
      { minute: 63, second: 27, player: "Matteo Politano", type: "Tackle", outcome: "Successful", x: 68, y: 22, zone: "Attacking Third" },
      { minute: 66, second: 50, player: "Scott McTominay", type: "BallRecovery", outcome: "Successful", x: 49, y: 66, zone: "Middle Third" },
      { minute: 71, second: 44, player: "Stanislav Lobotka", type: "BallRecovery", outcome: "Successful", x: 44, y: 58, zone: "Middle Third" },
      { minute: 78, second: 15, player: "Amir Rrahmani", type: "Interception", outcome: "Successful", x: 27, y: 40, zone: "Defensive Third" },
    ],
    metrics: [
      { label: "Recoveries", value: "38" },
      { label: "PPDA", value: "11.4" },
      { label: "Block height", value: "42m" },
    ],
  },
  duels: {
    id: "duels",
    matchId: "1911516",
    homeTeam: "Brest",
    awayTeam: "Angers",
    teamColors: { Brest: "#a3e635", Angers: "#22d3ee" },
    // no replay markers: duel map first, resolving into individual duels
    events: [],
    duelActions: [
      { minute: 21, player: "Brendan Chardonnet", team: "Brest", kind: "aerial", won: false, x: 30, y: 55 },
      { minute: 33, player: "Pierre Lees-Melou", team: "Brest", kind: "aerial", won: true, x: 48, y: 40 },
      { minute: 41, player: "Himad Abdelli", team: "Angers", kind: "ground", won: true, x: 56, y: 46 },
      { minute: 52, player: "Romain Del Castillo", team: "Brest", kind: "ground", won: true, x: 60, y: 58 },
      { minute: 66, player: "Pierrick Capelle", team: "Angers", kind: "aerial", won: true, x: 63, y: 72 },
      { minute: 74, player: "Hugo Magnetti", team: "Brest", kind: "ground", won: true, x: 44, y: 32, transitionTo: [74, 24] },
      { minute: 80, player: "Yassin Belkhdim", team: "Angers", kind: "ground", won: false, x: 50, y: 64 },
    ],
    duelZoneCounts: [
      { col: 0, row: 0, home: 1, away: 1 }, { col: 0, row: 1, home: 1, away: 0 },
      { col: 0, row: 2, home: 2, away: 1 }, { col: 0, row: 3, home: 1, away: 1 },
      { col: 0, row: 4, home: 0, away: 1 },
      { col: 1, row: 0, home: 1, away: 1 }, { col: 1, row: 1, home: 2, away: 1 },
      { col: 1, row: 2, home: 1, away: 2 }, { col: 1, row: 3, home: 2, away: 1 },
      { col: 1, row: 4, home: 1, away: 1 },
      { col: 2, row: 0, home: 1, away: 2 }, { col: 2, row: 1, home: 3, away: 1 },
      { col: 2, row: 2, home: 2, away: 2 }, { col: 2, row: 3, home: 1, away: 3 },
      { col: 2, row: 4, home: 2, away: 1 },
      { col: 3, row: 0, home: 2, away: 1 }, { col: 3, row: 1, home: 2, away: 2 },
      { col: 3, row: 2, home: 3, away: 2 }, { col: 3, row: 3, home: 2, away: 1 },
      { col: 3, row: 4, home: 1, away: 2 },
      { col: 4, row: 0, home: 0, away: 1 }, { col: 4, row: 1, home: 1, away: 1 },
      { col: 4, row: 2, home: 1, away: 2 }, { col: 4, row: 3, home: 2, away: 3 },
      { col: 4, row: 4, home: 1, away: 0 },
      { col: 5, row: 1, home: 1, away: 0 }, { col: 5, row: 2, home: 0, away: 1 },
      { col: 5, row: 3, home: 1, away: 1 },
    ],
    metrics: [
      { label: "Duels won", value: "51%" },
      { label: "Transitions", value: "14" },
      { label: "Final score", value: "1-1" },
    ],
  },
  "player-focus": {
    id: "player-focus",
    matchId: "1903459",
    homeTeam: "West Ham",
    awayTeam: "Man City",
    teamColors: { "West Ham": "#7c2d3a", "Man City": "#6cabdd" },
    focusPlayer: "Rodri",
    events: [],
    // real Rodri touch locations from West Ham 1-1 Man City (2026-03-14)
    heatTouches: [
      [63.5, 83.2], [61.8, 80.3], [63.8, 72.9], [63.3, 11.5], [69.5, 89.7], [72.3, 73.8], [65.9, 50.9], [58.4, 76.8],
      [62.2, 19.2], [54.4, 28.0], [58.3, 27.3], [52.9, 31.0], [59.5, 78.5], [39.7, 74.0], [58.9, 37.1], [27.8, 55.8],
      [35.2, 35.4], [24.4, 48.8], [74.7, 28.5], [43.0, 66.8], [46.2, 75.9], [55.1, 74.6], [60.7, 69.0], [35.1, 78.8],
      [52.8, 44.1], [66.1, 43.6], [43.3, 77.9], [71.0, 28.6], [60.4, 52.7], [78.5, 77.9], [75.9, 88.8], [38.5, 96.1],
      [69.9, 84.4], [74.7, 83.7], [55.3, 56.2], [57.1, 69.7], [59.0, 22.1], [55.1, 25.3], [61.8, 68.9], [62.0, 52.9],
      [59.5, 75.3], [48.4, 51.7], [46.1, 27.7], [15.7, 49.1], [33.0, 66.4], [59.6, 81.5], [36.7, 30.3], [22.5, 22.7],
      [59.4, 40.0], [78.0, 74.4], [67.7, 67.4], [68.6, 23.2], [30.3, 84.1], [24.0, 45.1], [47.0, 73.2], [21.6, 48.3],
      [40.7, 56.4], [61.8, 34.4], [41.2, 65.3], [30.0, 63.0], [37.0, 41.5], [65.5, 64.6], [63.6, 68.8], [53.0, 30.5],
      [46.8, 30.0], [63.1, 48.3], [70.7, 61.1], [90.4, 48.5], [62.4, 29.4], [91.2, 9.6], [58.3, 28.0], [36.5, 71.5],
      [39.8, 23.6], [65.0, 32.6], [45.3, 33.3], [49.3, 19.2], [52.2, 51.8], [72.6, 64.1], [64.4, 18.8], [64.7, 68.3],
      [28.6, 47.6], [34.3, 41.8], [36.6, 50.5], [60.7, 39.2], [78.1, 70.6], [54.8, 58.3], [57.6, 57.1], [72.2, 80.5],
      [68.0, 57.0], [60.4, 20.6], [55.1, 14.3], [23.5, 58.9], [56.7, 35.6], [70.2, 40.3], [63.2, 27.9], [87.6, 58.0],
      [93.7, 42.5], [70.8, 47.1], [9.4, 81.8], [68.4, 24.4], [27.3, 59.6],
    ],
    // his highest-xT passes and carries from the same match
    inPossessionActions: [
      { type: "Pass", minute: 66, x: 70.6, y: 33.2, end_x: 86.3, end_y: 32.3, xt: 0.026 },
      { type: "Pass", minute: 76, x: 78.1, y: 70.6, end_x: 86.6, end_y: 68.6, xt: 0.026 },
      { type: "Pass", minute: 56, x: 63.1, y: 63.8, end_x: 89.4, end_y: 13.6, xt: 0.017 },
      { type: "Carry", minute: 11, x: 42.6, y: 88.1, end_x: 60.7, end_y: 69.0, xt: 0.007 },
      { type: "Pass", minute: 17, x: 62.4, y: 90.0, end_x: 68.3, end_y: 72.7, xt: 0.007 },
      { type: "Pass", minute: 47, x: 68.6, y: 23.2, end_x: 76.6, end_y: 20.0, xt: 0.006 },
      { type: "Pass", minute: 84, x: 56.7, y: 21.5, end_x: 68.3, end_y: 34.8, xt: 0.005 },
      { type: "Pass", minute: 28, x: 59.5, y: 75.3, end_x: 71.5, end_y: 53.9, xt: 0.005 },
      { type: "Pass", minute: 56, x: 46.8, y: 30.0, end_x: 58.5, end_y: 32.3, xt: 0.005 },
    ],
    playerImages: {
      Rodri: "https://cdn.soccerwiki.org/images/player/82178.png",
    },
    metrics: [
      { label: "Touches", value: "202" },
      { label: "Prog passes", value: "80" },
      { label: "Minutes", value: "99" },
    ],
  },
};

export type SequenceTimelineEvent = LandingSequenceEvent & {
  start: number; // virtual seconds
  end: number;
};

export type SequenceTimeline = {
  events: SequenceTimelineEvent[];
  duration: number; // virtual seconds, including trailing hold
};

const MIN_GAP = 0.35;
const MAX_GAP = 1.6;
const HOLD = 1.1;

function eventDuration(event: LandingSequenceEvent) {
  if (event.end_x == null || event.end_y == null) return 0.6;
  const dx = event.end_x - event.x;
  const dy = (event.end_y ?? event.y) - event.y;
  const dist = Math.hypot(dx, dy);
  return Math.min(Math.max(dist / 34, 0.4), 1.3);
}

// Re-space real match timestamps onto a compact virtual clock so long gaps
// between events do not read as dead scroll.
export function buildTimeline(events: LandingSequenceEvent[]): SequenceTimeline {
  let clock = 0;
  let prevReal: number | null = null;
  const timed = events.map((event) => {
    const real = event.minute * 60 + event.second;
    if (prevReal != null) {
      const gap = Math.min(Math.max(real - prevReal, MIN_GAP), MAX_GAP);
      clock += gap;
    }
    prevReal = real;
    const start = clock;
    const end = start + eventDuration(event);
    clock = end;
    return { ...event, start, end };
  });
  return { events: timed, duration: clock + HOLD };
}
