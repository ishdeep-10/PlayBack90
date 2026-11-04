"use client";

import { useEffect, useState } from "react";

import { getPlayerActions, type ActionPoint, type SeasonZones } from "../../lib/api";
import { CHART_FONT_FAMILY, type ThemeColors } from "../../lib/theme";

export const PITCH_W = 105;
export const PITCH_H = 68;
export const BANDS = 6;
export const LANES = 5;
export type ZoneValue = "share" | "perMatch" | "vsLeague";

function pitchShapes(line: string) {
  const l = { color: line, width: 1.4 };
  const rect = (x0: number, y0: number, x1: number, y1: number) => ({ type: "rect", x0, y0, x1, y1, line: l, fillcolor: "rgba(0,0,0,0)", layer: "above" });
  return [
    rect(0, 0, PITCH_W, PITCH_H),
    { type: "line", x0: PITCH_W / 2, x1: PITCH_W / 2, y0: 0, y1: PITCH_H, line: l, layer: "above" },
    { type: "circle", x0: PITCH_W / 2 - 9.15, x1: PITCH_W / 2 + 9.15, y0: PITCH_H / 2 - 9.15, y1: PITCH_H / 2 + 9.15, line: l, layer: "above" },
    rect(0, 13.84, 16.5, 54.16),
    rect(PITCH_W - 16.5, 13.84, PITCH_W, 54.16),
    rect(0, 24.84, 5.5, 43.16),
    rect(PITCH_W - 5.5, 24.84, PITCH_W, 43.16),
  ];
}

const hexToRgb = (hex: string) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
export const mix = (a: string, b: string, t: number) => {
  const [r1, g1, b1] = hexToRgb(a);
  const [r2, g2, b2] = hexToRgb(b);
  return `rgb(${Math.round(r1 + (r2 - r1) * t)},${Math.round(g1 + (g2 - g1) * t)},${Math.round(b1 + (b2 - b1) * t)})`;
};

export type ZoneCells = { shown: number[]; own: number[]; league: number[]; total: number; matches: number };

/** Per-cell values for one team (or the league average when `team` is null) on the chosen basis. */
export function zoneCells(zones: SeasonZones, team: string | null, action: string, value: ZoneValue): ZoneCells | null {
  const counts = (t: SeasonZones["teams"][number]) => (Array.isArray(t[action]) ? (t[action] as number[]) : new Array(BANDS * LANES).fill(0));
  const basis = (t: SeasonZones["teams"][number], mode: "share" | "perMatch") => {
    const c = counts(t);
    const total = c.reduce((a, b) => a + b, 0) || 1;
    return c.map((v) => (mode === "share" ? (v / total) * 100 : v / Math.max(t.matches, 1)));
  };
  const mode = value === "perMatch" ? "perMatch" : "share";
  const league = new Array(BANDS * LANES).fill(0).map((_, i) => zones.teams.reduce((s, t) => s + basis(t, mode)[i], 0) / zones.teams.length);
  let own: number[];
  let total: number;
  let matches: number;
  if (team === null) {
    own = league;
    total = zones.teams.reduce((s, t) => s + counts(t).reduce((a, b) => a + b, 0), 0) / zones.teams.length;
    matches = zones.teams.reduce((s, t) => s + t.matches, 0) / zones.teams.length;
  } else {
    const row = zones.teams.find((t) => t.team === team);
    if (!row) return null;
    own = basis(row, mode);
    total = counts(row).reduce((a, b) => a + b, 0);
    matches = row.matches;
  }
  return { shown: value === "vsLeague" ? own.map((v, i) => v - league[i]) : own, own, league, total, matches };
}

/** Plotly figure for one pitch heatmap on the 6 x 5 grid. `scaleMax` lets two pitches share one colour scale. */
export function zoneFigure(opts: {
  zones: SeasonZones;
  cells: ZoneCells;
  value: ZoneValue;
  themeColors: ThemeColors;
  width: number;
  compact: boolean;
  title: string;
  scaleMax?: number;
}) {
  const { zones, cells, value, themeColors, width, compact, title, scaleMax } = opts;
  const { x: gx, y: gy } = zones.grid;
  const fg = themeColors.mode === "dark" ? "#0b1623" : "#ffffff";
  const lo = themeColors.mode === "dark" ? "#10304a" : "#e6f4d7";
  const hi = "#a3e635";
  const diffMax = Math.max(0.01, scaleMax ?? 0, ...cells.shown.map((v) => Math.abs(v)));
  const max = Math.max(0.01, scaleMax ?? 0, ...cells.shown);
  const fmt = (v: number) => (value === "vsLeague" ? `${v > 0 ? "+" : ""}${v.toFixed(1)}%` : value === "perMatch" ? v.toFixed(1) : `${v.toFixed(0)}%`);
  const shapes: unknown[] = [];
  const annotations: unknown[] = [];
  const cx: number[] = [];
  const cy: number[] = [];
  const hover: string[] = [];
  for (let lane = 0; lane < LANES; lane++) {
    for (let band = 0; band < BANDS; band++) {
      const i = lane * BANDS + band;
      const v = cells.shown[i];
      const fill = value === "vsLeague" ? (v >= 0 ? mix(fg, "#34d399", Math.min(1, v / diffMax)) : mix(fg, "#f87171", Math.min(1, -v / diffMax))) : mix(lo, hi, v / max);
      shapes.push({ type: "rect", x0: gx[band], x1: gx[band + 1], y0: gy[lane], y1: gy[lane + 1], fillcolor: fill, line: { color: themeColors.pitchLine, width: 1 }, layer: "below" });
      const light = value === "vsLeague" ? Math.abs(v) / diffMax > 0.55 : v / max > 0.55;
      annotations.push({ x: (gx[band] + gx[band + 1]) / 2, y: (gy[lane] + gy[lane + 1]) / 2, text: fmt(v), showarrow: false, font: { family: CHART_FONT_FAMILY, size: compact ? 9 : 12, color: light ? "#0b1623" : themeColors.text } });
      cx.push((gx[band] + gx[band + 1]) / 2);
      cy.push((gy[lane] + gy[lane + 1]) / 2);
      hover.push(`<b>${title}</b><br>${cells.own[i].toFixed(1)}${value === "perMatch" ? " per match" : "% of its total"}<br>League average: ${cells.league[i].toFixed(1)}${value === "perMatch" ? " per match" : "%"}`);
    }
  }
  const height = Math.round((width - 20) * (PITCH_H / PITCH_W)) + 70;
  return {
    data: [{ type: "scatter", mode: "markers", x: cx, y: cy, marker: { size: 40, color: "rgba(0,0,0,0)" }, hovertext: hover, hoverinfo: "text", hoverlabel: { bgcolor: themeColors.hoverBg, font: { color: themeColors.hoverText, family: CHART_FONT_FAMILY } } }],
    layout: {
      width, height, margin: { l: 10, r: 10, t: 10, b: 52 }, paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)", showlegend: false,
      xaxis: { range: [-1, PITCH_W + 1], visible: false, fixedrange: true, constrain: "domain" },
      yaxis: { range: [-1, PITCH_H + 1], visible: false, fixedrange: true, scaleanchor: "x", scaleratio: 1 },
      shapes: [...shapes, ...pitchShapes(themeColors.text)],
      annotations: [...annotations, { x: PITCH_W / 2, y: -3, xref: "x", yref: "y", text: "Direction of play →", showarrow: false, yshift: -14, font: { family: CHART_FONT_FAMILY, size: 12, color: themeColors.muted } }],
    },
    height,
  };
}

// ── one player's actions on a pitch (SVG) ───────────────────────────────────────────────────────

const actionCache = new Map<string, Promise<Record<string, ActionPoint[]>>>();

export function loadPlayerActions(league: string, season: string, playerId: number) {
  const key = `${league}/${season}/${playerId}`;
  if (!actionCache.has(key)) {
    actionCache.set(
      key,
      getPlayerActions(league, season, playerId)
        .then((r) => r.actions)
        .catch((e) => {
          actionCache.delete(key);
          throw e;
        }),
    );
  }
  return actionCache.get(key)!;
}

export function usePlayerActions(league: string, season: string, playerId: number | null) {
  const [actions, setActions] = useState<Record<string, ActionPoint[]> | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    if (playerId === null) {
      setActions(null);
      return;
    }
    let live = true;
    setActions(null);
    setError(false);
    const key = `${league}/${season}/${playerId}`;
    if (!actionCache.has(key)) {
      actionCache.set(
        key,
        getPlayerActions(league, season, playerId)
          .then((r) => r.actions)
          .catch((e) => {
            actionCache.delete(key);
            throw e;
          }),
      );
    }
    actionCache.get(key)!.then((a) => live && setActions(a)).catch(() => live && setError(true));
    return () => {
      live = false;
    };
  }, [league, season, playerId]);
  return { actions, error };
}

/** Shot kinds: colour and shape; the size of the mark follows the shot's xG. */
export const SHOT_STYLE: Record<string, { label: string; color: string; symbol: string; filled: boolean }> = {
  G: { label: "Goal", color: "#fbbf24", symbol: "star", filled: true },
  S: { label: "Saved", color: "#a3e635", symbol: "circle", filled: true },
  M: { label: "Off target", color: "#f87171", symbol: "circle-open", filled: false },
  P: { label: "Post", color: "#fb923c", symbol: "diamond", filled: true },
  B: { label: "Blocked", color: "#94a3b8", symbol: "square", filled: true },
};
export const shotRadius = (xg = 0.05) => 0.9 + 4.2 * Math.sqrt(Math.min(Math.max(xg, 0), 0.9)); // pitch units: 0.05 xG -> 1.8, 0.8 xG -> 4.7
export const hasEnd = (e: ActionPoint) => e[2] != null && e[3] != null;

function starPoints(cx: number, cy: number, r: number) {
  return Array.from({ length: 10 }, (_, i) => {
    const a = (Math.PI / 5) * i - Math.PI / 2;
    const rr = i % 2 === 0 ? r : r * 0.45;
    return `${(cx + rr * Math.cos(a)).toFixed(2)},${(cy + rr * Math.sin(a)).toFixed(2)}`;
  }).join(" ");
}

export function PlayerActionsMap({ events: all, title, subtitle, phase = null }: { events: ActionPoint[]; title: string; subtitle?: string; phase?: 0 | 1 | null }) {
  // phase: keep only open-play (0) or set-piece (1) events; null keeps both
  const events = phase === null ? all : all.filter((e) => (e[4] ?? 0) === phase);
  const isShots = events.some((e) => typeof e[5] === "string");
  const kindsPresent = [...new Set(events.map((e) => e[5]).filter((k): k is string => typeof k === "string"))];
  // Pitch y runs up in the data; SVG y runs down.
  const sy = (y: number) => PITCH_H - y;
  return (
    <figure className="season-pitch-map">
      <figcaption>
        <strong>{title}</strong>
        {subtitle ? <span className="muted"> · {subtitle}</span> : null}
      </figcaption>
      <svg viewBox={`-2 -2 ${PITCH_W + 4} ${PITCH_H + 4}`} role="img" aria-label={`${title}: ${events.length} actions`}>
        <defs>
          <marker id="season-arrow" viewBox="0 0 6 6" refX="5" refY="3" markerWidth="4" markerHeight="4" orient="auto-start-reverse">
            <path d="M0,0 L6,3 L0,6 z" fill="var(--accent)" />
          </marker>
        </defs>
        <rect x="0" y="0" width={PITCH_W} height={PITCH_H} className="pitch-fill" />
        <g className="pitch-lines" fill="none">
          <rect x="0" y="0" width={PITCH_W} height={PITCH_H} />
          <line x1={PITCH_W / 2} y1="0" x2={PITCH_W / 2} y2={PITCH_H} />
          <circle cx={PITCH_W / 2} cy={PITCH_H / 2} r="9.15" />
          <rect x="0" y={PITCH_H - 54.16} width="16.5" height="40.32" />
          <rect x={PITCH_W - 16.5} y={PITCH_H - 54.16} width="16.5" height="40.32" />
          <rect x="0" y={PITCH_H - 43.16} width="5.5" height="18.32" />
          <rect x={PITCH_W - 5.5} y={PITCH_H - 43.16} width="5.5" height="18.32" />
        </g>
        {events.map((e, i) => {
          if (typeof e[5] === "string") {
            // shot: shape = what happened to it, size = xG (largest drawn first so small ones stay visible)
            const st = SHOT_STYLE[e[5]] ?? SHOT_STYLE.S;
            const r = shotRadius(e[6]);
            const cx = e[0];
            const cy = sy(e[1]);
            const common = { fill: st.filled ? st.color : "none", stroke: st.filled ? "rgba(0,0,0,0.45)" : st.color, strokeWidth: st.filled ? 0.25 : 0.5, fillOpacity: 0.85 };
            return st.symbol === "star" ? <polygon key={i} {...common} points={starPoints(cx, cy, r * 1.25)} />
              : st.symbol === "diamond" ? <polygon key={i} {...common} points={`${cx},${cy - r} ${cx + r},${cy} ${cx},${cy + r} ${cx - r},${cy}`} />
              : st.symbol === "square" ? <rect key={i} {...common} x={cx - r * 0.85} y={cy - r * 0.85} width={r * 1.7} height={r * 1.7} />
              : <circle key={i} {...common} cx={cx} cy={cy} r={r} />;
          }
          return hasEnd(e) ? (
            <line key={i} x1={e[0]} y1={sy(e[1])} x2={e[2] as number} y2={sy(e[3] as number)} className="pitch-action-line" markerEnd="url(#season-arrow)" />
          ) : (
            <circle key={i} cx={e[0]} cy={sy(e[1])} r="1.1" className="pitch-action-dot" />
          );
        })}
      </svg>
      {isShots ? (
        <p className="muted season-pitch-foot season-shot-legend">
          {kindsPresent.map((k) => (
            <span key={k}><i style={{ background: SHOT_STYLE[k]?.filled ? SHOT_STYLE[k]?.color : "transparent", borderColor: SHOT_STYLE[k]?.color }} />{SHOT_STYLE[k]?.label}</span>
          ))}
          <span>size = xG</span>
        </p>
      ) : null}
      <p className="muted season-pitch-foot">Attacking left to right · {events.length} actions{all.length >= 300 ? " (latest 300)" : ""}{phase === 0 ? " · open play" : phase === 1 ? " · set pieces" : ""}</p>
    </figure>
  );
}
