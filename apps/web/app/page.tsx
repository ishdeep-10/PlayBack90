import { LandingHome } from "../components/landing/LandingHome";
import { getLeagues, type League } from "../lib/api";
import { getServerAuthToken } from "../lib/serverAuth";

const FALLBACK_LEAGUES: League[] = [
  { key: "premier-league", name: "Premier League" },
  { key: "laliga", name: "LaLiga" },
  { key: "bundesliga", name: "Bundesliga" },
  { key: "serie-a", name: "Serie A" },
  { key: "ligue-1", name: "Ligue 1" },
];

export const revalidate = 3_600;

async function loadLeagues() {
  const authToken = await getServerAuthToken();
  try {
    return await getLeagues(authToken);
  } catch {
    return FALLBACK_LEAGUES;
  }
}

export default async function HomePage() {
  const leagues = await loadLeagues();
  return <LandingHome leagues={leagues} />;
}
