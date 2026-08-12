import Image from "next/image";

import type { StandingsResponse } from "../lib/api";

type Props = {
  standings: StandingsResponse;
};

export function FixturesLeagueTable({ standings }: Props) {
  return (
    <section className="fixtures-standings" aria-labelledby="fixtures-standings-title">
      <header className="fixtures-standings-head">
        <div>
          <span className="fixtures-hero-kicker">Season position</span>
          <h2 id="fixtures-standings-title">League table</h2>
        </div>
        <span className={`standings-source${standings.is_official ? " is-official" : ""}`}>
          {standings.is_stale
            ? "Official · cached"
            : standings.is_official
              ? "Official"
              : "Calculated"}
        </span>
      </header>

      {standings.warning ? <p className="inline-warning">{standings.warning}</p> : null}

      <div className="fixtures-standings-scroll">
        <table className="fixtures-standings-table">
          <thead>
            <tr>
              <th scope="col">#</th>
              <th scope="col">Club</th>
              <th scope="col" className="fixtures-standings-mobile-points">Pts</th>
              <th scope="col" className="fixtures-standings-played">P</th>
              <th scope="col" className="fixtures-standings-detail">W</th>
              <th scope="col" className="fixtures-standings-detail">D</th>
              <th scope="col" className="fixtures-standings-detail">L</th>
              <th scope="col" className="fixtures-standings-goal-difference">GD</th>
              <th scope="col" className="fixtures-standings-points-desktop">Pts</th>
            </tr>
          </thead>
          <tbody>
            {standings.rows.map((row) => (
              <tr key={row.provider_team_id ?? row.team}>
                <td className="fixtures-standings-rank">{row.rank}</td>
                <th scope="row">
                  <span className="fixtures-standings-team">
                    {row.crest ? (
                      <Image
                        src={row.crest}
                        alt=""
                        width={28}
                        height={28}
                        className="fixtures-standings-crest"
                      />
                    ) : (
                      <span className="fixtures-standings-crest-fallback" aria-hidden="true">
                        {row.team_code?.slice(0, 3) ?? row.team.slice(0, 2).toUpperCase()}
                      </span>
                    )}
                    <strong>{row.team}</strong>
                  </span>
                </th>
                <td className="fixtures-standings-mobile-points">{row.pts}</td>
                <td className="fixtures-standings-played">{row.played}</td>
                <td className="fixtures-standings-detail">{row.won}</td>
                <td className="fixtures-standings-detail">{row.drawn}</td>
                <td className="fixtures-standings-detail">{row.lost}</td>
                <td className={`fixtures-standings-goal-difference${row.gd < 0 ? " is-negative" : row.gd > 0 ? " is-positive" : ""}`}>
                  {row.gd > 0 ? "+" : ""}{row.gd}
                </td>
                <td className="fixtures-standings-points fixtures-standings-points-desktop">{row.pts}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
