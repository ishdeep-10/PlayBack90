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
        <span className="coverage-heading-kicker">Pick your league</span>
        <h2>Five leagues. Every match, analysed.</h2>
        <p>Select a country or a league crest to open its latest matches.</p>
      </header>
      <LeagueCoverageMap leagues={leagues} />
    </div>
  );
}
