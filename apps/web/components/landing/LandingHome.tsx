import type { League } from "../../lib/api";
import { LandingCoverage } from "./LandingCoverage";
import { LandingJourney } from "./journey/LandingJourney";

export function LandingHome({
  leagues,
}: {
  leagues: League[];
}) {
  return (
    <main className="landing-home">
      <LandingJourney />
      <LandingCoverage leagues={leagues} />
    </main>
  );
}
