import { CHART_FONT_FAMILY } from "../../lib/theme";
import { drawExportHeader, drawFooter, ensureExportFonts, EXPORT_BG, EXPORT_MUTED, loadImage, loadRemoteImage } from "../exportFrame";
import { niceTicks } from "./scatterExport";

type Base = { title: string; subtitle: string; leagueLogo?: string };

export type RollingExport = Base & {
  series: { name: string; color: string; values: number[] }[];
  xTitle: string;
  yTitle: string;
  note?: string;
};

export type ImprovedExport = Base & {
  /** sorted best first */
  rows: { team: string; delta: number; early: number; late: number }[];
  recent: number;
};

const W = 2000;
const GOOD = "#34d399";
const BAD = "#f87171";

async function start(height: number, spec: Base) {
  const canvas = document.createElement("canvas");
  canvas.width = W;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  await ensureExportFonts();
  const [brand, league] = await Promise.all([loadImage("/logos/Logo-Dark.png"), loadRemoteImage(spec.leagueLogo)]);
  ctx.fillStyle = EXPORT_BG;
  ctx.fillRect(0, 0, W, height);
  drawExportHeader(ctx, { width: W, title: spec.title, subtitle: spec.subtitle, brand, league });
  return { canvas, ctx };
}

/** Rolling xG created / conceded, match by match. */
export async function renderRollingPng(spec: RollingExport): Promise<string | null> {
  const H = 1200;
  const frame = await start(H, spec);
  if (!frame) return null;
  const { canvas, ctx } = frame;
  const PL = 150;
  const PR = 120;
  const PT = 270;
  const PB = H - 215;
  const n = spec.series[0]?.values.length ?? 0;
  if (n < 2) return null;
  const hi = Math.max(...spec.series.flatMap((s) => s.values)) * 1.12 || 1;
  const sx = (i: number) => PL + 30 + (i / (n - 1)) * (W - PL - PR - 30);
  const sy = (v: number) => PB - (v / hi) * (PB - PT);

  // legend
  ctx.textAlign = "left";
  ctx.font = `600 28px ${CHART_FONT_FAMILY}`;
  let lx = PL;
  for (const s of spec.series) {
    ctx.fillStyle = s.color;
    ctx.fillRect(lx, 217, 34, 6);
    ctx.beginPath();
    ctx.arc(lx + 17, 220, 9, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#ffffff";
    ctx.fillText(s.name, lx + 48, 231);
    lx += 48 + ctx.measureText(s.name).width + 50;
  }

  // gridlines and axes
  const yt = niceTicks(0, hi, 6);
  ctx.font = `500 21px ${CHART_FONT_FAMILY}`;
  ctx.textAlign = "right";
  for (const v of yt.ticks) {
    ctx.strokeStyle = "rgba(148,163,184,0.16)";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(PL, sy(v));
    ctx.lineTo(W - PR, sy(v));
    ctx.stroke();
    ctx.fillStyle = EXPORT_MUTED;
    ctx.fillText(v.toFixed(yt.decimals), PL - 16, sy(v) + 7);
  }
  ctx.strokeStyle = "rgba(180,194,211,0.55)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(PL, PT - 10);
  ctx.lineTo(PL, PB);
  ctx.lineTo(W - PR, PB);
  ctx.stroke();
  ctx.textAlign = "center";
  const every = n > 24 ? 2 : 1;
  for (let i = 0; i < n; i += every) {
    ctx.fillStyle = EXPORT_MUTED;
    ctx.fillText(String(i + 1), sx(i), PB + 36);
    ctx.beginPath();
    ctx.moveTo(sx(i), PB);
    ctx.lineTo(sx(i), PB + 8);
    ctx.stroke();
  }
  ctx.fillStyle = "#e2e8f0";
  ctx.font = `500 31px ${CHART_FONT_FAMILY}`;
  ctx.fillText(spec.xTitle, PL + (W - PL - PR) / 2, PB + 90);
  ctx.save();
  ctx.translate(48, PT + (PB - PT) / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.fillText(spec.yTitle, 0, 0);
  ctx.restore();

  // smoothed lines (Catmull-Rom through every match), markers and the latest value
  for (const s of spec.series) {
    const pts = s.values.map((v, i) => [sx(i), sy(v)] as const);
    ctx.beginPath();
    ctx.moveTo(pts[0][0], pts[0][1]);
    for (let i = 0; i < pts.length - 1; i += 1) {
      const p0 = pts[Math.max(0, i - 1)];
      const p1 = pts[i];
      const p2 = pts[i + 1];
      const p3 = pts[Math.min(pts.length - 1, i + 2)];
      ctx.bezierCurveTo(p1[0] + (p2[0] - p0[0]) / 7, p1[1] + (p2[1] - p0[1]) / 7, p2[0] - (p3[0] - p1[0]) / 7, p2[1] - (p3[1] - p1[1]) / 7, p2[0], p2[1]);
    }
    ctx.strokeStyle = s.color;
    ctx.lineWidth = 6;
    ctx.lineJoin = "round";
    ctx.stroke();
    ctx.fillStyle = s.color;
    for (const [x, y] of pts) {
      ctx.beginPath();
      ctx.arc(x, y, 8.5, 0, Math.PI * 2);
      ctx.fill();
    }
    const last = pts[pts.length - 1];
    ctx.font = `700 30px ${CHART_FONT_FAMILY}`;
    ctx.textAlign = "left";
    ctx.fillText(s.values[n - 1].toFixed(2), last[0] + 18, last[1] + 10);
  }

  if (spec.note) {
    ctx.textAlign = "left";
    ctx.fillStyle = EXPORT_MUTED;
    ctx.font = `500 24px ${CHART_FONT_FAMILY}`;
    ctx.fillText(spec.note, 30, H - 76);
  }
  drawFooter(ctx, { left: 30, right: W - 30, baseline: H - 26, size: 24 });
  return canvas.toDataURL("image/png");
}

/** Change in xG difference per match, latest games vs everything before, one diverging bar per team. */
export async function renderImprovedPng(spec: ImprovedExport): Promise<string | null> {
  const rowH = 54;
  const H = 250 + spec.rows.length * rowH + 150;
  const frame = await start(H, spec);
  if (!frame) return null;
  const { canvas, ctx } = frame;
  const nameW = 330;
  const left = 30 + nameW;
  const right = W - 160;
  const top = 250;
  const maxAbs = Math.max(0.01, ...spec.rows.map((r) => Math.abs(r.delta)));
  const hasNeg = spec.rows.some((r) => r.delta < 0);
  const hasPos = spec.rows.some((r) => r.delta > 0);
  const lo = hasNeg ? -maxAbs : 0;
  const hiV = hasPos ? maxAbs : 0;
  const zeroX = left + ((0 - lo) / (hiV - lo || 1)) * (right - left);
  const scale = (right - left) / (hiV - lo || 1);

  ctx.strokeStyle = "rgba(180,194,211,0.55)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(zeroX, top - 14);
  ctx.lineTo(zeroX, top + spec.rows.length * rowH);
  ctx.stroke();

  spec.rows.forEach((r, i) => {
    const cy = top + i * rowH + rowH / 2;
    const color = r.delta >= 0 ? GOOD : BAD;
    if (i % 2 === 0) {
      ctx.fillStyle = "rgba(148,163,184,0.06)";
      ctx.fillRect(30, cy - rowH / 2, W - 60, rowH);
    }
    ctx.textAlign = "left";
    ctx.fillStyle = "#ffffff";
    ctx.font = `600 27px ${CHART_FONT_FAMILY}`;
    ctx.fillText(r.team, 40, cy + 9);
    const w = Math.abs(r.delta) * scale;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.roundRect(r.delta >= 0 ? zeroX : zeroX - w, cy - 16, Math.max(w, 3), 32, 4);
    ctx.fill();
    ctx.font = `700 27px ${CHART_FONT_FAMILY}`;
    const text = `${r.delta > 0 ? "+" : ""}${r.delta.toFixed(2)}`;
    ctx.textAlign = r.delta >= 0 ? "left" : "right";
    ctx.fillText(text, r.delta >= 0 ? zeroX + w + 14 : zeroX - w - 14, cy + 9);
  });

  ctx.textAlign = "left";
  ctx.fillStyle = EXPORT_MUTED;
  ctx.font = `500 24px ${CHART_FONT_FAMILY}`;
  ctx.fillText(`Change in xG difference per match: the latest ${spec.recent} games vs everything before them`, 30, H - 76);
  drawFooter(ctx, { left: 30, right: W - 30, baseline: H - 26, size: 24 });
  return canvas.toDataURL("image/png");
}
