import Image from "next/image";

import type { StandingRow, StandingsResponse } from "../lib/api";
import { teamLogo } from "../lib/stadiums";

type Props = {
  standings: StandingsResponse;
};

function StandingsTable({ rows, label }: { rows: StandingRow[]; label?: string }) {
  return (
    <div className="fixtures-standings-scroll">
      <table className="fixtures-standings-table" aria-label={label}>
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
          {rows.map((row) => {
            const crest = row.crest ?? teamLogo(row.team);
            return <tr key={row.provider_team_id ?? row.team}>
              <td className="fixtures-standings-rank">{row.rank}</td>
              <th scope="row">
                <span className="fixtures-standings-team">
                  {crest ? (
                    <Image
                      unoptimized
                      src={crest}
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
            </tr>;
          })}
        </tbody>
      </table>
    </div>
  );
}

export function FixturesLeagueTable({ standings }: Props) {
  const groups = standings.groups ?? [];
  const hasGroups = groups.length > 0;

  return (
    <section className="fixtures-standings" aria-labelledby="fixtures-standings-title">
      <header className="fixtures-standings-head">
        <div>
          <span className="fixtures-hero-kicker">Season position</span>
          <h2 id="fixtures-standings-title">{hasGroups ? "Conference tables" : "League table"}</h2>
        </div>
        <span className={`standings-source${standings.is_official ? " is-official" : ""}`}>
          {standings.is_official
            ? standings.is_stale
              ? "Official · cached"
              : "Official"
            : "Calculated · completed matches"}
        </span>
      </header>

      {standings.warning ? <p className="inline-warning">{standings.warning}</p> : null}

      {hasGroups ? (
        <div className="fixtures-standings-groups">
          {groups.map((group) => (
            <section className="fixtures-standings-group" key={group.id}>
              <h3>{group.label}</h3>
              <StandingsTable rows={group.rows} label={`${group.label} standings`} />
            </section>
          ))}
        </div>
      ) : (
        <StandingsTable rows={standings.rows} />
      )}
    </section>
  );
}
