"use client";

import { useMemo, useState } from "react";

import type { SeasonTeamMatches } from "../../lib/api";
import { LEAGUE_PRESENTATION } from "../../lib/leagues";
import { Plot } from "../../lib/plotly";
import { CHART_FONT_FAMILY } from "../../lib/theme";
import { DownloadPngButton } from "../DownloadPngButton";
import { renderImprovedPng, renderRollingPng } from "./trendExport";
import { fmtNum, useChartFrame, useSeasonFile } from "./useSeasonChart";

type Props = { league: string; season: string };
type Mode = "rolling" | "improved";

const plotConfig = { responsive: true, displayModeBar: false };
const GOOD = "#34d399";
const BAD = "#f87171";
const mean = (a: number[]) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : 0);

type TeamMatches = SeasonTeamMatches["teams"][number]["matches"];

/** Rolling mean of xG created / conceded over the last `size` matches (fewer at the start of the season). */
const rollingXg = (ms: TeamMatches, size: number, key: "xg" | "xga") => ms.map((_, i) => mean(ms.slice(Math.max(0, i - size + 1), i + 1).map((m) => m[key])));

/** xG difference per match in the latest `recent` games against everything before them, biggest improvement first. */
function improvedRows(data: SeasonTeamMatches, recent: number) {
  return data.teams
    .map((t) => {
      const diffs = t.matches.map((m) => m.xg - m.xga);
      if (diffs.length < recent + 2) return null;
      const early = mean(diffs.slice(0, diffs.length - recent));
      const late = mean(diffs.slice(diffs.length - recent));
      return { team: t.team, early, late, delta: late - early };
    })
    .filter((r): r is NonNullable<typeof r> => r !== null)
    .sort((a, b) => b.delta - a.delta);
}

export function SeasonTeamTrend({ league, season }: Props) {
  const { data, error } = useSeasonFile<SeasonTeamMatches>(league, season, "team-matches");
  const { themeColors, width, setHost, compact } = useChartFrame();
  const [mode, setMode] = useState<Mode>("rolling");
  const [team, setTeam] = useState("");
  const [windowSize, setWindowSize] = useState(4);
  const [recent, setRecent] = useState(4);

  const teams = useMemo(() => (data?.teams ?? []).map((t) => t.team).sort((a, b) => a.localeCompare(b)), [data]);
  const current = team || teams[0] || "";
  const maxPlayed = useMemo(() => Math.max(0, ...(data?.teams ?? []).map((t) => t.matches.length)), [data]);

  const figure = useMemo(() => {
    if (!data) return null;
    const font = { color: themeColors.text, family: CHART_FONT_FAMILY, size: compact ? 11 : 13 };
    const hoverlabel = { bgcolor: themeColors.hoverBg, font: { color: themeColors.hoverText, family: CHART_FONT_FAMILY } };
    const axis = (title: string) => ({
      title: { text: title, font: { color: themeColors.text, family: CHART_FONT_FAMILY, size: compact ? 11 : 13 }, standoff: 10 },
      gridcolor: themeColors.pitchLine,
      zeroline: false,
      linecolor: themeColors.pitchLine,
      tickfont: { color: themeColors.muted, family: CHART_FONT_FAMILY, size: compact ? 10 : 12 },
    });

    if (mode === "rolling") {
      const ms = data.teams.find((t) => t.team === current)?.matches ?? [];
      if (ms.length < 2) return null;
      const w = Math.min(windowSize, ms.length);
      const x = ms.map((_, i) => i + 1);
      const hover = (m: SeasonTeamMatches["teams"][number]["matches"][number], i: number, rolled: number[], label: string) =>
        `<b>${current}</b> ${m.v === "h" ? "vs" : "at"} ${m.opp}<br>${m.d} · ${m.gf}-${m.ga}<br>${label}: ${fmtNum(rolled[i])} (rolling ${w})<br>This match: xG ${fmtNum(m.xg)} · xGA ${fmtNum(m.xga)}`;
      const rf = rollingXg(ms, w, "xg");
      const ra = rollingXg(ms, w, "xga");
      return {
        data: [
          {
            type: "scatter", mode: "lines+markers", name: "xG created", x, y: rf, line: { color: "#a3e635", width: 3, shape: "spline", smoothing: 0.6 },
            marker: { size: 7 }, hovertext: ms.map((m, i) => hover(m, i, rf, "xG created")), hoverinfo: "text", hoverlabel,
          },
          {
            type: "scatter", mode: "lines+markers", name: "xG conceded", x, y: ra, line: { color: BAD, width: 3, shape: "spline", smoothing: 0.6 },
            marker: { size: 7 }, hovertext: ms.map((m, i) => hover(m, i, ra, "xG conceded")), hoverinfo: "text", hoverlabel,
          },
        ],
        layout: {
          width, height: compact ? 380 : 480, margin: { l: compact ? 48 : 64, r: 20, t: 40, b: compact ? 50 : 62 },
          paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: themeColors.surface, font, hovermode: "closest",
          legend: { orientation: "h", y: 1.1, x: 0, font: { color: themeColors.text, family: CHART_FONT_FAMILY } },
          xaxis: { ...axis("Match number"), dtick: 1 },
          yaxis: { ...axis(`xG per match (rolling ${w})`), rangemode: "tozero" },
        },
      };
    }

    // Most improved: xG difference per match over the latest N games compared with all the games before them.
    const rows = improvedRows(data, recent).reverse(); // plotly draws the first row at the bottom
    if (!rows.length) return null;
    return {
      data: [
        {
          type: "bar", orientation: "h", x: rows.map((r) => r.delta), y: rows.map((r) => r.team),
          marker: { color: rows.map((r) => (r.delta >= 0 ? GOOD : BAD)) },
          text: rows.map((r) => `${r.delta > 0 ? "+" : ""}${r.delta.toFixed(2)}`), textposition: "outside",
          textfont: { color: themeColors.text, family: CHART_FONT_FAMILY, size: 11 },
          hovertext: rows.map((r) => `<b>${r.team}</b><br>Before: ${r.early > 0 ? "+" : ""}${r.early.toFixed(2)} xG difference per match<br>Latest ${recent}: ${r.late > 0 ? "+" : ""}${r.late.toFixed(2)}`),
          hoverinfo: "text", hoverlabel,
        },
      ],
      layout: {
        width, height: Math.max(360, rows.length * (compact ? 22 : 26) + 90), margin: { l: compact ? 110 : 150, r: 50, t: 20, b: 56 },
        paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: themeColors.surface, font, showlegend: false,
        xaxis: axis(`Change in xG difference per match (latest ${recent} vs before)`),
        yaxis: { ...axis(""), tickfont: { color: themeColors.text, family: CHART_FONT_FAMILY, size: compact ? 10 : 12 }, automargin: true },
      },
    };
  }, [data, mode, current, windowSize, recent, themeColors, width, compact]);

  return (
    <section className="card stack">
      <div className="chart-card-head">
        <div>
          <h2>Form over time</h2>
          <p className="muted">
            {mode === "rolling"
              ? "Rolling average of the xG a team creates and concedes, match by match."
              : "Which teams have improved or slipped: xG difference per match in the latest games against everything before."}
          </p>
        </div>
        <DownloadPngButton
          filename={`${league}-${mode === "rolling" ? current : "most-improved"}-form`}
          title={mode === "rolling" ? `${current}: rolling xG` : "Most improved teams"}
          filters={() => (mode === "rolling" ? [`Rolling ${windowSize} matches`] : [`Latest ${recent} games vs before`])}
          renderImage={() => {
            if (!data) return Promise.resolve(null);
            const leagueInfo = LEAGUE_PRESENTATION[league];
            const where = `${leagueInfo?.name ?? league} ${season.replace("-", "/")}`;
            if (mode === "improved") {
              const rows = improvedRows(data, recent);
              return renderImprovedPng({ title: "Most improved teams", subtitle: [`Latest ${recent} games vs before`, where].join("  |  "), leagueLogo: leagueInfo?.logo, rows, recent });
            }
            const ms = data.teams.find((t) => t.team === current)?.matches ?? [];
            const w = Math.min(windowSize, ms.length);
            return renderRollingPng({
              title: `${current}: rolling xG`,
              subtitle: [`Rolling ${w} matches`, where].join("  |  "),
              leagueLogo: leagueInfo?.logo,
              series: [
                { name: "xG created", color: "#a3e635", values: rollingXg(ms, w, "xg") },
                { name: "xG conceded", color: BAD, values: rollingXg(ms, w, "xga") },
              ],
              xTitle: "Match number",
              yTitle: `xG per match (rolling ${w})`,
              note: "Each point is the average over the latest matches up to and including that one",
            });
          }}
        />
      </div>

      <div className="season-view-tabs" role="group" aria-label="Form view">
        {(["rolling", "improved"] as Mode[]).map((m) => (
          <button key={m} type="button" className={`season-view-tab${mode === m ? " is-active" : ""}`} onClick={() => setMode(m)}>
            {m === "rolling" ? "Rolling xG" : "Most improved"}
          </button>
        ))}
      </div>

      {error ? <p className="inline-warning">{error}</p> : null}

      <div className="season-scatter-controls">
        {mode === "rolling" ? (
          <>
            <label>
              <span>Team</span>
              <select className="select" value={current} onChange={(e) => setTeam(e.target.value)} disabled={!data}>
                {teams.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </label>
            <label>
              <span>Rolling window: {windowSize} matches</span>
              <input type="range" min={2} max={Math.max(3, Math.min(10, maxPlayed))} step={1} value={windowSize} onChange={(e) => setWindowSize(Number(e.target.value))} />
            </label>
          </>
        ) : (
          <label>
            <span>Latest games compared: {recent}</span>
            <input type="range" min={2} max={Math.max(3, Math.min(10, maxPlayed - 2))} step={1} value={recent} onChange={(e) => setRecent(Number(e.target.value))} />
          </label>
        )}
      </div>

      <div ref={setHost} className="plotly-chart-shell season-scatter-shell">
        {!data && !error ? <p className="muted">Loading…</p> : null}
        {data && !figure ? <p className="muted">Not enough matches played yet.</p> : null}
        {figure ? <Plot data={figure.data} layout={figure.layout} config={plotConfig} className="plotly-chart" style={{ width: "100%", height: figure.layout.height }} /> : null}
      </div>
    </section>
  );
}
