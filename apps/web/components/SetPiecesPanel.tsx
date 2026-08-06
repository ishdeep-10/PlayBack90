"use client";

import { DownloadPngButton, type ChartPanel, type SideTable, type SideTableRow } from "./DownloadPngButton";

import { useEffect, useMemo, useState } from "react";

import { getAnalysisView } from "../lib/api";
import { horizontalPitchShapes } from "../lib/pitch";
import { Plot } from "../lib/plotly";
import { CHART_FONT_FAMILY, colorWithAlpha, readThemeColors } from "../lib/theme";
import { PlayerAvatar, getCachedPlayerImage } from "./PlayerAvatar";

type Delivery = {
  minute: number;
  player: string;
  x: number;
  y: number;
  end_x: number;
  end_y: number;
  successful: boolean;
  led_to_shot: boolean;
  led_to_goal?: boolean;
  receiver?: string;
  swing?: string;
};

type CornerWon = {
  minute: number;
  player: string;
  x: number;
  y: number;
};

type TypeStats = {
  label: string;
  count: number;
  completed: number;
  completion_pct: number;
  into_box: number;
  retained: number;
  retention_pct: number;
  shots_generated: number;
  goals_generated: number;
  xg_generated: number;
  deliveries: Delivery[];
  won?: CornerWon[];
};

type Props = {
  matchId: string;
  source: string;
  league?: string;
  season?: string;
  jobId?: string;
  team: string;
  teamColor: string;
};

const TYPE_ORDER = ["corner", "free_kick", "throw_in", "goal_kick"] as const;

type DeliveryFilter = { value: string; label: string; test: (delivery: Delivery) => boolean };

const inBox = (delivery: Delivery) => delivery.end_x >= 88.5 && delivery.end_y >= 13.84 && delivery.end_y <= 54.16;

// Long throw = flight distance ≥ 20m (≈ top ~30% of PL throw-ins).
const throwDistance = (delivery: Delivery) => Math.hypot(delivery.end_x - delivery.x, delivery.end_y - delivery.y);

/** Low-frequency dead balls need territorial context more than volume stats. */
const DELIVERY_FILTERS: Record<string, DeliveryFilter[]> = {
  free_kick: [
    { value: "all", label: "All", test: () => true },
    { value: "own-half", label: "Own-half restarts", test: (delivery) => delivery.x < 52.5 },
    { value: "att-half", label: "Attacking half", test: (delivery) => delivery.x >= 52.5 },
    { value: "into-box", label: "Into the box", test: inBox },
  ],
  throw_in: [
    { value: "all", label: "All", test: () => true },
    { value: "def", label: "Defensive third", test: (delivery) => delivery.x < 35 },
    { value: "mid", label: "Middle third", test: (delivery) => delivery.x >= 35 && delivery.x < 70 },
    { value: "final", label: "Final third", test: (delivery) => delivery.x >= 70 },
    { value: "short-throw", label: "Short throws", test: (delivery) => throwDistance(delivery) < 20 },
    { value: "long-throw", label: "Long throws", test: (delivery) => throwDistance(delivery) >= 20 },
  ],
  goal_kick: [
    { value: "all", label: "All", test: () => true },
    { value: "short", label: "Short (own half)", test: (delivery) => delivery.end_x < 52.5 },
    { value: "long", label: "Long (past halfway)", test: (delivery) => delivery.end_x >= 52.5 },
  ],
};

function penaltyArcPath() {
  const cx = 94;
  const cy = 34;
  const radius = 9.15;
  const start = Math.PI - Math.acos((cx - 88.5) / radius);
  const end = Math.PI + Math.acos((cx - 88.5) / radius);
  const points: Array<[number, number]> = [];
  for (let i = 0; i <= 28; i += 1) {
    const angle = start + ((end - start) * i) / 28;
    points.push([cx + radius * Math.cos(angle), cy + radius * Math.sin(angle)]);
  }
  return points.map(([fieldX, fieldY], index) => `${index === 0 ? "M" : "L"} ${fieldY.toFixed(2)} ${fieldX.toFixed(2)}`).join(" ");
}

// Vertical half-pitch coordinates: plotX = 68 − pitchY, plotY = pitchX.
const toPlotX = (pitchY: number) => 68 - pitchY;
const toPlotY = (pitchX: number) => pitchX;

function verticalHalfPitchShapes(themeColors: { muted: string; text: string }) {
  return [
    { type: "rect", x0: 0, y0: 52.5, x1: 68, y1: 105, line: { color: themeColors.muted, width: 2 } },
    { type: "line", x0: 0, y0: 52.5, x1: 68, y1: 52.5, line: { color: themeColors.muted, width: 1.5 } },
    { type: "circle", x0: 24.85, y0: 43.35, x1: 43.15, y1: 61.65, line: { color: themeColors.muted, width: 1 } },
    { type: "rect", x0: 13.84, y0: 88.5, x1: 54.16, y1: 105, line: { color: themeColors.muted, width: 2 } },
    { type: "rect", x0: 24.84, y0: 99.5, x1: 43.16, y1: 105, line: { color: themeColors.muted, width: 2 } },
    { type: "line", x0: 30.34, y0: 105, x1: 30.34, y1: 105.8, line: { color: themeColors.text, width: 3 } },
    { type: "line", x0: 37.66, y0: 105, x1: 37.66, y1: 105.8, line: { color: themeColors.text, width: 3 } },
    { type: "line", x0: 30.34, y0: 105.8, x1: 37.66, y1: 105.8, line: { color: themeColors.text, width: 3 } },
    { type: "path", path: penaltyArcPath(), line: { color: themeColors.muted, width: 1.5 } },
  ];
}

// Opta-style corner end-location zones, normalized so the corner is always
// taken from the high-y side (front post = plot left).
type CornerZone = { x0: number; x1: number; y0: number; y1: number };
const CORNER_END_ZONES: CornerZone[] = [
  { y0: 54.16, y1: 68, x0: 88.5, x1: 105 },      // wide, front-post side
  { y0: 43.16, y1: 54.16, x0: 88.5, x1: 105 },   // front-post channel
  { y0: 37.05, y1: 43.16, x0: 99.5, x1: 105 },   // six-yard front · goalmouth
  { y0: 30.95, y1: 37.05, x0: 99.5, x1: 105 },   // six-yard centre · goalmouth
  { y0: 24.84, y1: 30.95, x0: 99.5, x1: 105 },   // six-yard back · goalmouth
  { y0: 37.05, y1: 43.16, x0: 94, x1: 99.5 },
  { y0: 30.95, y1: 37.05, x0: 94, x1: 99.5 },
  { y0: 24.84, y1: 30.95, x0: 94, x1: 99.5 },
  { y0: 24.84, y1: 43.16, x0: 88.5, x1: 94 },    // penalty-spot band
  { y0: 13.84, y1: 24.84, x0: 88.5, x1: 105 },   // back-post channel
  { y0: 0, y1: 13.84, x0: 88.5, x1: 105 },       // wide, back-post side
  { y0: 43.16, y1: 68, x0: 70, x1: 88.5 },       // edge of box, front side
  { y0: 24.84, y1: 43.16, x0: 70, x1: 88.5 },    // edge of box, centre
  { y0: 0, y1: 24.84, x0: 70, x1: 88.5 },        // edge of box, back side
];

// Returns a plain hex/team color — apply alpha exactly once at the call site
// (theme.colorWithAlpha only parses hex; re-wrapping an rgba() string falls
// back to green).
function deliveryColor(delivery: Delivery, teamColor: string) {
  if (delivery.led_to_goal) return "#22c55e";
  if (delivery.led_to_shot) return "#facc15";
  return teamColor;
}

function deliveryEmphasized(delivery: Delivery) {
  return delivery.successful || delivery.led_to_shot || Boolean(delivery.led_to_goal);
}

/** Quadratic bezier for the delivery flight: inswingers bow toward the goal
 *  line, outswingers away. Returns null when the swing is unknown (straight). */
function swingCurvePoints(delivery: Delivery): Array<[number, number]> | null {
  const direction = delivery.swing === "inswinger" ? 1 : delivery.swing === "outswinger" ? -1 : 0;
  if (!direction) return null;
  const { x: x0, y: y0, end_x: x1, end_y: y1 } = delivery;
  const dx = x1 - x0;
  const dy = y1 - y0;
  const length = Math.hypot(dx, dy) || 1;
  let normalX = -dy / length;
  let normalY = dx / length;
  if (normalX < 0) {
    normalX = -normalX;
    normalY = -normalY; // normal now points toward the goal line (larger x)
  }
  const bend = 0.14 * length * direction;
  // Corners start on the byline, so an unclamped goalward bow would leave the
  // pitch — keep the control point (and the sampled arc) inside the field.
  const controlX = Math.min(104.4, Math.max(53, (x0 + x1) / 2 + normalX * bend));
  const controlY = Math.min(67.6, Math.max(0.4, (y0 + y1) / 2 + normalY * bend));
  const points: Array<[number, number]> = [];
  for (let i = 0; i <= 20; i += 1) {
    const t = i / 20;
    points.push([
      Math.min(104.8, (1 - t) ** 2 * x0 + 2 * (1 - t) * t * controlX + t * t * x1),
      Math.min(67.75, Math.max(0.25, (1 - t) ** 2 * y0 + 2 * (1 - t) * t * controlY + t * t * y1)),
    ]);
  }
  return points;
}

function deliveryHover(delivery: Delivery) {
  const outcomeText = delivery.led_to_goal ? "Led to a goal" : delivery.led_to_shot ? "Led to a shot" : delivery.successful ? "Completed" : "Lost";
  const target = delivery.receiver ? `<br>Target: ${delivery.receiver}` : "";
  const swing = delivery.swing && delivery.swing !== "unknown" ? ` · ${delivery.swing}` : "";
  return `${delivery.minute}' · ${delivery.player}${swing}${target}<br>${outcomeText}`;
}

function shortName(name: string) {
  const parts = name.trim().split(/\s+/);
  return parts.length > 1 ? `${parts[0][0]}. ${parts[parts.length - 1]}` : name;
}

function CornerPitchPlotly({ stats, team, teamColor }: { stats: TypeStats; team: string; teamColor: string }) {
  const [themeColors, setThemeColors] = useState(readThemeColors);

  useEffect(() => {
    const updateColors = () => setThemeColors(readThemeColors());
    updateColors();
    const observer = new MutationObserver(updateColors);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "data-theme"] });
    return () => observer.disconnect();
  }, []);

  const deliveries = stats.deliveries;
  const wonVisible = (stats.won ?? []).filter((won) => won.x >= 52.5);

  const heatTrace = {
    x: deliveries.map((delivery) => toPlotX(delivery.end_y)),
    y: deliveries.map((delivery) => toPlotY(delivery.end_x)),
    type: "histogram2dcontour",
    ncontours: 12,
    colorscale: [
      [0, "rgba(0,0,0,0)"],
      [0.4, colorWithAlpha(teamColor, themeColors.mode === "dark" ? 0.18 : 0.13)],
      [0.75, colorWithAlpha(teamColor, themeColors.mode === "dark" ? 0.38 : 0.3)],
      [1, colorWithAlpha(teamColor, themeColors.mode === "dark" ? 0.62 : 0.48)],
    ],
    contours: { coloring: "heatmap", showlines: false },
    line: { width: 0, color: "rgba(0,0,0,0)" },
    showscale: false,
    opacity: 0.8,
    hoverinfo: "skip",
    showlegend: false,
  };

  const endMarkerTrace = {
    x: deliveries.map((delivery) => toPlotX(delivery.end_y)),
    y: deliveries.map((delivery) => toPlotY(delivery.end_x)),
    mode: "markers",
    type: "scatter",
    marker: {
      size: deliveries.map((delivery) => (delivery.led_to_shot || delivery.led_to_goal ? 12 : 9)),
      color: deliveries.map((delivery) => colorWithAlpha(deliveryColor(delivery, teamColor), deliveryEmphasized(delivery) ? 0.95 : 0.45)),
      line: { color: themeColors.mode === "dark" ? "#0f172a" : "#ffffff", width: 1.4 },
    },
    hovertext: deliveries.map(deliveryHover),
    hovertemplate: "%{hovertext}<extra></extra>",
    showlegend: false,
  };

  // Curved flight paths for inferred in/outswingers (straight arrows otherwise).
  const curveTraces = deliveries.flatMap((delivery) => {
    const points = swingCurvePoints(delivery);
    if (!points) return [];
    const hover = deliveryHover(delivery);
    return [{
      x: points.map(([, pitchY]) => toPlotX(pitchY)),
      y: points.map(([pitchX]) => toPlotY(pitchX)),
      mode: "lines",
      type: "scatter",
      line: {
        color: colorWithAlpha(deliveryColor(delivery, teamColor), deliveryEmphasized(delivery) ? 0.9 : 0.5),
        width: delivery.led_to_shot || delivery.led_to_goal ? 2.6 : 2,
        shape: "spline",
      },
      customdata: points.map(() => hover),
      hovertemplate: "%{customdata}<extra></extra>",
      showlegend: false,
    }];
  });

  const wonTrace = wonVisible.length
    ? {
        x: wonVisible.map((won) => toPlotX(won.y)),
        y: wonVisible.map((won) => toPlotY(won.x)),
        mode: "markers",
        type: "scatter",
        marker: {
          symbol: "diamond",
          size: 10,
          color: "rgba(56,189,248,0.9)",
          line: { color: themeColors.mode === "dark" ? "#0f172a" : "#ffffff", width: 1.2 },
        },
        hovertext: wonVisible.map((won) => `Corner won by ${won.player} · ${won.minute}'`),
        hovertemplate: "%{hovertext}<extra></extra>",
        showlegend: false,
      }
    : null;

  const arrowAnnotations = deliveries.map((delivery) => {
    const points = swingCurvePoints(delivery);
    // Curved deliveries only need the arrowhead (short final segment); straight
    // ones keep the full annotation arrow.
    const tail = points ? points[Math.max(0, points.length - 3)] : [delivery.x, delivery.y];
    return {
      x: toPlotX(delivery.end_y),
      y: toPlotY(delivery.end_x),
      ax: toPlotX(tail[1]),
      ay: toPlotY(tail[0]),
      xref: "x",
      yref: "y",
      axref: "x",
      ayref: "y",
      text: "",
      showarrow: true,
      arrowhead: 3,
      arrowsize: 1,
      arrowwidth: delivery.led_to_shot || delivery.led_to_goal ? 2.4 : 1.8,
      arrowcolor: colorWithAlpha(deliveryColor(delivery, teamColor), deliveryEmphasized(delivery) ? 0.9 : 0.5),
    };
  });

  const pitchShapes = verticalHalfPitchShapes(themeColors);

  return (
    <Plot
      data={[heatTrace, ...curveTraces, endMarkerTrace, ...(wonTrace ? [wonTrace] : [])]}
      layout={{
        autosize: true,
        height: 540,
        margin: { l: 18, r: 18, t: 8, b: 14 },
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: themeColors.surface,
        font: { color: themeColors.text, family: CHART_FONT_FAMILY },
        showlegend: false,
        xaxis: { range: [0, 68], visible: false, fixedrange: true, constrain: "domain" },
        yaxis: { range: [50, 105.8], visible: false, fixedrange: true, scaleanchor: "x", scaleratio: 1, constrain: "domain" },
        shapes: pitchShapes,
        annotations: arrowAnnotations,
        hoverlabel: {
          bgcolor: themeColors.mode === "dark" ? "#0f2236" : "#ffffff",
          bordercolor: themeColors.mode === "dark" ? "rgba(255,255,255,0.18)" : "rgba(15,23,42,0.16)",
          font: { color: themeColors.text, family: CHART_FONT_FAMILY, size: 12 },
        },
      }}
      config={{ responsive: true, displayModeBar: false }}
      className="plotly-chart setpiece-corner-chart"
      aria-label={`${team} corner delivery map`}
    />
  );
}

function CornerEndZonesPlotly({ stats, team, teamColor }: { stats: TypeStats; team: string; teamColor: string }) {
  const [themeColors, setThemeColors] = useState(readThemeColors);

  useEffect(() => {
    const updateColors = () => setThemeColors(readThemeColors());
    updateColors();
    const observer = new MutationObserver(updateColors);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "data-theme"] });
    return () => observer.disconnect();
  }, []);

  const deliveries = stats.deliveries;
  const total = Math.max(1, deliveries.length);
  const counts = CORNER_END_ZONES.map((zone) =>
    deliveries.filter((delivery) => {
      const endY = delivery.y < 34 ? 68 - delivery.end_y : delivery.end_y; // mirror right-side corners
      return delivery.end_x >= zone.x0 && delivery.end_x < zone.x1 && endY >= zone.y0 && endY < zone.y1;
    }).length,
  );
  const maxShare = Math.max(0.01, ...counts.map((count) => count / total));

  const zoneShapes = CORNER_END_ZONES.map((zone, index) => ({
    type: "rect",
    x0: toPlotX(zone.y1),
    x1: toPlotX(zone.y0),
    y0: zone.x0,
    y1: Math.min(zone.x1, 105),
    line: { color: "rgba(148,163,184,0.5)", width: 1, dash: "dot" },
    fillcolor: colorWithAlpha(teamColor, counts[index] ? 0.05 + ((counts[index] / total) / maxShare) * 0.5 : 0.02),
    layer: "below",
  }));

  const labelTrace = {
    x: CORNER_END_ZONES.map((zone) => toPlotX((zone.y0 + zone.y1) / 2)),
    y: CORNER_END_ZONES.map((zone) => (zone.x0 + Math.min(zone.x1, 105)) / 2),
    mode: "text",
    type: "scatter",
    text: counts.map((count) => `${Math.round((count / total) * 100)}%`),
    textfont: { color: themeColors.text, size: 13, family: CHART_FONT_FAMILY },
    hovertext: CORNER_END_ZONES.map((_, index) => `${counts[index]} of ${total} corners end here`),
    hovertemplate: "%{hovertext}<extra></extra>",
    showlegend: false,
  };

  return (
    <Plot
      data={[labelTrace]}
      layout={{
        autosize: true,
        height: 560,
        margin: { l: 18, r: 18, t: 8, b: 14 },
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: themeColors.surface,
        font: { color: themeColors.text, family: CHART_FONT_FAMILY },
        showlegend: false,
        xaxis: { range: [0, 68], visible: false, fixedrange: true, constrain: "domain" },
        yaxis: { range: [50, 109.5], visible: false, fixedrange: true, scaleanchor: "x", scaleratio: 1, constrain: "domain" },
        shapes: [...zoneShapes, ...verticalHalfPitchShapes(themeColors)],
        annotations: [
          { x: toPlotX(48.66), y: 107.6, xref: "x", yref: "y", text: "FRONT POST", showarrow: false, font: { color: themeColors.muted, size: 12, family: CHART_FONT_FAMILY } },
          { x: toPlotX(19.34), y: 107.6, xref: "x", yref: "y", text: "BACK POST", showarrow: false, font: { color: themeColors.muted, size: 12, family: CHART_FONT_FAMILY } },
        ],
        hoverlabel: {
          bgcolor: themeColors.mode === "dark" ? "#0f2236" : "#ffffff",
          bordercolor: themeColors.mode === "dark" ? "rgba(255,255,255,0.18)" : "rgba(15,23,42,0.16)",
          font: { color: themeColors.text, family: CHART_FONT_FAMILY, size: 12 },
        },
      }}
      config={{ responsive: true, displayModeBar: false }}
      className="plotly-chart setpiece-corner-chart"
      aria-label={`${team} corner end locations`}
    />
  );
}

function DeliveryPitchPlotly({ deliveries, team, teamColor, label }: { deliveries: Delivery[]; team: string; teamColor: string; label: string }) {
  const [themeColors, setThemeColors] = useState(readThemeColors);

  useEffect(() => {
    const updateColors = () => setThemeColors(readThemeColors());
    updateColors();
    const observer = new MutationObserver(updateColors);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "data-theme"] });
    return () => observer.disconnect();
  }, []);

  const heatTrace = {
    x: deliveries.map((delivery) => delivery.end_x),
    y: deliveries.map((delivery) => delivery.end_y),
    type: "histogram2dcontour",
    ncontours: 12,
    colorscale: [
      [0, "rgba(0,0,0,0)"],
      [0.4, colorWithAlpha(teamColor, themeColors.mode === "dark" ? 0.14 : 0.1)],
      [0.75, colorWithAlpha(teamColor, themeColors.mode === "dark" ? 0.3 : 0.24)],
      [1, colorWithAlpha(teamColor, themeColors.mode === "dark" ? 0.52 : 0.4)],
    ],
    contours: { coloring: "heatmap", showlines: false },
    line: { width: 0, color: "rgba(0,0,0,0)" },
    showscale: false,
    opacity: 0.75,
    hoverinfo: "skip",
    showlegend: false,
  };

  const endMarkerTrace = {
    x: deliveries.map((delivery) => delivery.end_x),
    y: deliveries.map((delivery) => delivery.end_y),
    mode: "markers",
    type: "scatter",
    marker: {
      size: deliveries.map((delivery) => (delivery.led_to_shot || delivery.led_to_goal ? 11 : 8)),
      color: deliveries.map((delivery) => colorWithAlpha(deliveryColor(delivery, teamColor), deliveryEmphasized(delivery) ? 0.95 : 0.45)),
      line: { color: themeColors.mode === "dark" ? "#0f172a" : "#ffffff", width: 1.3 },
    },
    hovertext: deliveries.map(deliveryHover),
    hovertemplate: "%{hovertext}<extra></extra>",
    showlegend: false,
  };

  const arrowAnnotations = deliveries.map((delivery) => ({
    x: delivery.end_x,
    y: delivery.end_y,
    ax: delivery.x,
    ay: delivery.y,
    xref: "x",
    yref: "y",
    axref: "x",
    ayref: "y",
    text: "",
    showarrow: true,
    arrowhead: 3,
    arrowsize: 1,
    arrowwidth: delivery.led_to_shot || delivery.led_to_goal ? 2.4 : 1.6,
    arrowcolor: colorWithAlpha(deliveryColor(delivery, teamColor), deliveryEmphasized(delivery) ? 0.9 : 0.45),
  }));

  return (
    <Plot
      data={[heatTrace, endMarkerTrace]}
      layout={{
        autosize: true,
        height: 470,
        margin: { l: 14, r: 14, t: 8, b: 12 },
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: themeColors.surface,
        font: { color: themeColors.text, family: CHART_FONT_FAMILY },
        showlegend: false,
        xaxis: { range: [-1.5, 106.5], visible: false, fixedrange: true, constrain: "domain" },
        yaxis: { range: [-1.5, 69.5], visible: false, fixedrange: true, scaleanchor: "x", scaleratio: 1, constrain: "domain" },
        shapes: horizontalPitchShapes(themeColors.muted),
        annotations: arrowAnnotations,
        hoverlabel: {
          bgcolor: themeColors.mode === "dark" ? "#0f2236" : "#ffffff",
          bordercolor: themeColors.mode === "dark" ? "rgba(255,255,255,0.18)" : "rgba(15,23,42,0.16)",
          font: { color: themeColors.text, family: CHART_FONT_FAMILY, size: 12 },
        },
      }}
      config={{ responsive: true, displayModeBar: false }}
      className="plotly-chart setpiece-corner-chart"
      aria-label={`${team} ${label} delivery map`}
    />
  );
}

export function SetPiecesPanel({ matchId, source, league, season, jobId, team, teamColor }: Props) {
  const [types, setTypes] = useState<Record<string, TypeStats>>({});
  const [activeType, setActiveType] = useState<string>("corner");
  const [cornerView, setCornerView] = useState<"arrows" | "zones">("arrows");
  const [deliveryFilter, setDeliveryFilter] = useState("all");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    const filters: Record<string, string | undefined> = { team };
    if (source !== "r2") filters.job_id = jobId;
    const body =
      source !== "r2"
        ? { match_id: matchId, source, filters }
        : { match_id: matchId, source: "r2", league, season, filters };
    getAnalysisView("set-pieces", body)
      .then((view) => {
        if (!cancelled) setTypes(((view.payload ?? {}).types as Record<string, TypeStats> | undefined) ?? {});
      })
      .catch(() => {
        if (!cancelled) setTypes({});
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [matchId, source, league, season, jobId, team]);

  const active = types[activeType];
  const isCorner = activeType === "corner";
  const typeFilters = DELIVERY_FILTERS[activeType];
  const activeFilter = typeFilters?.find((filter) => filter.value === deliveryFilter) ?? typeFilters?.[0];
  const filteredDeliveries = useMemo(
    () => (activeFilter ? (active?.deliveries ?? []).filter(activeFilter.test) : active?.deliveries ?? []),
    [active, activeFilter],
  );

  const cornerBreakdown = useMemo(() => {
    const deliveries = isCorner ? active?.deliveries ?? [] : filteredDeliveries;
    const takers = new Map<string, { taken: number; completed: number; intoBox: number; shots: number; goals: number }>();
    const targets = new Map<string, { targeted: number; shots: number }>();
    deliveries.forEach((delivery) => {
      const taker = takers.get(delivery.player) ?? { taken: 0, completed: 0, intoBox: 0, shots: 0, goals: 0 };
      taker.taken += 1;
      if (delivery.successful) taker.completed += 1;
      if (delivery.end_x >= 88.5 && delivery.end_y >= 13.84 && delivery.end_y <= 54.16) taker.intoBox += 1;
      if (delivery.led_to_shot) taker.shots += 1;
      if (delivery.led_to_goal) taker.goals += 1;
      takers.set(delivery.player, taker);
      const receiver = String(delivery.receiver ?? "").trim();
      if (receiver) {
        const target = targets.get(receiver) ?? { targeted: 0, shots: 0 };
        target.targeted += 1;
        if (delivery.led_to_shot) target.shots += 1;
        targets.set(receiver, target);
      }
    });
    const wonBy = new Map<string, number>();
    (active?.won ?? []).forEach((won) => {
      if (won.player) wonBy.set(won.player, (wonBy.get(won.player) ?? 0) + 1);
    });
    return {
      takers: [...takers.entries()].sort((a, b) => b[1].taken - a[1].taken),
      targets: [...targets.entries()].sort((a, b) => b[1].targeted - a[1].targeted),
      wonBy: [...wonBy.entries()].sort((a, b) => b[1] - a[1]),
    };
  }, [active, filteredDeliveries, isCorner]);

  if (!isLoading && !Object.keys(types).length) return null;

  const buildSideTable = (): SideTable | null => {
    if (!active) return null;
    const rows: SideTableRow[] = [];
    if (cornerBreakdown.takers.length) {
      rows.push({ header: isCorner ? "Corner takers" : "Takers" });
      cornerBreakdown.takers.slice(0, 4).forEach(([player, stats]) => {
        rows.push({
          image: getCachedPlayerImage(player, team),
          label: player,
          value: `${stats.taken}×`,
          sub: `${stats.completed} completed · ${stats.intoBox} into box · ${stats.shots} led to shots`,
        });
      });
    }
    if (cornerBreakdown.targets.length) {
      rows.push({ header: "Targets" });
      cornerBreakdown.targets.slice(0, 4).forEach(([player, stats]) => {
        rows.push({
          image: getCachedPlayerImage(player, team),
          label: player,
          value: `${stats.targeted}×`,
          sub: stats.shots ? `${stats.shots} led to shots` : undefined,
        });
      });
    }
    if (cornerBreakdown.wonBy.length) {
      rows.push({ header: "Corners won by" });
      cornerBreakdown.wonBy.slice(0, 4).forEach(([player, count]) => {
        rows.push({
          image: getCachedPlayerImage(player, team),
          label: player,
          value: `${count}×`,
        });
      });
    }
    return rows.length ? { title: `${team} · ${active.label}${!isCorner && activeFilter && activeFilter.value !== "all" ? ` · ${activeFilter.label}` : ""}`, rows } : null;
  };

  // The in-app legend is HTML, invisible to the canvas export — mirror it as a
  // structured chart panel legend.
  const buildChartPanels = (): ChartPanel[] => {
    if (isCorner && cornerView === "zones") {
      return [{ legend: [{ label: "Shade = share of corner endings", color: colorWithAlpha(teamColor, 0.7), shape: "square" }] }];
    }
    const legend: ChartPanel["legend"] = [
      { label: "Led to a goal", color: "#22c55e", shape: "line" },
      { label: "Led to a shot", color: "#facc15", shape: "line" },
      { label: "Completed", color: teamColor, shape: "line" },
      { label: "Lost", color: colorWithAlpha(teamColor, 0.4), shape: "line" },
    ];
    if (isCorner) legend.push({ label: "Corner won here", color: "rgba(56,189,248,0.9)", shape: "square" });
    return [{ legend }];
  };

  return (
    <section className={`card stack${isLoading ? " is-loading-soft" : ""}`}>
      <div className="chart-card-head">
        <div>
          <span className="eyebrow">Set Pieces</span>
          <h2 style={{ margin: "6px 0 0" }}>{team} — dead-ball situations</h2>
        </div>
        <DownloadPngButton
          filename={`${team}-set-pieces`}
          title={() => `Set Pieces — ${active?.label ?? "Corners"}`}
          filters={[team]}
          sideTable={buildSideTable}
          chartPanels={buildChartPanels}
          captureAspect={isCorner ? undefined : 71 / 108}
        />
      </div>
      <div className="setpiece-type-row" role="group" aria-label="Set piece type">
        {TYPE_ORDER.map((key) => {
          const stats = types[key];
          if (!stats) return null;
          return (
            <button
              key={key}
              type="button"
              className={activeType === key ? "phase-chip is-active" : "phase-chip"}
              onClick={() => {
                setActiveType(key);
                setDeliveryFilter("all");
              }}
            >
              <strong>
                {stats.label} ({stats.count})
              </strong>
              <span>
                {stats.shots_generated} shots · {stats.xg_generated.toFixed(2)} xG · {stats.retention_pct}% retained
              </span>
            </button>
          );
        })}
      </div>
      {active ? (
        <>
          <div className={`setpiece-grid${isCorner ? " setpiece-grid-corner" : ""}`}>
            {isCorner ? (
              <div className="plotly-chart-shell">
                <div className="channel-mode-toggle setpiece-corner-toggle" role="group" aria-label="Corner view">
                  {([
                    ["arrows", "Deliveries"],
                    ["zones", "End locations"],
                  ] as Array<["arrows" | "zones", string]>).map(([value, label]) => (
                    <button
                      key={value}
                      type="button"
                      className={cornerView === value ? "button" : "ghost-button"}
                      onClick={() => setCornerView(value)}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                {cornerView === "arrows" ? (
                  <CornerPitchPlotly stats={active} team={team} teamColor={teamColor} />
                ) : (
                  <CornerEndZonesPlotly stats={active} team={team} teamColor={teamColor} />
                )}
                <p className="muted-copy setpiece-corner-note">
                  {cornerView === "arrows"
                    ? "Curved paths show the inferred swing (kicking foot × corner side): bowing toward goal = inswinger, away = outswinger, straight = unknown foot."
                    : "Corners are mirrored so left and right are both shown from the same side — front post on the left."}
                </p>
              </div>
            ) : (
              <div className="plotly-chart-shell">
                {typeFilters && (
                  <div className="channel-mode-toggle setpiece-corner-toggle" role="group" aria-label={`${active.label} context filter`}>
                    {typeFilters.map((filter) => {
                      const count = (active.deliveries ?? []).filter(filter.test).length;
                      return (
                        <button
                          key={filter.value}
                          type="button"
                          className={deliveryFilter === filter.value ? "button" : "ghost-button"}
                          onClick={() => setDeliveryFilter(filter.value)}
                        >
                          {filter.label} ({count})
                        </button>
                      );
                    })}
                  </div>
                )}
                <DeliveryPitchPlotly deliveries={filteredDeliveries} team={team} teamColor={teamColor} label={active.label} />
                <p className="muted-copy setpiece-corner-note">
                  Attacking left → right. Arrow color: green led to a goal, gold led to a shot, team color completed, faded lost.
                </p>
              </div>
            )}
            <div className="setpiece-stat-grid">
              <div className="setpiece-stat"><b>{active.count}</b><span>Taken</span></div>
              <div className="setpiece-stat"><b>{active.completion_pct}%</b><span>Completed</span></div>
              <div className="setpiece-stat"><b>{active.into_box}</b><span>Into the box</span></div>
              <div className="setpiece-stat"><b>{active.retention_pct}%</b><span>Retained</span></div>
              <div className="setpiece-stat"><b>{active.shots_generated}</b><span>Shots generated</span></div>
              <div className="setpiece-stat"><b>{active.xg_generated.toFixed(2)}</b><span>xG generated</span></div>
              <div className="setpiece-stat"><b>{active.goals_generated}</b><span>Goals</span></div>
              {isCorner && <div className="setpiece-stat"><b>{active.won?.length ?? 0}</b><span>Corners won</span></div>}
              <div className="setpiece-legend">
                {isCorner ? (
                  <>
                    <span><i style={{ background: "#22c55e" }} /> led to a goal</span>
                    <span><i style={{ background: "#facc15" }} /> led to a shot</span>
                    <span><i style={{ background: teamColor }} /> completed</span>
                    <span><i style={{ background: colorWithAlpha(teamColor, 0.35) }} /> lost</span>
                    <span><i style={{ background: "rgba(56,189,248,0.9)" }} /> corner won here</span>
                  </>
                ) : (
                  <>
                    <span><i style={{ background: "#facc15" }} /> led to a shot</span>
                    <span><i style={{ background: teamColor }} /> completed</span>
                    <span><i style={{ background: colorWithAlpha(teamColor, 0.35) }} /> lost</span>
                  </>
                )}
              </div>
              {isCorner && cornerBreakdown.wonBy.length > 0 && (
                <div className="setpiece-won-card">
                  <span className="eyebrow">Corners won by</span>
                  {cornerBreakdown.wonBy.map(([player, count]) => (
                    <div key={player} className="setpiece-won-row">
                      <PlayerAvatar name={player} team={team} size={22} />
                      <span>{shortName(player)}</span>
                      <b>{count}×</b>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
          {(cornerBreakdown.takers.length > 0 || cornerBreakdown.targets.length > 0) && (
            <div className="setpiece-tables">
              <div className="setpiece-table-card">
                <span className="eyebrow">{isCorner ? "Corner takers" : `Takers — ${active.label}`}</span>
                <table className="table setpiece-table">
                  <thead>
                    <tr><th>Player</th><th>Taken</th><th>Cmp</th><th>Into box</th><th>Shots</th><th>Goals</th></tr>
                  </thead>
                  <tbody>
                    {cornerBreakdown.takers.map(([player, stats]) => (
                      <tr key={player}>
                        <td>
                          <span className="player-cell">
                            <PlayerAvatar name={player} team={team} size={24} />
                            <span>{player}</span>
                          </span>
                        </td>
                        <td>{stats.taken}</td>
                        <td>{stats.completed}</td>
                        <td>{stats.intoBox}</td>
                        <td>{stats.shots}</td>
                        <td>{stats.goals}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="setpiece-table-card">
                <span className="eyebrow">Delivery targets (first touch)</span>
                <table className="table setpiece-table">
                  <thead>
                    <tr><th>Player</th><th>Targeted</th><th>Led to shot</th></tr>
                  </thead>
                  <tbody>
                    {cornerBreakdown.targets.map(([player, stats]) => (
                      <tr key={player}>
                        <td>
                          <span className="player-cell">
                            <PlayerAvatar name={player} team={team} size={24} />
                            <span>{player}</span>
                          </span>
                        </td>
                        <td>{stats.targeted}</td>
                        <td>{stats.shots}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      ) : null}
    </section>
  );
}
