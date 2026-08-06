"use client";

import { useEffect, useState } from "react";

import type { OppositionDossier, OppositionMetricRow } from "../lib/api";
import { horizontalPitchShapes, JUEGO_X, JUEGO_Y } from "../lib/pitch";
import { Plot } from "../lib/plotly";
import { CHART_FONT_FAMILY, colorWithAlpha, readThemeColors } from "../lib/theme";

type Props = {
  radarMetrics: OppositionMetricRow[];
  recentMatches: OppositionDossier["recentForm"]["matches"];
};

type EventPitchProfile = NonNullable<NonNullable<OppositionDossier["inPossessionProfile"]>["event_pitch_profile"]>;
type EventPitchRow = EventPitchProfile["progressive_actions"][number];
type PitchSituation = "all" | "open_play" | "transition" | "direct" | "set_piece";

const SITUATION_OPTIONS: Array<{ value: PitchSituation; label: string }> = [
  { value: "all", label: "All situations" },
  { value: "open_play", label: "Open play" },
  { value: "transition", label: "Transition" },
  { value: "direct", label: "Direct" },
  { value: "set_piece", label: "Set pieces" },
];

const plotConfig = {
  responsive: true,
  displayModeBar: false,
};

function formatMetric(value?: number) {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  return value.toFixed(value >= 10 ? 1 : 2);
}

function compactDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("en-GB", { day: "2-digit", month: "short" });
}

export function OppositionStyleRadarPlotly({ radarMetrics }: { radarMetrics: OppositionMetricRow[] }) {
  const [themeColors, setThemeColors] = useState(readThemeColors);

  useEffect(() => {
    const update = () => setThemeColors(readThemeColors());
    const observer = new MutationObserver(update);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "data-theme"] });
    window.addEventListener("themechange", update);
    return () => {
      observer.disconnect();
      window.removeEventListener("themechange", update);
    };
  }, []);

  const labels = radarMetrics.map((metric) => metric.label);
  const values = radarMetrics.map((metric) => metric.higher_is_better === false ? 100 - metric.percentile : metric.percentile);
  const hover = radarMetrics.map((metric) => {
    const score = metric.higher_is_better === false ? 100 - metric.percentile : metric.percentile;
    return `${metric.label}<br>Value: ${formatMetric(metric.value)}<br>League avg: ${formatMetric(metric.league_average)}<br>Profile score: ${formatMetric(score)}<br>Percentile: ${formatMetric(metric.percentile)}%`;
  });

  return (
    <div className="opposition-plotly-shell">
      <Plot
        data={[
          {
            type: "scatterpolar",
            r: [...values, values[0] ?? 0],
            theta: [...labels, labels[0] ?? ""],
            mode: "lines+markers",
            fill: "toself",
            name: "Profile",
            text: [...hover, hover[0] ?? ""],
            hovertemplate: "%{text}<extra></extra>",
            line: { color: themeColors.accent, width: 3 },
            marker: { color: themeColors.accent, size: 7 },
            fillcolor: "rgba(163, 230, 53, 0.24)",
          },
        ]}
        layout={{
          autosize: true,
          paper_bgcolor: "rgba(0,0,0,0)",
          plot_bgcolor: "rgba(0,0,0,0)",
          margin: { l: 58, r: 58, t: 26, b: 34 },
          font: { color: themeColors.text, family: CHART_FONT_FAMILY },
          polar: {
            bgcolor: "rgba(0,0,0,0)",
            radialaxis: {
              range: [0, 100],
              tickvals: [25, 50, 75, 100],
              tickfont: { color: themeColors.muted, size: 10 },
              gridcolor: themeColors.pitchLine,
              linecolor: themeColors.pitchLine,
            },
            angularaxis: {
              tickfont: { color: themeColors.muted, size: 10 },
              gridcolor: themeColors.pitchLine,
              linecolor: themeColors.pitchLine,
            },
          },
          showlegend: false,
        }}
        config={plotConfig}
        className="plotly-chart"
        style={{ width: "100%", height: "360px" }}
      />
    </div>
  );
}

export function OppositionRecentFormPlotly({
  recentMatches,
  opponentLogos = {},
}: {
  recentMatches: OppositionDossier["recentForm"]["matches"];
  opponentLogos?: Record<string, string | null>;
}) {
  const [themeColors, setThemeColors] = useState(readThemeColors);

  useEffect(() => {
    const update = () => setThemeColors(readThemeColors());
    const observer = new MutationObserver(update);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "data-theme"] });
    window.addEventListener("themechange", update);
    return () => {
      observer.disconnect();
      window.removeEventListener("themechange", update);
    };
  }, []);

  const matches = [...recentMatches].reverse();
  const positions = matches.map((_, index) => index);
  const hover = matches.map((match) => `${compactDate(match.date)} vs ${match.opponent}<br>Score: ${match.score}<br>xG: ${formatMetric(match.xg)}<br>xGA: ${formatMetric(match.xga)}`);
  const logoImages = matches
    .map((match, index) => {
      const source = opponentLogos[match.opponent];
      if (!source) return null;
      return {
        source,
        xref: "x",
        yref: "paper",
        x: index,
        y: -0.18,
        sizex: 0.36,
        sizey: 0.16,
        xanchor: "center",
        yanchor: "middle",
        layer: "above",
      };
    })
    .filter(Boolean);

  return (
    <div className="opposition-plotly-shell">
      <Plot
        data={[
          {
            type: "scatter",
            mode: "lines+markers",
            name: "xG",
            x: positions,
            y: matches.map((match) => match.xg),
            text: hover,
            hovertemplate: "%{text}<extra>xG</extra>",
            line: { color: "#22c55e", width: 3, shape: "spline" },
            marker: { color: "#22c55e", size: 8 },
          },
          {
            type: "scatter",
            mode: "lines+markers",
            name: "xGA",
            x: positions,
            y: matches.map((match) => match.xga),
            text: hover,
            hovertemplate: "%{text}<extra>xGA</extra>",
            line: { color: "#ef4444", width: 3, shape: "spline" },
            marker: { color: "#ef4444", size: 8 },
          },
        ]}
        layout={{
          autosize: true,
          paper_bgcolor: "rgba(0,0,0,0)",
          plot_bgcolor: "rgba(0,0,0,0)",
          margin: { l: 42, r: 18, t: 20, b: 76 },
          font: { color: themeColors.text, family: CHART_FONT_FAMILY },
          xaxis: {
            range: [-0.5, Math.max(0.5, matches.length - 0.5)],
            tickmode: "array",
            tickvals: positions,
            ticktext: positions.map(() => ""),
            showticklabels: false,
            gridcolor: "rgba(0,0,0,0)",
            linecolor: themeColors.pitchLine,
            zeroline: false,
          },
          yaxis: {
            rangemode: "tozero",
            tickfont: { color: themeColors.muted, size: 11 },
            gridcolor: themeColors.pitchLine,
            linecolor: themeColors.pitchLine,
            title: { text: "Expected goals", font: { color: themeColors.muted, size: 11 } },
          },
          legend: { orientation: "h", y: -0.22, x: 0, font: { color: themeColors.muted, size: 12 } },
          hovermode: "x unified",
          images: logoImages,
        }}
        config={plotConfig}
        className="plotly-chart"
        style={{ width: "100%", height: "320px" }}
      />
    </div>
  );
}

function validPoint(row: EventPitchRow) {
  return typeof row.x === "number" && typeof row.y === "number";
}

function validEndPoint(row: EventPitchRow) {
  return typeof row.end_x === "number" && typeof row.end_y === "number";
}

type PitchBin = {
  key: string;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  cx: number;
  cy: number;
  count: number;
  value: number;
  progressive: number;
  boxEntries: number;
  startX: number;
  startY: number;
  endX: number;
  endY: number;
  endCount: number;
};

function aggregateBins(rows: EventPitchRow[]) {
  const bins = new Map<string, PitchBin>();
  rows.filter(validPoint).forEach((row) => {
    const xIndex = JUEGO_X.findIndex((value, index) => Number(row.x) >= value && Number(row.x) < (JUEGO_X[index + 1] ?? 106));
    const yIndex = JUEGO_Y.findIndex((value, index) => Number(row.y) >= value && Number(row.y) < (JUEGO_Y[index + 1] ?? 69));
    if (xIndex < 0 || yIndex < 0) return;
    const key = `${xIndex}:${yIndex}`;
    const bin = bins.get(key) ?? {
      key,
      x0: JUEGO_X[xIndex],
      y0: JUEGO_Y[yIndex],
      x1: JUEGO_X[xIndex + 1],
      y1: JUEGO_Y[yIndex + 1],
      cx: (JUEGO_X[xIndex] + JUEGO_X[xIndex + 1]) / 2,
      cy: (JUEGO_Y[yIndex] + JUEGO_Y[yIndex + 1]) / 2,
      count: 0,
      value: 0,
      progressive: 0,
      boxEntries: 0,
      startX: 0,
      startY: 0,
      endX: 0,
      endY: 0,
      endCount: 0,
    };
    bin.count += 1;
    bin.value += Number(row.value ?? 0);
    bin.progressive += row.kind === "progressive" ? 1 : 0;
    bin.boxEntries += row.kind === "box_entry" ? 1 : 0;
    if (validEndPoint(row)) {
      bin.startX += Number(row.x);
      bin.startY += Number(row.y);
      bin.endX += Number(row.end_x);
      bin.endY += Number(row.end_y);
      bin.endCount += 1;
    }
    bins.set(key, bin);
  });
  return [...bins.values()];
}

function binShapes(bins: PitchBin[], accent: string, mode: "progression" | "shots") {
  const maxMetric = Math.max(1, ...bins.map((bin) => mode === "shots" ? bin.value : bin.count));
  return bins.map((bin) => {
    const metric = mode === "shots" ? bin.value : bin.count;
    const alpha = 0.1 + (metric / maxMetric) * 0.36;
    return {
      type: "rect",
      x0: bin.x0,
      y0: bin.y0,
      x1: bin.x1,
      y1: bin.y1,
      line: {
        color: bin.boxEntries > 0 ? "#facc15" : colorWithAlpha(accent, 0.25),
        width: bin.boxEntries > 0 ? 1.8 : 0,
      },
      fillcolor: colorWithAlpha(accent, alpha),
      layer: "below",
    };
  });
}

function binArrowAnnotations(bins: PitchBin[], color: string, limit: number) {
  return bins
    .filter((bin) => bin.endCount > 0)
    .sort((a, b) => b.count - a.count)
    .slice(0, limit)
    .map((bin) => ({
      x: bin.endX / bin.endCount,
      y: bin.endY / bin.endCount,
      ax: bin.startX / bin.endCount,
      ay: bin.startY / bin.endCount,
      xref: "x",
      yref: "y",
      axref: "x",
      ayref: "y",
      showarrow: true,
      arrowhead: 2,
      arrowsize: 1,
      arrowwidth: bin.boxEntries > 0 ? 2.5 : 1.7,
      arrowcolor: bin.boxEntries > 0 ? "#facc15" : color,
      opacity: bin.boxEntries > 0 ? 0.86 : 0.58,
    }));
}

function binLabel(bin: PitchBin, mode: "progression" | "shots") {
  if (mode === "shots") return `${bin.count}<br>${formatMetric(bin.value)} xG`;
  return bin.boxEntries > 0 ? `${bin.count}<br>${bin.boxEntries} box` : `${bin.count}`;
}

function binHover(bin: PitchBin, mode: "progression" | "shots") {
  if (mode === "shots") return `Shot zone<br>Shots: ${bin.count}<br>xG: ${formatMetric(bin.value)}`;
  return `Progression zone<br>Actions: ${bin.count}<br>Progressive: ${bin.progressive}<br>Box entries: ${bin.boxEntries}<br>xT: ${formatMetric(bin.value)}`;
}

function buildUpBinTrace(bins: PitchBin[], name: string, color: string, themeColors: ReturnType<typeof readThemeColors>, yOffset = 0) {
  return {
    type: "scatter",
    mode: "markers+text",
    name,
    x: bins.map((bin) => bin.cx),
    y: bins.map((bin) => bin.cy + yOffset),
    text: bins.map((bin) => String(bin.count)),
    hovertext: bins.map((bin) => `${name}<br>Actions: ${bin.count}`),
    hovertemplate: "%{hovertext}<extra></extra>",
    texttemplate: "%{text}",
    textposition: "middle center",
    textfont: { color: themeColors.text, size: 10, family: CHART_FONT_FAMILY },
    marker: {
      color: colorWithAlpha(color, 0.34),
      size: bins.map((bin) => 18 + Math.sqrt(bin.count) * 5),
      line: { color, width: 1.4 },
    },
  };
}

export function OppositionBuildUpTemperamentPitch({ profile }: { profile?: EventPitchProfile }) {
  const [themeColors, setThemeColors] = useState(readThemeColors);

  useEffect(() => {
    const update = () => setThemeColors(readThemeColors());
    const observer = new MutationObserver(update);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "data-theme"] });
    window.addEventListener("themechange", update);
    return () => {
      observer.disconnect();
      window.removeEventListener("themechange", update);
    };
  }, []);

  const buildUpRows = (profile?.build_up_actions ?? []).filter(validPoint);
  const directRows = (profile?.direct_actions ?? []).filter(validPoint);
  if (!profile?.available || (!buildUpRows.length && !directRows.length)) {
    return <p className="opposition-empty-note">Build-up event-location data is not available for this sample yet.</p>;
  }

  const buildUpBins = aggregateBins(buildUpRows);
  const directBins = aggregateBins(directRows);
  const total = buildUpRows.length + directRows.length;
  const directShare = total ? (directRows.length / total) * 100 : 0;
  const pitchShapes = horizontalPitchShapes(themeColors.muted, { zoneLines: true, transparentFill: true });

  return (
    <div className="opposition-plotly-shell opposition-event-pitch-shell opposition-build-up-pitch-shell">
      <div className="opposition-pitch-context-count">
        <strong>{formatMetric(directShare)}%</strong>
        <span>direct event share from {total} build-up/direct actions</span>
      </div>
      <Plot
        data={[
          buildUpBinTrace(buildUpBins, "Build-up actions", themeColors.accent, themeColors, -0.75),
          buildUpBinTrace(directBins, "Direct actions", "#facc15", themeColors, 0.75),
        ]}
        layout={{
          autosize: true,
          height: 470,
          margin: { l: 12, r: 12, t: 8, b: 12 },
          paper_bgcolor: "rgba(0,0,0,0)",
          plot_bgcolor: themeColors.surface,
          font: { color: themeColors.text, family: CHART_FONT_FAMILY },
          showlegend: false,
          xaxis: { range: [-1.5, 106.5], visible: false, fixedrange: true, constrain: "domain" },
          yaxis: { range: [-1.5, 69.5], visible: false, fixedrange: true, scaleanchor: "x", scaleratio: 1, constrain: "domain" },
          shapes: pitchShapes,
          annotations: [
            ...binArrowAnnotations(buildUpBins, themeColors.accent, 7),
            ...binArrowAnnotations(directBins, "#facc15", 7),
          ],
          hoverlabel: {
            bgcolor: themeColors.mode === "dark" ? "#0f2236" : "#ffffff",
            bordercolor: themeColors.mode === "dark" ? "rgba(255,255,255,0.18)" : "rgba(15,23,42,0.16)",
            font: { color: themeColors.text, family: CHART_FONT_FAMILY, size: 12 },
          },
        }}
        config={plotConfig}
        className="plotly-chart opposition-event-pitch-chart"
        style={{ width: "100%", height: "100%" }}
      />
      <div className="opposition-pitch-legend" aria-hidden="true">
        <span><i className="is-progressive" />Build-up actions</span>
        <span><i className="is-box" />Direct actions</span>
      </div>
    </div>
  );
}

export function OppositionInPossessionPitchPlotly({
  profile,
  mode,
}: {
  profile?: EventPitchProfile;
  mode: "progression" | "shots";
}) {
  const [themeColors, setThemeColors] = useState(readThemeColors);
  const [situation, setSituation] = useState<PitchSituation>("all");

  useEffect(() => {
    const update = () => setThemeColors(readThemeColors());
    const observer = new MutationObserver(update);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "data-theme"] });
    window.addEventListener("themechange", update);
    return () => {
      observer.disconnect();
      window.removeEventListener("themechange", update);
    };
  }, []);

  if (!profile?.available) {
    return <p className="opposition-empty-note">Event-location data is not available for this sample yet.</p>;
  }

  const rowMatchesContext = (row: EventPitchRow) => situation === "all" || row.situation === situation;
  const progressionRows = [...(profile.progressive_actions ?? []), ...(profile.box_entries ?? [])].filter(validPoint).filter(rowMatchesContext);
  const shotRows = (profile.shots ?? []).filter(validPoint).filter(rowMatchesContext);
  const isProgression = mode === "progression";
  const scopedRows = isProgression ? progressionRows : shotRows;
  const accent = isProgression ? themeColors.accent : "#38bdf8";
  const bins = aggregateBins(scopedRows);
  const zoneDensityShapes = binShapes(bins, accent, mode);

  const binTrace = {
    type: "scatter",
    mode: "markers+text",
    x: bins.map((bin) => bin.cx),
    y: bins.map((bin) => bin.cy),
    text: bins.map((bin) => binLabel(bin, mode)),
    hovertext: bins.map((bin) => binHover(bin, mode)),
    hovertemplate: "%{hovertext}<extra></extra>",
    texttemplate: "%{text}",
    textposition: "middle center",
    textfont: { color: themeColors.text, size: 11, family: CHART_FONT_FAMILY },
    marker: {
      color: "rgba(0,0,0,0)",
      size: 34,
      line: { color: "rgba(0,0,0,0)", width: 0 },
    },
    showlegend: false,
  };
  const pitchShapes = [
    ...zoneDensityShapes,
    ...horizontalPitchShapes(themeColors.muted, { zoneLines: true, transparentFill: true }),
  ];

  return (
    <div className="opposition-plotly-shell opposition-event-pitch-shell">
      <div className="opposition-pitch-context-controls">
        <div>
          {SITUATION_OPTIONS.map((option) => (
            <button key={option.value} type="button" className={situation === option.value ? "is-active" : ""} onClick={() => setSituation(option.value)}>
              {option.label}
            </button>
          ))}
        </div>
      </div>
      <div className="opposition-pitch-context-count">
        <strong>{bins.length}</strong>
        <span>{isProgression ? "progression / entry zones" : "shot zones"} from {scopedRows.length} actions</span>
      </div>
      <Plot
        data={[binTrace]}
        layout={{
          autosize: true,
          height: isProgression ? 760 : 430,
          margin: { l: 12, r: 12, t: 8, b: 12 },
          paper_bgcolor: "rgba(0,0,0,0)",
          plot_bgcolor: themeColors.surface,
          font: { color: themeColors.text, family: CHART_FONT_FAMILY },
          showlegend: false,
          xaxis: { range: isProgression ? [-1.5, 106.5] : [50, 106.5], visible: false, fixedrange: true, constrain: "domain" },
          yaxis: { range: [-1.5, 69.5], visible: false, fixedrange: true, scaleanchor: "x", scaleratio: 1, constrain: "domain" },
          shapes: pitchShapes,
          annotations: isProgression ? binArrowAnnotations(bins, themeColors.accent, 10) : [],
          hoverlabel: {
            bgcolor: themeColors.mode === "dark" ? "#0f2236" : "#ffffff",
            bordercolor: themeColors.mode === "dark" ? "rgba(255,255,255,0.18)" : "rgba(15,23,42,0.16)",
            font: { color: themeColors.text, family: CHART_FONT_FAMILY, size: 12 },
          },
        }}
        config={plotConfig}
        className="plotly-chart opposition-event-pitch-chart"
        style={{ width: "100%", height: "100%" }}
      />
      <div className="opposition-pitch-legend" aria-hidden="true">
        {isProgression ? (
          <>
            <span><i className="is-progressive" />Progressive actions</span>
            <span><i className="is-box" />Box entries</span>
            <span><i className="is-zone" />Zone volume</span>
          </>
        ) : (
          <>
            <span><i className="is-shot" />Shot zones</span>
            <span><i className="is-zone" />Zone xG</span>
          </>
        )}
      </div>
    </div>
  );
}

export function OppositionOverviewCharts({ radarMetrics, recentMatches }: Props) {
  return (
    <>
      <OppositionStyleRadarPlotly radarMetrics={radarMetrics} />
      <OppositionRecentFormPlotly recentMatches={recentMatches} />
    </>
  );
}
