import { CHART_FONT_FAMILY } from "../../lib/theme";
import type { ShareMatchInfo } from "../ShareExportContext";
import { drawExportHeader, drawFooter, ensureExportFonts, EXPORT_BG, EXPORT_MUTED, loadHeaderImages } from "../exportFrame";
import { drawRadar } from "./radarExport";
import { niceTicks } from "./scatterExport";

// The match-page "season context" charts, redrawn in the shared export look. One image holds one or two chart panels
// side by side under the usual header (with the club crests and score on match pages).

type Series = { name: string; color: string };

export type BarsPanel = {
  kind: "bars";
  heading?: string;
  series: Series[];
  /** pcts are percent vs the season level (-100..100), null where there is no value */
  rows: { label: string; pcts: (number | null)[]; texts?: string[] }[];
  xTitle: string;
};
export type RadarPanel = {
  kind: "radar";
  heading?: string;
  axes: string[];
  series: (Series & { values: number[] })[];
};
export type LinesPanel = {
  kind: "lines";
  heading?: string;
  series: (Series & { values: number[] })[];
  xTitle: string;
  yTitle: string;
  /** the last point of every line is drawn as a diamond (tonight) */
  lastIsTonight?: boolean;
};
export type MapPanel = {
  kind: "map";
  heading?: string;
  /** faded dots for past matches and diamonds for tonight, per team */
  series: (Series & { past: [number, number][]; tonight: [number, number] })[];
  xTitle: string;
  yTitle: string;
  max: number;
  corners: [string, string];
};
export type ContextPanel = BarsPanel | RadarPanel | LinesPanel | MapPanel;

export type ContextExport = {
  title: string;
  subtitle: string;
  leagueLogo?: string;
  match?: ShareMatchInfo | null;
  panels: ContextPanel[];
  /** explanation lines under the charts */
  captions: string[];
};

type Region = { x: number; y: number; w: number; h: number };

const W = 2000;
const HEADER_H = 215;
const GOOD_LINE = "rgba(148,163,184,0.55)";

const naturalHeight = (panel: ContextPanel, w: number) => {
  if (panel.kind === "bars") return 130 + panel.rows.length * (panel.series.length * 31 + 28) + 90;
  if (panel.kind === "radar") return Math.min(1100, w + 60);
  return Math.round(w * 0.5) + 150;
};

function drawShape(ctx: CanvasRenderingContext2D, shape: "circle" | "diamond", x: number, y: number, r: number) {
  ctx.beginPath();
  if (shape === "diamond") {
    ctx.moveTo(x, y - r * 1.25);
    ctx.lineTo(x + r * 1.25, y);
    ctx.lineTo(x, y + r * 1.25);
    ctx.lineTo(x - r * 1.25, y);
    ctx.closePath();
  } else {
    ctx.arc(x, y, r, 0, Math.PI * 2);
  }
  ctx.fill();
}

function legend(ctx: CanvasRenderingContext2D, x: number, y: number, items: { label: string; color: string; shape?: "circle" | "diamond" }[]) {
  ctx.font = `600 24px ${CHART_FONT_FAMILY}`;
  ctx.textAlign = "left";
  let lx = x;
  for (const item of items) {
    ctx.fillStyle = item.color;
    drawShape(ctx, item.shape ?? "circle", lx + 9, y - 8, item.shape === "diamond" ? 8 : 9);
    ctx.fillStyle = "#ffffff";
    ctx.fillText(item.label, lx + 28, y);
    lx += 28 + ctx.measureText(item.label).width + 34;
  }
}

function heading(ctx: CanvasRenderingContext2D, r: Region, text?: string) {
  if (!text) return 0;
  ctx.textAlign = "left";
  ctx.fillStyle = "#ffffff";
  ctx.font = `700 32px ${CHART_FONT_FAMILY}`;
  ctx.fillText(text, r.x, r.y + 30);
  return 52;
}

function drawBars(ctx: CanvasRenderingContext2D, r: Region, p: BarsPanel) {
  const top = r.y + heading(ctx, r, p.heading);
  legend(ctx, r.x, top + 28, p.series.map((s) => ({ label: s.name, color: s.color })));
  const plotTop = top + 56;
  const labelW = Math.min(400, r.w * 0.3);
  const left = r.x + labelW;
  const right = r.x + r.w - 70;
  const lo = -118;
  const hi = 118;
  const sx = (v: number) => left + ((v - lo) / (hi - lo)) * (right - left);
  const rowH = p.series.length * 31 + 28;
  const bottom = plotTop + p.rows.length * rowH;

  ctx.font = `500 21px ${CHART_FONT_FAMILY}`;
  ctx.textAlign = "center";
  [-100, -50, 0, 50, 100].forEach((v) => {
    ctx.strokeStyle = v === 0 ? GOOD_LINE : "rgba(148,163,184,0.14)";
    ctx.lineWidth = v === 0 ? 2 : 1.5;
    ctx.setLineDash(v === 0 ? [3, 7] : []);
    ctx.beginPath();
    ctx.moveTo(sx(v), plotTop - 8);
    ctx.lineTo(sx(v), bottom);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = EXPORT_MUTED;
    ctx.fillText(v === 0 ? "season" : `${v > 0 ? "+" : "−"}${Math.abs(v)}%`, sx(v), bottom + 32);
  });
  ctx.fillStyle = "#e2e8f0";
  ctx.font = `500 26px ${CHART_FONT_FAMILY}`;
  ctx.fillText(p.xTitle, (left + right) / 2, bottom + 76);

  p.rows.forEach((row, i) => {
    const rowTop = plotTop + i * rowH;
    if (i % 2 === 0) {
      ctx.fillStyle = "rgba(148,163,184,0.06)";
      ctx.fillRect(r.x, rowTop, r.w, rowH);
    }
    ctx.textAlign = "left";
    ctx.fillStyle = "#ffffff";
    ctx.font = `600 24px ${CHART_FONT_FAMILY}`;
    let label = row.label;
    while (label.length > 1 && ctx.measureText(label).width > labelW - 16) label = label.slice(0, -1);
    ctx.fillText(label === row.label ? label : `${label.trimEnd()}…`, r.x + 8, rowTop + rowH / 2 + 8);
    row.pcts.forEach((pct, si) => {
      if (pct === null) return;
      const y = rowTop + 14 + si * 31;
      const x0 = sx(0);
      const x1 = sx(pct);
      ctx.fillStyle = p.series[si].color;
      ctx.fillRect(Math.min(x0, x1), y, Math.max(Math.abs(x1 - x0), 3), 25);
      const text = row.texts?.[si];
      if (text) {
        ctx.font = `700 21px ${CHART_FONT_FAMILY}`;
        ctx.textAlign = pct >= 0 ? "left" : "right";
        ctx.fillText(text, pct >= 0 ? x1 + 10 : x1 - 10, y + 20);
      }
    });
  });
}

function drawRadarPanel(ctx: CanvasRenderingContext2D, r: Region, p: RadarPanel) {
  const top = r.y + heading(ctx, r, p.heading);
  legend(ctx, r.x, top + 28, p.series.map((s) => ({ label: s.name, color: s.color })));
  const cy = top + 56 + (r.y + r.h - top - 56) / 2;
  const radius = Math.min((r.w - 2 * Math.min(260, r.w * 0.26)) / 2, (r.y + r.h - top - 56) / 2 - 56);
  drawRadar(ctx, { cx: r.x + r.w / 2, cy, radius, labelMax: Math.min(260, r.w * 0.26), fontSize: 22 }, p.axes, p.series);
}

function drawAxes(ctx: CanvasRenderingContext2D, r: Region, plot: { l: number; t: number; rgt: number; b: number }, xr: [number, number], yr: [number, number], xTitle: string, yTitle: string, xTicks: number[] | null) {
  const sx = (v: number) => plot.l + ((v - xr[0]) / (xr[1] - xr[0])) * (plot.rgt - plot.l);
  const sy = (v: number) => plot.b - ((v - yr[0]) / (yr[1] - yr[0])) * (plot.b - plot.t);
  const yt = niceTicks(yr[0], yr[1], 6);
  ctx.font = `500 21px ${CHART_FONT_FAMILY}`;
  ctx.textAlign = "right";
  for (const v of yt.ticks) {
    ctx.strokeStyle = "rgba(148,163,184,0.16)";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(plot.l, sy(v));
    ctx.lineTo(plot.rgt, sy(v));
    ctx.stroke();
    ctx.fillStyle = EXPORT_MUTED;
    ctx.fillText(v.toFixed(yt.decimals), plot.l - 14, sy(v) + 7);
  }
  const xt = xTicks ? { ticks: xTicks, decimals: 0 } : niceTicks(xr[0], xr[1], 7);
  ctx.textAlign = "center";
  for (const v of xt.ticks) {
    ctx.strokeStyle = "rgba(148,163,184,0.1)";
    ctx.beginPath();
    ctx.moveTo(sx(v), plot.t);
    ctx.lineTo(sx(v), plot.b);
    ctx.stroke();
    ctx.fillStyle = EXPORT_MUTED;
    ctx.fillText(v.toFixed(xt.decimals), sx(v), plot.b + 34);
  }
  ctx.strokeStyle = "rgba(180,194,211,0.55)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(plot.l, plot.t);
  ctx.lineTo(plot.l, plot.b);
  ctx.lineTo(plot.rgt, plot.b);
  ctx.stroke();
  ctx.fillStyle = "#e2e8f0";
  ctx.font = `500 26px ${CHART_FONT_FAMILY}`;
  ctx.fillText(xTitle, (plot.l + plot.rgt) / 2, plot.b + 78);
  ctx.save();
  ctx.translate(r.x + 14, (plot.t + plot.b) / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.fillText(yTitle, 0, 0);
  ctx.restore();
  return { sx, sy };
}

function drawLines(ctx: CanvasRenderingContext2D, r: Region, p: LinesPanel) {
  const top = r.y + heading(ctx, r, p.heading);
  legend(ctx, r.x + 70, top + 28, p.series.map((s) => ({ label: s.name, color: s.color })));
  const plot = { l: r.x + 92, t: top + 56, rgt: r.x + r.w - 40, b: r.y + r.h - 100 };
  const all = p.series.flatMap((s) => s.values);
  const pad = (Math.max(...all) - Math.min(...all, 0)) * 0.1 || 0.5;
  const yr: [number, number] = [Math.min(0, Math.min(...all) - pad), Math.max(0, Math.max(...all) + pad)];
  const n = Math.max(...p.series.map((s) => s.values.length));
  const xr: [number, number] = [0.6, n + 0.4];
  const every = n > 30 ? 5 : n > 16 ? 2 : 1;
  const { sx, sy } = drawAxes(ctx, r, plot, xr, yr, p.xTitle, p.yTitle, Array.from({ length: n }, (_, i) => i + 1).filter((v) => v % every === 0 || v === n));
  ctx.save();
  ctx.setLineDash([3, 8]);
  ctx.strokeStyle = GOOD_LINE;
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(plot.l, sy(0));
  ctx.lineTo(plot.rgt, sy(0));
  ctx.stroke();
  ctx.restore();
  for (const s of p.series) {
    ctx.strokeStyle = s.color;
    ctx.lineWidth = 5;
    ctx.lineJoin = "round";
    ctx.beginPath();
    s.values.forEach((v, i) => (i === 0 ? ctx.moveTo(sx(i + 1), sy(v)) : ctx.lineTo(sx(i + 1), sy(v))));
    ctx.stroke();
    ctx.fillStyle = s.color;
    s.values.forEach((v, i) => {
      const last = p.lastIsTonight && i === s.values.length - 1;
      drawShape(ctx, last ? "diamond" : "circle", sx(i + 1), sy(v), last ? 13 : 6);
    });
  }
}

function drawMap(ctx: CanvasRenderingContext2D, r: Region, p: MapPanel) {
  const top = r.y + heading(ctx, r, p.heading);
  legend(ctx, r.x + 70, top + 28, p.series.flatMap((s) => [{ label: `${s.name} season`, color: s.color }, { label: `${s.name} tonight`, color: s.color, shape: "diamond" as const }]));
  const plot = { l: r.x + 92, t: top + 56, rgt: r.x + r.w - 40, b: r.y + r.h - 100 };
  const { sx, sy } = drawAxes(ctx, r, plot, [0, p.max], [0, p.max], p.xTitle, p.yTitle, null);
  ctx.save();
  ctx.setLineDash([3, 8]);
  ctx.strokeStyle = GOOD_LINE;
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(sx(0), sy(0));
  ctx.lineTo(sx(p.max), sy(p.max));
  ctx.stroke();
  ctx.restore();
  ctx.fillStyle = EXPORT_MUTED;
  ctx.font = `500 24px ${CHART_FONT_FAMILY}`;
  ctx.textAlign = "right";
  ctx.fillText(p.corners[0], sx(p.max * 0.98), sy(p.max * 0.04));
  ctx.textAlign = "left";
  ctx.fillText(p.corners[1], sx(p.max * 0.02), sy(p.max * 0.96) + 14);
  for (const s of p.series) {
    ctx.globalAlpha = 0.38;
    ctx.fillStyle = s.color;
    for (const [x, y] of s.past) drawShape(ctx, "circle", sx(x), sy(y), 9);
  }
  ctx.globalAlpha = 1;
  for (const s of p.series) {
    ctx.fillStyle = s.color;
    drawShape(ctx, "diamond", sx(s.tonight[0]), sy(s.tonight[1]), 15);
    ctx.strokeStyle = EXPORT_BG;
    ctx.lineWidth = 3;
    ctx.stroke();
  }
}

export async function renderContextPng({ title, subtitle, leagueLogo, match, panels, captions }: ContextExport): Promise<string | null> {
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");
  if (!ctx || !panels.length) return null;
  await ensureExportFonts();
  const gap = 50;
  const panelW = (W - 60 - gap * (panels.length - 1)) / panels.length;
  const panelH = Math.max(...panels.map((p) => naturalHeight(p, panelW)));
  ctx.font = `500 23px ${CHART_FONT_FAMILY}`;
  const wrapped = captions.flatMap((raw) => {
    const lines: string[] = [];
    let line = "";
    for (const word of raw.split(/\s+/)) {
      const next = line ? `${line} ${word}` : word;
      if (ctx.measureText(next).width > W - 60 && line) {
        lines.push(line);
        line = word;
      } else {
        line = next;
      }
    }
    if (line) lines.push(line);
    return lines;
  });
  const captionH = wrapped.length ? wrapped.length * 32 + 30 : 0;
  const H = HEADER_H + panelH + captionH + 100;
  canvas.width = W;
  canvas.height = H;
  const { brand, league, matchLine } = await loadHeaderImages(leagueLogo, match);
  ctx.fillStyle = EXPORT_BG;
  ctx.fillRect(0, 0, W, H);
  drawExportHeader(ctx, { width: W, title, subtitle, brand, league, match: matchLine });

  panels.forEach((panel, i) => {
    const region = { x: 30 + i * (panelW + gap), y: HEADER_H, w: panelW, h: panelH };
    if (panel.kind === "bars") drawBars(ctx, region, panel);
    else if (panel.kind === "radar") drawRadarPanel(ctx, region, panel);
    else if (panel.kind === "lines") drawLines(ctx, region, panel);
    else drawMap(ctx, region, panel);
  });

  ctx.textAlign = "left";
  ctx.fillStyle = EXPORT_MUTED;
  ctx.font = `500 23px ${CHART_FONT_FAMILY}`;
  wrapped.forEach((line, i) => ctx.fillText(line, 30, HEADER_H + panelH + 42 + i * 32));
  drawFooter(ctx, { left: 30, right: W - 30, baseline: H - 26, size: 24 });
  return canvas.toDataURL("image/png");
}
