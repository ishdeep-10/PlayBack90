import { LandingHome } from "../components/landing/LandingHome";
import { getLeagues } from "../lib/api";
import { FALLBACK_LEAGUES } from "../lib/leagues";
import { getServerAuthToken } from "../lib/serverAuth";

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
