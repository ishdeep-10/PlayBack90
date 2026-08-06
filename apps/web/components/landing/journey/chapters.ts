import type { Route } from "next";
import {
  CHAPTER_SEQUENCES,
  type CameraFraming,
  type ChapterSequence,
  type ChapterTreatment,
} from "../../../lib/landing-sequences";

export type JourneyChapter = {
  key: string; // matches analysis ?view=
  kicker: string;
  headline: string;
  support: string;
  league: string;
  match: string;
  score: string;
  date: string;
  treatment: ChapterTreatment;
  camera: CameraFraming;
  // optional end-of-chapter camera: the view dives from `camera` to this
  // framing over the last part of the chapter (shots: following the ball
  // into the goal before the goal-mouth map appears)
  finaleCamera?: CameraFraming;
  sequence: ChapterSequence;
  href: Route;
  screenshot: { dark: string; light: string; alt: string };
};

export function analysisHref({
  matchId,
  league,
  season,
  view,
  team,
}: {
  matchId: string;
  league: string;
  season: string;
  view: string;
  team: string;
}) {
  const params = new URLSearchParams({
    source: "r2",
    league,
    season,
    view,
    team,
    situation: "All",
    half: "Full 90",
    duelType: "Total",
    transitionType: "Offensive",
    subWindow: "0",
  });
  return `/analysis/${matchId}?${params.toString()}` as Route;
}

export const AERIAL_CAMERA: CameraFraming = {
  center: [50, 50],
  span: 132,
  tiltDeg: 8,
};

export const JOURNEY_CHAPTERS: JourneyChapter[] = [
  {
    key: "match-dynamics",
    kicker: "Match Dynamics",
    headline: "Two shapes, one pitch: who really controlled the space.",
    support:
      "Inside this tab: cumulative xG flow, xT & EPV momentum, average positions with Voronoi control zones, PPDA, turnovers, and big chances.",
    league: "Premier League",
    match: "Crystal Palace vs Arsenal",
    score: "1-2",
    date: "24 May 2026",
    treatment: "momentum",
    camera: { center: [50, 50], span: 122, tiltDeg: 38, screenOffsetX: 0.16 },
    sequence: CHAPTER_SEQUENCES.momentum,
    href: analysisHref({
      matchId: "1903353",
      league: "premier-league",
      season: "2025_2026",
      view: "match-dynamics",
      team: "Crystal Palace",
    }),
    screenshot: {
      dark: "/media/landing/showcase/match-dynamics-premier-league.png",
      light: "/media/landing/showcase/match-dynamics-premier-league-light.png",
      alt: "PlayBack90 cumulative xG flow for Crystal Palace against Arsenal",
    },
  },
  {
    key: "shots",
    kicker: "Shots + SCA",
    headline: "Four players, three actions, one 0.60 chance buried.",
    support:
      "Inside this tab: shot maps, SCA chains, and the goal-mouth view — xG for the chance, xGOT for the finish.",
    league: "LaLiga",
    match: "Villarreal vs Atletico Madrid",
    score: "5-1",
    date: "24 May 2026",
    treatment: "shots",
    camera: { center: [66, 48], span: 82, tiltDeg: 48, screenOffsetX: -0.16 },
    finaleCamera: { center: [96, 50], span: 26, tiltDeg: 60, screenOffsetX: -0.1 },
    sequence: CHAPTER_SEQUENCES.shots,
    href: analysisHref({
      matchId: "1914257",
      league: "laliga",
      season: "2025_2026",
      view: "shots",
      team: "Villarreal",
    }),
    screenshot: {
      dark: "/media/landing/showcase/shots-laliga.png",
      light: "/media/landing/showcase/shots-laliga-light.png",
      alt: "PlayBack90 shot and goal-mouth maps for Villarreal against Atletico Madrid",
    },
  },
  {
    key: "in-possession",
    kicker: "In Possession",
    headline: "612 passes, one structure: Bayern's full passing network.",
    support:
      "The full match network: node size = involvement, link width = pass volume, with the hub and passing triangles picked out.",
    league: "Bundesliga",
    match: "Bayern Munich vs FC Koln",
    score: "5-1",
    date: "16 May 2026",
    treatment: "pass-network",
    camera: { center: [54, 52], span: 92, tiltDeg: 38, screenOffsetX: 0.16 },
    sequence: CHAPTER_SEQUENCES["pass-network"],
    href: analysisHref({
      matchId: "1910895",
      league: "bundesliga",
      season: "2025_2026",
      view: "in-possession",
      team: "Bayern Munich",
    }),
    screenshot: {
      dark: "/media/landing/showcase/in-possession-bundesliga.png",
      light: "/media/landing/showcase/in-possession-bundesliga-light.png",
      alt: "PlayBack90 passing network for Bayern Munich against FC Koln",
    },
  },
  {
    key: "out-of-possession",
    kicker: "Out of Possession",
    headline: "Napoli's block held the middle third — then conceded behind it.",
    support:
      "Zone % shows where the defensive work happened; scroll on and the zones resolve into every labeled intervention.",
    league: "Serie A",
    match: "Napoli vs Bologna",
    score: "2-3",
    date: "11 May 2026",
    treatment: "defensive-shape",
    camera: { center: [50, 53], span: 128, tiltDeg: 46, screenOffsetX: -0.11 },
    sequence: CHAPTER_SEQUENCES["defensive-shape"],
    href: analysisHref({
      matchId: "1901418",
      league: "serie-a",
      season: "2025_2026",
      view: "out-of-possession",
      team: "Napoli",
    }),
    screenshot: {
      dark: "/media/landing/showcase/out-of-possession-serie-a.png",
      light: "/media/landing/showcase/out-of-possession-serie-a-light.png",
      alt: "PlayBack90 defensive block and action zones for Napoli against Bologna",
    },
  },
  {
    key: "duels-transitions",
    kicker: "Duels & Transitions",
    headline: "A duel won in midfield became a transition in four seconds.",
    support:
      "The duel map shows who owned each zone; scroll on and it resolves into aerial and ground contests — one of them sprang the counter.",
    league: "Ligue 1",
    match: "Brest vs Angers",
    score: "1-1",
    date: "17 May 2026",
    treatment: "duels",
    camera: { center: [50, 53], span: 128, tiltDeg: 46, screenOffsetX: 0.11 },
    sequence: CHAPTER_SEQUENCES.duels,
    href: analysisHref({
      matchId: "1911516",
      league: "ligue-1",
      season: "2025_2026",
      view: "duels-transitions",
      team: "__both__",
    }),
    screenshot: {
      dark: "/media/landing/showcase/duels-ligue-1.png",
      light: "/media/landing/showcase/duels-ligue-1-light.png",
      alt: "PlayBack90 duel map for Brest against Angers",
    },
  },
  {
    key: "player-analysis",
    kicker: "Player Analysis",
    headline: "202 touches: Rodri's match, one lens at a time.",
    support:
      "One profile, three views — the ground he covered, every touch he took, then the passes and carries that moved City forward.",
    league: "Premier League",
    match: "West Ham vs Man City",
    score: "1-1",
    date: "14 Mar 2026",
    treatment: "player-focus",
    camera: { center: [50, 53], span: 128, tiltDeg: 46, screenOffsetX: -0.13 },
    sequence: CHAPTER_SEQUENCES["player-focus"],
    href: analysisHref({
      matchId: "1903459",
      league: "premier-league",
      season: "2025_2026",
      view: "player-analysis",
      team: "Man City",
    }),
    screenshot: {
      dark: "/media/landing/showcase/player-analysis-premier-league.png",
      light: "/media/landing/showcase/player-analysis-premier-league-light.png",
      alt: "PlayBack90 three-pitch player analysis view",
    },
  },
];
