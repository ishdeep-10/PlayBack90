import Image from "next/image";

import {
  getLeagues,
  getSeasons,
  getLeagueTable,
  getTeamForm,
  getPlayerLeaderboard,
  getSeasonAssetUrl,
  type StandingRow,
  type StandingsResponse,
} from "../../lib/api";
import { getServerAuthToken } from "../../lib/serverAuth";
import { teamLogo } from "../../lib/stadiums";


type PageProps = {
  searchParams: Promise<{
    league?: string;
    season?: string;
    tab?: string;
    team?: string;
    window?: string;
    sortBy?: string;
    minMins?: string;
  }>;
};

const TABS = [
  { id: "league-table",      label: "League Table" },
  { id: "team-form",         label: "Team Form" },
  { id: "player-leaderboard", label: "Player Leaderboards" },
  { id: "overview-chart",    label: "Overview Chart" },
];

const SORT_OPTIONS = [
  { value: "xG",           label: "xG" },
  { value: "goals",        label: "Goals" },
  { value: "shots",        label: "Shots" },
  { value: "xA",           label: "xA" },
  { value: "key_passes",   label: "Key Passes" },
  { value: "tackles",      label: "Tackles" },
  { value: "xT",           label: "xT" },
  { value: "prog_passes",  label: "Progressive Passes" },
  { value: "dribbles_won", label: "Dribbles Won" },
];

export default async function SeasonStatsPage({ searchParams }: PageProps) {
  const {
    league,
    season,
    tab = "league-table",
    team,
    window: windowParam = "5",
    sortBy = "xG",
    minMins = "0",
  } = await searchParams;
  const authToken = await getServerAuthToken();

  const leagues = await getLeagues(authToken);

  // Build base href preserving league+season
  function base(overrides: Record<string, string> = {}) {
    const p = new URLSearchParams({
      ...(league ? { league } : {}),
      ...(season ? { season } : {}),
      tab,
      ...(team ? { team } : {}),
      window: windowParam,
      sortBy,
      minMins,
      ...overrides,
    });
    return `/season-stats?${p.toString()}`;
  }

  // If no league selected, show league picker
  if (!league) {
    return (
      <div className="stack" style={{ marginTop: 24 }}>
        <section className="hero">
          <span className="eyebrow">Season Stats</span>
          <h1>Choose a League</h1>
          <p>Select a league to browse standings, form, and player leaderboards.</p>
        </section>
        <div className="league-grid">
          {leagues.map((l) => (
            <a key={l.key} href={`/season-stats?league=${l.key}&tab=league-table`} className="league-card">
              <strong className="league-name">{l.name}</strong>
            </a>
          ))}
        </div>
      </div>
    );
  }

  // Fetch seasons for selected league
  const seasonData = await getSeasons(league, authToken);
  const seasons = seasonData.seasons;
  const activeSeason = season ?? seasons[0];

  if (!activeSeason) {
    return (
      <div className="placeholder card" style={{ marginTop: 24 }}>
        <p className="muted">No seasons found for this league.</p>
      </div>
    );
  }

  // Fetch data for active tab (in parallel where possible)
  let tableRows: StandingRow[] = [];
  let standingsMeta: StandingsResponse | null = null;
  let formData: { team: string; window: number; matches: Array<Record<string, unknown>> } | null = null;
  let leaderboardRows: Record<string, string | number>[] = [];
  let teamList: string[] = [];
  let loadError: string | null = null;

  try {
    if (tab === "league-table") {
      const tableResult = await getLeagueTable(league, activeSeason, authToken);
      standingsMeta = tableResult;
      tableRows = tableResult.rows ?? [];
      teamList = tableRows.map((r) => String(r.team));
    } else if (tab === "team-form") {
      const tableResult = await getLeagueTable(league, activeSeason);
      teamList = (tableResult.rows ?? []).map((r) => String(r.team));
      const selectedTeam = team ?? teamList[0];
      if (selectedTeam) {
        formData = await getTeamForm(league, activeSeason, selectedTeam, Number(windowParam), authToken);
      }
    } else if (tab === "player-leaderboard") {
      const result = await getPlayerLeaderboard(league, activeSeason, sortBy, Number(minMins), authToken);
      leaderboardRows = result.rows ?? [];
    } else if (tab === "overview-chart") {
      // Just need team list for the team selector
      const tableResult = await getLeagueTable(league, activeSeason);
      teamList = (tableResult.rows ?? []).map((r) => String(r.team));
    }
  } catch (error) {
    loadError = error instanceof Error ? error.message : "Unable to load season stats right now.";
  }

  const selectedTeam = team ?? teamList[0] ?? "";
  const hasAnalyticsColumns = tableRows.some(
    (row) => row.xg !== null || row.xga !== null || row.xgd !== null,
  );

  return (
    <div className="stack" style={{ marginTop: 24 }}>
      {/* Header */}
      <section className="hero">
        <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 16 }}>
          <div className="stack" style={{ gap: 6 }}>
            <span className="eyebrow">Season Stats</span>
            <h1 style={{ fontSize: "clamp(1.8rem, 3vw, 2.8rem)", margin: 0 }}>
              {leagues.find((l) => l.key === league)?.name ?? league}
            </h1>
          </div>
          <div className="stack" style={{ gap: 8, alignItems: "flex-end" }}>
            {/* League selector */}
            <div className="row">
              {leagues.map((l) => (
                <a key={l.key} className={l.key === league ? "button" : "ghost-button"}
                  style={{ minHeight: 38, padding: "0 12px", fontSize: "0.82rem" }}
                  href={`/season-stats?league=${l.key}&tab=${tab}`}>
                  {l.name}
                </a>
              ))}
            </div>
            {/* Season selector */}
            <div className="row">
              {seasons.slice(0, 4).map((s) => (
                <a key={s} className={s === activeSeason ? "button" : "ghost-button"}
                  style={{ minHeight: 36, padding: "0 12px", fontSize: "0.82rem" }}
                  href={base({ season: s })}>
                  {s.replace("_", "/")}
                </a>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Tab bar */}
      <nav className="tab-bar">
        {TABS.map((t) => (
          <a key={t.id} href={base({ tab: t.id })} className={`tab-link${tab === t.id ? " active" : ""}`}>
            {t.label}
          </a>
        ))}
      </nav>

      {/* ══════ LEAGUE TABLE ══════ */}
      {tab === "league-table" && (
        <section className="card stack">
          <div className="standings-heading">
            <h2 style={{ margin: 0 }}>{leagues.find((l) => l.key === league)?.name} — {activeSeason.replace("_", "/")} Standings</h2>
            {standingsMeta && (
              <span className={`standings-source${standingsMeta.is_official ? " is-official" : ""}`}>
                {standingsMeta.is_official
                  ? standingsMeta.is_stale
                    ? "Official · cached"
                    : "Official"
                  : "Calculated · completed matches"}
              </span>
            )}
          </div>
          {standingsMeta?.warning && <p className="inline-warning">{standingsMeta.warning}</p>}
          {tableRows.length === 0 ? (
            <div className="placeholder" style={{ minHeight: "20vh" }}>
              <p className="muted">
                {loadError ?? <>No season stats available yet. Run <code>generate_season_stats.py</code> first.</>}
              </p>
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table className="table">
                <thead>
                  <tr>
                    <th>#</th><th>Team</th><th>P</th><th>W</th><th>D</th><th>L</th>
                    <th>GF</th><th>GA</th><th>GD</th><th>Pts</th>
                    {hasAnalyticsColumns && <><th>xG</th><th>xGA</th><th>xGD</th></>}
                  </tr>
                </thead>
                <tbody>
                  {tableRows.map((row) => {
                    const xgd = Number(row.xgd ?? 0);
                    const crest = row.crest || teamLogo(String(row.team));
                    return (
                      <tr key={String(row.team)}>
                        <td style={{ color: "var(--muted)" }}>{row.rank}</td>
                        <td>
                          <span className="standings-team">
                            {crest && (
                              <Image
                                unoptimized
                                src={crest}
                                alt=""
                                width={24}
                                height={24}
                                className="standings-crest"
                              />
                            )}
                            <strong>{row.team}</strong>
                          </span>
                        </td>
                        <td>{row.played}</td>
                        <td>{row.won}</td>
                        <td>{row.drawn}</td>
                        <td>{row.lost}</td>
                        <td>{row.gf}</td>
                        <td>{row.ga}</td>
                        <td style={{ color: Number(row.gd) >= 0 ? "var(--success)" : "var(--danger)" }}>
                          {Number(row.gd) > 0 ? "+" : ""}{row.gd}
                        </td>
                        <td><strong>{row.pts}</strong></td>
                        {hasAnalyticsColumns && (
                          <>
                            <td>{row.xg ?? "—"}</td>
                            <td>{row.xga ?? "—"}</td>
                            <td style={{ color: row.xgd === null ? "var(--muted)" : xgd >= 0 ? "var(--success)" : "var(--danger)" }}>
                              {row.xgd === null ? "—" : <>{xgd > 0 ? "+" : ""}{xgd}</>}
                            </td>
                          </>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {/* ══════ TEAM FORM ══════ */}
      {tab === "team-form" && (
        <div className="stack">
          {/* Team selector */}
          {teamList.length > 0 && (
            <div className="row">
              {teamList.map((t) => (
                <a key={t} className={t === selectedTeam ? "button" : "ghost-button"}
                  style={{ minHeight: 36, padding: "0 12px", fontSize: "0.82rem" }}
                  href={base({ team: t, tab: "team-form" })}>
                  {t}
                </a>
              ))}
            </div>
          )}

          {/* Window selector */}
          <div className="row">
            <span className="muted" style={{ fontFamily: "system-ui,sans-serif", fontSize: "0.85rem" }}>Last:</span>
            {["5", "10", "0"].map((w) => (
              <a key={w} className={windowParam === w ? "button" : "ghost-button"}
                style={{ minHeight: 36, padding: "0 12px", fontSize: "0.82rem" }}
                href={base({ window: w })}>
                {w === "0" ? "All" : w} matches
              </a>
            ))}
          </div>

          {formData && formData.matches.length > 0 ? (
            <>
              <section className="card stack">
                <h2 style={{ margin: 0 }}>{formData.team} — Form</h2>
                <div className="row">
                  {formData.matches.map((m, i) => (
                    <div key={i} className="form-chip" title={`vs ${String(m.opponent)} ${String(m.score)}`}
                      style={{ backgroundColor: m.result === "W" ? "var(--success)" : m.result === "D" ? "var(--muted)" : "var(--danger)", color: "#fff" }}>
                      {String(m.result)}
                    </div>
                  ))}
                </div>
              </section>

              {/* xG chart */}
              <section className="card stack">
                <h2 style={{ margin: 0 }}>xG Chart</h2>
                <Image alt="Team form xG" src={getSeasonAssetUrl(league, activeSeason, "team-form-chart", { team: selectedTeam })}
                  width={1200} height={600} style={{ width: "100%", height: "auto", borderRadius: 14 }} unoptimized />
              </section>

              {/* Match log table */}
              <section className="card stack">
                <h2 style={{ margin: 0 }}>Match Log</h2>
                <table className="table">
                  <thead>
                    <tr><th>Date</th><th>Opponent</th><th>Result</th><th>Score</th><th>xG For</th><th>xG Against</th></tr>
                  </thead>
                  <tbody>
                    {formData.matches.map((m, i) => (
                      <tr key={i}>
                        <td className="muted">{String(m.date)}</td>
                        <td>{String(m.opponent)}</td>
                        <td>
                          <span className="form-chip" style={{ backgroundColor: m.result === "W" ? "var(--success)" : m.result === "D" ? "var(--muted)" : "var(--danger)", color: "#fff" }}>
                            {String(m.result)}
                          </span>
                        </td>
                        <td><strong>{String(m.score)}</strong></td>
                        <td>{String(m.xg_for)}</td>
                        <td>{String(m.xg_against)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            </>
          ) : (
            <div className="placeholder card" style={{ minHeight: "20vh" }}>
              <p className="muted">
                {loadError ?? <>No form data — select a team above or run <code>generate_season_stats.py</code>.</>}
              </p>
            </div>
          )}
        </div>
      )}

      {/* ══════ PLAYER LEADERBOARD ══════ */}
      {tab === "player-leaderboard" && (
        <div className="stack">
          {/* Sort selector */}
          <div className="row">
            <span className="muted" style={{ fontFamily: "system-ui,sans-serif", fontSize: "0.85rem" }}>Sort by:</span>
            {SORT_OPTIONS.map((opt) => (
              <a key={opt.value} className={sortBy === opt.value ? "button" : "ghost-button"}
                style={{ minHeight: 36, padding: "0 12px", fontSize: "0.82rem" }}
                href={base({ sortBy: opt.value })}>
                {opt.label}
              </a>
            ))}
          </div>

          {leaderboardRows.length === 0 ? (
            <div className="placeholder card" style={{ minHeight: "20vh" }}>
              <p className="muted">
                {loadError ?? <>No player stats — run <code>generate_season_stats.py</code> first.</>}
              </p>
            </div>
          ) : (
            <section className="card stack">
              <h2 style={{ margin: 0 }}>Top Players by {SORT_OPTIONS.find((o) => o.value === sortBy)?.label ?? sortBy}</h2>
              <div style={{ overflowX: "auto" }}>
                <table className="table">
                  <thead>
                    <tr>
                      <th>#</th><th>Player</th><th>Team</th><th>Mins</th>
                      <th>Goals</th><th>xG</th><th>Shots</th><th>xA</th>
                      <th>Key Passes</th><th>Tackles</th><th>xT</th>
                    </tr>
                  </thead>
                  <tbody>
                    {leaderboardRows.slice(0, 30).map((row, i) => (
                      <tr key={`${row.player}-${i}`}>
                        <td style={{ color: "var(--muted)" }}>{i + 1}</td>
                        <td><strong>{row.player}</strong></td>
                        <td className="muted">{row.team}</td>
                        <td>{row.mins_played}</td>
                        <td>{row.goals}</td>
                        <td>{row.xG}</td>
                        <td>{row.shots}</td>
                        <td>{row.xA}</td>
                        <td>{row.key_passes}</td>
                        <td>{row.tackles}</td>
                        <td>{row.xT}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
        </div>
      )}

      {/* ══════ OVERVIEW CHART ══════ */}
      {tab === "overview-chart" && (
        <div className="stack">
          <section className="card stack">
            <h2 style={{ margin: 0 }}>xG For vs xG Against</h2>
            <p className="muted">Teams above the diagonal line are underperforming their xG; below are overperforming.</p>
            <Image alt="xG Scatter" src={getSeasonAssetUrl(league, activeSeason, "xg-scatter")}
              width={1200} height={700} style={{ width: "100%", height: "auto", borderRadius: 14 }} unoptimized />
          </section>

          <section className="card stack">
            <h2 style={{ margin: 0 }}>Team xG Form Chart</h2>
            {teamList.length > 0 && (
              <div className="row">
                {teamList.map((t) => (
                  <a key={t} className={t === selectedTeam ? "button" : "ghost-button"}
                    style={{ minHeight: 36, padding: "0 12px", fontSize: "0.82rem" }}
                    href={base({ team: t, tab: "overview-chart" })}>
                    {t}
                  </a>
                ))}
              </div>
            )}
            {selectedTeam && (
              <Image alt="Team xG form" src={getSeasonAssetUrl(league, activeSeason, "team-form-chart", { team: selectedTeam })}
                width={1200} height={600} style={{ width: "100%", height: "auto", borderRadius: 14 }} unoptimized />
            )}
            {!selectedTeam && loadError && (
              <div className="placeholder">
                <p className="muted">{loadError}</p>
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
