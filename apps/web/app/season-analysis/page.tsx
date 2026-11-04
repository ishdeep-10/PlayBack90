import Link from "next/link";
import { notFound } from "next/navigation";

import { SeasonLeaderboard } from "../../components/season/SeasonLeaderboard";
import { SeasonOverUnder } from "../../components/season/SeasonOverUnder";
import { SeasonZoneLeaders } from "../../components/season/SeasonZoneLeaders";
import { SeasonPlayerScatter } from "../../components/season/SeasonPlayerScatter";
import { SeasonTeamRadar } from "../../components/season/SeasonTeamRadar";
import { SeasonTeamScatter } from "../../components/season/SeasonTeamScatter";
import { SeasonTeamTrend } from "../../components/season/SeasonTeamTrend";
import { SeasonZonesChart } from "../../components/season/SeasonZones";
import { getLeagueTable, getSeasonAnalysisIndex, getSeasonTeamMetrics } from "../../lib/api";
import { leaguePresentation } from "../../lib/leagues";
import { getServerAuthToken } from "../../lib/serverAuth";
import { teamLogo } from "../../lib/stadiums";

export const metadata = { title: "Season analysis | PlayBack90" };
export const dynamic = "force-dynamic";

type PageProps = { searchParams: Promise<{ league?: string; season?: string; view?: string }> };

const ORDER = ["premier-league", "laliga", "bundesliga", "serie-a", "ligue-1", "mls", "champions-league", "europa-league"];
const VIEWS = [
  { id: "teams", label: "Teams" },
  { id: "players", label: "Players" },
];

/** "2025_2026" -> "2025/26"; a calendar-year season ("2026") stays as it is. */
function seasonTabLabel(season: string) {
  const [from, to] = season.split("_");
  return to ? `${from}/${to.slice(2)}` : from;
}

export default async function SeasonAnalysisPage({ searchParams }: PageProps) {
  const { league, season: seasonParam, view: viewParam } = await searchParams;
  const view = viewParam === "players" ? "players" : "teams";
  const token = await getServerAuthToken();

  let index;
  try {
    index = await getSeasonAnalysisIndex(token);
  } catch {
    notFound();
  }
  if (!index.length) notFound();
  // Competition order, newest season first within a league.
  index = [...index].sort((a, b) => ORDER.indexOf(a.league) - ORDER.indexOf(b.league) || b.season.localeCompare(a.season));
  const latest = index.filter((i, n) => index.findIndex((j) => j.league === i.league) === n);

  const current =
    index.find((i) => i.league === league && i.season === seasonParam) ?? latest.find((i) => i.league === league) ?? latest[0];
  const seasons = index.filter((i) => i.league === current.league);
  const presentation = leaguePresentation(current.league);

  // Team figures are small and drive the header; the player table (much larger) is fetched in the browser on demand.
  const data = await getSeasonTeamMetrics(current.league, current.season, token);

  // Crests: the standings provider's crest first, then the app's club-logo table (teams view only).
  const crests: Record<string, string> = {};
  if (view === "teams") {
    try {
      const standings = await getLeagueTable(current.league, current.season, token);
      const rows = [...standings.rows, ...standings.groups.flatMap((g) => g.rows)];
      for (const row of rows) if (row.crest) crests[row.team] = row.crest;
    } catch {
      // standings unavailable: fall back to the club-logo table below
    }
    for (const t of data.teams) {
      const logo = crests[t.team] ?? (typeof t.crest === "string" ? t.crest : null) ?? teamLogo(t.team);
      if (logo) crests[t.team] = logo;
    }
  }

  return (
    <main className="stack season-page">
      <header className="season-hero">
        <div className="season-hero-glow" aria-hidden="true" />
        <span className="season-kicker">Season analysis</span>
        <div className="season-title-row" key={`${current.league}-${current.season}`}>
          {presentation?.logo ? <img className="season-title-logo" src={presentation.logo} alt="" width={64} height={64} /> : null}
          <div>
            <h1 className="season-title">{data.league_name}</h1>
            <p className="season-sub">
              {data.season_label} · {data.matches} matches · updated {data.generated_at.slice(0, 10)}
            </p>
          </div>
        </div>

        <p className="season-tabs-hint">Select a logo to change the league</p>
        <nav className="season-league-tabs" aria-label="Competition">
          {latest.map((i, n) => {
            const p = leaguePresentation(i.league);
            const active = i.league === current.league;
            return (
              <Link
                key={i.league}
                href={{ pathname: "/season-analysis", query: { league: i.league, view } }}
                className={`season-logo-tab${active ? " is-active" : ""}`}
                style={{ animationDelay: `${n * 60}ms` }}
                aria-current={active ? "page" : undefined}
                aria-label={p?.name ?? i.league}
                title={p?.name ?? i.league}
                prefetch={false}
              >
                {p?.logo ? <img src={p.logo} alt="" width={34} height={34} /> : <span>{(p?.name ?? i.league).slice(0, 3)}</span>}
              </Link>
            );
          })}
        </nav>

        <nav className="season-view-tabs" aria-label="View">
          {VIEWS.map((v) => (
            <Link
              key={v.id}
              href={{ pathname: "/season-analysis", query: { league: current.league, season: current.season, view: v.id } }}
              className={`season-view-tab${v.id === view ? " is-active" : ""}`}
              aria-current={v.id === view ? "page" : undefined}
              prefetch={false}
            >
              {v.label}
            </Link>
          ))}
        </nav>

        {seasons.length > 1 ? (
          <nav className="season-view-tabs" aria-label="Season">
            {seasons.map((i) => (
              <Link
                key={i.season}
                href={{ pathname: "/season-analysis", query: { league: i.league, season: i.season, view } }}
                className={`season-view-tab${i.season === current.season ? " is-active" : ""}`}
                aria-current={i.season === current.season ? "page" : undefined}
                prefetch={false}
              >
                {seasonTabLabel(i.season)}
              </Link>
            ))}
          </nav>
        ) : null}
      </header>

      {view === "players" ? (
        <>
          <SeasonPlayerScatter key={`ps-${current.league}-${current.season}`} league={current.league} season={current.season} />
          <SeasonLeaderboard key={`lb-${current.league}-${current.season}`} league={current.league} season={current.season} />
          <SeasonZoneLeaders key={`zl-${current.league}-${current.season}`} league={current.league} season={current.season} />
          <SeasonOverUnder key={`ou-${current.league}-${current.season}`} league={current.league} season={current.season} />
        </>
      ) : (
        <>
          <SeasonTeamScatter key={`ts-${current.league}-${current.season}`} data={data} crests={crests} />
          <SeasonTeamRadar key={`tr-${current.league}-${current.season}`} data={data} />
          <SeasonTeamTrend key={`tt-${current.league}-${current.season}`} league={current.league} season={current.season} />
          <SeasonZonesChart key={`tz-${current.league}-${current.season}`} league={current.league} season={current.season} />
        </>
      )}
    </main>
  );
}
