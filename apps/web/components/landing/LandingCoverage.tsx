"use client";

import dynamic from "next/dynamic";

import type { League } from "../../lib/api";

const LeagueCoverageMap = dynamic(
  () => import("../LeagueCoverageMap").then((module) => module.LeagueCoverageMap),
  {
    ssr: false,
    loading: () => <div className="coverage-map-loading" aria-label="Loading league coverage" />,
  },
);

export function LandingCoverage({
  leagues,
}: {
  leagues: League[];
}) {
  return (
    <div id="league-coverage" className="landing-coverage-band">
      <header className="coverage-heading">
        <span className="coverage-heading-kicker">Explore coverage</span>
        <h2>From the world to the match.</h2>
        <p>Spin the globe, choose a continent, then open a league.</p>
      </header>
      <LeagueCoverageMap leagues={leagues} />
    </div>
  );
}
