"use client";

import { memo, useEffect, useState } from "react";

import { PUBLIC_API_BASE, getAuthHeaders } from "../lib/api";
import { CARD_ICON_RED, CARD_ICON_SECOND_YELLOW, CARD_ICON_YELLOW, SUB_ICON, circularImageDataUrl } from "../lib/images";
import { Plot } from "../lib/plotly";
import { CHART_FONT_FAMILY, readThemeColors } from "../lib/theme";

import { DownloadPngButton } from "./DownloadPngButton";
import { metricByKey, type TeamBaseline as TeamBaselineData } from "./season/baselineTypes";



type DataRow = Record<string, string | number | null | undefined>;
type TeamSummary = { team: string; xg: number; xgot?: number };
type MomentumMetric = "xt" | "epv" | "combined";

type Props = {
  teams: [string, string];
  teamColors: Record<string, string>;
  fullTime: number;
  xgFlowRows: DataRow[];
  xgMarkers: DataRow[];
  passRows: DataRow[];
  flankRows: DataRow[];
  ppdaRows: DataRow[];
  momentumRows: DataRow[];
  epvMomentumRows?: DataRow[];
  eventMarkers: DataRow[];
  teamSummaries: Array<TeamSummary & { epv_added?: number; xt?: number }>;
  thirdsRows?: DataRow[];
  seasonBaselines?: Record<string, TeamBaselineData>;
};

type ThirdKey = "all" | "defensive" | "middle" | "final";

const THIRD_OPTIONS: Array<{ value: ThirdKey; label: string }> = [
  { value: "all", label: "All thirds" },
  { value: "defensive", label: "Defensive 3rd" },
  { value: "middle", label: "Middle 3rd" },
  { value: "final", label: "Final 3rd" },
];

function ThirdSelect({ value, onChange, id }: { value: ThirdKey; onChange: (value: ThirdKey) => void; id: string }) {
  return (
    <select
      id={id}
      aria-label="Filter by pitch third"
      className="third-select"
      value={value}
      onChange={(event) => onChange(event.target.value as ThirdKey)}
    >
      {THIRD_OPTIONS.map((option) => (
        <option key={option.value} value={option.value}>{option.label}</option>
      ))}
    </select>
  );
}

const plotConfig = {
  responsive: true,
  displayModeBar: false,
};

function teamSeries(rows: DataRow[], team: string, valueKey: string) {
  return rows
    .filter((row) => String(row.team ?? "") === team)
    .map((row) => ({
      minute: Number(row.minute ?? 0),
      value: Number(row[valueKey] ?? 0),
    }))
    .filter((row) => Number.isFinite(row.minute) && Number.isFinite(row.value))
    .sort((a, b) => a.minute - b.minute);
}

function thirdSeries(rows: DataRow[], team: string, third: ThirdKey, valueKey: string) {
  return teamSeries(rows.filter((row) => String(row.third ?? "") === third), team, valueKey);
}

function flankFor(rows: DataRow[], team: string, flank: string) {
  return rows.find((row) => String(row.team ?? "") === team && String(row.flank ?? "") === flank) ?? {};
}

function flankAlpha(rows: DataRow[], team: string, flank: string) {
  const values = ["Left", "Center", "Right"].map((key) => Number(flankFor(rows, team, key).num_attacks ?? 0));
  return 0.18 + (Number(flankFor(rows, team, flank).num_attacks ?? 0) / Math.max(1, ...values)) * 0.72;
}

function combineMomentumSeries(
  first: Array<{ minute: number; value: number }>,
  second: Array<{ minute: number; value: number }>
) {
  const byMinute = new Map<number, number>();
  first.forEach((row) => byMinute.set(row.minute, (byMinute.get(row.minute) ?? 0) + row.value));
  second.forEach((row) => byMinute.set(row.minute, (byMinute.get(row.minute) ?? 0) + row.value));
  return [...byMinute.entries()]
    .map(([minute, value]) => ({ minute, value }))
    .sort((a, b) => a.minute - b.minute);
}

export const MatchDynamicsPlotly = memo(function MatchDynamicsPlotlyInner({
  teams,
  teamColors,
  fullTime,
  xgFlowRows,
  xgMarkers,
  passRows,
  flankRows,
  ppdaRows,
  momentumRows,
  epvMomentumRows = [],
  eventMarkers,
  teamSummaries,
  thirdsRows = [],
  seasonBaselines,
}: Props) {
  const [themeColors, setThemeColors] = useState(readThemeColors);
  const [possessionThird, setPossessionThird] = useState<ThirdKey>("all");
  const [passThird, setPassThird] = useState<ThirdKey>("all");
  const [ppdaThird, setPpdaThird] = useState<ThirdKey>("all");
  const [turnoverThird, setTurnoverThird] = useState<ThirdKey>("all");
  const [momentumMetric, setMomentumMetric] = useState<MomentumMetric>("xt");
  // "player|team" -> circular headshot data URL for goal markers
  const [headshots, setHeadshots] = useState<Record<string, string>>({});

  useEffect(() => {
    const goalRows = [...xgMarkers, ...eventMarkers].filter((row) => String(row.event_type ?? "") === "goal");
    const byTeam = new Map<string, Set<string>>();
    goalRows.forEach((row) => {
      const team = String(row.team ?? "");
      const player = String(row.player ?? "");
      if (!team || !player) return;
      if (!byTeam.has(team)) byTeam.set(team, new Set());
      byTeam.get(team)!.add(player);
    });
    let cancelled = false;
    (async () => {
      for (const [team, names] of byTeam) {
        try {
          const response = await fetch(
            `${PUBLIC_API_BASE}/players/images?names=${encodeURIComponent([...names].join(","))}&team=${encodeURIComponent(team)}`,
            { headers: await getAuthHeaders() }
          );
          const data = (await response.json()) as Record<string, string | null>;
          const border = teamColors[team] ?? "#22c55e";
          await Promise.all(
            Object.entries(data).map(async ([name, url]) => {
              if (!url) return;
              const circular = await circularImageDataUrl(url, border);
              if (circular && !cancelled) setHeadshots((prev) => ({ ...prev, [`${name}|${team}`]: circular }));
            })
          );
        } catch {
          // headshots are progressive enhancement only
        }
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [xgMarkers, eventMarkers]);

  const headshotFor = (row: DataRow) => headshots[`${String(row.player ?? "")}|${String(row.team ?? "")}`];

  useEffect(() => {
    const updateColors = () => setThemeColors(readThemeColors());
    updateColors();
    const observer = new MutationObserver(updateColors);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "data-theme"] });
    return () => observer.disconnect();
  }, []);

  const chartText = themeColors.text;
  const chartMuted = themeColors.muted;
  const markerLine = themeColors.surface;

  function axisStyle(title: string, range?: [number, number]) {
    return {
      title,
      range,
      zeroline: false,
      gridcolor: "rgba(148,163,184,0.22)",
      linecolor: "rgba(148,163,184,0.36)",
      tickfont: { color: chartMuted, size: 11 },
      titlefont: { color: chartMuted, size: 12 },
    };
  }

  function baseLayout(height = 330) {
    return {
      autosize: true,
      height,
      margin: { l: 52, r: 24, t: 18, b: 48 },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(148,163,184,0.08)",
      font: { color: chartText, family: CHART_FONT_FAMILY },
      hovermode: "x unified",
      legend: {
        orientation: "h",
        y: -0.22,
        x: 0,
        font: { color: chartMuted, size: 12 },
      },
    };
  }

  function xgGoalLabel(row: DataRow) {
    const player = String(row.player ?? "").trim();
    return `${player}<br>xG ${Number(row.xg ?? 0).toFixed(2)}`;
  }

  function goalMarkerTrace(goals: DataRow[], yValue: number, label = "Goals") {
    return {
      x: goals.map((row) => Number(row.minute ?? 0)),
      y: goals.map(() => yValue),
      text: goals.map((row) => {
        const player = String(row.player ?? "").trim();
        const team = String(row.team ?? "").trim();
        return `${team}${player ? `<br>${player}` : ""}`;
      }),
      name: label,
      type: "scatter",
      mode: "markers",
      cliponaxis: false,
      marker: {
        symbol: "star",
        size: 11,
        color: goals.map((row) => String(row.team ?? "")),
        line: { color: markerLine, width: 1 },
      },
      hovertemplate: "%{x}'<br>%{text}<extra></extra>",
      showlegend: false,
    };
  }

  const [teamA, teamB] = teams;
  const colorA = teamColors[teamA] ?? "#22c55e";
  const colorB = teamColors[teamB] ?? "#60a5fa";
  const minuteRange: [number, number] = [0, Math.max(90, fullTime)];
  const xgA = teamSeries(xgFlowRows, teamA, "cumulative_xg");
  const xgB = teamSeries(xgFlowRows, teamB, "cumulative_xg");
  const summaryA = teamSummaries.find((row) => row.team === teamA);
  const summaryB = teamSummaries.find((row) => row.team === teamB);
  const hasThirds = thirdsRows.length > 0;
  const possessionA = possessionThird === "all" ? teamSeries(passRows, teamA, "possession_pct") : thirdSeries(thirdsRows, teamA, possessionThird, "possession_pct");
  const possessionB = possessionThird === "all" ? teamSeries(passRows, teamB, "possession_pct") : thirdSeries(thirdsRows, teamB, possessionThird, "possession_pct");
  const passA = passThird === "all" ? teamSeries(passRows, teamA, "pass_accuracy_pct") : thirdSeries(thirdsRows, teamA, passThird, "pass_accuracy_pct");
  const passB = passThird === "all" ? teamSeries(passRows, teamB, "pass_accuracy_pct") : thirdSeries(thirdsRows, teamB, passThird, "pass_accuracy_pct");
  const ppdaA = ppdaThird === "all" ? teamSeries(ppdaRows, teamA, "ppda") : thirdSeries(thirdsRows, teamA, ppdaThird, "ppda");
  const ppdaB = ppdaThird === "all" ? teamSeries(ppdaRows, teamB, "ppda") : thirdSeries(thirdsRows, teamB, ppdaThird, "ppda");
  const toA = turnoverThird === "all" ? teamSeries(ppdaRows, teamA, "turnovers") : thirdSeries(thirdsRows, teamA, turnoverThird, "turnovers");
  const toB = turnoverThird === "all" ? teamSeries(ppdaRows, teamB, "turnovers") : thirdSeries(thirdsRows, teamB, turnoverThird, "turnovers");
  const xtA = momentumRows.map((row) => ({ minute: Number(row.minute ?? 0), value: Number(row[teamA] ?? 0) }));
  const xtB = momentumRows.map((row) => ({ minute: Number(row.minute ?? 0), value: Number(row[teamB] ?? 0) }));
  const epvA = epvMomentumRows.map((row) => ({ minute: Number(row.minute ?? 0), value: Number(row[teamA] ?? 0) }));
  const epvB = epvMomentumRows.map((row) => ({ minute: Number(row.minute ?? 0), value: Number(row[teamB] ?? 0) }));
  const goals = xgMarkers.filter((row) => String(row.event_type ?? "") === "goal");
  const subs = xgMarkers.filter((row) => String(row.event_type ?? "") === "substitution");
  const momentumGoals = eventMarkers.filter((row) => String(row.event_type ?? "") === "goal");
  const yellowCards = eventMarkers.filter((row) => String(row.event_type ?? "") === "yellow_card");
  const redCards = eventMarkers.filter((row) => String(row.event_type ?? "") === "red_card");
  const straightRedCards = redCards.filter((row) => String(row.card_kind ?? "") !== "second_yellow_red");
  const secondYellowRedCards = redCards.filter((row) => String(row.card_kind ?? "") === "second_yellow_red");
  const xgMax = Math.max(0.1, ...xgFlowRows.map((row) => Number(row.cumulative_xg ?? 0)));
  const ppdaMax = Math.max(1, ...ppdaA.map((row) => row.value), ...ppdaB.map((row) => row.value));
  const ppdaSeasonRefs = [teamA, teamB]
    .map((team) => {
      const baseline = seasonBaselines?.[team];
      return baseline && !baseline.lowSample ? metricByKey(baseline, "ppda")?.seasonAvg : undefined;
    })
    .filter((value): value is number => value !== undefined);
  const ppdaSpanMax = Math.max(ppdaMax, ...ppdaSeasonRefs);
  const toMax = Math.max(1, ...toA.map((row) => row.value), ...toB.map((row) => row.value));
  const selectedMomentumA = momentumMetric === "epv" ? epvA : momentumMetric === "combined" ? combineMomentumSeries(xtA, epvA) : xtA;
  const selectedMomentumB = momentumMetric === "epv" ? epvB : momentumMetric === "combined" ? combineMomentumSeries(xtB, epvB) : xtB;
  const selectedMomentumMax = Math.max(
    0.01,
    ...selectedMomentumA.map((row) => Math.abs(row.value)),
    ...selectedMomentumB.map((row) => Math.abs(row.value))
  );
  const momentumLabel = momentumMetric === "epv" ? "EPV" : momentumMetric === "combined" ? "xT + EPV" : "xT";
  const momentumFilenameMetric = momentumMetric === "epv" ? "epv" : momentumMetric === "combined" ? "xt-epv" : "xt";
  const momentumFootnote =
    momentumMetric === "epv"
      ? "Rolling expected-possession-value gains from successful passes and carries — this isolates how much each team moved possession into more valuable pitch states; player faces mark goals, card icons bookings."
      : momentumMetric === "combined"
        ? "Combined rolling xT and EPV swings — use this to blend direct threat creation with possession value gained in each spell; player faces mark goals, card icons bookings."
        : "Rolling expected-threat swings — the team pushing the shaded area away from the zero line is building more danger in that spell; player faces mark goals, card icons bookings.";
  const goalMarkerColors = goals.map((row) => (String(row.team) === teamA ? colorA : colorB));
  const xSpan = Math.max(90, fullTime);
  const xgYMax = Math.max(0.5, xgMax * 1.28);
  const xgLabelOffset = xgYMax * 0.075;
  const markerImage = (source: string, x: number, y: number, sizex: number, sizey: number) => ({
    source,
    xref: "x",
    yref: "y",
    x,
    y,
    sizex,
    sizey,
    xanchor: "center",
    yanchor: "middle",
    layer: "above",
  });
  const xgFlowImages = [
    ...goals
      .filter((row) => headshotFor(row))
      .map((row) => markerImage(headshotFor(row)!, Number(row.minute ?? 0), Number(row.cumulative_xg ?? 0), xSpan * 0.055, xgYMax * 0.135)),
    ...subs.map((row) => markerImage(SUB_ICON, Number(row.minute ?? 0), Number(row.cumulative_xg ?? 0), xSpan * 0.034, xgYMax * 0.085)),
  ];
  const momentumSpanY = selectedMomentumMax * 1.15 * 2;
  const momentumImages = [
    ...momentumGoals
      .filter((row) => headshotFor(row))
      .map((row) => markerImage(headshotFor(row)!, Number(row.minute ?? 0), eventYFor(row, selectedMomentumMax, 0.9), xSpan * 0.05, momentumSpanY * 0.12)),
    ...yellowCards.map((row) => markerImage(CARD_ICON_YELLOW, Number(row.minute ?? 0), eventYFor(row, selectedMomentumMax, 0.72), xSpan * 0.026, momentumSpanY * 0.085)),
    ...straightRedCards.map((row) => markerImage(CARD_ICON_RED, Number(row.minute ?? 0), eventYFor(row, selectedMomentumMax, 0.72), xSpan * 0.028, momentumSpanY * 0.09)),
    ...secondYellowRedCards.map((row) => markerImage(CARD_ICON_SECOND_YELLOW, Number(row.minute ?? 0), eventYFor(row, selectedMomentumMax, 0.72), xSpan * 0.04, momentumSpanY * 0.09)),
  ];

  function lineTrace(name: string, data: Array<{ minute: number; value: number }>, color: string, extra: Record<string, unknown> = {}) {
    return {
      x: data.map((row) => row.minute),
      y: data.map((row) => row.value),
      name,
      type: "scatter",
      mode: "lines+markers",
      line: { color, width: 3 },
      marker: { color, size: 6 },
      cliponaxis: false,
      hovertemplate: "%{x}'<br>%{y:.2f}<extra></extra>",
      ...extra,
    };
  }

  function eventYFor(row: DataRow, axisMax: number, multiplier = 0.88) {
    return String(row.team ?? "") === teamB ? -axisMax * multiplier : axisMax * multiplier;
  }

  function eventText(rows: DataRow[]) {
    return rows.map((row) => {
      const player = String(row.player ?? "").trim();
      return `${String(row.label ?? row.event_type ?? "Event")}${player ? `<br>${player}` : ""}`;
    });
  }

  function hexAlpha(hex: string, alpha: number) {
    const match = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
    if (!match) return hex;
    const n = parseInt(match[1], 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
  }

  function seasonAvgFor(team: string, metricKey: string): number | undefined {
    const baseline = seasonBaselines?.[team];
    if (!baseline || baseline.lowSample) return undefined;
    return metricByKey(baseline, metricKey)?.seasonAvg;
  }

  // Dashed season-average reference lines; whole-pitch baselines only apply
  // when the third filter is "all".
  function seasonRefLayer(metricKey: string, third: ThirdKey) {
    if (third !== "all") return { shapes: [], annotations: [] };
    const refs = [
      { team: teamA, color: colorA },
      { team: teamB, color: colorB },
    ]
      .map(({ team, color }) => ({ value: seasonAvgFor(team, metricKey), color }))
      .filter((ref): ref is { value: number; color: string } => ref.value !== undefined);
    return {
      shapes: refs.map((ref) => ({
        type: "line",
        xref: "x",
        yref: "y",
        x0: minuteRange[0],
        x1: minuteRange[1],
        y0: ref.value,
        y1: ref.value,
        line: { color: hexAlpha(ref.color, 0.4), width: 1.5, dash: "dot" },
        layer: "below",
      })),
      annotations: refs.map((ref, index) => ({
        x: minuteRange[1],
        y: ref.value,
        xref: "x",
        yref: "y",
        text: "season avg",
        showarrow: false,
        xanchor: "right" as const,
        yanchor: index % 2 === 0 ? ("bottom" as const) : ("top" as const),
        font: { size: 9, color: hexAlpha(ref.color, 0.75), family: CHART_FONT_FAMILY },
      })),
    };
  }

  function metricGoalTrace(yValue: number) {
    return {
      ...goalMarkerTrace(goals, yValue),
      marker: {
        symbol: "star",
        size: 10,
        color: goalMarkerColors,
        line: { color: markerLine, width: 1 },
      },
    };
  }

  return (
    <>
      <section className="card stack">
        <div className="chart-card-head">
          <div>
            <span className="eyebrow">Match Dynamics</span>
            <h2 style={{ margin: "6px 0 0" }}>xG Flow</h2>
          </div>
          <DownloadPngButton filename={`${teamA}-vs-${teamB}-xg-flow`} title="xG Flow" />
        </div>
        <div className="xg-flow-summary-strip">
          <span><strong>{teamA}</strong> xG {Number(summaryA?.xg ?? 0).toFixed(2)} · xGOT {Number(summaryA?.xgot ?? 0).toFixed(2)} · EPV {Number(summaryA?.epv_added ?? 0).toFixed(2)}</span>
          <span><strong>{teamB}</strong> xG {Number(summaryB?.xg ?? 0).toFixed(2)} · xGOT {Number(summaryB?.xgot ?? 0).toFixed(2)} · EPV {Number(summaryB?.epv_added ?? 0).toFixed(2)}</span>
        </div>
        <div className="plotly-chart-shell">
          <Plot
            data={[
              lineTrace(teamA, xgA, colorA, { line: { color: colorA, width: 3, shape: "hv" }, mode: "lines" }),
              lineTrace(teamB, xgB, colorB, { line: { color: colorB, width: 3, shape: "hv" }, mode: "lines" }),
              {
                x: goals.map((row) => Number(row.minute ?? 0)),
                y: goals.map((row) => Number(row.cumulative_xg ?? 0)),
                name: "Goals",
                type: "scatter",
                mode: "markers",
                marker: {
                  symbol: "star",
                  size: 14,
                  color: goals.map((row) => (String(row.team) === teamA ? colorA : colorB)),
                  opacity: goals.map((row) => (headshotFor(row) ? 0 : 1)),
                  line: { color: markerLine, width: 1 },
                },
                text: goals.map(xgGoalLabel),
                hovertemplate: "%{text}<extra></extra>",
              },
              {
                x: goals.map((row) => Number(row.minute ?? 0)),
                y: goals.map((row) => Math.min(xgYMax - xgLabelOffset * 0.25, Number(row.cumulative_xg ?? 0) + xgLabelOffset)),
                text: goals.map(xgGoalLabel),
                name: "Goal labels",
                type: "scatter",
                mode: "text",
                textposition: "top center",
                textfont: {
                  color: chartText,
                  size: 11,
                  family: CHART_FONT_FAMILY,
                },
                hoverinfo: "skip",
                showlegend: false,
              },
              {
                x: subs.map((row) => Number(row.minute ?? 0)),
                y: subs.map((row) => Number(row.cumulative_xg ?? 0)),
                text: subs.map((row) => String(row.player ?? "")),
                name: "Sub on",
                type: "scatter",
                mode: "markers",
                marker: { symbol: "triangle-up", size: 12, color: "#22c55e", opacity: 0, line: { color: markerLine, width: 1 } },
                hovertemplate: "%{x}'<br>Sub on: %{text}<extra></extra>",
              },
            ]}
            layout={{
              ...baseLayout(390),
              xaxis: axisStyle("Minute", minuteRange),
              yaxis: axisStyle("Cumulative xG", [0, xgYMax]),
              shapes: [{ type: "line", x0: 45, x1: 45, y0: 0, y1: xgYMax, line: { color: "rgba(148,163,184,0.55)", width: 1, dash: "dash" } }],
              images: xgFlowImages,
            }}
            config={plotConfig}
            className="plotly-chart"
          />
          <p className="chart-footnote">Cumulative expected goals across the match — steeper climbs mean sustained chance creation; player faces mark goals, arrow icons substitutions. A team well above its opponent &quot;deserved&quot; more from the game.</p>
        </div>
      </section>

      <div className="grid grid-2">
        <section className="card stack">
          <div className="chart-card-head">
            <h2 style={{ margin: 0 }}>Possession</h2>
            <div className="row" style={{ gap: 8 }}>
              {hasThirds ? <ThirdSelect id="possession-third" value={possessionThird} onChange={setPossessionThird} /> : null}
              <DownloadPngButton filename={`${teamA}-vs-${teamB}-possession`} title="Possession" filters={possessionThird !== "all" ? [`${THIRD_OPTIONS.find((o) => o.value === possessionThird)?.label}`] : []} />
            </div>
          </div>
          <Plot
            data={[lineTrace(teamA, possessionA, colorA), lineTrace(teamB, possessionB, colorB), metricGoalTrace(2)]}
            layout={{ ...baseLayout(), xaxis: axisStyle("Minute", minuteRange), yaxis: axisStyle("Possession %", [0, 100]), ...seasonRefLayer("possession_pct", possessionThird) }}
            config={plotConfig}
            className="plotly-chart"
          />
          <p className="chart-footnote">Share of touches per 15-minute window{possessionThird !== "all" ? ` inside the ${THIRD_OPTIONS.find((o) => o.value === possessionThird)?.label.toLowerCase()}` : ""} — spells above 50% mean territorial control; stars mark goals.</p>
        </section>
        <section className="card stack">
          <div className="chart-card-head">
            <h2 style={{ margin: 0 }}>Pass Accuracy</h2>
            <div className="row" style={{ gap: 8 }}>
              {hasThirds ? <ThirdSelect id="pass-third" value={passThird} onChange={setPassThird} /> : null}
              <DownloadPngButton filename={`${teamA}-vs-${teamB}-pass-accuracy`} title="Pass Accuracy" filters={passThird !== "all" ? [`${THIRD_OPTIONS.find((o) => o.value === passThird)?.label}`] : []} />
            </div>
          </div>
          <Plot
            data={[lineTrace(teamA, passA, colorA), lineTrace(teamB, passB, colorB), metricGoalTrace(2)]}
            layout={{ ...baseLayout(), xaxis: axisStyle("Minute", minuteRange), yaxis: axisStyle("Pass Accuracy %", [0, 100]) }}
            config={plotConfig}
            className="plotly-chart"
          />
          <p className="chart-footnote">Completed-pass rate per 15-minute window{passThird !== "all" ? ` for passes starting in the ${THIRD_OPTIONS.find((o) => o.value === passThird)?.label.toLowerCase()}` : ""} — dips usually coincide with pressure or more direct play.</p>
        </section>
      </div>

      <section className="card stack">
        <div className="chart-card-head">
          <h2 style={{ margin: 0 }}>Attacks by Flanks</h2>
          <DownloadPngButton filename={`${teamA}-vs-${teamB}-attacks-by-flanks`} title="Attacks by Flanks" maxCharts={2} />
        </div>
        <div className="embedded-mini-pitches">
          {[{ team: teamA, color: colorA }, { team: teamB, color: colorB }].map((tm) => (
            <div key={tm.team} className="embedded-mini-pitch">
              <strong>{tm.team}</strong>
              <svg viewBox="0 0 68 52.5" className="embedded-pitch-svg embedded-half-pitch-svg" aria-label={`${tm.team} attacks by flank`}>
                <rect x="0" y="0" width="68" height="52.5" fill="var(--bg-muted)" />
                <rect x="0" y="0" width="20" height="52.5" fill={tm.color} opacity={flankAlpha(flankRows, tm.team, "Left")} />
                <rect x="20" y="0" width="28" height="52.5" fill={tm.color} opacity={flankAlpha(flankRows, tm.team, "Center")} />
                <rect x="48" y="0" width="20" height="52.5" fill={tm.color} opacity={flankAlpha(flankRows, tm.team, "Right")} />
                <path className="embedded-pitch-line" d="M0 0H68V52.5H0Z M13.84 36H54.16V52.5H13.84Z M24.84 47H43.16V52.5H24.84Z M34 0V7 M34 0m-9.15 0a9.15 9.15 0 0 0 18.3 0" />
                {["Left", "Center", "Right"].map((flank, idx) => {
                  const f = flankFor(flankRows, tm.team, flank);
                  const x = [10, 34, 58][idx];
                  return (
                    <g key={`${tm.team}-${flank}`}>
                      <text x={x} y={22} className="embedded-pitch-text" textAnchor="middle">{Number(f.num_attacks ?? 0)}</text>
                      <text x={x} y={30} className="embedded-pitch-text-small" textAnchor="middle">{Number(f.total_xg ?? 0).toFixed(2)} xG</text>
                      <text x={x} y={40} className="embedded-pitch-text-small" textAnchor="middle">{flank}</text>
                    </g>
                  );
                })}
              </svg>
            </div>
          ))}
        </div>
        <p className="chart-footnote">Where each team&apos;s attacks entered the final third — darker bands carried more attacks, and the xG label shows which side actually produced danger.</p>
      </section>

      <div className="grid grid-2">
        <section className="card stack">
          <div className="chart-card-head">
            <h2 style={{ margin: 0 }}>PPDA</h2>
            <div className="row" style={{ gap: 8 }}>
              {hasThirds ? <ThirdSelect id="ppda-third" value={ppdaThird} onChange={setPpdaThird} /> : null}
              <DownloadPngButton filename={`${teamA}-vs-${teamB}-ppda`} title="PPDA" filters={ppdaThird !== "all" ? [`${THIRD_OPTIONS.find((o) => o.value === ppdaThird)?.label}`] : []} />
            </div>
          </div>
          <Plot
            data={[lineTrace(teamA, ppdaA, colorA), lineTrace(teamB, ppdaB, colorB), metricGoalTrace(0)]}
            layout={{ ...baseLayout(), xaxis: axisStyle("Minute", minuteRange), yaxis: axisStyle("PPDA", [0, Math.ceil(ppdaSpanMax * 1.15)]), ...seasonRefLayer("ppda", ppdaThird) }}
            config={plotConfig}
            className="plotly-chart"
          />
          <p className="chart-footnote">Opposition passes allowed per defensive action{ppdaThird !== "all" ? ` in the ${THIRD_OPTIONS.find((o) => o.value === ppdaThird)?.label.toLowerCase()}` : ""} — lower values mean a more aggressive press.</p>
        </section>
        <section className="card stack">
          <div className="chart-card-head">
            <h2 style={{ margin: 0 }}>Turnovers</h2>
            <div className="row" style={{ gap: 8 }}>
              {hasThirds ? <ThirdSelect id="turnover-third" value={turnoverThird} onChange={setTurnoverThird} /> : null}
              <DownloadPngButton filename={`${teamA}-vs-${teamB}-turnovers`} title="Turnovers" filters={turnoverThird !== "all" ? [`${THIRD_OPTIONS.find((o) => o.value === turnoverThird)?.label}`] : []} />
            </div>
          </div>
          <Plot
            data={[lineTrace(teamA, toA, colorA), lineTrace(teamB, toB, colorB), metricGoalTrace(0)]}
            layout={{ ...baseLayout(), xaxis: axisStyle("Minute", minuteRange), yaxis: axisStyle("Turnovers", [0, Math.ceil(toMax * 1.15)]) }}
            config={plotConfig}
            className="plotly-chart"
          />
          <p className="chart-footnote">Possessions lost per 15-minute window{turnoverThird !== "all" ? ` in the ${THIRD_OPTIONS.find((o) => o.value === turnoverThird)?.label.toLowerCase()}` : ""} — spikes flag sloppy spells or effective opposition pressure.</p>
        </section>
      </div>

      <section className="card stack xt-momentum-card">
        <div className="chart-card-head">
          <h2 style={{ margin: 0 }}>Momentum</h2>
          <div className="row" style={{ gap: 8 }}>
            <select
              aria-label="Momentum metric"
              className="third-select"
              value={momentumMetric}
              onChange={(event) => setMomentumMetric(event.target.value as MomentumMetric)}
            >
              <option value="xt">xT</option>
              <option value="epv">EPV</option>
              <option value="combined">xT + EPV</option>
            </select>
            <DownloadPngButton
              filename={`${teamA}-vs-${teamB}-${momentumFilenameMetric}-momentum`}
              title={`${momentumLabel} Momentum`}
              scopeSelector=".xt-momentum-card"
              canvasHeight={720}
            />
          </div>
        </div>
        <Plot
          data={[
            {
              x: selectedMomentumA.map((row) => row.minute),
              y: selectedMomentumA.map((row) => Math.abs(row.value)),
              customdata: selectedMomentumA.map((row) => Math.abs(row.value)),
              name: teamA,
              type: "scatter",
              mode: "lines",
              line: { color: colorA, width: 2 },
              fill: "tozeroy",
              fillcolor: `${colorA}55`,
              hovertemplate: `%{x}'<br>${momentumLabel} %{customdata:.3f}<extra></extra>`,
            },
            {
              x: selectedMomentumB.map((row) => row.minute),
              y: selectedMomentumB.map((row) => -Math.abs(row.value)),
              customdata: selectedMomentumB.map((row) => Math.abs(row.value)),
              name: teamB,
              type: "scatter",
              mode: "lines",
              line: { color: colorB, width: 2 },
              fill: "tozeroy",
              fillcolor: `${colorB}55`,
              hovertemplate: `%{x}'<br>${momentumLabel} %{customdata:.3f}<extra></extra>`,
            },
            {
              x: momentumGoals.map((row) => Number(row.minute ?? 0)),
              y: momentumGoals.map((row) => eventYFor(row, selectedMomentumMax, 0.9)),
              text: eventText(momentumGoals),
              name: "Goals",
              type: "scatter",
              mode: "markers",
              marker: {
                symbol: "star",
                size: 14,
                color: momentumGoals.map((row) => (String(row.team) === teamA ? colorA : colorB)),
                opacity: momentumGoals.map((row) => (headshotFor(row) ? 0 : 1)),
                line: { color: markerLine, width: 1 },
              },
              hovertemplate: "%{x}'<br>%{text}<extra></extra>",
            },
            {
              x: yellowCards.map((row) => Number(row.minute ?? 0)),
              y: yellowCards.map((row) => eventYFor(row, selectedMomentumMax, 0.72)),
              text: eventText(yellowCards),
              name: "Yellow cards",
              type: "scatter",
              mode: "markers",
              marker: { symbol: "diamond", size: 11, color: "#facc15", opacity: 0, line: { color: markerLine, width: 1 } },
              hovertemplate: "%{x}'<br>%{text}<extra></extra>",
            },
            {
              x: redCards.map((row) => Number(row.minute ?? 0)),
              y: redCards.map((row) => eventYFor(row, selectedMomentumMax, 0.72)),
              text: eventText(redCards),
              name: "Red cards",
              type: "scatter",
              mode: "markers",
              marker: { symbol: "diamond", size: 12, color: "#ef4444", opacity: 0, line: { color: markerLine, width: 1 } },
              hovertemplate: "%{x}'<br>%{text}<extra></extra>",
            },
          ]}
          layout={{
            ...baseLayout(440),
            margin: { l: 52, r: 24, t: 18, b: 34 },
            legend: {
              orientation: "h",
              y: -0.13,
              x: 0,
              font: { color: chartMuted, size: 12 },
            },
            xaxis: axisStyle("Minute", minuteRange),
            yaxis: axisStyle(momentumLabel, [-selectedMomentumMax * 1.15, selectedMomentumMax * 1.15]),
            shapes: [{ type: "line", x0: 0, x1: Math.max(90, fullTime), y0: 0, y1: 0, line: { color: "rgba(148,163,184,0.55)", width: 1, dash: "dash" } }],
            images: momentumImages,
          }}
          config={plotConfig}
          className="plotly-chart xt-momentum-chart"
        />
        <p className="chart-footnote">{momentumFootnote}</p>
      </section>
    </>
  );
});
