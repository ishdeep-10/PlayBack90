"use client";

import { useEffect, useState } from "react";

import { Plot } from "../../lib/plotly";
import { CHART_FONT_FAMILY, readThemeColors } from "../../lib/theme";
import { DownloadPngButton } from "../DownloadPngButton";
import { metricByKey, type MetricGroup, type PlayerBaseline } from "./baselineTypes";

export type SeasonContextPlayer = {
  player: string;
  baseline: PlayerBaseline;
  color: string;
};

type Props = {
  players: SeasonContextPlayer[];
  groups: MetricGroup[];
};

type DeltaRow = {
  key: string;
  label: string;
  pct: number;
  match: number;
  season: number;
};

const plotConfig = { responsive: true, displayModeBar: false };

function fmt(v: number) {
  return Math.abs(v) >= 10 ? v.toFixed(0) : v.toFixed(Math.abs(v) < 1 ? 2 : 1);
}

function clamp(v: number, lo: number, hi: number) {
  return Math.min(hi, Math.max(lo, v));
}

function ordinal(n: number): string {
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return `${n}${s[(v - 20) % 10] ?? s[v] ?? s[0]}`;
}

export function SeasonContextPanel({ players, groups }: Props) {
  const [themeColors, setThemeColors] = useState(readThemeColors);
  const [groupId, setGroupId] = useState(groups[0]?.id ?? "");

  useEffect(() => {
    setThemeColors(readThemeColors());
    const observer = new MutationObserver(() => setThemeColors(readThemeColors()));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "data-theme"] });
    return () => observer.disconnect();
  }, []);

  const group = groups.find((candidate) => candidate.id === groupId) ?? groups[0];
  if (!group || !players.length) return null;

  const eligiblePlayers = players.filter(({ baseline }) => !baseline.lowSample);
  const lowSamplePlayers = players.filter(({ baseline }) => baseline.lowSample);
  const chartMuted = themeColors.muted;
  const comparisonTitle =
    players.length === 1 ? players[0].player : players.map(({ player }) => player).join(" vs ");

  const metricsByPlayer = eligiblePlayers.map((entry) => ({
    ...entry,
    metrics: group.keys
      .map((key) => metricByKey(entry.baseline, key))
      .filter((metric): metric is NonNullable<typeof metric> => Boolean(metric)),
  }));

  const deltasByPlayer = metricsByPlayer.map((entry) => ({
    ...entry,
    deltas: entry.metrics.flatMap((metric): DeltaRow[] => {
      if (metric.matchValuePer90 === undefined || metric.seasonPer90 === undefined) return [];
      const season = metric.seasonPer90;
      const match = metric.matchValuePer90;
      if (season < 0.02 && match < 0.02) return [];
      const denominator = Math.max(season, 0.25 * (metric.leagueMeanPer90 ?? 0), 0.05);
      return [{
        key: metric.key,
        label: metric.label,
        pct: clamp(((match - season) / denominator) * 100, -100, 100),
        match,
        season,
      }];
    }),
  }));

  const deltaMetricKeys = group.keys.filter((key) =>
    deltasByPlayer.some((entry) => entry.deltas.some((delta) => delta.key === key))
  );
  const deltaLabels = deltaMetricKeys.map((key) =>
    deltasByPlayer.flatMap((entry) => entry.deltas).find((delta) => delta.key === key)?.label ?? key
  );
  const radarKeys = group.keys.filter((key) =>
    metricsByPlayer.some((entry) =>
      entry.metrics.some((metric) => metric.key === key && metric.leaguePercentilePer90 !== undefined)
    )
  );
  const radarLabels = radarKeys.map((key) =>
    metricsByPlayer.flatMap((entry) => entry.metrics).find((metric) => metric.key === key)?.label ?? key
  );
  const chartHeight = Math.max(330, deltaMetricKeys.length * Math.max(48, eligiblePlayers.length * 25) + 100);

  const standouts = metricsByPlayer.flatMap((entry) =>
    entry.metrics
      .filter((metric) =>
        metric.gameRank !== undefined && metric.nMatches >= 5 && metric.gameRank <= 3 && metric.matchValue > 0
      )
      .sort((a, b) => (a.gameRank ?? 99) - (b.gameRank ?? 99))
      .slice(0, 1)
      .map((metric) => `${entry.player}: ${ordinal(metric.gameRank ?? 0)}-best ${metric.label} game`)
  );

  const legend = (
    <div className="season-radar-legend" aria-label="Player comparison colors">
      {players.map(({ player, baseline, color }) => (
        <span key={`${player}|${baseline.team}`} className="season-radar-legend-item">
          <i className="season-radar-swatch" style={{ background: color }} />
          <strong>{player}</strong>
          <span>{baseline.matchesPlayed} matches · {baseline.minsSeason} mins</span>
        </span>
      ))}
    </div>
  );

  const comparisonLegend = players.map(({ player, color }) => ({
    label: player,
    color,
    shape: "line" as const,
  }));
  const exportChartLabels = [
    ...(deltaMetricKeys.length >= 2 ? [`Match vs own season · ${group.label.toLowerCase()}`] : []),
    ...(radarKeys.length >= 3 ? [`League percentile · ${group.label.toLowerCase()}`] : []),
  ];

  const header = (
    <div className="season-context-header">
      <div>
        <span className="eyebrow">Season Context</span>
        <h2>{comparisonTitle}</h2>
      </div>
      <div className="season-context-actions">
        <div className="row season-context-tabs">
          {groups.map((candidate) => (
            <button
              key={candidate.id}
              type="button"
              className={candidate.id === group.id ? "button" : "ghost-button"}
              onClick={() => setGroupId(candidate.id)}
            >
              {candidate.label}
            </button>
          ))}
        </div>
        {eligiblePlayers.length > 0 && exportChartLabels.length > 0 && (
          <DownloadPngButton
            filename={`${comparisonTitle}-season-context-${group.id}`}
            title={() => `${comparisonTitle} · Season Context`}
            scopeSelector=".season-context-panel"
            filters={() => [group.label, "Per 90"]}
            chartLabels={() => exportChartLabels}
            chartPanels={() => exportChartLabels.map(() => ({ legend: comparisonLegend }))}
            maxCharts={2}
            chartsPerRow={2}
          />
        )}
      </div>
    </div>
  );

  if (!eligiblePlayers.length) {
    return (
      <section className="card stack season-context-panel">
        {header}
        {legend}
        <p className="chart-footnote">
          Season context needs at least 450 season minutes and 20 minutes in this match. The selected players are
          below that threshold.
        </p>
      </section>
    );
  }

  const axisStyle = (title: string, range?: [number, number]) => ({
    title,
    range,
    zeroline: false,
    gridcolor: "rgba(148,163,184,0.22)",
    linecolor: "rgba(148,163,184,0.36)",
    tickfont: { color: chartMuted, size: 11 },
    titlefont: { color: chartMuted, size: 12 },
  });

  return (
    <section className="card stack season-context-panel">
      {header}
      {legend}
      {lowSamplePlayers.length > 0 && (
        <p className="season-context-warning">
          Not charted due to the sample threshold:{" "}
          {lowSamplePlayers
            .map(({ player, baseline }) => `${player} (${baseline.minsSeason} season mins, ${baseline.matchMins} today)`)
            .join("; ")}.
        </p>
      )}
      <div className="grid grid-2 season-context-grid">
        <div className="stack season-chart-scope" style={{ gap: 6 }}>
          <div className="chart-card-head">
            <h3 className="comb-subtitle">Match vs own season · {group.label.toLowerCase()}</h3>
          </div>
          {deltaMetricKeys.length >= 2 ? (
            <Plot
              data={deltasByPlayer.map((entry) => ({
                name: entry.player,
                x: deltaMetricKeys.map((key) => entry.deltas.find((delta) => delta.key === key)?.pct ?? null),
                y: deltaLabels,
                type: "bar",
                orientation: "h",
                marker: {
                  color: entry.color,
                  line: { color: themeColors.panel, width: 1 },
                },
                customdata: deltaMetricKeys.map((key) => {
                  const delta = entry.deltas.find((candidate) => candidate.key === key);
                  return delta ? [fmt(delta.match), fmt(delta.season), Math.round(delta.pct)] : ["—", "—", "—"];
                }),
                hovertemplate:
                  `${entry.player}<br>%{y}<br>this match %{customdata[0]} vs season %{customdata[1]} per 90 (%{customdata[2]}%)<extra></extra>`,
              })) as never}
              layout={{
                autosize: true,
                height: chartHeight,
                margin: { l: 150, r: 34, t: 12, b: 50 },
                paper_bgcolor: "rgba(0,0,0,0)",
                plot_bgcolor: "rgba(148,163,184,0.08)",
                font: { color: themeColors.text, family: CHART_FONT_FAMILY },
                hovermode: "closest",
                showlegend: false,
                barmode: "group",
                bargap: 0.28,
                bargroupgap: 0.08,
                xaxis: {
                  ...axisStyle("% vs own season per 90", [-118, 118]),
                  tickvals: [-100, -50, 0, 50, 100],
                  ticktext: ["−100%", "−50%", "season", "+50%", "+100%"],
                },
                yaxis: {
                  autorange: "reversed",
                  gridcolor: "rgba(148,163,184,0.12)",
                  tickfont: { color: themeColors.text, size: 12 },
                },
                shapes: [{
                  type: "line",
                  xref: "x",
                  yref: "paper",
                  x0: 0,
                  x1: 0,
                  y0: 0,
                  y1: 1,
                  line: { color: "rgba(148,163,184,0.6)", width: 1.5, dash: "dot" },
                }],
              } as never}
              config={plotConfig}
              className="plotly-chart"
            />
          ) : (
            <p className="chart-footnote">Not enough data for {group.label.toLowerCase()} yet.</p>
          )}
          <p className="chart-footnote">
            Each bar compares that player&apos;s match per-90 rate with their own season level. Values are capped at
            ±100%; hover for match and season values.
          </p>
        </div>

        <div className="stack season-chart-scope" style={{ gap: 6 }}>
          <div className="chart-card-head">
            <h3 className="comb-subtitle">League percentile · {group.label.toLowerCase()}</h3>
          </div>
          {radarKeys.length >= 3 ? (
            <Plot
              data={metricsByPlayer.flatMap((entry) => {
                const values = radarKeys.map((key) =>
                  entry.metrics.find((metric) => metric.key === key)?.leaguePercentilePer90
                );
                if (values.filter((value) => value !== undefined).length < 3) return [];
                const radarValues = values.map((value) => value ?? 0);
                return [{
                  name: entry.player,
                  type: "scatterpolar",
                  r: [...radarValues, radarValues[0]],
                  theta: [...radarLabels, radarLabels[0]],
                  fill: "toself",
                  fillcolor: `${entry.color}24`,
                  line: { color: entry.color, width: 2.5 },
                  marker: { color: entry.color, size: 5 },
                  hovertemplate: `${entry.player}<br>%{theta}: %{r:.0f}th percentile<extra></extra>`,
                }];
              }) as never}
              layout={{
                autosize: true,
                height: chartHeight,
                margin: { l: 100, r: 100, t: 28, b: 40 },
                paper_bgcolor: "rgba(0,0,0,0)",
                font: { color: chartMuted, family: CHART_FONT_FAMILY, size: 11 },
                showlegend: false,
                polar: {
                  bgcolor: "rgba(148,163,184,0.08)",
                  radialaxis: {
                    range: [0, 100],
                    tickvals: [25, 50, 75],
                    tickfont: { size: 9, color: chartMuted },
                    gridcolor: "rgba(148,163,184,0.22)",
                    linecolor: "transparent",
                    angle: 90,
                    tickangle: 90,
                  },
                  angularaxis: {
                    tickfont: { size: 10, color: themeColors.text },
                    gridcolor: "rgba(148,163,184,0.22)",
                    linecolor: "rgba(148,163,184,0.36)",
                    rotation: 90,
                    direction: "clockwise",
                  },
                },
              } as never}
              config={plotConfig}
              className="plotly-chart"
            />
          ) : (
            <p className="chart-footnote">Not enough league data for {group.label.toLowerCase()} yet.</p>
          )}
          <p className="chart-footnote">
            Season per-90 output as league percentile ranks among players with 450+ minutes.
            {standouts.length ? ` Today: ${standouts.join("; ")}.` : ""}
          </p>
        </div>
      </div>
    </section>
  );
}
