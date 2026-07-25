import Link from "next/link";
import { redirect } from "next/navigation";

import { MatchdayExplorer } from "../../../../components/MatchdayExplorer";
import { FixturesLeagueTable } from "../../../../components/FixturesLeagueTable";
import { RoundNavigator } from "../../../../components/RoundNavigator";
import { getFixtureRound, getFixtureRounds, getLeagueTable, getSeasons } from "../../../../lib/api";

type PageProps = {
  params: Promise<{ league: string; season: string }>;
  searchParams: Promise<{ round?: string }>;
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
  const { round: requestedRoundId } = await searchParams;
  const leagueName = formatLeagueName(league);

  let seasonData: Awaited<ReturnType<typeof getSeasons>>;
  try {
    seasonData = await getSeasons(league);
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

  let roundData: Awaited<ReturnType<typeof getFixtureRounds>>;
  try {
    roundData = await getFixtureRounds(league, season);
  } catch {
    return (
      <ErrorHero
        league={league}
        title="Fixtures could not be loaded."
        message={`The season list loaded, but fixture data for ${formatSeason(season)} is unavailable right now.`}
      />
    );
  }

  if (!roundData.rounds.length || !roundData.latest_round_id) {
    return (
      <ErrorHero
        league={league}
        title="No fixture rounds found yet."
        message={`No hosted matches are currently available for ${formatSeason(season)}.`}
      />
    );
  }

  const selectedRoundId = roundData.rounds.some((round) => round.id === requestedRoundId)
    ? String(requestedRoundId)
    : roundData.latest_round_id;

  const [selectedRoundResult, standingsResult] = await Promise.allSettled([
    getFixtureRound(league, season, selectedRoundId),
    getLeagueTable(league, season),
  ]);

  if (selectedRoundResult.status === "rejected") {
    return (
      <ErrorHero
        league={league}
        title="This fixture round could not be loaded."
        message={`Round data for ${formatSeason(season)} is temporarily unavailable.`}
      />
    );
  }
  const selectedRoundData = selectedRoundResult.value;
  const standings = standingsResult.status === "fulfilled" ? standingsResult.value : null;

  const logo = LEAGUE_LOGOS[league];
  const roundDateRange = formatRoundDateRange(
    selectedRoundData.round.start_date,
    selectedRoundData.round.end_date,
  );

  return (
    <div className="stack fixtures-page">
      <section className="fixtures-hero">
        <div className="fixtures-hero-title">
          {logo ? <img className="fixtures-hero-logo" src={logo} alt={`${leagueName} logo`} /> : null}
          <div>
            <span className="fixtures-hero-kicker">{leagueName}</span>
            <h1>{formatSeason(season)} fixtures</h1>
            <p className="fixtures-hero-sub">
              {roundDateRange} · {selectedRoundData.fixtures.length}{" "}
              {selectedRoundData.fixtures.length === 1 ? "match" : "matches"}
            </p>
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

      <RoundNavigator rounds={roundData.rounds} selectedRoundId={selectedRoundId} />

      <MatchdayExplorer
        league={league}
        fixtures={selectedRoundData.fixtures}
        roundLabel={
          selectedRoundData.round.metadata_source === "manifest"
            ? selectedRoundData.round.label
            : roundDateRange
        }
        roundStage={selectedRoundData.round.stage ?? "Selected round"}
      />

      {standings?.rows.length ? (
        <FixturesLeagueTable standings={standings} />
      ) : null}
    </div>
  );
}
