import type { League } from "../../lib/api";
import { LandingCoverage } from "./LandingCoverage";
import { LandingJourney } from "./journey/LandingJourney";

const MOBILE_LEAGUES = [
  {
    key: "premier-league",
    name: "Premier League",
    country: "England",
    logo: "/logos/premier-league.png",
  },
  {
    key: "laliga",
    name: "LaLiga",
    country: "Spain",
    logo: "/logos/laliga.png",
  },
  {
    key: "bundesliga",
    name: "Bundesliga",
    country: "Germany",
    logo: "/logos/bundesliga.png",
  },
  {
    key: "serie-a",
    name: "Serie A",
    country: "Italy",
    logo: "/logos/serie-a.png",
  },
  {
    key: "ligue-1",
    name: "Ligue 1",
    country: "France",
    logo: "/logos/ligue-1.png",
  },
];

export function LandingHome({
  leagues,
}: {
  leagues: League[];
}) {
  const availableKeys = new Set(leagues.map((league) => league.key));
  const mobileLeagues = MOBILE_LEAGUES.filter(
    (league) => availableKeys.size === 0 || availableKeys.has(league.key),
  );

  return (
    <main className="landing-home">
      <section className="landing-mobile-select" aria-label="Select a league">
        <div className="landing-mobile-select-inner">
          <span className="landing-mobile-kicker">Football, translated</span>
          <h1>PlayBack90</h1>
          <p>Choose a league to open the latest match analysis.</p>
          <div className="landing-mobile-leagues">
            {mobileLeagues.map((league) => (
              <a href={`/matches/${league.key}/latest`} key={league.key}>
                <img src={league.logo} alt="" />
                <span>{league.country}</span>
                <strong>{league.name}</strong>
              </a>
            ))}
          </div>
          <a className="ghost-button landing-mobile-import" href="/live-scrape">
            Import Match
          </a>
        </div>
      </section>
      <div className="landing-desktop-experience">
        <LandingJourney />
        <LandingCoverage leagues={leagues} />
      </div>
    </main>
  );
}
