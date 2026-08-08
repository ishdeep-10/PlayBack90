"use client";

import { Plot } from "../lib/plotly";

import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { CHART_FONT_FAMILY, num, readThemeColors } from "../lib/theme";
import { PlayerAvatar } from "./PlayerAvatar";


type LeadupEvent = {
  minute?: number;
  second?: number;
  player?: string;
  type?: string;
  outcome?: string;
  is_assist?: boolean;
  xT?: number;
  xA?: number;
  x?: number;
  y?: number;
  end_x?: number;
  end_y?: number;
};

type ShotRow = Record<string, string | number | boolean | null | undefined | LeadupEvent[]> & {
  leadup_events?: LeadupEvent[];
};
type NumberedShot = ShotRow & { shotNumber: number };

type Props = {
  shots: ShotRow[];
  team: string;
  teamColor: string;
  orientation?: "stacked" | "side-by-side";
};

const plotConfig = {
  responsive: true,
  displayModeBar: false,
};

function colorWithAlpha(color: string, alpha: number) {
  const trimmed = color.trim();
  if (trimmed.startsWith("#")) {
    const hex = trimmed.slice(1);
    const fullHex = hex.length === 3 ? hex.split("").map((char) => char + char).join("") : hex;
    const value = Number.parseInt(fullHex.slice(0, 6), 16);
    if (Number.isFinite(value)) {
      const red = (value >> 16) & 255;
      const green = (value >> 8) & 255;
      const blue = value & 255;
      return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
    }
  }
  const rgb = trimmed.match(/rgba?\(([^)]+)\)/);
  if (rgb) {
    const [red, green, blue] = rgb[1].split(",").map((part) => part.trim());
    return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
  }
  return alpha >= 0.3 ? "rgba(100,116,139,0.38)" : "rgba(100,116,139,0.18)";
}

function shotOutcome(row: ShotRow) {
  if (Boolean(row.own_goal)) return "Own goal";
  if (Boolean(row.blocked)) return "Blocked";
  const type = String(row.type ?? "");
  if (type === "Goal") return "Goal";
  if (type === "SavedShot") return "On target";
  if (type === "ShotOnPost") return "Woodwork";
  return "Off target";
}

function shotSymbol(row: ShotRow) {
  if (Boolean(row.own_goal)) return "star-diamond";
  if (Boolean(row.blocked)) return "square";
  const type = String(row.type ?? "");
  if (type === "Goal") return "star";
  if (type === "ShotOnPost") return "diamond";
  return "circle";
}

function shotFill(row: ShotRow, teamColor: string) {
  const outcome = shotOutcome(row);
  if (outcome === "Off target" || outcome === "Blocked") return "rgba(0,0,0,0)";
  return teamColor;
}

function shotLine(row: ShotRow, teamColor: string, mode: string) {
  const outcome = shotOutcome(row);
  if (outcome === "Own goal") return "#f59e0b";
  if (outcome === "Goal" || outcome === "On target") return mode === "dark" ? "#ffffff" : "#0f172a";
  if (outcome === "Woodwork") return "#22c55e";
  return teamColor;
}

function pitchPath(points: Array<[number, number]>) {
  return points.map(([fieldX, fieldY], index) => `${index === 0 ? "M" : "L"} ${fieldY.toFixed(2)} ${fieldX.toFixed(2)}`).join(" ");
}

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
  return pitchPath(points);
}

function shotText(row: ShotRow, index: number) {
  const player = String(row.player ?? "");
  const minute = num(row.minute);
  const xg = num(row.xg).toFixed(2);
  const xgot = num(row.xgot ?? row.xGOT).toFixed(2);
  const state = String(row.game_state_label ?? "Level");
  const score = String(row.score_before ?? "0-0");
  return `#${index + 1} · ${minute}' ${player}<br>${shotOutcome(row)} · xG ${xg} · xGOT ${xgot}<br>${String(row.situation ?? "")}<br>${state} · score ${score}`;
}

function eventLabel(event: LeadupEvent) {
  const second = String(num(event.second)).padStart(2, "0");
  const time = `${num(event.minute)}:${second}`;
  const player = String(event.player ?? "").trim();
  const type = String(event.type ?? "Action");
  const outcome = String(event.outcome ?? "").trim();
  return `${time} · ${player || "Unknown"} · ${type}${outcome ? ` (${outcome})` : ""}`;
}

function eventMetricLabel(event: LeadupEvent) {
  const xt = num(event.xT);
  const xa = num(event.xA);
  const parts = [`xT ${xt.toFixed(3)}`];
  if (event.is_assist) parts.push(`xA ${xa.toFixed(3)}`);
  return parts.join(" · ");
}

type PlotlyClickEvent = {
  points?: Array<{
    customdata?: unknown;
    pointIndex?: number;
    pointNumber?: number;
    data?: { customdata?: unknown[] };
  }>;
};

function plotlyPointIndex(event: PlotlyClickEvent) {
  const point = event.points?.[0];
  const value = Array.isArray(point?.customdata) ? point.customdata[0] : point?.customdata;
  const parsed = Number(value);
  if (Number.isFinite(parsed)) return parsed;
  const localPoint = point?.pointIndex ?? point?.pointNumber;
  if (localPoint === undefined || !Array.isArray(point?.data?.customdata)) return null;
  const fallback = Number(point.data.customdata[localPoint]);
  return Number.isFinite(fallback) ? fallback : null;
}

function goalMapX(goalMouthY: unknown) {
  const goalLeft = 30.8;
  const goalWidth = 6.4;
  const frameLeft = 4;
  const frameWidth = 60;
  return frameLeft + ((goalLeft + goalWidth - num(goalMouthY, 34)) / goalWidth) * frameWidth;
}

function toggleSelection(currentIndex: number | null, nextIndex: number) {
  return currentIndex === nextIndex ? null : nextIndex;
}

function flipPitchY(value: unknown) {
  return 68 - num(value);
}

function hasValidPitchPoint(row: ShotRow) {
  return Number.isFinite(Number(row.x)) && Number.isFinite(Number(row.y));
}

function shouldMirrorShot(row: ShotRow) {
  return !Boolean(row.own_goal) && num(row.x, 105) < 52.5;
}

function shotDisplayX(row: ShotRow) {
  const x = num(row.x);
  return shouldMirrorShot(row) ? 105 - x : x;
}

function shotDisplayY(row: ShotRow) {
  const y = num(row.y);
  return shouldMirrorShot(row) ? 68 - y : y;
}

function eventDisplayX(event: LeadupEvent, mirrored: boolean) {
  const x = num(event.x);
  return mirrored ? 105 - x : x;
}

function eventDisplayY(event: LeadupEvent, mirrored: boolean) {
  const y = num(event.y);
  return mirrored ? 68 - y : y;
}

function eventDisplayEndX(event: LeadupEvent, mirrored: boolean) {
  const x = num(event.end_x ?? event.x);
  return mirrored ? 105 - x : x;
}

function eventDisplayEndY(event: LeadupEvent, mirrored: boolean) {
  const y = num(event.end_y ?? event.y);
  return mirrored ? 68 - y : y;
}

function pct(value: number, min: number, max: number) {
  return ((value - min) / (max - min)) * 100;
}

export function ShotsPlotly({ shots, team, teamColor, orientation = "stacked" }: Props) {
  const [themeColors, setThemeColors] = useState(readThemeColors);
  const attackingShots = useMemo(
    () => shots.filter(hasValidPitchPoint).map((row, index) => ({ ...row, shotNumber: index + 1 }) as NumberedShot),
    [shots],
  );
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [animateSequence, setAnimateSequence] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [sequenceStep, setSequenceStep] = useState(0);
  const [stepWindowMs, setStepWindowMs] = useState(900);
  const selectedShot = selectedIndex === null ? null : attackingShots[selectedIndex] ?? null;

  useEffect(() => {
    const updateColors = () => setThemeColors(readThemeColors());
    updateColors();
    const observer = new MutationObserver(updateColors);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "data-theme"] });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!attackingShots.length || (selectedIndex !== null && selectedIndex >= attackingShots.length)) {
      setSelectedIndex(null);
    }
  }, [attackingShots, selectedIndex]);

  useEffect(() => {
    if (!animateSequence || selectedIndex !== null || !attackingShots.length) return;
    setSelectedIndex(0);
  }, [animateSequence, attackingShots.length, selectedIndex]);

  useEffect(() => {
    setSequenceStep(0);
    setIsPlaying(false);
  }, [selectedIndex, animateSequence]);

  const selectedLeadup = selectedShot?.leadup_events ?? [];
  const selectedShotMirrored = selectedShot ? shouldMirrorShot(selectedShot) : false;
  const sequenceFinalStep = selectedLeadup.length + 1;
  const visibleLeadup = animateSequence ? selectedLeadup.slice(0, Math.min(sequenceStep, selectedLeadup.length)) : selectedLeadup;
  const showAnimatedShot = !animateSequence || sequenceStep >= sequenceFinalStep;
  const markerOpacity = attackingShots.map((_, index) => {
    if (!animateSequence) return selectedIndex === null || selectedIndex === index ? 0.96 : 0.28;
    if (selectedIndex === null) return 0.18;
    if (selectedIndex !== index) return 0.08;
    return showAnimatedShot ? 0.96 : 0.12;
  });
  const markerLineWidth = attackingShots.map((_, index) => (selectedIndex === index ? 4 : 2));
  const markerSizes = attackingShots.map((row, index) => {
    const base = Math.max(14, Math.min(33, 13 + num(row.xg) * 42));
    return selectedIndex === index ? base + 4 : base;
  });
  const customData = attackingShots.map((_, index) => index);
  const labels = attackingShots.map((row) => String(row.shotNumber));
  const hoverText = attackingShots.map(shotText);
  const onGoalShots = attackingShots.filter((row) => ["Goal", "Own goal", "On target", "Woodwork"].includes(shotOutcome(row)));
  const onGoalIndices = onGoalShots.map((row) => attackingShots.indexOf(row));
  const selectShot = (index: number) => setSelectedIndex((current) => animateSequence ? index : toggleSelection(current, index));
  const advanceStep = (direction: 1 | -1) => {
    setSequenceStep((current) => Math.max(0, Math.min(sequenceFinalStep, current + direction)));
  };

  useEffect(() => {
    if (!animateSequence || !isPlaying || !selectedShot) return undefined;
    const timer = window.setInterval(() => {
      setSequenceStep((current) => {
        if (current >= sequenceFinalStep) {
          setIsPlaying(false);
          return current;
        }
        return current + 1;
      });
    }, stepWindowMs);
    return () => window.clearInterval(timer);
  }, [animateSequence, isPlaying, selectedShot, sequenceFinalStep, stepWindowMs]);

  const goalChartData = [
    {
      x: onGoalShots.map((row) => goalMapX(row.goal_mouth_y)),
      y: onGoalShots.map((row) => num(row.goal_mouth_z)),
      customdata: onGoalIndices,
      text: onGoalShots.map((row) => String(row.shotNumber)),
      textposition: "top center",
      hovertext: onGoalShots.map((row) => shotText(row, Number(row.shotNumber) - 1)),
      name: team,
      type: "scatter",
      mode: "markers+text",
      marker: {
        symbol: onGoalShots.map(shotSymbol),
        size: onGoalIndices.map((index) => Math.max(12, markerSizes[index] - 3)),
        color: onGoalShots.map((row) => shotFill(row, teamColor)),
        line: {
          color: onGoalShots.map((row) => shotLine(row, teamColor, themeColors.mode)),
          width: onGoalIndices.map((index) => markerLineWidth[index]),
        },
        opacity: onGoalIndices.map((index) => markerOpacity[index]),
      },
      textfont: { color: themeColors.text, size: 10, family: CHART_FONT_FAMILY },
      hovertemplate: "%{hovertext}<extra></extra>",
    },
  ];

  const pitchChartData = [
    ...visibleLeadup.map((event, index) => {
      const isCurrentStep = animateSequence && index === Math.max(0, Math.min(sequenceStep - 1, selectedLeadup.length - 1));
      return {
      x: [flipPitchY(eventDisplayY(event, selectedShotMirrored)), flipPitchY(eventDisplayEndY(event, selectedShotMirrored))],
      y: [eventDisplayX(event, selectedShotMirrored), eventDisplayEndX(event, selectedShotMirrored)],
      text: [`${eventLabel(event)}<br>${eventMetricLabel(event)}`, `${eventLabel(event)}<br>${eventMetricLabel(event)}`],
      name: `SCA ${index + 1}`,
      type: "scatter",
      mode: "lines+markers",
      line: { color: event.is_assist ? "#22c55e" : "#f59e0b", width: isCurrentStep ? 6 : event.is_assist ? 5 : 4, dash: event.is_assist ? "solid" : "dot" },
      marker: { color: event.is_assist ? "#22c55e" : "#f59e0b", size: isCurrentStep ? [11, 16] : event.is_assist ? [9, 13] : [8, 11], symbol: ["circle", "triangle-up"] },
      opacity: animateSequence && !isCurrentStep ? 0.52 : 1,
      hovertemplate: "%{text}<extra></extra>",
      showlegend: false,
      };
    }),
    {
      x: attackingShots.map((row) => flipPitchY(shotDisplayY(row))),
      y: attackingShots.map((row) => shotDisplayX(row)),
      customdata: customData,
      text: labels,
      hovertext: hoverText,
      textposition: "top center",
      name: team,
      type: "scatter",
      mode: "markers+text",
      marker: {
        symbol: attackingShots.map(shotSymbol),
        size: markerSizes,
        color: attackingShots.map((row) => shotFill(row, teamColor)),
        line: {
          color: attackingShots.map((row) => shotLine(row, teamColor, themeColors.mode)),
          width: markerLineWidth,
        },
        opacity: markerOpacity,
      },
      textfont: { color: themeColors.text, size: 10, family: CHART_FONT_FAMILY },
      hovertemplate: "%{hovertext}<extra></extra>",
      showlegend: false,
    },
  ];

  const pitchShapes = [
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

  const goalFront = { left: 4, right: 64, bottom: 0, top: 31 };
  const goalBack = { left: 8.5, right: 59.5, bottom: 4, top: 28.5 };
  const netLine = colorWithAlpha(themeColors.muted, themeColors.mode === "dark" ? 0.3 : 0.42);
  const backNetLine = colorWithAlpha(themeColors.muted, themeColors.mode === "dark" ? 0.18 : 0.26);
  const netPlaneLine = colorWithAlpha(themeColors.muted, themeColors.mode === "dark" ? 0.1 : 0.16);
  const netPlaneFill = colorWithAlpha(themeColors.muted, themeColors.mode === "dark" ? 0.06 : 0.09);
  const goalPostWidth = 4;
  const groundWidth = 1.5;
  const goalShapes = [
    { type: "line", x0: 0, y0: 0, x1: 68, y1: 0, line: { color: themeColors.muted, width: groundWidth } },
    {
      type: "path",
      path: `M ${goalFront.left} ${goalFront.bottom} L ${goalBack.left} ${goalBack.bottom} L ${goalBack.right} ${goalBack.bottom} L ${goalFront.right} ${goalFront.bottom} Z`,
      line: { color: netPlaneLine, width: 1 },
      fillcolor: netPlaneFill,
    },
    {
      type: "path",
      path: `M ${goalFront.left} ${goalFront.top} L ${goalBack.left} ${goalBack.top} L ${goalBack.right} ${goalBack.top} L ${goalFront.right} ${goalFront.top} Z`,
      line: { color: netPlaneLine, width: 1 },
      fillcolor: colorWithAlpha(themeColors.muted, themeColors.mode === "dark" ? 0.04 : 0.07),
    },
    { type: "rect", x0: goalBack.left, y0: goalBack.bottom, x1: goalBack.right, y1: goalBack.top, line: { color: backNetLine, width: 1.5 } },
    ...Array.from({ length: 7 }).map((_, index) => ({
      type: "line",
      x0: goalBack.left + index * ((goalBack.right - goalBack.left) / 6),
      y0: goalBack.bottom,
      x1: goalBack.left + index * ((goalBack.right - goalBack.left) / 6),
      y1: goalBack.top,
      line: { color: backNetLine, width: 1 },
    })),
    ...Array.from({ length: 7 }).map((_, index) => ({
      type: "line",
      x0: goalBack.left,
      y0: goalBack.bottom + index * ((goalBack.top - goalBack.bottom) / 6),
      x1: goalBack.right,
      y1: goalBack.bottom + index * ((goalBack.top - goalBack.bottom) / 6),
      line: { color: backNetLine, width: 1 },
    })),
    { type: "line", x0: goalFront.left, y0: goalFront.bottom, x1: goalBack.left, y1: goalBack.bottom, line: { color: netLine, width: 1.5 } },
    { type: "line", x0: goalFront.right, y0: goalFront.bottom, x1: goalBack.right, y1: goalBack.bottom, line: { color: netLine, width: 1.5 } },
    { type: "line", x0: goalFront.left, y0: goalFront.top, x1: goalBack.left, y1: goalBack.top, line: { color: netLine, width: 1.5 } },
    { type: "line", x0: goalFront.right, y0: goalFront.top, x1: goalBack.right, y1: goalBack.top, line: { color: netLine, width: 1.5 } },
    ...Array.from({ length: 7 }).map((_, index) => ({
      type: "line",
      x0: goalFront.left + index * ((goalFront.right - goalFront.left) / 6),
      y0: goalFront.bottom,
      x1: goalBack.left + index * ((goalBack.right - goalBack.left) / 6),
      y1: goalBack.bottom,
      line: { color: backNetLine, width: 1 },
    })),
    ...Array.from({ length: 7 }).map((_, index) => ({
      type: "line",
      x0: goalFront.left + index * ((goalFront.right - goalFront.left) / 6),
      y0: goalFront.top,
      x1: goalBack.left + index * ((goalBack.right - goalBack.left) / 6),
      y1: goalBack.top,
      line: { color: backNetLine, width: 1 },
    })),
    ...Array.from({ length: 7 }).map((_, index) => ({
      type: "line",
      x0: goalFront.left + index * ((goalFront.right - goalFront.left) / 6),
      y0: goalFront.bottom,
      x1: goalFront.left + index * ((goalFront.right - goalFront.left) / 6),
      y1: goalFront.top,
      line: { color: netLine, width: 1 },
    })),
    ...Array.from({ length: 5 }).map((_, index) => ({
      type: "line",
      x0: goalFront.left,
      y0: goalFront.bottom + (index + 1) * ((goalFront.top - goalFront.bottom) / 6),
      x1: goalFront.right,
      y1: goalFront.bottom + (index + 1) * ((goalFront.top - goalFront.bottom) / 6),
      line: { color: netLine, width: 1 },
    })),
    { type: "line", x0: goalFront.left, y0: goalFront.bottom, x1: goalFront.left, y1: goalFront.top, line: { color: themeColors.text, width: goalPostWidth } },
    { type: "line", x0: goalFront.right, y0: goalFront.bottom, x1: goalFront.right, y1: goalFront.top, line: { color: themeColors.text, width: goalPostWidth } },
    { type: "line", x0: goalFront.left, y0: goalFront.top, x1: goalFront.right, y1: goalFront.top, line: { color: themeColors.text, width: goalPostWidth } },
    { type: "line", x0: goalFront.left, y0: goalFront.bottom, x1: goalFront.right, y1: goalFront.bottom, line: { color: themeColors.muted, width: groundWidth } },
  ];

  return (
    <div className={`shots-sca-layout is-${orientation}`}>
      <div className={`plotly-chart-shell shots-plotly-shell is-${orientation}`}>
        <div className="shot-click-chart shot-click-chart-goal">
          <Plot
            data={goalChartData}
            layout={{
              autosize: true,
              height: 290,
              margin: { l: 24, r: 24, t: 8, b: 18 },
              paper_bgcolor: "rgba(0,0,0,0)",
              plot_bgcolor: themeColors.surface,
              font: { color: themeColors.text, family: CHART_FONT_FAMILY },
              showlegend: false,
              xaxis: { range: [0, 68], visible: false, fixedrange: true, constrain: "domain" },
              yaxis: { range: [-2, 34], visible: false, fixedrange: true, constrain: "domain" },
              shapes: goalShapes,
            }}
            config={plotConfig}
            className="plotly-chart shots-goalmap-chart"
            onClick={(event: PlotlyClickEvent) => {
              const index = plotlyPointIndex(event);
              if (index !== null) selectShot(index);
            }}
          />
          <div className="shot-click-layer" aria-label="On-goal shot selection">
            {onGoalShots.map((row, localIndex) => {
              const shotIndex = onGoalIndices[localIndex];
              const x = goalMapX(row.goal_mouth_y);
              const y = num(row.goal_mouth_z);
              return (
                <button
                  key={`goal-button-${shotIndex}`}
                  type="button"
                  className={`shot-click-button${selectedIndex === shotIndex ? " is-selected" : ""}`}
                  style={{
                    left: `${pct(x, 0, 68)}%`,
                    top: `${(100 - pct(y, -2, 34)).toFixed(4)}%`,
                  }}
                  aria-pressed={selectedIndex === shotIndex}
                  aria-label={`Select shot ${row.shotNumber}`}
                  onClick={() => selectShot(shotIndex)}
                />
              );
            })}
          </div>
        </div>

        <div className="shot-click-chart shot-click-chart-pitch">
          <Plot
            data={pitchChartData}
            layout={{
              autosize: true,
              height: 560,
              margin: { l: 18, r: 18, t: 8, b: 18 },
              paper_bgcolor: "rgba(0,0,0,0)",
              plot_bgcolor: themeColors.surface,
              font: { color: themeColors.text, family: CHART_FONT_FAMILY },
              showlegend: false,
              xaxis: { range: [0, 68], visible: false, fixedrange: true, constrain: "domain" },
              yaxis: { range: [58, 105.8], visible: false, fixedrange: true, scaleanchor: "x", scaleratio: 1, constrain: "domain" },
              shapes: pitchShapes,
            }}
            config={plotConfig}
            className="plotly-chart shots-plotly-chart"
            onClick={(event: PlotlyClickEvent) => {
              const index = plotlyPointIndex(event);
              if (index !== null) selectShot(index);
            }}
          />
          <div className="shot-click-layer" aria-label="Pitch shot selection">
            {attackingShots.map((row, shotIndex) => {
              const x = flipPitchY(shotDisplayY(row));
              const y = shotDisplayX(row);
              return (
                <button
                  key={`pitch-button-${shotIndex}`}
                  type="button"
                  className={`shot-click-button${selectedIndex === shotIndex ? " is-selected" : ""}`}
                  style={{
                    left: `${pct(x, 0, 68)}%`,
                    top: `${(100 - pct(y, 58, 105.8)).toFixed(4)}%`,
                  }}
                  aria-pressed={selectedIndex === shotIndex}
                  aria-label={`Select shot ${row.shotNumber}`}
                  onClick={() => selectShot(shotIndex)}
                />
              );
            })}
          </div>
        </div>

        <div className="embedded-shot-legend">
          {[
            ["goal", "Goal"],
            ["own-goal", "Own goal"],
            ["on-target", "On target"],
            ["off-target", "Off target"],
            ["woodwork", "Woodwork"],
            ["blocked", "Blocked"],
          ].map(([className, label]) => (
            <span key={label}>
              <i className={`embedded-shot-legend-dot ${className}`} style={{ "--shot-color": teamColor } as CSSProperties} />
              {label}
            </span>
          ))}
        </div>
      </div>

      <aside
        className="shot-detail-panel"
        data-player={selectedShot ? String(selectedShot.player ?? "").replace(/\s*\(OG\)$/, "") : undefined}
        data-team={selectedShot ? String(selectedShot.shooting_team ?? team) : undefined}
      >
        <span className="eyebrow">{selectedShot ? "Selected Shot" : "Shot Details"}</span>
        {selectedShot ? (
          <>
            <div className="shot-detail-panel-title">
              <strong>#{selectedIndex === null ? 1 : selectedIndex + 1}</strong>
              <PlayerAvatar
                name={String(selectedShot.player ?? "").replace(/\s*\(OG\)$/, "")}
                team={String(selectedShot.shooting_team ?? team)}
                size={46}
              />
              <h3>{String(selectedShot.player ?? "Unknown player")}</h3>
            </div>
            <div className="shot-sequence-controls">
              <label className="shot-sequence-toggle">
                <input
                  type="checkbox"
                  checked={animateSequence}
                  onChange={(event) => setAnimateSequence(event.target.checked)}
                />
                <span>Animate SCA sequence</span>
              </label>
              {animateSequence && (
                <>
                  <label>
                    <span>Shot</span>
                    <select
                      className="select"
                      value={selectedIndex ?? 0}
                      onChange={(event) => setSelectedIndex(Number(event.target.value))}
                    >
                      {attackingShots.map((shot, index) => (
                        <option key={`${String(shot.player)}-${String(shot.minute)}-${index}`} value={index}>
                          #{shot.shotNumber} · {String(shot.player ?? "Unknown")} · {num(shot.minute)}'
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="shot-sequence-buttons">
                    <button type="button" className="ghost-button" onClick={() => advanceStep(-1)} disabled={sequenceStep <= 0}>Prev</button>
                    <button
                      type="button"
                      className="button"
                      onClick={() => {
                        if (sequenceStep >= sequenceFinalStep) setSequenceStep(0);
                        setIsPlaying((current) => !current);
                      }}
                    >
                      {isPlaying ? "Pause" : sequenceStep >= sequenceFinalStep ? "Replay" : "Play"}
                    </button>
                    <button type="button" className="ghost-button" onClick={() => advanceStep(1)} disabled={sequenceStep >= sequenceFinalStep}>Next</button>
                    <button type="button" className="ghost-button" onClick={() => { setSequenceStep(0); setIsPlaying(false); }}>Reset</button>
                  </div>
                  <label>
                    <span>Time window</span>
                    <input
                      type="range"
                      min="400"
                      max="1800"
                      step="100"
                      value={stepWindowMs}
                      onChange={(event) => setStepWindowMs(Number(event.target.value))}
                    />
                    <small>{(stepWindowMs / 1000).toFixed(1)}s per action · step {sequenceStep}/{sequenceFinalStep}</small>
                  </label>
                </>
              )}
            </div>
            <div className="shot-detail-grid">
              <span>Minute</span><strong>{num(selectedShot.minute)}&apos;</strong>
              <span>xG</span><strong>{num(selectedShot.xg).toFixed(2)}</strong>
              <span>xGOT</span><strong>{num(selectedShot.xgot ?? selectedShot.xGOT).toFixed(2)}</strong>
              <span>Result</span><strong>{shotOutcome(selectedShot)}</strong>
              <span>Situation</span><strong>{String(selectedShot.situation ?? "N/A")}</strong>
              <span>Body Part</span><strong>{String(selectedShot.body_part ?? "N/A")}</strong>
              <span>Game State</span><strong>{String(selectedShot.game_state_label ?? "Level")} ({String(selectedShot.score_before ?? "0-0")})</strong>
            </div>
            <div className="shot-sca-list">
              <strong>Shot-creating actions</strong>
              {selectedLeadup.length ? selectedLeadup.map((event, index) => (
                <div
                  key={`${eventLabel(event)}-${index}`}
                  className={`shot-sca-event${event.is_assist ? " is-assist" : ""}${animateSequence && sequenceStep === index + 1 ? " is-current" : ""}${animateSequence && sequenceStep < index + 1 ? " is-pending" : ""}`}
                >
                  <span>{event.is_assist ? "Assist" : `SCA ${index + 1}`}</span>
                  <div className="shot-sca-event-body">
                    <PlayerAvatar
                      name={String(event.player ?? "").trim()}
                      team={String(selectedShot.shooting_team ?? team)}
                      size={28}
                    />
                    <p>{eventLabel(event)}</p>
                  </div>
                  <small>{eventMetricLabel(event)}</small>
                </div>
              )) : <p className="muted">No lead-up events found in the current payload.</p>}
              {animateSequence && selectedLeadup.length > 0 && (
                <div className={`shot-sca-event is-shot-end${sequenceStep >= sequenceFinalStep ? " is-current" : " is-pending"}`}>
                  <span>Shot</span>
                  <p>{String(selectedShot.player ?? "Unknown")} · {shotOutcome(selectedShot)}</p>
                  <small>xG {num(selectedShot.xg).toFixed(2)} · xGOT {num(selectedShot.xgot ?? selectedShot.xGOT).toFixed(2)}</small>
                </div>
              )}
            </div>
          </>
        ) : (
          <p className="muted">Select a numbered shot marker to inspect the shot and its successful same-sequence lead-up actions.</p>
        )}
      </aside>
    </div>
  );
}
