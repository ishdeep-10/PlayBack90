import Image from "next/image";

import { getLeagues, getSeasons, getLeagueTable, getOppositionReport, getOppositionAssetUrl } from "../../lib/api";


type PageProps = {
  searchParams: Promise<{
    league?: string;
    season?: string;
    team?: string;
  }>;
};

export default async function OppositionAnalysisPage({ searchParams }: PageProps) {
  const { league, season, team } = await searchParams;

  const leagues = await getLeagues();

  // If no league selected, show league picker
  if (!league) {
    return (
      <div className="stack" style={{ marginTop: 24 }}>
        <section className="hero">
          <span className="eyebrow">Opposition Analysis</span>
          <h1>Choose a League</h1>
          <p>Select a league to scout teams, review strengths and weaknesses, and analyse head-to-head history.</p>
        </section>
        <div className="league-grid">
          {leagues.map((l) => (
            <a key={l.key} href={`/opposition-analysis?league=${l.key}`} className="league-card">
              <strong className="league-name">{l.name}</strong>
            </a>
          ))}
        </div>
      </div>
    );
  }

  const seasonData = await getSeasons(league);
  const seasons = seasonData.seasons;
  const activeSeason = season ?? seasons[0];

  if (!activeSeason) {
    return (
      <div className="placeholder card" style={{ marginTop: 24 }}>
        <p className="muted">No seasons found.</p>
      </div>
    );
  }

  // Fetch team list from league table
  let teamList: string[] = [];
  let teamListError: string | null = null;
  try {
    const tableResult = await getLeagueTable(league, activeSeason);
    teamList = (tableResult.rows ?? []).map((r) => String(r.team));
  } catch (error) {
    teamListError = error instanceof Error ? error.message : "Unable to load teams for this season.";
  }

  const selectedTeam = team ?? teamList[0] ?? "";

  function href(overrides: Record<string, string> = {}) {
    const p = new URLSearchParams({
      league: league ?? "",
      season: activeSeason,
      ...(selectedTeam ? { team: selectedTeam } : {}),
      ...overrides,
    });
    return `/opposition-analysis?${p.toString()}`;
  }

  // Fetch scouting report
  let report: {
    team: string;
    strengths: Array<{ metric: string; percentile: number; value: number }>;
    weaknesses: Array<{ metric: string; percentile: number; value: number }>;
    top_players: Array<{ player: string; goals: number; xg: number; assists: number; mins?: number }>;
    h2h: Array<{ date: string; opponent: string; result: string; goals_for: number; goals_against: number; score?: string }>;
  } | null = null;
  let reportError: string | null = null;

  if (selectedTeam) {
    try {
      report = await getOppositionReport(league, activeSeason, selectedTeam);
    } catch (error) {
      reportError = error instanceof Error ? error.message : "Unable to load the scouting report right now.";
    }
  }

  return (
    <div className="stack" style={{ marginTop: 24 }}>
      {/* Header */}
      <section className="hero">
        <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 16 }}>
          <div className="stack" style={{ gap: 6 }}>
            <span className="eyebrow">Opposition Analysis</span>
            <h1 style={{ fontSize: "clamp(1.8rem, 3vw, 2.8rem)", margin: 0 }}>
              {selectedTeam || "Select a Team"}
            </h1>
            <p className="muted">{leagues.find((l) => l.key === league)?.name} · {activeSeason.replace("_", "/")}</p>
          </div>
          {/* Season selector */}
          <div className="row">
            {seasons.slice(0, 4).map((s) => (
              <a key={s} className={s === activeSeason ? "button" : "ghost-button"}
                style={{ minHeight: 36, padding: "0 12px", fontSize: "0.82rem" }}
                href={href({ season: s })}>
                {s.replace("_", "/")}
              </a>
            ))}
          </div>
        </div>
        {/* League row */}
        <div className="row">
          {leagues.map((l) => (
            <a key={l.key} className={l.key === league ? "button" : "ghost-button"}
              style={{ minHeight: 36, padding: "0 12px", fontSize: "0.82rem" }}
              href={`/opposition-analysis?league=${l.key}`}>
              {l.name}
            </a>
          ))}
        </div>
      </section>

      {/* Team selector */}
      {teamList.length > 0 && (
        <div className="card stack">
          <h3 style={{ margin: 0, fontFamily: "system-ui,sans-serif", fontSize: "0.9rem", color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Select Team to Scout
          </h3>
          <div className="row">
            {teamList.map((t) => (
              <a key={t} className={t === selectedTeam ? "button" : "ghost-button"}
                style={{ minHeight: 36, padding: "0 12px", fontSize: "0.82rem" }}
                href={href({ team: t })}>
                {t}
              </a>
            ))}
          </div>
        </div>
      )}
      {teamListError && (
        <div className="placeholder card" style={{ minHeight: "12vh" }}>
          <p className="muted">{teamListError}</p>
        </div>
      )}

      {!report && (
        <div className="placeholder card" style={{ minHeight: "24vh" }}>
          <div className="stack" style={{ textAlign: "center" }}>
            <p className="muted">
              {reportError
                ? reportError
                : selectedTeam
                ? `No scouting data for ${selectedTeam}. Run generate_season_stats.py to populate season data.`
                : "Select a team above to view the scouting report."}
            </p>
          </div>
        </div>
      )}

      {report && (
        <>
          {/* Strengths & Weaknesses */}
          <section className="card stack">
            <h2 style={{ margin: 0 }}>Strengths &amp; Weaknesses</h2>
            <p className="muted">Based on percentile ranking vs the rest of the league. ≥ 70th percentile = strength, ≤ 30th = weakness.</p>
            <div className="grid grid-2">
              <div className="stack">
                <strong style={{ color: "var(--success)" }}>Strengths</strong>
                {report.strengths.length === 0 ? (
                  <p className="muted">No clear strengths identified.</p>
                ) : (
                  <div className="row" style={{ flexWrap: "wrap" }}>
                    {report.strengths.map((s) => (
                      <span key={s.metric} className="strength-pill positive" title={`${s.value} (${s.percentile}th percentile)`}>
                        {s.metric} · {s.percentile}th pct
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <div className="stack">
                <strong style={{ color: "var(--danger)" }}>Weaknesses</strong>
                {report.weaknesses.length === 0 ? (
                  <p className="muted">No clear weaknesses identified.</p>
                ) : (
                  <div className="row" style={{ flexWrap: "wrap" }}>
                    {report.weaknesses.map((w) => (
                      <span key={w.metric} className="strength-pill negative" title={`${w.value} (${w.percentile}th percentile)`}>
                        {w.metric} · {w.percentile}th pct
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </section>

          {/* Charts */}
          <div className="grid grid-2">
            <section className="card stack">
              <h2 style={{ margin: 0 }}>Attack Profile</h2>
              <Image alt="Attack Profile" src={getOppositionAssetUrl(league, activeSeason, selectedTeam, "shot-map")}
                width={1200} height={700} style={{ width: "100%", height: "auto", borderRadius: 14 }} unoptimized />
            </section>
            <section className="card stack">
              <h2 style={{ margin: 0 }}>League Comparison</h2>
              <Image alt="Radar comparison" src={getOppositionAssetUrl(league, activeSeason, selectedTeam, "radar")}
                width={1200} height={700} style={{ width: "100%", height: "auto", borderRadius: 14 }} unoptimized />
            </section>
          </div>

          {/* Key Players */}
          {report.top_players.length > 0 && (
            <section className="card stack">
              <h2 style={{ margin: 0 }}>Key Players to Watch</h2>
              <table className="table">
                <thead>
                  <tr><th>Player</th><th>Goals</th><th>xG</th><th>Minutes</th></tr>
                </thead>
                <tbody>
                  {report.top_players.map((p) => (
                    <tr key={p.player}>
                      <td><strong>{p.player}</strong></td>
                      <td>{p.goals}</td>
                      <td>{p.xg}</td>
                      <td>{p.mins}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}

          {/* H2H History */}
          {report.h2h.length > 0 && (
            <section className="card stack">
              <h2 style={{ margin: 0 }}>Head-to-Head Results This Season</h2>
              <div className="row">
                {report.h2h.map((m, i) => (
                  <span key={i} className="form-chip" title={`vs ${m.opponent} ${m.score}`}
                    style={{ backgroundColor: m.result === "W" ? "var(--success)" : m.result === "D" ? "var(--muted)" : "var(--danger)", color: "#fff" }}>
                    {m.result}
                  </span>
                ))}
              </div>
              <table className="table">
                <thead>
                  <tr><th>Date</th><th>Opponent</th><th>Result</th><th>Score</th></tr>
                </thead>
                <tbody>
                  {report.h2h.map((m, i) => (
                    <tr key={i}>
                      <td className="muted">{m.date}</td>
                      <td>{m.opponent}</td>
                      <td>
                        <span className="form-chip" style={{ backgroundColor: m.result === "W" ? "var(--success)" : m.result === "D" ? "var(--muted)" : "var(--danger)", color: "#fff" }}>
                          {m.result}
                        </span>
                      </td>
                      <td><strong>{m.score}</strong></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}
        </>
      )}
    </div>
  );
}
