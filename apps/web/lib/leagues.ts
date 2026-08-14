import type { League } from "./api";

export type LeaguePresentation = {
  key: string;
  name: string;
  country: string;
  logo: string;
  mapNames: string[];
  coordinates: [number, number];
  chipOffset?: [number, number];
};

export const LEAGUE_PRESENTATION: Record<string, LeaguePresentation> = {
  "premier-league": {
    key: "premier-league",
    name: "Premier League",
    country: "England",
    logo: "/logos/premier-league.png",
    mapNames: ["United Kingdom"],
    coordinates: [-1.6, 52.9],
    chipOffset: [-34, -28],
  },
  laliga: {
    key: "laliga",
    name: "LaLiga",
    country: "Spain",
    logo: "/logos/laliga.png",
    mapNames: ["Spain"],
    coordinates: [-3.7, 40.2],
    chipOffset: [-58, 28],
  },
  bundesliga: {
    key: "bundesliga",
    name: "Bundesliga",
    country: "Germany",
    logo: "/logos/bundesliga.png",
    mapNames: ["Germany"],
    coordinates: [10.4, 51.1],
    chipOffset: [58, -34],
  },
  "serie-a": {
    key: "serie-a",
    name: "Serie A",
    country: "Italy",
    logo: "/logos/serie-a.png",
    mapNames: ["Italy"],
    coordinates: [12.6, 42.8],
    chipOffset: [76, 32],
  },
  "ligue-1": {
    key: "ligue-1",
    name: "Ligue 1",
    country: "France",
    logo: "/logos/ligue-1.png",
    mapNames: ["France"],
    coordinates: [2.3, 46.4],
    chipOffset: [4, 58],
  },
  mls: {
    key: "mls",
    name: "Major League Soccer",
    country: "United States",
    logo: "/logos/mls.svg",
    mapNames: ["United States of America"],
    coordinates: [-98.5, 39.5],
    chipOffset: [0, 42],
  },
};

export const FALLBACK_LEAGUES: League[] = Object.values(LEAGUE_PRESENTATION).map(({ key, name }) => ({
  key,
  name,
}));

export function leaguePresentation(key: string): LeaguePresentation | undefined {
  return LEAGUE_PRESENTATION[key];
}
