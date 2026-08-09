import Image from "next/image";
import type { Route } from "next";
import { Suspense } from "react";

import {
  getAnalysis,
  getAnalysisView,
  getTransientAnalysis
} from "../../../lib/api";
import { getServerAuthToken } from "../../../lib/serverAuth";
import { AiInsightCard } from "../../../components/AiInsightCard";
import { AnalysisRouteProgress } from "../../../components/AnalysisRouteProgress";
import { AnalysisViewNav } from "../../../components/AnalysisViewNav";
import { GlossaryPopover } from "../../../components/GlossaryPopover";
import { OrbLoader } from "../../../components/OrbLoader";
import { DuelsTransitionsSection } from "../../../components/DuelsTransitionsSection";
import { InPossessionNetworkSection } from "../../../components/InPossessionNetworkSection";
import { LineupsPanel } from "../../../components/LineupsPanel";
import { MatchDynamicsPlotly } from "../../../components/MatchDynamicsPlotly";
import { TeamComparisonPanel } from "../../../components/TeamComparisonPanel";
import { OutOfPossessionSection } from "../../../components/OutOfPossessionSection";
import { PlayerAnalysisSection } from "../../../components/PlayerAnalysisSection";
import { ShotsScaSection } from "../../../components/ShotsScaSection";
import { ShareExportProvider } from "../../../components/ShareExportContext";
import { TeamFormStrip } from "../../../components/TeamFormStrip";
import { TeamSeasonContextPanel } from "../../../components/season/TeamSeasonContextPanel";
import type { SeasonBaselinePayload } from "../../../components/season/baselineTypes";


type PageProps = {
  params: Promise<{ matchId: string }>;
  searchParams: Promise<{
    source?: string;
    league?: string;
    season?: string;
    team?: string;
    jobId?: string;
    situation?: string;
    player?: string;
    half?: string;
    duelType?: string;
    transitionType?: string;
    view?: string;
    subWindow?: string;
    gameState?: string;
    timeRange?: string;
    third?: string;
  }>;
};

const VIEWS = [
  { id: "match-dynamics",    label: "Match Dynamics" },
  { id: "shots",             label: "Shots and SCA" },
  { id: "in-possession",     label: "In Possession" },
  { id: "out-of-possession", label: "Out of Possession" },
  { id: "duels-transitions", label: "Duels & Transitions" },
  { id: "player-analysis",   label: "Player Analysis" },
];

const HOME_TEAM_COLOR = "#22c55e";
const AWAY_TEAM_COLOR = "#38bdf8";

function staticMatchColors(homeTeam: string, awayTeam: string) {
  return {
    ...(homeTeam ? { [homeTeam]: HOME_TEAM_COLOR } : {}),
    ...(awayTeam ? { [awayTeam]: AWAY_TEAM_COLOR } : {}),
  };
}

const LOGO_LEAGUE_FOLDERS: Record<string, string> = {
  "premier-league": "England - Premier League",
  "la-liga": "Spain - LaLiga",
  laliga: "Spain - LaLiga",
  "serie-a": "Italy - Serie A",
  "bundesliga": "Germany - Bundesliga",
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
  "serie-a": {
    Pisa: "Pisa Sporting Club",
    Atalanta: "Atalanta BC",
    Fiorentina: "ACF Fiorentina",
    Cagliari: "Cagliari Calcio",
    Lazio: "SS Lazio",
    Como: "Como 1907",
    Genoa: "Genoa CFC",
    Lecce: "US Lecce",
    Torino: "Torino FC",
    Inter: "Inter Milan",
    Juventus: "Juventus FC",
    "Parma Calcio": "Parma Calcio 1913",
    Cremonese: "US Cremonese",
    "AC Milan": "AC Milan",
    Bologna: "Bologna FC 1909",
    Roma: "AS Roma",
    Napoli: "SSC Napoli",
    Sassuolo: "US Sassuolo",
    Verona: "Hellas Verona",
    Udinese: "Udinese Calcio",
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

function teamLogoUrl(league: string | null | undefined, teamName: string) {
  const leagueKey = normalizeLeagueKey(league);
  const folder = LOGO_LEAGUE_FOLDERS[leagueKey];
  if (!folder || !teamName) return null;

  const logoTeamName = TEAM_LOGO_NAMES[leagueKey]?.[teamName] ?? teamName;
  return `https://raw.githubusercontent.com/luukhopman/football-logos/master/logos/${encodeURIComponent(folder)}/${encodeURIComponent(logoTeamName)}.png`;
}

export async function generateMetadata({ params, searchParams }: PageProps) {
  const { matchId } = await params;
  const { league, season, source = "r2", jobId } = await searchParams;
  const authToken = await getServerAuthToken();
  const fallback = { title: "Match Analysis | PlayBack90" };
  if (source === "r2" && (!league || !season)) return fallback;
  try {
    const analysis =
      source !== "r2" && jobId
        ? await getTransientAnalysis(matchId, source === "import" ? "import" : "live", jobId, authToken)
        : await getAnalysis(matchId, league!, season!, authToken);
    const home = analysis.context.home_team ?? "";
    const away = analysis.context.away_team ?? "";
    const score = analysis.context.score?.replace(/--/g, "-") ?? "vs";
    const colors = analysis.context.team_colors ?? {};
    const leagueLabelValue = analysis.context.league ?? league ?? "";
    const title = `${home} ${score} ${away} | PlayBack90`;
    const ogUrl = `/og?home=${encodeURIComponent(home)}&away=${encodeURIComponent(away)}&score=${encodeURIComponent(score)}&league=${encodeURIComponent(leagueLabelValue)}&homeColor=${encodeURIComponent(colors[home] ?? "#22c55e")}&awayColor=${encodeURIComponent(colors[away] ?? "#38bdf8")}`;
    return {
      title,
      description: `Full tactical breakdown: xG, pass networks, duels, set pieces and player analysis for ${home} vs ${away}.`,
      openGraph: { title, images: [{ url: ogUrl, width: 1200, height: 630 }] },
      twitter: { card: "summary_large_image", title, images: [ogUrl] },
    };
  } catch {
    return fallback;
  }
}

export default async function AnalysisPage({ params, searchParams }: PageProps) {
  const { matchId } = await params;
  const {
    league,
    season,
    team,
    source = "r2",
    jobId,
    situation = "All",
    player,
    half = "Full 90",
    duelType = "Total",
    transitionType = "Offensive",
    view = "match-dynamics",
    subWindow = "0",
    gameState = "all",
    timeRange = "all",
    third = "all",
  } = await searchParams;
  const authToken = await getServerAuthToken();

  if (source === "r2" && (!league || !season)) {
    return (
      <div className="placeholder card" style={{ marginTop: 24 }}>
        <div className="stack">
          <h1>Analysis link is missing league/season context.</h1>
          <p className="muted">Use the fixture browser to open a match.</p>
        </div>
      </div>
    );
  }

  if (source !== "r2" && !jobId) {
    return (
      <div className="placeholder card" style={{ marginTop: 24 }}>
        <div className="stack">
          <h1>Imported analysis link is missing a job id.</h1>
          <p className="muted">Transient match imports need the background job id.</p>
        </div>
      </div>
    );
  }

  let analysis: Awaited<ReturnType<typeof getAnalysis>>;
  try {
    analysis =
      source !== "r2" && jobId
        ? await getTransientAnalysis(matchId, source === "import" ? "import" : "live", jobId, authToken)
        : await getAnalysis(matchId, league!, season!, authToken);
  } catch {
    return (
      <div className="placeholder card" style={{ marginTop: 24 }}>
        <div className="stack">
          <h1>Match analysis is unavailable right now.</h1>
          <p className="muted">
            The PlayBack90 API did not respond for this match. It may be starting up or the event file may be missing.
          </p>
          <div className="row">
            <a className="button" href="">Retry</a>
            <a className="ghost-button" href="/">Back to Coverage Map</a>
          </div>
        </div>
      </div>
    );
  }

  const homeTeam = analysis.context.home_team ?? analysis.team_summaries[0]?.team ?? "";
  const awayTeam = analysis.context.away_team ?? analysis.team_summaries.find((row) => row.team !== homeTeam)?.team ?? "";
  const selectedTeam = team ?? homeTeam ?? analysis.team_summaries[0]?.team;
  const displayScore = analysis.context.score?.replace(/--/g, "-");
  const matchTeamColors = analysis.context.team_colors ?? staticMatchColors(homeTeam, awayTeam);

  // URL helpers
  const base =
    source !== "r2" && jobId
      ? `/analysis/${matchId}?source=${encodeURIComponent(source)}&jobId=${encodeURIComponent(jobId)}`
      : `/analysis/${matchId}?source=r2&league=${encodeURIComponent(league!)}&season=${encodeURIComponent(season!)}`;

  const preserveFilters = `&team=${encodeURIComponent(selectedTeam)}&situation=${encodeURIComponent(situation)}${player ? `&player=${encodeURIComponent(player)}` : ""}&half=${encodeURIComponent(half)}&duelType=${encodeURIComponent(duelType)}&transitionType=${encodeURIComponent(transitionType)}&subWindow=${encodeURIComponent(subWindow)}&gameState=${encodeURIComponent(gameState)}&timeRange=${encodeURIComponent(timeRange)}`;

  function tabHref(viewId: string) {
    return `${base}&view=${encodeURIComponent(viewId)}${preserveFilters}` as Route;
  }

  const teamA = homeTeam || analysis.team_summaries[0]?.team || "";
  const teamB = awayTeam || analysis.team_summaries.find((row) => row.team !== teamA)?.team || "";
  const leagueKey = normalizeLeagueKey(analysis.context.league ?? league);
  const teamALogoUrl = teamLogoUrl(leagueKey, teamA);
  const teamBLogoUrl = teamLogoUrl(leagueKey, teamB);
  const contentKey = [view, selectedTeam, situation, player ?? "", subWindow, gameState, timeRange, duelType, transitionType, third].join("|");
  const matchDateLabel = analysis.context.start_date_label;
  const leagueLabel = (analysis.context.league ?? league ?? "")
    .replace(/-/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());

  return (
    <ShareExportProvider
      value={{
        home: teamA,
        away: teamB,
        score: displayScore ?? undefined,
        league: leagueLabel || undefined,
        dateLabel: matchDateLabel ?? undefined,
        homeLogoUrl: teamALogoUrl,
        awayLogoUrl: teamBLogoUrl,
        homeColor: matchTeamColors[teamA],
        awayColor: matchTeamColors[teamB],
      }}
    >
    <div className="stack analysis-page-workspace" style={{ marginTop: 24 }}>
      <AnalysisRouteProgress />
      {/* ── Match header ── */}
      <section className="hero">
        <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 16 }}>
          <div className="stack" style={{ gap: 6 }}>
            <span className="eyebrow">{source === "live" ? "Live Analysis" : source === "import" ? "Imported Analysis" : "Post Match Analysis"}</span>
            <div className="match-title-row">
              {teamALogoUrl && <Image unoptimized className="match-title-logo" src={teamALogoUrl} alt={`${teamA} logo`} width={52} height={52} />}
              <h1 style={{ fontSize: "clamp(1.8rem, 3.5vw, 3rem)", margin: 0 }}>
                {teamA} <span className="muted" style={{ fontSize: "0.6em" }}>vs</span> {teamB}
              </h1>
              {teamBLogoUrl && <Image unoptimized className="match-title-logo" src={teamBLogoUrl} alt={`${teamB} logo`} width={52} height={52} />}
            </div>
            {displayScore && (
              <p style={{ margin: 0, fontSize: "1.5rem", fontWeight: 700 }}>{displayScore}</p>
            )}
            <div className="form-strip-row">
              <TeamFormStrip league={league} season={season} team={teamA} />
              <TeamFormStrip league={league} season={season} team={teamB} />
            </div>
          </div>
        </div>

      </section>

      {/* ── Tab bar ── */}
      <div className="tab-bar-row">
      <AnalysisViewNav
        activeView={view}
        links={VIEWS.map((item) => ({ ...item, href: tabHref(item.id) }))}
      />
      <GlossaryPopover viewId={view} />
      </div>

      {/* ── Main layout ── */}
      <div className="analysis-layout analysis-layout-full">
        <Suspense key={contentKey} fallback={<AnalysisTabSkeleton />}>
          <AnalysisContent
            matchId={matchId}
            source={source}
            league={league}
            season={season}
            jobId={jobId}
            view={view}
            situation={situation}
            player={player}
            subWindow={subWindow}
            gameState={gameState}
            timeRange={timeRange}
            third={third}
            duelType={duelType}
            transitionType={transitionType}
            selectedTeam={selectedTeam}
            homeTeam={homeTeam}
            awayTeam={awayTeam}
            analysis={analysis}
            matchTeamColors={matchTeamColors}
            authToken={authToken}
          />
        </Suspense>
      </div>
    </div>
    </ShareExportProvider>
  );
}

function AnalysisTabSkeleton() {
  return (
    <main className="analysis-main">
      <div className="skeleton" style={{ minHeight: 420, display: "grid", placeItems: "center", borderRadius: 16 }}>
        <OrbLoader label="Crunching match data" />
      </div>
      <div className="skeleton skeleton-card" style={{ marginTop: 16 }} />
    </main>
  );
}

type AnalysisData = Awaited<ReturnType<typeof getAnalysis>>;

type AnalysisContentProps = {
  matchId: string;
  source: string;
  league?: string;
  season?: string;
  jobId?: string;
  view: string;
  situation: string;
  player?: string;
  subWindow: string;
  gameState: string;
  timeRange: string;
  third: string;
  duelType: string;
  transitionType: string;
  selectedTeam: string;
  homeTeam: string;
  awayTeam: string;
  analysis: AnalysisData;
  matchTeamColors: Record<string, string>;
  authToken?: string | null;
};

async function AnalysisContent({
  matchId,
  source,
  league,
  season,
  jobId,
  view,
  situation,
  player,
  subWindow,
  gameState,
  timeRange,
  third,
  duelType,
  transitionType,
  selectedTeam,
  homeTeam,
  awayTeam,
  analysis,
  matchTeamColors,
  authToken,
}: AnalysisContentProps) {
  const commonBody =
    source !== "r2"
      ? { match_id: matchId, source, filters: { team: selectedTeam, situation, player, subWindow, gameState, timeRange, third, job_id: jobId } }
      : { match_id: matchId, source: "r2", league, season, filters: { team: selectedTeam, situation, player, subWindow, gameState, timeRange, third } };
  const inPossessionMetricsBody =
    source !== "r2"
      ? { match_id: matchId, source, filters: { team: selectedTeam, situation, player, subWindow: "all", gameState: "all", timeRange: "all", job_id: jobId } }
      : { match_id: matchId, source: "r2", league, season, filters: { team: selectedTeam, situation, player, subWindow: "all", gameState: "all", timeRange: "all" } };
  const duelsTransitionsBody =
    source !== "r2"
      ? { match_id: matchId, source, filters: { team: "__both__", duelType, transitionType, gameState, timeRange, job_id: jobId } }
      : { match_id: matchId, source: "r2", league, season, filters: { team: "__both__", duelType, transitionType, gameState, timeRange } };

  // Fetch only the data needed by the active view. A failed view request must
  // not crash the page — sections render their own empty states on null.
  const safeView = (promise: ReturnType<typeof getAnalysisView>) => promise.catch(() => null);
  const seasonBaselineBody = { match_id: matchId, source: "r2", league, season, filters: {} };
  const wantsSeasonBaseline = source === "r2" && ["match-dynamics", "in-possession", "out-of-possession", "duels-transitions", "player-analysis"].includes(view);
  const [shotsScaView, dynamicsView, passNetworkView, inPossessionMetricsView, defensiveActionsView, duelsTransitionsView, playerAnalysisView, seasonBaselineView] = await Promise.all([
    view === "shots" ? safeView(getAnalysisView("shots-sca", commonBody, authToken)) : Promise.resolve(null),
    view === "match-dynamics" ? safeView(getAnalysisView("match-dynamics", commonBody, authToken)) : Promise.resolve(null),
    view === "in-possession" ? safeView(getAnalysisView("pass-network", commonBody, authToken)) : Promise.resolve(null),
    view === "in-possession" ? safeView(getAnalysisView("in-possession-player-metrics", inPossessionMetricsBody, authToken)) : Promise.resolve(null),
    view === "out-of-possession" ? safeView(getAnalysisView("defensive-actions", commonBody, authToken)) : Promise.resolve(null),
    view === "duels-transitions" ? safeView(getAnalysisView("duels-transitions", duelsTransitionsBody, authToken)) : Promise.resolve(null),
    view === "player-analysis" ? safeView(getAnalysisView("player-analysis", commonBody, authToken)) : Promise.resolve(null),
    wantsSeasonBaseline ? safeView(getAnalysisView("season-baseline", seasonBaselineBody, authToken)) : Promise.resolve(null),
  ]);


  const shotsPayload = (shotsScaView?.payload ?? {}) as Record<string, unknown>;
  const shotPlayerRows = (shotsPayload.player_summary as Array<Record<string, string | number>>) ?? [];
  const shotDetailRows = (shotsPayload.shot_rows as Array<Record<string, string | number | boolean | null | undefined | Array<Record<string, unknown>>>>) ?? [];
  const shotTeamTotals = (shotsPayload.team_totals as Array<Record<string, string | number>>) ?? [];
  const shotGameStateOptions = (shotsPayload.game_state_options as Array<Record<string, string>> | undefined) ?? [];
  const shotTimeRangeOptions = (shotsPayload.time_range_options as Array<Record<string, string | number>> | undefined) ?? [];
  const shotTeamStateControls = (shotsPayload.team_state_controls as Record<string, unknown> | undefined) ?? {};
  const dynamicsPayload = (dynamicsView?.payload ?? {}) as Record<string, unknown>;
  const passNetworkPayload = (passNetworkView?.payload ?? {}) as Record<string, unknown>;
  const passNetworkWindows = (passNetworkPayload.windows as Array<Record<string, string | number>> | undefined) ?? [];
  const passNetworkGameStateOptions = (passNetworkPayload.game_state_options as Array<Record<string, string>> | undefined) ?? [];
  const passNetworkTimeRangeOptions = (passNetworkPayload.time_range_options as Array<Record<string, string | number>> | undefined) ?? [];
  const inPossessionMetricsPayload = (inPossessionMetricsView?.payload ?? {}) as Record<string, unknown>;
  const inPossessionMetricRows = (inPossessionMetricsPayload.rows as Array<Record<string, string | number>> | undefined) ?? [];
  const defensiveActionsPayload = (defensiveActionsView?.payload ?? {}) as Record<string, unknown>;
  const duelsTransitionsPayload = (duelsTransitionsView?.payload ?? {}) as Record<string, unknown>;
  const playerAnalysisPayload = (playerAnalysisView?.payload ?? {}) as Record<string, unknown>;
  const seasonBaseline = (seasonBaselineView?.payload ?? null) as SeasonBaselinePayload | null;
  const seasonTeamBaselines = seasonBaseline?.available ? seasonBaseline.teams ?? {} : {};
  const seasonPlayerBaselines = seasonBaseline?.available ? seasonBaseline.players ?? {} : {};

  const dynamicsTeams = (dynamicsPayload.teams as string[] | undefined) ?? [];
  const teamA = homeTeam || dynamicsTeams[0] || analysis.team_summaries[0]?.team || "";
  const teamB = awayTeam || dynamicsTeams.find((name) => name !== teamA) || analysis.team_summaries.find((row) => row.team !== teamA)?.team || "";
  const leagueKey = normalizeLeagueKey(analysis.context.league ?? league);
  const teamALogoUrl = teamLogoUrl(leagueKey, teamA);
  const teamBLogoUrl = teamLogoUrl(leagueKey, teamB);
  const xgFlowRows = (dynamicsPayload.xg_flow as Array<Record<string, string | number>> | undefined) ?? [];
  const xgMarkers = (dynamicsPayload.xg_markers as Array<Record<string, string | number>> | undefined) ?? [];
  const passRows = (dynamicsPayload.possession_pass_accuracy as Array<Record<string, string | number>> | undefined) ?? [];
  const flankRows = (dynamicsPayload.attack_flanks as Array<Record<string, string | number>> | undefined) ?? [];
  const ppdaRows = (dynamicsPayload.ppda_turnovers as Array<Record<string, string | number | null>> | undefined) ?? [];
  const momentumRows = (dynamicsPayload.xt_momentum as Array<Record<string, string | number>> | undefined) ?? [];
  const epvMomentumRows = (dynamicsPayload.epv_momentum as Array<Record<string, string | number>> | undefined) ?? [];
  const eventMarkers = (dynamicsPayload.event_markers as Array<Record<string, string | number>> | undefined) ?? [];
  const thirdsSeriesRows = (dynamicsPayload.thirds_series as Array<Record<string, string | number>> | undefined) ?? [];
  const statBreakdowns = (dynamicsPayload.stat_breakdowns as Record<string, Record<string, unknown>> | undefined) ?? {};
  const lineupsPayload = (dynamicsPayload.lineups as { teams?: Record<string, never>; substitutions?: Array<never> } | undefined) ?? {};
  const richTeamSummaryRows = (dynamicsPayload.team_summary_rows as Array<Record<string, string | number>> | undefined) ?? [];
  const dynamicsTeamSummaryRows: Array<Record<string, string | number>> = richTeamSummaryRows.length
    ? richTeamSummaryRows
    : analysis.team_summaries.map((row) => ({
      team: row.team,
      goals: row.goals,
      shots: row.shots,
      xg: row.xg,
      completed_passes: row.completed_passes ?? 0,
      big_chances_created: 0,
      big_chances_missed: 0,
      corners_taken: 0,
      pass_accuracy: row.pass_accuracy ?? 0,
    }));
  const teamColorMap = matchTeamColors;
  const teamAColor = teamColorMap[teamA] ?? HOME_TEAM_COLOR;
  const teamBColor = teamColorMap[teamB] ?? AWAY_TEAM_COLOR;
  const fullTime = Number(dynamicsPayload.full_time ?? 90);
  const summaryTeamA = dynamicsTeamSummaryRows.find((row) => String(row.team) === teamA) ?? dynamicsTeamSummaryRows[0] ?? {};
  const summaryTeamB = dynamicsTeamSummaryRows.find((row) => String(row.team) === teamB) ?? dynamicsTeamSummaryRows[1] ?? {};
  return (
    <main className="analysis-main">
      <AiInsightCard
        matchId={matchId}
        source={source}
        league={league}
        season={season}
        jobId={jobId}
        view={view}
        team={view === "duels-transitions" ? undefined : selectedTeam}
      />

          {/* ══════════════ TAB 1 — MATCH DYNAMICS ══════════════ */}
          {view === "match-dynamics" && (
            <div className="match-dynamics-tab stack">
              <LineupsPanel
                teams={[teamA, teamB]}
                teamColors={{ [teamA]: teamAColor, [teamB]: teamBColor }}
                lineups={(lineupsPayload.teams ?? {}) as never}
                substitutions={(lineupsPayload.substitutions ?? []) as never}
                phases={((lineupsPayload as { phases?: unknown }).phases ?? []) as never}
              />

              <TeamComparisonPanel
                teamA={String(summaryTeamA.team ?? teamA)}
                teamB={String(summaryTeamB.team ?? teamB)}
                summaryTeamA={summaryTeamA}
                summaryTeamB={summaryTeamB}
                teamAColor={teamColorMap[String(summaryTeamA.team)] ?? teamAColor}
                teamBColor={teamColorMap[String(summaryTeamB.team)] ?? teamBColor}
                teamALogoUrl={teamALogoUrl}
                teamBLogoUrl={teamBLogoUrl}
                breakdowns={statBreakdowns}
                seasonBaselines={seasonTeamBaselines}
              />

              <MatchDynamicsPlotly
                teams={[teamA, teamB]}
                teamColors={{ [teamA]: teamAColor, [teamB]: teamBColor }}
                fullTime={fullTime}
                xgFlowRows={xgFlowRows}
                xgMarkers={xgMarkers}
                passRows={passRows}
                flankRows={flankRows}
                ppdaRows={ppdaRows}
                momentumRows={momentumRows}
                epvMomentumRows={epvMomentumRows}
                eventMarkers={eventMarkers}
                teamSummaries={dynamicsTeamSummaryRows as never}
                thirdsRows={thirdsSeriesRows}
                seasonBaselines={seasonTeamBaselines}
              />

              <TeamSeasonContextPanel
                teamA={teamA}
                teamB={teamB}
                teamAColor={teamAColor}
                teamBColor={teamBColor}
                baselines={seasonTeamBaselines}
                fullTime={fullTime}
              />
            </div>
          )}

          {/* ══════════════ TAB 2 — SHOTS ══════════════ */}
          {view === "shots" && (
            <div className="analysis-dense-tab shots-dense-tab stack">
              <ShotsScaSection
                teams={[homeTeam, awayTeam].filter(Boolean)}
                initialTeam={selectedTeam}
                initialPlayer={player}
                shotRows={shotDetailRows}
                playerRows={shotPlayerRows}
                teamTotals={shotTeamTotals}
                teamColors={matchTeamColors}
                initialGameState={gameState}
                initialTimeRange={timeRange}
                gameStateOptions={shotGameStateOptions}
                timeRangeOptions={shotTimeRangeOptions}
                teamStateControls={shotTeamStateControls}
              />
            </div>
          )}

          {/* ══════════════ TAB 3 — IN POSSESSION ══════════════ */}
          {view === "in-possession" && (
            <div className="analysis-dense-tab in-possession-dense-tab stack">
              <InPossessionNetworkSection
                matchId={matchId}
                source={source}
                league={league}
        season={season}
                jobId={jobId}
                situation={situation}
                player={player}
                teams={[homeTeam, awayTeam].filter(Boolean)}
                selectedTeam={selectedTeam}
                selectedWindow={subWindow}
                selectedGameState={gameState}
                selectedTimeRange={timeRange}
                gameStateOptions={passNetworkGameStateOptions}
                timeRangeOptions={passNetworkTimeRangeOptions}
                windows={passNetworkWindows}
                payload={passNetworkPayload}
                metricRows={inPossessionMetricRows}
                teamColor={matchTeamColors[selectedTeam] ?? teamAColor}
                teamColors={matchTeamColors}
                playerBaselines={seasonPlayerBaselines}
              />
            </div>
          )}

          {/* ══════════════ TAB 4 — OUT OF POSSESSION ══════════════ */}
          {view === "out-of-possession" && (
            <div className="analysis-dense-tab out-of-possession-dense-tab stack">
              <OutOfPossessionSection
                matchId={matchId}
                source={source}
                league={league}
                season={season}
                jobId={jobId}
                teams={[homeTeam, awayTeam].filter(Boolean)}
                selectedTeam={selectedTeam}
                payload={defensiveActionsPayload}
                teamColors={matchTeamColors}
                playerBaselines={seasonPlayerBaselines}
              />
            </div>
          )}

          {/* ══════════════ TAB 5 — DUELS & TRANSITIONS ══════════════ */}
          {view === "duels-transitions" && (
            <div className="analysis-dense-tab duels-dense-tab stack">
              <DuelsTransitionsSection
                matchId={matchId}
                source={source}
                league={league}
                season={season}
                jobId={jobId}
                teams={[teamA, teamB].filter(Boolean)}
                selectedTeam="__both__"
                selectedDuelType={duelType}
                selectedTransitionType={transitionType}
                payload={duelsTransitionsPayload}
                teamColors={matchTeamColors}
                playerBaselines={seasonPlayerBaselines}
              />
            </div>
          )}

          {/* ══════════════ TAB 6 — PLAYER ANALYSIS ══════════════ */}
          {view === "player-analysis" && (
            <div className="analysis-dense-tab player-analysis-dense-tab stack">
              <PlayerAnalysisSection
                matchId={matchId}
                source={source}
                league={league}
                season={season}
                jobId={jobId}
                teams={[homeTeam, awayTeam].filter(Boolean)}
                selectedTeam={selectedTeam}
                payload={playerAnalysisPayload}
                teamColors={matchTeamColors}
                initialPlayer={player}
                seasonBaseline={seasonBaseline}
              />
            </div>
          )}

    </main>
  );
}
