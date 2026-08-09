"use client";

import { useEffect, useState } from "react";

import { Plot } from "../../lib/plotly";
import { CHART_FONT_FAMILY, readThemeColors } from "../../lib/theme";
import { useCompactAnalysis } from "../../lib/useCompactAnalysis";
import { DownloadPngButton } from "../DownloadPngButton";
import { metricByKey, type TeamBaseline, type TeamSeasonMatch } from "./baselineTypes";

type Props = {
  teamA: string;
  teamB: string;
  teamAColor: string;
  teamBColor: string;
  baselines: Record<string, TeamBaseline>;
  /** Minutes played tonight — volume metrics are normalized to per-90. */
  fullTime?: number;
};

// Ratio metrics are never per-90 scaled.
const RATE_KEYS = new Set(["possession_pct", "pass_accuracy", "ppda"]);

const plotConfig = { responsive: true, displayModeBar: false };

// Metric rows for the match-vs-season bars, in display order.
const BAR_METRICS = [
  "goals", "xg", "xgot", "shots", "shots_on_target", "big_chances_created",
  "possession_pct", "pass_accuracy", "ppda", "turnovers", "xt", "epv_added",
];

function fmt(v: number) {
  return Math.abs(v) >= 10 ? v.toFixed(0) : v.toFixed(Math.abs(v) < 1 ? 2 : 1);
}

function clamp(v: number, lo: number, hi: number) {
  return Math.min(hi, Math.max(lo, v));
}

function rolling(values: number[], window: number): number[] {
  return values.map((_, i) => {
    const slice = values.slice(Math.max(0, i - window + 1), i + 1);
    return slice.reduce((a, b) => a + b, 0) / slice.length;
  });
}

export function TeamSeasonContextPanel({ teamA, teamB, teamAColor, teamBColor, baselines, fullTime }: Props) {
  const [themeColors, setThemeColors] = useState(readThemeColors);
  const compactAnalysis = useCompactAnalysis();
  useEffect(() => {
    setThemeColors(readThemeColors());
    const observer = new MutationObserver(() => setThemeColors(readThemeColors()));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "data-theme"] });
    return () => observer.disconnect();
  }, []);

  const chartMuted = themeColors.muted;
  const sides = [
    { team: teamA, color: teamAColor, baseline: baselines[teamA] },
    { team: teamB, color: teamBColor, baseline: baselines[teamB] },
  ].filter((side) => side.baseline && !side.baseline.lowSample && side.baseline.metrics.length);
  if (sides.length < 2) return null;

  const axisStyle = (title: string, range?: [number, number]) => ({
    title,
    range,
    zeroline: false,
    gridcolor: "rgba(148,163,184,0.22)",
    linecolor: "rgba(148,163,184,0.36)",
    tickfont: { color: chartMuted, size: compactAnalysis ? 8 : 11 },
    titlefont: { color: chartMuted, size: compactAnalysis ? 9 : 12 },
  });
  const baseLayout = (height: number) => ({
    autosize: true,
    height,
    margin: compactAnalysis ? { l: 38, r: 10, t: 8, b: 32 } : { l: 52, r: 24, t: 18, b: 48 },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(148,163,184,0.08)",
    font: { color: themeColors.text, family: CHART_FONT_FAMILY, size: compactAnalysis ? 9 : 12 },
    legend: { orientation: "h" as const, y: -0.2, x: 0, font: { color: chartMuted, size: compactAnalysis ? 8 : 12 } },
  });

  // ── #1 match vs season bars (volume metrics normalized to per-90) ─────────
  const per90Factor = 90 / Math.max(90, fullTime ?? 90);
  const barRows = BAR_METRICS.flatMap((key) => {
    const entries = sides.map((side) => metricByKey(side.baseline, key));
    if (entries.some((m) => !m || m.seasonAvg === undefined || m.nMatches < 4)) return [];
    const label = entries[0]!.label;
    const factor = RATE_KEYS.has(key) ? 1 : per90Factor;
    const tonight = entries.map((m) => m!.matchValue * factor);
    const pcts = entries.map((m, i) => {
      const denom = Math.max(Math.abs(m!.seasonAvg ?? 0), 0.05);
      return clamp(((tonight[i] - (m!.seasonAvg ?? 0)) / denom) * 100, -100, 100);
    });
    return [{ key, label, entries, tonight, pcts }];
  });
  const barHeight = compactAnalysis ? Math.max(260, barRows.length * 30 + 70) : Math.max(340, barRows.length * 52 + 110);

  // ── #2 scatter + #3 rolling form data ─────────────────────────────────────
  const tonight = sides.map((side) => ({
    xg: metricByKey(side.baseline, "xg")?.matchValue ?? 0,
  }));
  const tonightByTeam: Record<string, { xg: number; xga: number }> = {
    [sides[0].team]: { xg: tonight[0].xg, xga: tonight[1].xg },
    [sides[1].team]: { xg: tonight[1].xg, xga: tonight[0].xg },
  };
  const allSeason = sides.flatMap((side) => (side.baseline.matches ?? []).map((m) => ({ ...m, team: side.team })));
  const scatterMax = Math.max(1, ...allSeason.map((m) => Math.max(m.xg, m.xga)), ...sides.map((s) => Math.max(tonightByTeam[s.team].xg, tonightByTeam[s.team].xga))) * 1.1;

  const formSeries = sides.map((side) => {
    const matches: TeamSeasonMatch[] = [...(side.baseline.matches ?? [])];
    const xgd = matches.map((m) => m.xg - m.xga);
    xgd.push(tonightByTeam[side.team].xg - tonightByTeam[side.team].xga);
    return { ...side, labels: [...matches.map((m) => m.opponent), "Tonight"], rolling: rolling(xgd, 5) };
  });

  return (
    <section className="card stack">
      <div className="chart-card-head">
        <div>
          <span className="eyebrow">Season Context</span>
          <h2 style={{ margin: "6px 0 0" }}>This match vs the season</h2>
        </div>
      </div>

      {barRows.length >= 3 ? (
        <div className="stack season-chart-scope" style={{ gap: 6 }}>
          <div className="chart-card-head">
            <h3 className="comb-subtitle" style={{ margin: 0 }}>Over / under each side&apos;s season level</h3>
            <DownloadPngButton
              filename={`${teamA}-vs-${teamB}-season-baseline`}
              title="Match vs Season Baselines"
              scopeSelector=".season-chart-scope"
              filters={["Per 90"]}
              chartPanels={() => [{
                legend: sides.map((side) => ({ label: side.team, color: side.color, shape: "square" as const })),
              }]}
            />
          </div>
          <Plot
            data={sides.map((side, sideIndex) => ({
              x: barRows.map((row) => row.pcts[sideIndex]),
              y: barRows.map((row) => row.label),
              name: side.team,
              type: "bar",
              orientation: "h",
              marker: { color: side.color, line: { color: themeColors.panel, width: 1 } },
              // Short single number (tonight, per-90) so it fits every bar;
              // the season value and % delta live in the hover.
              text: barRows.map((row) => ` ${fmt(row.tonight[sideIndex])} `),
              textposition: "auto",
              textangle: 0,
              textfont: { size: compactAnalysis ? 8 : 11, family: CHART_FONT_FAMILY },
              outsidetextfont: { color: themeColors.text, size: compactAnalysis ? 8 : 11, family: CHART_FONT_FAMILY },
              constraintext: "none",
              cliponaxis: false,
              customdata: barRows.map((row) => [fmt(row.tonight[sideIndex]), fmt(row.entries[sideIndex]!.seasonAvg ?? 0), Math.round(row.pcts[sideIndex])]),
              hovertemplate: `%{y} — ${side.team}<br>tonight %{customdata[0]} vs season %{customdata[1]} per 90 (%{customdata[2]}%)<extra></extra>`,
            })) as never}
            layout={{
              ...baseLayout(barHeight),
              barmode: "group",
              bargap: 0.3,
              bargroupgap: 0.12,
              margin: compactAnalysis ? { l: 82, r: 28, t: 4, b: 32 } : { l: 130, r: 60, t: 8, b: 48 },
              hovermode: "closest",
              xaxis: {
                ...axisStyle("% vs own season average", [-118, 118]),
                tickvals: [-100, -50, 0, 50, 100],
                ticktext: ["−100%", "−50%", "season", "+50%", "+100%"],
              },
              yaxis: { autorange: "reversed", gridcolor: "rgba(148,163,184,0.12)", tickfont: { color: themeColors.text, size: compactAnalysis ? 8 : 12 } },
              shapes: [{ type: "line", xref: "x", yref: "paper", x0: 0, x1: 0, y0: 0, y1: 1, line: { color: "rgba(148,163,184,0.6)", width: 1.5, dash: "dot" } }],
            } as never}
            config={plotConfig}
            className="plotly-chart"
          />
          <p className="chart-footnote">
            Bars compare tonight&apos;s per-90 value with each side&apos;s season per-90 average (dotted line; bars capped
            at ±100%) — the number on each bar is tonight&apos;s value, hover for the season figure. Possession, pass
            accuracy and PPDA compare as rates; for PPDA and turnovers a left bar is the better direction.
          </p>
        </div>
      ) : null}

      <div className="grid grid-2">
        <div className="stack season-chart-scope" style={{ gap: 6 }}>
          <div className="chart-card-head">
            <h3 className="comb-subtitle" style={{ margin: 0 }}>Where tonight sits in their seasons</h3>
            <DownloadPngButton
              filename={`${teamA}-vs-${teamB}-season-scatter`}
              title="Season xG Map"
              scopeSelector=".season-chart-scope"
              chartPanels={() => [{
                legend: [
                  ...sides.map((side) => ({ label: `${side.team} season`, color: side.color, shape: "circle" as const })),
                  ...sides.map((side) => ({ label: `${side.team} tonight`, color: side.color, shape: "square" as const })),
                ],
              }]}
            />
          </div>
          <Plot
            data={[
              ...sides.map((side) => ({
                x: (side.baseline.matches ?? []).map((m) => m.xg),
                y: (side.baseline.matches ?? []).map((m) => m.xga),
                name: `${side.team} season`,
                type: "scatter",
                mode: "markers",
                marker: { color: side.color, size: 8, opacity: 0.35 },
                customdata: (side.baseline.matches ?? []).map((m) => [m.opponent, m.date, `${m.goals}–${m.goalsAgainst}`]),
                hovertemplate: "vs %{customdata[0]} (%{customdata[1]}, %{customdata[2]})<br>xG %{x:.2f} · xGA %{y:.2f}<extra></extra>",
              })),
              ...sides.map((side) => ({
                x: [tonightByTeam[side.team].xg],
                y: [tonightByTeam[side.team].xga],
                name: `${side.team} tonight`,
                type: "scatter",
                mode: "markers",
                marker: { color: side.color, size: 16, symbol: "diamond", line: { color: themeColors.panel, width: 2 } },
                hovertemplate: `${side.team} tonight<br>xG %{x:.2f} · xGA %{y:.2f}<extra></extra>`,
              })),
            ] as never}
            layout={{
              ...baseLayout(compactAnalysis ? 240 : 360),
              hovermode: "closest",
              xaxis: axisStyle("xG created", [0, scatterMax]),
              yaxis: axisStyle("xG conceded", [0, scatterMax]),
              shapes: [{ type: "line", xref: "x", yref: "y", x0: 0, y0: 0, x1: scatterMax, y1: scatterMax, line: { color: "rgba(148,163,184,0.4)", width: 1, dash: "dot" } }],
              annotations: [
                { x: scatterMax * 0.82, y: scatterMax * 0.06, text: "dominant", showarrow: false, font: { size: 10, color: chartMuted } },
                { x: scatterMax * 0.08, y: scatterMax * 0.95, text: "under siege", showarrow: false, font: { size: 10, color: chartMuted } },
              ],
            } as never}
            config={plotConfig}
            className="plotly-chart"
          />
          <p className="chart-footnote">
            Every match of each side&apos;s season by xG created and conceded — faded dots are past matches, the large
            diamonds are tonight. Below the dotted diagonal means outcreating the opponent.
          </p>
        </div>
        <div className="stack season-chart-scope" style={{ gap: 6 }}>
          <div className="chart-card-head">
            <h3 className="comb-subtitle" style={{ margin: 0 }}>Form coming into tonight</h3>
            <DownloadPngButton
              filename={`${teamA}-vs-${teamB}-form-into-tonight`}
              title="Form Into Tonight"
              scopeSelector=".season-chart-scope"
              filters={["Rolling 5-match xG diff"]}
              chartPanels={() => [{
                legend: sides.map((side) => ({ label: side.team, color: side.color, shape: "line" as const })),
              }]}
            />
          </div>
          <Plot
            data={formSeries.map((side) => ({
              x: side.labels.map((_, i) => i + 1),
              y: side.rolling,
              name: side.team,
              type: "scatter",
              mode: "lines+markers",
              line: { color: side.color, width: 3 },
              marker: {
                color: side.color,
                size: side.labels.map((_, i) => (i === side.labels.length - 1 ? 12 : 5)),
                symbol: side.labels.map((_, i) => (i === side.labels.length - 1 ? "diamond" : "circle")),
                line: { color: themeColors.panel, width: 1 },
              },
              customdata: side.labels,
              hovertemplate: "%{customdata}: rolling xG diff %{y:.2f}<extra></extra>",
            })) as never}
            layout={{
              ...baseLayout(compactAnalysis ? 240 : 360),
              hovermode: "x unified",
              xaxis: axisStyle("Match number"),
              yaxis: axisStyle("Rolling 5-match xG difference"),
              shapes: [{ type: "line", xref: "paper", yref: "y", x0: 0, x1: 1, y0: 0, y1: 0, line: { color: "rgba(148,163,184,0.4)", width: 1, dash: "dot" } }],
            } as never}
            config={plotConfig}
            className="plotly-chart"
          />
          <p className="chart-footnote">
            Rolling five-match xG difference through the season, ending with tonight (diamond) — above zero means
            sustained chance superiority; the last step shows whether tonight extended or broke the trend.
          </p>
        </div>
      </div>
    </section>
  );
}
