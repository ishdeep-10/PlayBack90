import Link from "next/link";
import { redirect } from "next/navigation";
import type { Route } from "next";

import { MatchdayExplorer } from "../../../../components/MatchdayExplorer";
import { FixturesLeagueTable } from "../../../../components/FixturesLeagueTable";
import { RoundNavigator } from "../../../../components/RoundNavigator";
import { getFixtureHub, getLeagueTable, getSeasons } from "../../../../lib/api";
import { getServerAuthToken } from "../../../../lib/serverAuth";

type PageProps = {
  params: Promise<{ league: string; season: string }>;
  searchParams: Promise<{ round?: string; state?: string }>;
};

const LEAGUE_NAMES: Record<string, string> = {
  "premier-league": "Premier League",
  laliga: "La Liga",
  bundesliga: "Bundesliga",
  "serie-a": "Serie A",
  "ligue-1": "Ligue 1",
  "champions-league": "Champions League",
  "fifa-world-cup": "FIFA World Cup",
};

const LEAGUE_LOGOS: Record<string, string> = {
  "premier-league": "/logos/premier-league.png",
  laliga: "/logos/laliga.png",
  bundesliga: "/logos/bundesliga.png",
  "serie-a": "/logos/serie-a.png",
  "ligue-1": "/logos/ligue-1.png",
  "champions-league": "/logos/ucl.png",
};

function formatLeagueName(league: string) {
  return (
    LEAGUE_NAMES[league] ??
    league
      .split("-")
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(" ")
  );
}

function formatSeason(season: string) {
  return season.replace("_", "/");
}

const ROUND_DATE_FORMATTER = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "long",
  timeZone: "UTC",
});

function formatRoundDateRange(startDate: string, endDate: string) {
  const start = ROUND_DATE_FORMATTER.format(new Date(`${startDate}T00:00:00Z`));
  if (startDate === endDate) return start;
  const end = ROUND_DATE_FORMATTER.format(new Date(`${endDate}T00:00:00Z`));
  return `${start} - ${end}`;
}

function ErrorHero({ league, title, message }: { league: string; title: string; message: string }) {
  return (
    <div className="stack">
      <section className="hero">
        <span className="pill">{formatLeagueName(league)}</span>
        <div className="stack">
          <h1 style={{ fontSize: "clamp(2rem, 4vw, 3.6rem)" }}>{title}</h1>
          <p>{message}</p>
        </div>
        <div className="row">
          <Link href="/" className="ghost-button">
            Back to Coverage Map
          </Link>
          <Link href="/live-scrape" className="button">
            Import Match
          </Link>
        </div>
      </section>
    </div>
  );
}

export default async function FixturesPage({ params, searchParams }: PageProps) {
  const { league, season } = await params;
  const { round: requestedRoundId, state: requestedState } = await searchParams;
  const leagueName = formatLeagueName(league);
  const authToken = await getServerAuthToken();
  const fixtureState = ["all", "completed", "upcoming"].includes(String(requestedState))
    ? (requestedState as "all" | "completed" | "upcoming")
    : "all";

  let seasonData: Awaited<ReturnType<typeof getSeasons>>;
  try {
    seasonData = await getSeasons(league, authToken);
  } catch {
    return (
      <ErrorHero
        league={league}
        title="Match data is temporarily unavailable."
        message="The web app is running, but the PlayBack90 API is not reachable right now. Start the API service and reload this page to browse fixtures for this competition."
      />
    );
  }

  if (!seasonData.seasons.length) {
    return (
      <ErrorHero
        league={league}
        title="No seasons found yet."
        message="This league is covered on the landing map, but no hosted fixture seasons were returned by the API."
      />
    );
  }

  if (season === "latest") {
    redirect(`/matches/${league}/${seasonData.seasons[0]}`);
  }

  let fixtureHub: Awaited<ReturnType<typeof getFixtureHub>>;
  try {
    fixtureHub = await getFixtureHub(
      league,
      season,
      {
        state: fixtureState,
        ...(requestedRoundId ? { round: requestedRoundId } : {}),
      },
      authToken,
    );
  } catch {
    return (
      <ErrorHero
        league={league}
        title="Fixtures could not be loaded."
        message={`The season list loaded, but fixture data for ${formatSeason(season)} is unavailable right now.`}
      />
    );
  }

  if (!fixtureHub.rounds.length || !fixtureHub.selected_round_id) {
    return (
      <ErrorHero
        league={league}
        title="No fixture rounds found yet."
        message={`No completed or scheduled matches are currently available for ${formatSeason(season)}.`}
      />
    );
  }

  const selectedRoundId = fixtureHub.selected_round_id;
  const selectedRound = fixtureHub.rounds.find((round) => round.id === selectedRoundId) ?? fixtureHub.rounds[0];

  const standingsResult = await Promise.allSettled([getLeagueTable(league, season, authToken)]);
  const standings = standingsResult[0].status === "fulfilled" ? standingsResult[0].value : null;

  const logo = LEAGUE_LOGOS[league];
  const roundDateRange = formatRoundDateRange(
    selectedRound.start_date,
    selectedRound.end_date,
  );
  const stateOptions = [
    { id: "all", label: "All", count: fixtureHub.counts.all },
    { id: "completed", label: "Completed", count: fixtureHub.counts.completed },
    { id: "upcoming", label: "Upcoming", count: fixtureHub.counts.upcoming },
  ] as const;
  function stateHref(state: string) {
    const params = new URLSearchParams();
    params.set("state", state);
    if (selectedRoundId) params.set("round", selectedRoundId);
    return `/matches/${league}/${season}?${params.toString()}` as Route;
  }

  return (
    <div className="stack fixtures-page">
      <section className="fixtures-hero">
        <div className="fixtures-hero-title">
          {logo ? <img className="fixtures-hero-logo" src={logo} alt={`${leagueName} logo`} /> : null}
          <div>
            <span className="fixtures-hero-kicker">{leagueName}</span>
            <h1>{formatSeason(season)} fixtures</h1>
            <p className="fixtures-hero-sub">
              {roundDateRange} · {fixtureHub.fixtures.length}{" "}
              {fixtureHub.fixtures.length === 1 ? "match" : "matches"}
            </p>
            {fixtureHub.warning ? <p className="inline-warning">{fixtureHub.warning}</p> : null}
          </div>
        </div>
        {seasonData.seasons.length > 1 ? (
          <nav className="season-switcher" aria-label="Season">
            {seasonData.seasons.map((item) => (
              <Link
                key={item}
                href={`/matches/${league}/${item}`}
                className={item === season ? "season-pill is-active" : "season-pill"}
              >
                {formatSeason(item)}
              </Link>
            ))}
          </nav>
        ) : null}
      </section>

      <nav className="fixture-state-tabs" aria-label="Fixture state">
        {stateOptions.map((option) => (
          <Link
            key={option.id}
            href={stateHref(option.id)}
            className={fixtureState === option.id ? "season-pill is-active" : "season-pill"}
          >
            {option.label} <span>{option.count}</span>
          </Link>
        ))}
      </nav>

      {fixtureHub.counts.completed === 0 && fixtureHub.counts.upcoming > 0 ? (
        <section className="fixture-low-data-banner" aria-label="Schedule-only season notice">
          <strong>Schedule available, analysis pending</strong>
          <span>
            This season currently has upcoming fixtures but no completed PlayBack90 match data. Upcoming matches can open
            the opposition dossier workspace; post-match analysis appears once matches are scraped and enriched.
          </span>
        </section>
      ) : null}

      <RoundNavigator rounds={fixtureHub.rounds} selectedRoundId={selectedRoundId} />

      <MatchdayExplorer
        league={league}
        fixtures={fixtureHub.fixtures}
        roundLabel={
          selectedRound.metadata_source === "manifest"
            ? selectedRound.label
            : roundDateRange
        }
        roundStage={selectedRound.stage ?? "Selected round"}
      />

      {standings?.rows.length ? (
        <FixturesLeagueTable standings={standings} />
      ) : null}
    </div>
  );
}
