import Image from "next/image";
import Link from "next/link";
import type { Route } from "next";

import { OppositionLineupVisual } from "../../components/OppositionLineupVisual";
import { OppositionBuildUpTemperamentPitch, OppositionInPossessionPitchPlotly, OppositionRecentFormPlotly, OppositionStyleRadarPlotly } from "../../components/OppositionOverviewCharts";
import { getOppositionDossier, type OppositionDossier, type OppositionMetricRow } from "../../lib/api";
import { getServerAuthToken } from "../../lib/serverAuth";

type PageProps = {
  searchParams: Promise<{
    league?: string;
    season?: string;
    fixtureId?: string;
    home?: string;
    away?: string;
    referenceTeam?: string;
    opponentTeam?: string;
    sampleSize?: string;
    view?: string;
  }>;
};

const OPPOSITION_VIEWS = [
  { id: "overview", label: "Overview", status: "ready" },
  { id: "in-possession", label: "In Possession", status: "ready" },
  { id: "out-of-possession", label: "Out Of Possession", status: "planned" },
  { id: "players", label: "Players", status: "planned" },
  { id: "action-plan", label: "Action Plan", status: "planned" },
] as const;

type OppositionViewId = (typeof OPPOSITION_VIEWS)[number]["id"];

const CATEGORY_LABELS: Record<string, string> = {
  style: "Style",
  chance_profile: "Chance Profile",
  defensive_vulnerability: "Defensive Vulnerability",
};

const LOGO_LEAGUE_FOLDERS: Record<string, string> = {
  "premier-league": "England - Premier League",
  "la-liga": "Spain - LaLiga",
  laliga: "Spain - LaLiga",
  "serie-a": "Italy - Serie A",
  bundesliga: "Germany - Bundesliga",
};

const TEAM_LOGO_NAMES: Record<string, Record<string, string>> = {
  "premier-league": {
    Sunderland: "Sunderland AFC",
    Liverpool: "Liverpool FC",
    Arsenal: "Arsenal FC",
    Chelsea: "Chelsea FC",
    Fulham: "Fulham FC",
    Everton: "Everton FC",
    Brentford: "Brentford FC",
    Burnley: "Burnley FC",
    "Man City": "Manchester City",
    "Man Utd": "Manchester United",
    Bournemouth: "AFC Bournemouth",
    Brighton: "Brighton & Hove Albion",
    Leeds: "Leeds United",
    Newcastle: "Newcastle United",
    Tottenham: "Tottenham Hotspur",
    "West Ham": "West Ham United",
    Wolves: "Wolverhampton Wanderers",
    "Crystal Palace": "Crystal Palace",
    "Aston Villa": "Aston Villa",
    "Nottingham Forest": "Nottingham Forest",
    Leicester: "Leicester City",
    Southampton: "Southampton FC",
    Ipswich: "Ipswich Town",
  },
  "la-liga": {
    "Real Madrid": "Real Madrid",
    "Real Oviedo": "Real Oviedo",
    Elche: "Elche CF",
    "Real Betis": "Real Betis Balompié",
    "Deportivo Alaves": "Deportivo Alavés",
    "Atletico Madrid": "Atlético de Madrid",
    Osasuna: "CA Osasuna",
    Villarreal: "Villarreal CF",
    "Celta Vigo": "Celta de Vigo",
    Barcelona: "FC Barcelona",
    Levante: "Levante UD",
    "Real Sociedad": "Real Sociedad",
    Valencia: "Valencia CF",
    Mallorca: "RCD Mallorca",
    Espanyol: "RCD Espanyol Barcelona",
    "Atletic Club": "Athletic Bilbao",
    "Athletic Club": "Athletic Bilbao",
    "Rayo Vallecano": "Rayo Vallecano",
    Girona: "Girona FC",
    Sevilla: "Sevilla FC",
    Getafe: "Getafe CF",
  },
};

function normalizeLeagueKey(league?: string | null) {
  const key = String(league ?? "").trim().toLowerCase().replace(/\s+/g, "-");
  if (key === "laliga" || key === "spain---laliga") return "la-liga";
  if (key === "england---premier-league") return "premier-league";
  if (key === "italy---serie-a") return "serie-a";
  if (key === "germany---bundesliga") return "bundesliga";
  return key;
}

function teamLogoUrl(league: string | null | undefined, teamName?: string | null) {
  const leagueKey = normalizeLeagueKey(league);
  const folder = LOGO_LEAGUE_FOLDERS[leagueKey];
  if (!folder || !teamName) return null;

  const logoTeamName = TEAM_LOGO_NAMES[leagueKey]?.[teamName] ?? teamName;
  return `https://raw.githubusercontent.com/luukhopman/football-logos/master/logos/${encodeURIComponent(folder)}/${encodeURIComponent(logoTeamName)}.png`;
}

function formatSeason(season?: string) {
  return season ? season.replace("_", "/") : "Season pending";
}

function formatPoolStrategy(strategy?: string) {
  if (strategy === "previous_season") return "Previous season sample";
  if (strategy === "current_plus_previous") return "Current + previous season blend";
  if (strategy === "current_season") return "Current season sample";
  return "Sample context";
}

function formatMetric(value?: number, suffix = "") {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  return `${value.toFixed(value >= 10 ? 1 : 2)}${suffix}`;
}

function formatProfileMetric(row?: { value: number; unit?: string }) {
  return row ? formatMetric(row.value, row.unit ?? "") : "-";
}

function resultClass(result: string) {
  if (result === "W") return "is-win";
  if (result === "D") return "is-draw";
  if (result === "L") return "is-loss";
  return "";
}

function metricDirection(metric: OppositionMetricRow) {
  const delta = metric.value - metric.league_average;
  if (Math.abs(delta) < 0.05) return "Near league average";
  const direction = delta > 0 ? "above" : "below";
  return `${formatMetric(Math.abs(delta))} ${direction} league avg`;
}

function groupMetrics(metrics: OppositionMetricRow[]) {
  return metrics.reduce<Record<string, OppositionMetricRow[]>>((acc, metric) => {
    const key = metric.category || "profile";
    acc[key] = [...(acc[key] ?? []), metric];
    return acc;
  }, {});
}

function clamp(value: number, min = 0, max = 100) {
  return Math.max(min, Math.min(max, value));
}

function metricPercentile(metric?: OppositionMetricRow, fallback = 50) {
  return clamp(typeof metric?.percentile === "number" ? metric.percentile : fallback);
}

function riskPercentile(metric?: OppositionMetricRow, fallback = 50) {
  if (!metric) return fallback;
  return clamp(metric.higher_is_better ? 100 - metric.percentile : metric.percentile);
}

function metricByLabel(metrics: OppositionMetricRow[], label: string) {
  return metrics.find((metric) => metric.label.toLowerCase() === label.toLowerCase());
}

function metricByKey(metrics: OppositionMetricRow[], key: string) {
  return metrics.find((metric) => metric.metric === key);
}

function trendClass(value: number) {
  if (value >= 70) return "is-positive";
  if (value <= 35) return "is-risk";
  return "is-neutral";
}

function avg(values: number[]) {
  const filtered = values.filter((value) => Number.isFinite(value));
  return filtered.length ? filtered.reduce((sum, value) => sum + value, 0) / filtered.length : 50;
}

function formScore(record: { wins: number; draws: number; losses: number }) {
  const total = record.wins + record.draws + record.losses;
  if (!total) return 50;
  return clamp(((record.wins * 3 + record.draws) / (total * 3)) * 100);
}

function sampleRecord(matches: OppositionDossier["sampleContext"]["sample_matches"]) {
  return matches.reduce(
    (record, match) => {
      if (match.result === "W") record.wins += 1;
      else if (match.result === "D") record.draws += 1;
      else if (match.result === "L") record.losses += 1;
      return record;
    },
    { wins: 0, draws: 0, losses: 0 },
  );
}

function compactDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("en-GB", { day: "2-digit", month: "short" });
}

function visualMetricRows(metrics: OppositionMetricRow[]) {
  return [
    metricByLabel(metrics, "Possession"),
    metricByLabel(metrics, "Pass accuracy"),
    metricByLabel(metrics, "Field tilt"),
    metricByLabel(metrics, "Box entries"),
    metricByLabel(metrics, "xG"),
    metricByLabel(metrics, "xGA"),
  ].filter((metric): metric is OppositionMetricRow => Boolean(metric));
}

function buildDossierHref(params: {
  league: string;
  season: string;
  fixtureId?: string;
  home?: string;
  away?: string;
  referenceTeam: string;
  opponentTeam: string;
  sampleSize: number;
  view?: OppositionViewId;
}) {
  const query = new URLSearchParams({
    league: params.league,
    season: params.season,
    referenceTeam: params.referenceTeam,
    opponentTeam: params.opponentTeam,
    sampleSize: String(params.sampleSize),
  });
  if (params.view && params.view !== "overview") query.set("view", params.view);
  if (params.fixtureId) query.set("fixtureId", params.fixtureId);
  if (params.home) query.set("home", params.home);
  if (params.away) query.set("away", params.away);
  return `/opposition-analysis?${query.toString()}`;
}

function safeView(value?: string): OppositionViewId {
  return OPPOSITION_VIEWS.some((view) => view.id === value) ? value as OppositionViewId : "overview";
}

function safeSegment(value: string) {
  return value.replace(/[^a-z0-9]+/gi, "-").replace(/^-+|-+$/g, "").toLowerCase();
}

function ComingSoon() {
  return (
    <div className="opposition-page stack">
      <section className="opposition-hero">
        <span className="eyebrow">Opposition Analysis</span>
        <h1>Coming soon</h1>
        <p>Opposition Analysis is still under development and isn&apos;t available in this beta yet.</p>
        <Link className="primary-action" href="/">
          Go to league map
        </Link>
      </section>
    </div>
  );
}

function MissingContext() {
  return (
    <div className="opposition-page stack">
      <section className="opposition-hero">
        <span className="eyebrow">Opposition Analysis</span>
        <h1>Choose an upcoming fixture</h1>
        <p>
          Opposition Analysis is built from the fixture hub so the report can understand the match, reference team, and opponent.
        </p>
        <Link className="primary-action" href="/">
          Go to league map
        </Link>
      </section>
    </div>
  );
}

function LoadError({ message, league, season }: { message: string; league?: string; season?: string }) {
  const href = league && season ? `/matches/${encodeURIComponent(league)}/${encodeURIComponent(season)}` : "/";
  return (
    <div className="opposition-page stack">
      <section className="opposition-hero">
        <span className="eyebrow">Opposition Analysis</span>
        <h1>Dossier data is not available yet</h1>
        <p>{message}</p>
        <Link className="primary-action" href={href as Route}>
          Back to fixtures
        </Link>
      </section>
    </div>
  );
}

function ReportControls({
  dossier,
  fixtureId,
  sampleSize,
  view,
}: {
  dossier: OppositionDossier;
  fixtureId?: string;
  sampleSize: number;
  view: OppositionViewId;
}) {
  const fixture = dossier.fixtureContext;
  const home = fixture.home_team ?? undefined;
  const away = fixture.away_team ?? undefined;
  const league = dossier.meta.league;
  const season = dossier.meta.fixture_season;
  const referenceOptions = [home, away].filter((team): team is string => Boolean(team));
  const sampleOptions = [3, 5, 10];

  return (
    <div className="opposition-control-grid">
      {referenceOptions.length === 2 ? (
        <div className="opposition-control-group">
          <span>Reference</span>
          <div className="opposition-control-pills">
            {referenceOptions.map((team) => {
              const opponentTeam = team === home ? away : home;
              if (!opponentTeam) return null;
              const href = buildDossierHref({
                league,
                season,
                fixtureId,
                home,
                away,
                referenceTeam: team,
                opponentTeam,
                sampleSize,
                view,
              });
              return (
                <Link
                  key={team}
                  href={href as Route}
                  className={team === dossier.meta.reference_team ? "season-pill is-active" : "season-pill"}
                >
                  {teamLogoUrl(league, team) ? <Image src={teamLogoUrl(league, team)!} alt={`${team} logo`} width={18} height={18} className="opposition-pill-logo" /> : null}
                  {team}
                </Link>
              );
            })}
          </div>
        </div>
      ) : null}
      <div className="opposition-control-group">
        <span>Sample</span>
        <div className="opposition-control-pills">
          {sampleOptions.map((size) => {
            const href = buildDossierHref({
              league,
              season,
              fixtureId,
              home,
              away,
              referenceTeam: dossier.meta.reference_team,
              opponentTeam: dossier.meta.opponent_team,
              sampleSize: size,
              view,
            });
            return (
              <Link
                key={size}
                href={href as Route}
                className={size === sampleSize ? "season-pill is-active" : "season-pill"}
              >
                {size}
              </Link>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function MatchupHeader({
  dossier,
  fixtureId,
  sampleSize,
  view,
}: {
  dossier: OppositionDossier;
  fixtureId?: string;
  sampleSize: number;
  view: OppositionViewId;
}) {
  const fixture = dossier.fixtureContext;
  const matchup = fixture.home_team && fixture.away_team ? `${fixture.home_team} vs ${fixture.away_team}` : "Fixture context";
  const opponentLogo = teamLogoUrl(dossier.meta.league, dossier.meta.opponent_team);
  const homeLogo = teamLogoUrl(dossier.meta.league, fixture.home_team);
  const awayLogo = teamLogoUrl(dossier.meta.league, fixture.away_team);

  return (
    <section className="opposition-hero opposition-export-scope">
      <div className="opposition-hero-grid">
        <div>
          <span className="eyebrow">Opposition Analysis</span>
          <div className="opposition-title-row">
            {opponentLogo ? <Image src={opponentLogo} alt={`${dossier.meta.opponent_team} logo`} width={54} height={54} className="opposition-team-logo" /> : null}
            <h1>{dossier.meta.opponent_team}</h1>
          </div>
          <div className="opposition-fixture-logos">
            {homeLogo ? <Image src={homeLogo} alt={`${fixture.home_team} logo`} width={28} height={28} /> : null}
            <span>{matchup}</span>
            {awayLogo ? <Image src={awayLogo} alt={`${fixture.away_team} logo`} width={28} height={28} /> : null}
          </div>
        </div>
        <div className="opposition-context-panel" aria-label="Report context">
          <span>{dossier.meta.league.replaceAll("-", " ")}</span>
          <strong>{formatSeason(dossier.meta.fixture_season)}</strong>
          <small>{formatPoolStrategy(dossier.sampleContext.pool_strategy)}</small>
        </div>
      </div>
      <div className="opposition-toolbar">
        <ReportControls dossier={dossier} fixtureId={fixtureId} sampleSize={sampleSize} view={view} />
      </div>
    </section>
  );
}

function buildTabHref({
  dossier,
  fixtureId,
  sampleSize,
  view,
}: {
  dossier: OppositionDossier;
  fixtureId?: string;
  sampleSize: number;
  view: OppositionViewId;
}) {
  const fixture = dossier.fixtureContext;
  return buildDossierHref({
    league: dossier.meta.league,
    season: dossier.meta.fixture_season,
    fixtureId,
    home: fixture.home_team ?? undefined,
    away: fixture.away_team ?? undefined,
    referenceTeam: dossier.meta.reference_team,
    opponentTeam: dossier.meta.opponent_team,
    sampleSize,
    view,
  });
}

function OppositionTabBar({
  dossier,
  fixtureId,
  sampleSize,
  activeView,
}: {
  dossier: OppositionDossier;
  fixtureId?: string;
  sampleSize: number;
  activeView: OppositionViewId;
}) {
  return (
    <div className="tab-bar-row opposition-tab-row">
      <nav className="tab-bar opposition-tab-bar" aria-label="Opposition report views">
        {OPPOSITION_VIEWS.map((view) => (
          <Link
            key={view.id}
            href={buildTabHref({ dossier, fixtureId, sampleSize, view: view.id }) as Route}
            prefetch={false}
            aria-current={activeView === view.id ? "page" : undefined}
            className={`tab-link${activeView === view.id ? " active" : ""}${view.status === "planned" ? " is-planned" : ""}`}
          >
            {view.label}
          </Link>
        ))}
      </nav>
    </div>
  );
}

function ExecutiveSummary({ dossier }: { dossier: OppositionDossier }) {
  const sample = dossier.sampleContext;
  return (
    <section className="opposition-section">
      <div className="opposition-section-header">
        <div>
          <span className="eyebrow">Executive Summary</span>
          <h2>What matters first</h2>
        </div>
      </div>
      <div className="opposition-summary-grid">
        <div className="opposition-panel">
          <ul className="opposition-bullets">
            {dossier.summary.bullets.length ? (
              dossier.summary.bullets.map((item: string) => <li key={item}>{item}</li>)
            ) : (
              <li>Not enough completed data yet for confident summary bullets.</li>
            )}
          </ul>
        </div>
        <div className="opposition-sample-card">
          <span>Analysis sample</span>
          <strong>{sample.actual_sample_size}/{sample.requested_sample_size}</strong>
          <small>{sample.pool_seasons.map(formatSeason).join(", ")}</small>
          <small>{sample.sample_strategy.replaceAll("_", " ")}</small>
        </div>
      </div>
      {sample.warnings.length ? (
        <p className="opposition-warning">{sample.warnings.join(" ")}</p>
      ) : null}
    </section>
  );
}

function StrengthWeaknessPanel({ title, rows, empty }: { title: string; rows: OppositionMetricRow[]; empty: string }) {
  return (
    <div className="opposition-panel">
      <h3>{title}</h3>
      <div className="opposition-signal-list">
        {rows.length ? (
          rows.map((metric) => (
            <div key={`${title}-${metric.metric}`} className="opposition-signal">
              <div>
                <strong>{metric.label}</strong>
                <span>{metricDirection(metric)}</span>
              </div>
              <b>{formatMetric(metric.percentile, "%")}</b>
            </div>
          ))
        ) : (
          <p className="muted">{empty}</p>
        )}
      </div>
    </div>
  );
}

function TeamProfile({ dossier }: { dossier: OppositionDossier }) {
  const groups = groupMetrics(dossier.teamProfile.metrics);
  return (
    <section className="opposition-section">
      <div className="opposition-section-header">
        <div>
          <span className="eyebrow">Team Profile</span>
          <h2>{dossier.teamProfile.team} against this sample</h2>
        </div>
        <span className="opposition-subtle">{dossier.teamProfile.match_count} season rows in pool</span>
      </div>
      <div className="opposition-profile-groups">
        {Object.entries(groups).map(([category, metrics]) => (
          <div key={category} className="opposition-panel">
            <h3>{CATEGORY_LABELS[category] ?? category}</h3>
            <div className="opposition-metric-grid">
              {metrics.map((metric) => (
                <div key={metric.metric} className="opposition-metric">
                  <span>{metric.label}</span>
                  <strong>{formatMetric(metric.value)}</strong>
                  <small>{metricDirection(metric)}</small>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function RecentForm({ dossier }: { dossier: OppositionDossier }) {
  const form = dossier.recentForm;
  return (
    <section className="opposition-section">
      <div className="opposition-section-header">
        <div>
          <span className="eyebrow">Recent Form</span>
          <h2>Last {form.window} completed matches</h2>
        </div>
        <span className="opposition-subtle">
          {form.record.wins}W {form.record.draws}D {form.record.losses}L
        </span>
      </div>
      <div className="opposition-form-grid">
        <div className="opposition-panel">
          <div className="opposition-match-list">
            {form.matches.map((match: OppositionDossier["recentForm"]["matches"][number]) => (
              <div key={match.match_id} className="opposition-match-row">
                <span className={`opposition-result ${resultClass(match.result)}`}>{match.result}</span>
                <div>
                  <strong>{match.opponent}</strong>
                  <small>{match.date} · {match.home_away === "h" ? "Home" : match.home_away === "a" ? "Away" : "Venue n/a"}</small>
                </div>
                <b>{match.score}</b>
                <small>xG {formatMetric(match.xg)} - {formatMetric(match.xga)}</small>
              </div>
            ))}
          </div>
        </div>
        <div className="opposition-panel">
          <h3>Recent averages</h3>
          <div className="opposition-metric-grid is-compact">
            {Object.entries(form.averages).map(([key, value]: [string, number]) => (
              <div key={key} className="opposition-metric">
                <span>{key.replaceAll("_", " ")}</span>
                <strong>{formatMetric(value)}</strong>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function ComparableMatches({ dossier }: { dossier: OppositionDossier }) {
  return (
    <section className="opposition-section">
      <div className="opposition-section-header">
        <div>
          <span className="eyebrow">Comparable Matchups</span>
          <h2>Opponent versus similar references</h2>
        </div>
      </div>
      <div className="opposition-comparable-grid">
        <div className="opposition-panel">
          <h3>Sample matches</h3>
          <div className="opposition-match-list">
            {dossier.sampleContext.sample_matches.map((match: OppositionDossier["sampleContext"]["sample_matches"][number]) => (
              <div key={match.match_id} className="opposition-match-row">
                <span className={`opposition-result ${resultClass(match.result)}`}>{match.result}</span>
                <div>
                  <strong>{match.opponent}</strong>
                  <small>{formatSeason(match.season)} · {match.date} · {match.sample_reason.replaceAll("_", " ")}</small>
                </div>
                <b>{match.score}</b>
                <small>xG {formatMetric(match.xg)} - {formatMetric(match.xga)}</small>
              </div>
            ))}
          </div>
        </div>
        <div className="opposition-panel">
          <h3>Closest style peers</h3>
          <div className="opposition-peer-list">
            {dossier.sampleContext.similar_teams.slice(0, 6).map((peer: OppositionDossier["sampleContext"]["similar_teams"][number]) => (
              <div key={peer.team} className="opposition-peer">
                <span>{peer.team}</span>
                <strong>{formatMetric(peer.similarity, "%")}</strong>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function KeyPlayers({ dossier }: { dossier: OppositionDossier }) {
  return (
    <section className="opposition-section">
      <div className="opposition-section-header">
        <div>
          <span className="eyebrow">Key Players</span>
          <h2>Threat board</h2>
        </div>
      </div>
      <div className="opposition-player-grid">
        {dossier.keyPlayers.map((player: OppositionDossier["keyPlayers"][number]) => (
          <div key={player.player} className="opposition-player-card">
            <strong>{player.player}</strong>
            <div>
              <span>{player.goals} G</span>
              <span>{formatMetric(player.xg)} xG</span>
              <span>{formatMetric(player.xa)} xA</span>
              <span>{player.shots} shots</span>
            </div>
            <small>{player.mins} mins</small>
          </div>
        ))}
      </div>
    </section>
  );
}

function OverviewKpiStrip({ dossier }: { dossier: OppositionDossier }) {
  const metrics = dossier.teamProfile.metrics;
  const record = sampleRecord(dossier.sampleContext.sample_matches);
  const attackScore = avg([
    metricPercentile(metricByLabel(metrics, "xG")),
    metricPercentile(metricByLabel(metrics, "Shots")),
    metricPercentile(metricByLabel(metrics, "Big chances")),
  ]);
  const vulnerabilityScore = avg([
    riskPercentile(metricByLabel(metrics, "xGA")),
    riskPercentile(metricByLabel(metrics, "Shots conceded")),
    riskPercentile(metricByLabel(metrics, "Goals conceded")),
  ]);
  const confidenceScore = clamp((dossier.sampleContext.actual_sample_size / Math.max(1, dossier.sampleContext.requested_sample_size)) * 100);
  const cards = [
    {
      label: "Form",
      value: `${record.wins}W ${record.draws}D ${record.losses}L`,
      score: formScore(record),
      sub: `${dossier.sampleContext.actual_sample_size} match sample`,
    },
    {
      label: "Attack Threat",
      value: formatMetric(metricByLabel(metrics, "xG")?.value),
      score: attackScore,
      sub: "xG sample avg",
    },
    {
      label: "Defensive Risk",
      value: formatMetric(metricByLabel(metrics, "xGA")?.value),
      score: vulnerabilityScore,
      sub: "xGA sample avg",
    },
    {
      label: "Sample Fit",
      value: `${dossier.sampleContext.actual_sample_size}/${dossier.sampleContext.requested_sample_size}`,
      score: confidenceScore,
      sub: dossier.summary.confidence,
    },
  ];

  return (
    <section className="opposition-overview-kpis" aria-label="Opposition overview key metrics">
      {cards.map((card) => (
        <div key={card.label} className={`opposition-kpi-card ${trendClass(card.score)}`}>
          <span>{card.label}</span>
          <strong>{card.value}</strong>
          <small>{card.sub}</small>
          <div className="opposition-kpi-track" aria-hidden="true">
            <i style={{ width: `${card.score}%` }} />
          </div>
        </div>
      ))}
    </section>
  );
}

function CoachSquadContext({ dossier }: { dossier: OppositionDossier }) {
  const teamContext = dossier.teamContext;
  const opponent = teamContext?.teams?.opponent;
  if (!opponent) {
    return (
      <section className="opposition-visual-panel">
        <div className="opposition-visual-head">
          <div>
            <span className="eyebrow">Team Context</span>
            <h2>Coach and transfer status</h2>
          </div>
        </div>
        <p className="opposition-empty-note">{teamContext?.warning ?? "Coach and transfer context is not available for this fixture yet."}</p>
      </section>
    );
  }

  const coach = opponent.coach;
  const change = opponent.coach_change;
  const squad = opponent.squad_changes;
  const transfers = opponent.transfer_activity;
  const crest = opponent.crest || teamLogoUrl(dossier.meta.league, opponent.team);
  const incomingCount = transfers?.incoming_count ?? 0;
  const outgoingCount = transfers?.outgoing_count ?? 0;
  const coachStatus = (change?.status || "unknown").replace(/[^a-z0-9_-]/gi, "").toLowerCase();

  return (
    <section className="opposition-visual-panel">
      <div className="opposition-visual-head">
        <div>
          <span className="eyebrow">Team Context</span>
          <h2>Coach and transfer activity</h2>
        </div>
        <span className="opposition-subtle">Analysed opponent only</span>
      </div>
      <div className="opposition-team-context-card opposition-team-context-card-wide">
        <div className="opposition-context-main">
          <div className="opposition-context-team-head">
            {crest ? <Image src={crest} alt={`${opponent.team} logo`} width={42} height={42} /> : null}
            <div>
              <strong>{opponent.team}</strong>
              <span>Opponent being analysed</span>
            </div>
          </div>
          <div className={`opposition-context-coach-card is-${coachStatus}`}>
            <span>Coach</span>
            <strong>{coach?.name || "Unavailable"}</strong>
            <small>{coach?.name ? change?.label ?? "Change status unknown" : "Coach data is not currently populated by the configured providers."}</small>
            <i aria-hidden="true" />
          </div>
        </div>
        <div className="opposition-context-squad">
          <div className="is-in">
            <span>Incomings</span>
            <strong>{incomingCount}</strong>
          </div>
          <div className="is-out">
            <span>Outgoings</span>
            <strong>{outgoingCount}</strong>
          </div>
          <div>
            <span>Squad</span>
            <strong>{squad?.current_squad_count ?? "-"}</strong>
          </div>
        </div>
        {transfers?.available ? (
          <TransferActivityTables transfers={transfers} />
        ) : (
          <p className="opposition-provider-note">{transfers?.warning ?? "Transfer activity is not available for this team yet."}</p>
        )}
      </div>
      <p className="opposition-context-note">
        Transfers are filtered to the fixture season window. Squad count comes from FootballData registration data.
      </p>
    </section>
  );
}

type TransferActivity = NonNullable<NonNullable<OppositionDossier["teamContext"]>["teams"][string]["transfer_activity"]>;
type TransferItem = TransferActivity["incomings"][number];

function transferInitials(name: string) {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

function transferValueScore(item: TransferItem) {
  const raw = String(item.type || "");
  const match = raw.match(/€\s?([\d.]+)\s?([mk])?/i);
  if (!match) return 0;
  const value = Number(match[1]);
  if (!Number.isFinite(value)) return 0;
  const unit = match[2]?.toLowerCase();
  return unit === "k" ? value * 1_000 : value * 1_000_000;
}

function sortedTransfers(rows: TransferItem[]) {
  return [...rows].sort((a, b) => {
    const valueDiff = transferValueScore(b) - transferValueScore(a);
    if (valueDiff) return valueDiff;
    return String(b.date || "").localeCompare(String(a.date || ""));
  });
}

function TransferActivityTables({ transfers }: { transfers: TransferActivity }) {
  if (!transfers.incomings?.length && !transfers.outgoings?.length) {
    return <p className="opposition-empty-note">No incoming or outgoing transfers found for this season window.</p>;
  }
  return (
    <div className="opposition-transfer-tables">
      <TransferTable title="Incomings" direction="in" rows={sortedTransfers(transfers.incomings ?? [])} />
      <TransferTable title="Outgoings" direction="out" rows={sortedTransfers(transfers.outgoings ?? [])} />
    </div>
  );
}

function TransferTable({ title, direction, rows }: { title: string; direction: "in" | "out"; rows: TransferItem[] }) {
  return (
    <details className={`opposition-transfer-details is-${direction}`}>
      <summary>
        <div className="opposition-transfer-summary-main">
          <span>{title}</span>
          <strong>{rows.length}</strong>
        </div>
      </summary>
      <div className="opposition-transfer-table-wrap">
        <table className="opposition-transfer-table">
          <thead>
            <tr>
              <th>Player</th>
              <th>{direction === "in" ? "From" : "To"}</th>
              <th>Type / value</th>
              <th>Date</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((item) => {
              const club = (direction === "in" ? item.from_team : item.to_team) || (item.type === "Free agent" ? "Free agent" : "Club not listed");
              return (
                <tr key={`${direction}-${item.player_id ?? item.player}-${item.date}-${club}`}>
                  <td>
                    <span className="opposition-transfer-player">
                      {item.image ? (
                        <Image unoptimized src={item.image} alt={`${item.player} headshot`} width={30} height={30} />
                      ) : (
                        <span className="opposition-transfer-avatar">{transferInitials(item.player)}</span>
                      )}
                      <strong>{item.player}</strong>
                    </span>
                  </td>
                  <td>
                    <span className="opposition-transfer-club">
                      {club}
                    </span>
                  </td>
                  <td><b className={`opposition-transfer-type is-${direction}`}>{item.type || "N/A"}</b></td>
                  <td>{item.date || "-"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </details>
  );
}

type LineupContextPayload = NonNullable<OppositionDossier["lineupContext"]>;
type LineupMatch = NonNullable<LineupContextPayload["matches"]>[number];

function LineupContext({ dossier }: { dossier: OppositionDossier }) {
  const context = dossier.lineupContext;
  const recent = context?.latest_match ?? context?.matches?.[0];
  const logo = teamLogoUrl(dossier.meta.league, dossier.meta.opponent_team);

  if (!context?.available) {
    return (
      <section className="opposition-visual-panel">
        <div className="opposition-visual-head">
          <div>
            <span className="eyebrow">Lineups</span>
            <h2>Shape history</h2>
          </div>
        </div>
        <p className="opposition-empty-note">{context?.warning ?? "Recent lineup and formation history is not available yet."}</p>
      </section>
    );
  }

  const latestView = {
    id: "last",
    label: "Last Match XI",
    team: dossier.meta.opponent_team,
    formation: recent?.formation,
    subtitle: recent ? `${recent.date} vs ${recent.opponent}` : "No recent XI found.",
    players: recent?.starters ?? [],
  };
  const sampleViews = (context.matches ?? []).map((match: LineupMatch, index: number) => ({
    id: `sample-${match.match_id || index}`,
    label: `${match.date} vs ${match.opponent} (${match.formation || "shape unknown"})`,
    team: dossier.meta.opponent_team,
    formation: match.formation,
    subtitle: `${match.date} vs ${match.opponent} · recent lineup ${index + 1}/${context.matches?.length ?? 0}`,
    players: match.starters ?? [],
  }));

  return (
    <section className="opposition-visual-panel">
      <div className="opposition-visual-head">
        <div className="opposition-visual-title">
          {logo ? <Image src={logo} alt={`${dossier.meta.opponent_team} logo`} width={34} height={34} className="opposition-mini-logo" /> : null}
          <div>
            <span className="eyebrow">Lineups</span>
            <h2>Shape and squad signals</h2>
          </div>
        </div>
        <span className="opposition-subtle">{context.sample_match_count ?? sampleViews.length} matches</span>
      </div>
      <OppositionLineupVisual latestView={latestView} sampleViews={sampleViews} teamColor="#22c55e" />
    </section>
  );
}

function StyleRadar({ dossier }: { dossier: OppositionDossier }) {
  const rows = visualMetricRows(dossier.teamProfile.metrics);
  const logo = teamLogoUrl(dossier.meta.league, dossier.meta.opponent_team);

  return (
    <section className="opposition-visual-panel opposition-style-radar">
      <div className="opposition-visual-head">
        <div className="opposition-visual-title">
          {logo ? <Image src={logo} alt={`${dossier.meta.opponent_team} logo`} width={34} height={34} className="opposition-mini-logo" /> : null}
          <div>
          <span className="eyebrow">Style Fingerprint</span>
          <h2>{dossier.meta.opponent_team} profile</h2>
          </div>
        </div>
        <span className="opposition-subtle">Percentile vs league pool</span>
      </div>
      <div className="opposition-radar-wrap">
        <OppositionStyleRadarPlotly radarMetrics={rows} />
        <div className="opposition-radar-stat-grid">
          {rows.map((metric) => (
            <div key={metric.metric}>
              <span>{metric.label}</span>
              <strong>{formatMetric(metric.value)}</strong>
              <small>{formatMetric(metric.percentile, "%")}</small>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function SignalBars({ title, rows, mode }: { title: string; rows: OppositionMetricRow[]; mode: "strength" | "risk" }) {
  const displayRows = rows.slice(0, 4);
  return (
    <div className={`opposition-visual-panel opposition-signal-bars is-${mode}`}>
      <div className="opposition-visual-head">
        <div>
          <span className="eyebrow">{mode === "strength" ? "Strengths" : "Vulnerabilities"}</span>
          <h2>{title}</h2>
        </div>
      </div>
      <div className="opposition-bar-list">
        {displayRows.length ? displayRows.map((metric) => {
          const score = mode === "risk" ? 100 - metric.percentile : metric.percentile;
          return (
            <div key={`${mode}-${metric.metric}`} className="opposition-bar-row">
              <div>
                <strong>{metric.label}</strong>
                <span>{metricDirection(metric)}</span>
              </div>
              <div className="opposition-bar-track" aria-hidden="true">
                <i style={{ width: `${clamp(score)}%` }} />
              </div>
              <b>{formatMetric(mode === "risk" ? 100 - metric.percentile : metric.percentile, "%")}</b>
            </div>
          );
        }) : (
          <p className="opposition-empty-note">{mode === "strength" ? "No standout positive indicators in this sample." : "No major vulnerability indicators in this sample."}</p>
        )}
      </div>
    </div>
  );
}

function TeamProfileBars({ dossier }: { dossier: OppositionDossier }) {
  const groups = groupMetrics(dossier.teamProfile.metrics);
  return (
    <section className="opposition-visual-panel">
      <div className="opposition-visual-head">
        <div>
          <span className="eyebrow">Team Profile</span>
          <h2>Opponent vs league average</h2>
        </div>
        <span className="opposition-subtle">{dossier.teamProfile.match_count} rows in pool</span>
      </div>
      <div className="opposition-profile-bars">
        {Object.entries(groups).map(([category, metrics]) => (
          <div key={category} className="opposition-profile-bar-group">
            <h3>{CATEGORY_LABELS[category] ?? category}</h3>
            {metrics.slice(0, 5).map((metric) => {
              const valuePct = clamp(metricPercentile(metric));
              return (
                <div key={metric.metric} className="opposition-profile-bar">
                  <div>
                    <span>{metric.label}</span>
                    <strong>{formatMetric(metric.value)}</strong>
                  </div>
                  <div className="opposition-bar-track" aria-hidden="true">
                    <i style={{ width: `${valuePct}%` }} />
                    <em />
                  </div>
                  <small>{metricDirection(metric)}</small>
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </section>
  );
}

function RecentFormVisual({ dossier }: { dossier: OppositionDossier }) {
  const matches = [...dossier.recentForm.matches].reverse();
  const opponentLogos = Object.fromEntries(
    dossier.recentForm.matches.map((match) => [match.opponent, teamLogoUrl(dossier.meta.league, match.opponent)]),
  );

  return (
    <section className="opposition-visual-panel opposition-form-visual">
      <div className="opposition-visual-head">
        <div>
          <span className="eyebrow">Recent Form</span>
          <h2>xG trend over last {dossier.recentForm.window}</h2>
        </div>
        <span className="opposition-subtle">{dossier.recentForm.record.wins}W {dossier.recentForm.record.draws}D {dossier.recentForm.record.losses}L</span>
      </div>
      <OppositionRecentFormPlotly recentMatches={dossier.recentForm.matches} opponentLogos={opponentLogos} />
      <div className="opposition-form-result-strip">
        {matches.map((match) => (
          <div key={`strip-${match.match_id}`} className="opposition-form-result">
            <span className={`opposition-result ${resultClass(match.result)}`}>{match.result}</span>
            <strong>{match.score}</strong>
            <small>{match.opponent}</small>
          </div>
        ))}
      </div>
    </section>
  );
}

type HomeAwayRow = NonNullable<OppositionDossier["homeAwaySplit"]>["rows"][number];
type GameStateRow = NonNullable<OppositionDossier["gameStateProfile"]>["rows"][number];

function resultRecord(matches: Array<{ result: string }>) {
  return {
    wins: matches.filter((match) => match.result === "W").length,
    draws: matches.filter((match) => match.result === "D").length,
    losses: matches.filter((match) => match.result === "L").length,
  };
}

function sampleHomeAwayRows(dossier: OppositionDossier): HomeAwayRow[] {
  const matches = dossier.sampleContext.sample_matches;
  return ([
    ["h", "Home"],
    ["a", "Away"],
  ] as const).flatMap(([venue, label]) => {
    const scoped = matches.filter((match) => String(match.home_away).toLowerCase() === venue);
    if (!scoped.length) return [];
    const mean = (values: number[]) => {
      const valid = values.filter((value) => Number.isFinite(value));
      return valid.length ? valid.reduce((sum, value) => sum + value, 0) / valid.length : 0;
    };
    return [{
      venue,
      label,
      match_count: scoped.length,
      record: resultRecord(scoped),
      metrics: {
        xG: mean(scoped.map((match) => match.xg)),
        xG_against: mean(scoped.map((match) => match.xga)),
        shots: mean(scoped.map((match) => match.shots)),
        shots_against: mean(scoped.map((match) => match.shots_against)),
        possession_pct: mean(scoped.map((match) => match.possession_pct ?? 0).filter((value) => value > 0)),
        ppda: mean(scoped.map((match) => match.ppda ?? 0).filter((value) => value > 0)),
      },
    }];
  });
}

function sampleResultStateRows(dossier: OppositionDossier): GameStateRow[] {
  const groups = [
    { state: "leading", label: "Wins", results: ["W"] },
    { state: "level", label: "Draws", results: ["D"] },
    { state: "trailing", label: "Losses", results: ["L"] },
  ];
  return groups.map((group) => {
    const scoped = dossier.sampleContext.sample_matches.filter((match) => group.results.includes(match.result));
    const matchCount = scoped.length;
    const xG = scoped.reduce((sum, match) => sum + match.xg, 0);
    const xGA = scoped.reduce((sum, match) => sum + match.xga, 0);
    return {
      state: group.state,
      label: group.label,
      match_count: matchCount,
      shots: scoped.reduce((sum, match) => sum + match.shots, 0),
      shots_against: scoped.reduce((sum, match) => sum + match.shots_against, 0),
      xG,
      xGA,
      xG_per_match: matchCount ? xG / matchCount : 0,
      xGA_per_match: matchCount ? xGA / matchCount : 0,
    };
  });
}

function HomeAwaySplitVisual({ dossier }: { dossier: OppositionDossier }) {
  const split = dossier.homeAwaySplit;
  const rows = split?.available && split.rows.length ? split.rows : sampleHomeAwayRows(dossier);
  const maxXg = Math.max(1, ...rows.flatMap((row) => [row.metrics.xG ?? 0, row.metrics.xG_against ?? 0]));

  return (
    <section className="opposition-visual-panel opposition-split-visual">
      <div className="opposition-visual-head">
        <div>
          <span className="eyebrow">Home / Away</span>
          <h2>Venue split in selected sample</h2>
        </div>
        <span className="opposition-subtle">{rows.reduce((sum, row) => sum + row.match_count, 0)} matches</span>
      </div>
      {rows.length ? (
        <div className="opposition-home-away-grid">
          {rows.map((row) => (
            <div key={row.venue} className="opposition-home-away-card">
              <div className="opposition-home-away-head">
                <div>
                  <span>{row.label}</span>
                  <strong>{row.record.wins}W {row.record.draws}D {row.record.losses}L</strong>
                </div>
                <b>{row.match_count}</b>
              </div>
              <div className="opposition-venue-bars">
                <div>
                  <span>xG</span>
                  <div className="opposition-bar-track" aria-hidden="true"><i style={{ width: `${clamp(((row.metrics.xG ?? 0) / maxXg) * 100)}%` }} /></div>
                  <strong>{formatMetric(row.metrics.xG)}</strong>
                </div>
                <div className="is-risk">
                  <span>xGA</span>
                  <div className="opposition-bar-track" aria-hidden="true"><i style={{ width: `${clamp(((row.metrics.xG_against ?? 0) / maxXg) * 100)}%` }} /></div>
                  <strong>{formatMetric(row.metrics.xG_against)}</strong>
                </div>
                <div>
                  <span>Shots</span>
                  <strong>{formatMetric(row.metrics.shots)}</strong>
                  <small>{formatMetric(row.metrics.shots_against)} conceded</small>
                </div>
                <div>
                  <span>Poss.</span>
                  <strong>{formatMetric(row.metrics.possession_pct, "%")}</strong>
                  <small>PPDA {formatMetric(row.metrics.ppda)}</small>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="opposition-empty-note">Home and away split is not available for this sample.</p>
      )}
    </section>
  );
}

function GameStateVisual({ dossier }: { dossier: OppositionDossier }) {
  const profile = dossier.gameStateProfile;
  const hasEventProfile = Boolean(profile?.available && profile.rows.length);
  const rows = hasEventProfile ? profile?.rows ?? [] : sampleResultStateRows(dossier);
  const maxXg = Math.max(1, ...rows.flatMap((row) => [row.xG_per_match, row.xGA_per_match]));

  return (
    <section className="opposition-visual-panel opposition-game-state-visual">
      <div className="opposition-visual-head">
        <div>
          <span className="eyebrow">Game State</span>
          <h2>{hasEventProfile ? "xG by score state" : "xG by result state"}</h2>
        </div>
      </div>
      {rows.length ? (
        <div className="opposition-game-state-grid">
          {rows.map((row) => (
            <div key={row.state} className={`opposition-game-state-card is-${row.state}`}>
              <div className="opposition-game-state-head">
                <span>{row.label}</span>
                <strong>{row.match_count}</strong>
              </div>
              <div className="opposition-game-state-bars">
                <div>
                  <span>xG / match</span>
                  <div className="opposition-bar-track" aria-hidden="true"><i style={{ width: `${clamp((row.xG_per_match / maxXg) * 100)}%` }} /></div>
                  <b>{formatMetric(row.xG_per_match)}</b>
                </div>
                <div className="is-risk">
                  <span>xGA / match</span>
                  <div className="opposition-bar-track" aria-hidden="true"><i style={{ width: `${clamp((row.xGA_per_match / maxXg) * 100)}%` }} /></div>
                  <b>{formatMetric(row.xGA_per_match)}</b>
                </div>
              </div>
              <small>{row.shots} shots for · {row.shots_against} against</small>
            </div>
          ))}
        </div>
      ) : (
        <p className="opposition-empty-note">{profile?.warning ?? "Game-state event data is not available for this sample yet."}</p>
      )}
    </section>
  );
}

function TeamProfileRadars({ dossier }: { dossier: OppositionDossier }) {
  const groups = groupMetrics(dossier.teamProfile.metrics);
  const categories = [
    { key: "style", title: "Style", subtitle: "Territory, possession and progression rhythm" },
    { key: "chance_profile", title: "Chance Profile", subtitle: "Shot volume and chance quality" },
    { key: "defensive_vulnerability", title: "Defensive Vulnerability", subtitle: "How exposed they were in the selected sample" },
  ];

  return (
    <section className="opposition-visual-panel opposition-profile-radar-section">
      <div className="opposition-visual-head">
        <div>
          <span className="eyebrow">Team Profile</span>
          <h2>Sample-based radar profile</h2>
        </div>
        <span className="opposition-subtle">{dossier.teamProfile.match_count} rows in analysis pool</span>
      </div>
      <div className="opposition-profile-radar-grid">
        {categories.map((category) => {
          const metrics = groups[category.key] ?? [];
          return (
            <div key={category.key} className={`opposition-profile-radar-card is-${category.key}`}>
              <div className="opposition-profile-radar-head">
                <div>
                  <span>{category.title}</span>
                  <small>{category.subtitle}</small>
                </div>
                <strong>{metrics.length}</strong>
              </div>
              {metrics.length ? (
                <OppositionStyleRadarPlotly radarMetrics={metrics} />
              ) : (
                <p className="opposition-empty-note">No metrics available for this profile.</p>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

function KeyPlayerVisual({ dossier }: { dossier: OppositionDossier }) {
  const players = dossier.keyPlayers.slice(0, 5);
  const maxThreat = Math.max(1, ...players.map((player) => player.xg + player.xa + player.shots * 0.03));
  return (
    <section className="opposition-visual-panel">
      <div className="opposition-visual-head">
        <div>
          <span className="eyebrow">Key Players</span>
          <h2>Threat contributors</h2>
        </div>
      </div>
      <div className="opposition-player-threat-list">
        {players.map((player) => {
          const threat = player.xg + player.xa + player.shots * 0.03;
          return (
            <div key={player.player} className="opposition-player-threat">
              <div>
                <strong>{player.player}</strong>
                <span>{player.goals} G · {formatMetric(player.xg)} xG · {formatMetric(player.xa)} xA</span>
              </div>
              <div className="opposition-bar-track" aria-hidden="true">
                <i style={{ width: `${clamp((threat / maxThreat) * 100)}%` }} />
              </div>
              <b>{player.shots}</b>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function ComparableVisual({ dossier }: { dossier: OppositionDossier }) {
  return (
    <section className="opposition-visual-panel">
      <div className="opposition-visual-head">
        <div>
          <span className="eyebrow">Comparable Sample</span>
          <h2>Matches and style peers</h2>
        </div>
        <span className="opposition-subtle">{dossier.sampleContext.sample_strategy.replaceAll("_", " ")}</span>
      </div>
      <div className="opposition-context-visual-grid">
        <div className="opposition-compact-match-list">
          {dossier.sampleContext.sample_matches.slice(0, 5).map((match) => (
            <div key={match.match_id} className="opposition-compact-match">
              <span className={`opposition-result ${resultClass(match.result)}`}>{match.result}</span>
              <strong>
                {teamLogoUrl(dossier.meta.league, match.opponent) ? <Image src={teamLogoUrl(dossier.meta.league, match.opponent)!} alt={`${match.opponent} logo`} width={20} height={20} /> : null}
                {match.opponent}
              </strong>
              <small>{formatSeason(match.season)} · xG {formatMetric(match.xg)}-{formatMetric(match.xga)}</small>
            </div>
          ))}
        </div>
        <div className="opposition-peer-bars">
          {dossier.sampleContext.similar_teams.slice(0, 5).map((peer) => (
            <div key={peer.team} className="opposition-peer-bar">
              <div>
                <strong>
                  {teamLogoUrl(dossier.meta.league, peer.team) ? <Image src={teamLogoUrl(dossier.meta.league, peer.team)!} alt={`${peer.team} logo`} width={20} height={20} /> : null}
                  {peer.team}
                </strong>
                <small>{peer.matches} matches</small>
              </div>
              <div className="opposition-bar-track" aria-hidden="true">
                <i style={{ width: `${clamp(peer.similarity)}%` }} />
              </div>
              <b>{formatMetric(peer.similarity, "%")}</b>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

type InPossessionProfile = NonNullable<OppositionDossier["inPossessionProfile"]>;
type InPossessionMetric = InPossessionProfile["identity"][number];
type InPossessionPlayer = InPossessionProfile["player_roles"][string][number];

function InPossessionMetricCards({ rows }: { rows: InPossessionMetric[] }) {
  return (
    <div className="opposition-in-possession-kpis">
      {rows.map((row) => (
        <div key={row.metric} className="opposition-kpi-card">
          <span>{row.label}</span>
          <strong>{formatProfileMetric(row)}</strong>
          <div className="opposition-kpi-track" aria-hidden="true">
            <i style={{ width: `${clamp(row.metric === "ppda" ? 100 - row.value * 4 : row.value)}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}

function PossessionIdentityQuadrant({ profile }: { profile: InPossessionProfile }) {
  const identity = profile.possession_identity;
  if (!identity?.available) return <InPossessionMetricCards rows={profile.identity} />;

  const quadrantByKey = new Map(identity.quadrants.map((quadrant) => [quadrant.key, quadrant]));
  const controlScore = Number(quadrantByKey.get("control")?.score ?? 50);
  const territoryScore = Number(quadrantByKey.get("territory")?.score ?? 50);
  const directScore = Number(quadrantByKey.get("directness")?.score ?? 50);
  const patientScore = clamp((controlScore + territoryScore + (100 - directScore)) / 3);
  const directMarker = clamp(directScore);
  const tendency = directMarker >= 58 ? "Direct first" : directMarker <= 42 ? "Patient build-up" : "Mixed build-up";
  const getMetric = (label: string) => {
    for (const quadrant of identity.quadrants) {
      const metric = quadrant.metrics.find((item) => item.label.toLowerCase() === label.toLowerCase());
      if (metric) return metric;
    }
    return null;
  };
  const cues = [
    getMetric("Possession"),
    getMetric("Passes / possession"),
    getMetric("Long balls"),
    getMetric("Prog. actions / possession"),
  ].filter(Boolean);

  return (
    <div className="opposition-build-up-profile">
      <div className="opposition-build-up-scoreboard">
        <div className="opposition-build-up-mode">
          <span>Patient build-up</span>
          <strong>{formatMetric(patientScore, "%")}</strong>
        </div>
        <div className="opposition-build-up-spectrum" aria-label={`${tendency}: ${formatMetric(directMarker, "%")} directness`}>
          <div>
            <span>Build through thirds</span>
            <span>Play forward early</span>
          </div>
          <i style={{ left: `${directMarker}%` }}>
            <b>{tendency}</b>
          </i>
        </div>
        <div className="opposition-build-up-mode is-direct">
          <span>Direct attack</span>
          <strong>{formatMetric(directScore, "%")}</strong>
        </div>
      </div>

      <div className="opposition-build-up-cues">
        {cues.map((metric) => (
          <div key={metric!.label}>
            <span>{metric!.label}</span>
            <strong>{metric!.value === null ? "-" : formatMetric(metric!.value, metric!.unit)}</strong>
          </div>
        ))}
      </div>

      <OppositionBuildUpTemperamentPitch profile={profile.event_pitch_profile} />

      <div className="opposition-identity-quadrant">
        <div className="opposition-identity-centre">
          <span>Profile</span>
          <strong>{identity.label}</strong>
        </div>
        {identity.quadrants.map((quadrant) => (
          <div key={quadrant.key} className={`opposition-identity-card is-${quadrant.key}`}>
            <div className="opposition-identity-card-head">
              <span>{quadrant.label}</span>
              <strong>{formatMetric(quadrant.score, "%")}</strong>
            </div>
            <div className="opposition-kpi-track" aria-hidden="true">
              <i style={{ width: `${clamp(quadrant.score)}%` }} />
            </div>
            <div className="opposition-identity-metrics">
              {quadrant.metrics.map((metric) => (
                <div key={`${quadrant.key}-${metric.label}`}>
                  <span>{metric.label}</span>
                  <strong>{metric.value === null ? "-" : formatMetric(metric.value, metric.unit)}</strong>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function InPossessionBars({ rows }: { rows: InPossessionMetric[] }) {
  const maxValue = Math.max(1, ...rows.map((row) => row.value));
  return (
    <div className="opposition-bar-list">
      {rows.map((row) => (
        <div key={row.metric} className="opposition-bar-row">
          <div>
            <strong>{row.label}</strong>
            <span>Per match in selected sample</span>
          </div>
          <div className="opposition-bar-track" aria-hidden="true">
            <i style={{ width: `${clamp((row.value / maxValue) * 100)}%` }} />
          </div>
          <b>{formatProfileMetric(row)}</b>
        </div>
      ))}
    </div>
  );
}

function InPossessionPlayerRoleList({
  title,
  players,
  value,
}: {
  title: string;
  players: InPossessionPlayer[];
  value: keyof InPossessionPlayer;
}) {
  const maxValue = Math.max(1, ...players.map((player) => Number(player[value]) || 0));
  return (
    <div className="opposition-role-card">
      <div className="opposition-role-card-head">
        <span>{title}</span>
        <strong>{players.length}</strong>
      </div>
      <div className="opposition-player-threat-list">
        {players.length ? players.map((player) => {
          const metricValue = Number(player[value]) || 0;
          return (
            <div key={`${title}-${player.player}`} className="opposition-player-threat">
              <div>
                <strong>{player.player}</strong>
                <span>{player.mins} mins · {player.goals} G · {formatMetric(player.xg)} xG · {formatMetric(player.xa)} xA</span>
              </div>
              <div className="opposition-bar-track" aria-hidden="true">
                <i style={{ width: `${clamp((metricValue / maxValue) * 100)}%` }} />
              </div>
              <b>{formatMetric(metricValue)}</b>
            </div>
          );
        }) : (
          <p className="opposition-empty-note">Player role data is not available for this sample yet.</p>
        )}
      </div>
    </div>
  );
}

function InPossessionChannelStrip({
  title,
  rows,
}: {
  title: string;
  rows?: Array<{ channel: string; count: number; pct: number }>;
}) {
  const displayRows = rows?.filter((row) => row.channel !== "unknown") ?? [];
  if (!displayRows.length) return null;
  return (
    <div className="opposition-channel-strip">
      <span>{title}</span>
      <div>
        {displayRows.map((row) => (
          <strong key={`${title}-${row.channel}`} style={{ width: `${clamp(row.pct, 14, 100)}%` }}>
            {row.channel} {formatMetric(row.pct, "%")}
          </strong>
        ))}
      </div>
    </div>
  );
}

function InPossessionTab({ dossier }: { dossier: OppositionDossier }) {
  const profile = dossier.inPossessionProfile;
  if (!profile?.available) {
    return (
      <section className="opposition-section opposition-empty-tab">
        <div className="opposition-section-header">
          <div>
            <span className="eyebrow">In Possession</span>
            <h2>Sample profile not available</h2>
          </div>
        </div>
        <div className="opposition-panel">
          <p>The selected sample does not have enough team-history metrics for an in-possession profile yet.</p>
        </div>
      </section>
    );
  }

  return (
    <>
      <section className="opposition-visual-panel">
        <div className="opposition-visual-head">
          <div>
            <span className="eyebrow">In Possession</span>
            <h2>Are they patient builders or direct attackers?</h2>
          </div>
        </div>
        <PossessionIdentityQuadrant profile={profile} />
      </section>

      <section className="opposition-visual-panel opposition-in-possession-pitch-wide">
        <div className="opposition-visual-head">
          <div>
            <span className="eyebrow">Pitch Context</span>
            <h2>Where do they progress and enter the box?</h2>
          </div>
        </div>
        <OppositionInPossessionPitchPlotly profile={profile.event_pitch_profile} mode="progression" />
        <InPossessionChannelStrip title="Progression lanes" rows={profile.event_pitch_profile?.channels?.progression} />
        <InPossessionChannelStrip title="Box entry lanes" rows={profile.event_pitch_profile?.channels?.box_entries} />
      </section>

      <div className="opposition-in-possession-grid">
        <section className="opposition-visual-panel">
          <div className="opposition-visual-head">
            <div>
              <span className="eyebrow">Progression</span>
              <h2>How do they move the ball into dangerous areas?</h2>
            </div>
          </div>
          <InPossessionBars rows={profile.progression} />
        </section>

        <section className="opposition-visual-panel">
          <div className="opposition-visual-head">
            <div>
              <span className="eyebrow">Chance Creation</span>
              <h2>What type of chance volume do they generate?</h2>
            </div>
          </div>
          <InPossessionBars rows={profile.chance_creation} />
        </section>
      </div>

    </>
  );
}

function OverviewTab({ dossier }: { dossier: OppositionDossier }) {
  return (
    <>
      <OverviewKpiStrip dossier={dossier} />
      <CoachSquadContext dossier={dossier} />
      <LineupContext dossier={dossier} />
      <RecentFormVisual dossier={dossier} />
      <div className="opposition-overview-grid">
        <HomeAwaySplitVisual dossier={dossier} />
        <GameStateVisual dossier={dossier} />
      </div>
      <TeamProfileRadars dossier={dossier} />
    </>
  );
}

function PlannedTab({ view }: { view: OppositionViewId }) {
  const selected = OPPOSITION_VIEWS.find((item) => item.id === view);
  const descriptions: Record<Exclude<OppositionViewId, "overview">, string> = {
    "in-possession": "This tab will hold the opponent's pass network, buildup routes, progression channels, entries, chance creation, shot quality, top creators, top shooters, attacking set pieces, and notes for slowing their attack.",
    "out-of-possession": "This tab will cover pressing, defensive actions, territory conceded, entries conceded, shots conceded, transition vulnerability, turnover risks, defensive set pieces, and where the opponent can be attacked.",
    players: "This tab will become the role-based player board with starters, key contributors, minutes, threat metrics, and future availability context.",
    "action-plan": "This tab will turn the dossier into concise attacking, defensive, set-piece, matchup, and risk recommendations.",
  };

  if (view === "overview") return null;

  return (
    <section className="opposition-section opposition-empty-tab">
      <div className="opposition-section-header">
        <div>
          <span className="eyebrow">Report Section</span>
          <h2>{selected?.label ?? "Planned section"}</h2>
        </div>
        <span className="opposition-subtle">Planned for the next phases</span>
      </div>
      <div className="opposition-panel">
        <p>{descriptions[view]}</p>
      </div>
    </section>
  );
}

function ActiveReportTab({ dossier, view }: { dossier: OppositionDossier; view: OppositionViewId }) {
  if (view === "overview") return <OverviewTab dossier={dossier} />;
  if (view === "in-possession") return <InPossessionTab dossier={dossier} />;
  return <PlannedTab view={view} />;
}

export default async function OppositionAnalysisPage({ searchParams }: PageProps) {
  if (process.env.NEXT_PUBLIC_OPPOSITION_ANALYSIS_ENABLED !== "true") {
    return <ComingSoon />;
  }

  const params = await searchParams;
  const league = params.league;
  const season = params.season;
  const referenceTeam = params.referenceTeam ?? params.home;
  const opponentTeam = params.opponentTeam ?? (referenceTeam === params.home ? params.away : params.home);
  const sampleSize = Number(params.sampleSize ?? 5);
  const view = safeView(params.view);

  if (!league || !season || !referenceTeam || !opponentTeam) {
    return <MissingContext />;
  }

  const authToken = await getServerAuthToken();
  let dossier: OppositionDossier;
  try {
    dossier = await getOppositionDossier(
      league,
      season,
      opponentTeam,
      {
        referenceTeam,
        fixtureId: params.fixtureId,
        home: params.home,
        away: params.away,
        sampleSize: Number.isFinite(sampleSize) ? sampleSize : 5,
      },
      authToken,
    );
  } catch (error) {
    return (
      <LoadError
        league={league}
        season={season}
        message={error instanceof Error ? error.message : "The dossier could not be loaded."}
      />
    );
  }

  return (
    <div className="opposition-page stack">
      <MatchupHeader dossier={dossier} fixtureId={params.fixtureId} sampleSize={Number.isFinite(sampleSize) ? sampleSize : 5} view={view} />
      <OppositionTabBar dossier={dossier} fixtureId={params.fixtureId} sampleSize={Number.isFinite(sampleSize) ? sampleSize : 5} activeView={view} />
      <ActiveReportTab dossier={dossier} view={view} />
    </div>
  );
}
