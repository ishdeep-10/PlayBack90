import { CHART_FONT_FAMILY } from "../../lib/theme";
import { drawExportHeader, drawFooter, ensureExportFonts, EXPORT_BG, EXPORT_MUTED, loadImage, loadRemoteImage } from "../exportFrame";

export type ScatterExportPoint = {
  x: number;
  y: number;
  color: string;
  /** "dot" (default) is a plain marker; "photo" is a ringed headshot placed beside the point; "crest" is a club badge on the point */
  kind?: "dot" | "photo" | "crest";
  /** dot radius in export pixels */
  r?: number;
  alpha?: number;
  imageUrl?: string | null;
  /** name under a photo, or the initials shown when a crest is missing */
  label?: string;
};

export type ScatterExport = {
  title: string;
  subtitle: string;
  leagueLogo?: string;
  xTitle: string;
  yTitle: string;
  xRange: [number, number];
  yRange: [number, number];
  /** dashed reference lines (league median or mean) */
  refX?: number;
  refY?: number;
  legend?: { label: string; color: string }[];
  note?: string;
  points: ScatterExportPoint[];
};

// Same look as the social-media scatters: L-shaped axes, dashed reference lines, ringed photos beside their dots.
const W = 2000;
const H = 1330;
const PL = 150;
const PR = 50;
const PT = 225;
const PB = H - 215;
const PHOTO = 84;
const CREST_BADGE = 30;

type Box = { x: number; y: number; w: number; h: number };
const overlaps = (a: Box, b: Box, pad = 6) => a.x < b.x + b.w + pad && a.x + a.w + pad > b.x && a.y < b.y + b.h + pad && a.y + a.h + pad > b.y;

export function niceTicks(lo: number, hi: number, count = 6) {
  const raw = (hi - lo) / count || 1;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  const ticks: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-6; v += step) ticks.push(+v.toFixed(10));
  const decimals = String(+step.toFixed(6)).split(".")[1]?.length ?? 0;
  return { ticks, decimals };
}

export async function renderScatterPng(spec: ScatterExport): Promise<string | null> {
  const { title, subtitle, leagueLogo, xTitle, yTitle, xRange, yRange, refX, refY, legend, note, points } = spec;
  const canvas = document.createElement("canvas");
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  await ensureExportFonts();
  const [brand, league, ...images] = await Promise.all([loadImage("/logos/Logo-Dark.png"), loadRemoteImage(leagueLogo), ...points.map((p) => loadRemoteImage(p.imageUrl))]);

  ctx.fillStyle = EXPORT_BG;
  ctx.fillRect(0, 0, W, H);
  drawExportHeader(ctx, { width: W, title, subtitle, brand, league });

  const sx = (v: number) => PL + ((v - xRange[0]) / (xRange[1] - xRange[0])) * (W - PL - PR);
  const sy = (v: number) => PB - ((v - yRange[0]) / (yRange[1] - yRange[0])) * (PB - PT);

  // axes
  ctx.strokeStyle = "rgba(180,194,211,0.55)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(PL, PT - 10);
  ctx.lineTo(PL, PB);
  ctx.lineTo(W - PR, PB);
  ctx.stroke();
  ctx.fillStyle = EXPORT_MUTED;
  ctx.font = `500 21px ${CHART_FONT_FAMILY}`;
  const xt = niceTicks(...xRange, 7);
  ctx.textAlign = "center";
  for (const v of xt.ticks) {
    ctx.fillText(v.toFixed(xt.decimals), sx(v), PB + 36);
    ctx.beginPath();
    ctx.moveTo(sx(v), PB);
    ctx.lineTo(sx(v), PB + 8);
    ctx.stroke();
  }
  const yt = niceTicks(...yRange, 6);
  ctx.textAlign = "right";
  for (const v of yt.ticks) {
    ctx.fillText(v.toFixed(yt.decimals), PL - 16, sy(v) + 7);
    ctx.beginPath();
    ctx.moveTo(PL - 8, sy(v));
    ctx.lineTo(PL, sy(v));
    ctx.stroke();
  }
  ctx.fillStyle = "#e2e8f0";
  ctx.font = `500 31px ${CHART_FONT_FAMILY}`;
  ctx.textAlign = "center";
  ctx.fillText(xTitle, PL + (W - PL - PR) / 2, PB + 88);
  ctx.save();
  ctx.translate(48, PT + (PB - PT) / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.fillText(yTitle, 0, 0);
  ctx.restore();

  // dashed reference lines
  ctx.save();
  ctx.setLineDash([10, 8]);
  ctx.strokeStyle = "rgba(180,194,211,0.5)";
  ctx.lineWidth = 1.6;
  ctx.beginPath();
  if (refX !== undefined) {
    ctx.moveTo(sx(refX), PT - 10);
    ctx.lineTo(sx(refX), PB);
  }
  if (refY !== undefined) {
    ctx.moveTo(PL, sy(refY));
    ctx.lineTo(W - PR, sy(refY));
  }
  ctx.stroke();
  ctx.restore();

  // plain dots first (and the dot under each crest), photos and crests on top
  points.forEach((p) => {
    if (p.kind === "photo" || p.kind === "crest") return;
    ctx.globalAlpha = p.alpha ?? 0.8;
    ctx.fillStyle = p.color;
    ctx.beginPath();
    ctx.arc(sx(p.x), sy(p.y), p.r ?? 9, 0, Math.PI * 2);
    ctx.fill();
    if (p.label) {
      ctx.globalAlpha = 1;
      ctx.fillStyle = "#ffffff";
      ctx.font = `700 22px ${CHART_FONT_FAMILY}`;
      ctx.textAlign = "left";
      ctx.fillText(p.label, sx(p.x) + (p.r ?? 9) + 8, sy(p.y) + 7);
    }
  });
  ctx.globalAlpha = 1;

  points.forEach((p, i) => {
    if (p.kind !== "crest") return;
    const cx = sx(p.x);
    const cy = sy(p.y);
    ctx.globalAlpha = p.alpha ?? 1;
    ctx.fillStyle = images[i] ? "rgba(255,255,255,0.94)" : "rgba(100,116,139,0.95)";
    ctx.beginPath();
    ctx.arc(cx, cy, CREST_BADGE, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "rgba(148,163,184,0.6)";
    ctx.lineWidth = 1.5;
    ctx.stroke();
    const img = images[i];
    if (img) {
      const box = CREST_BADGE * 1.35;
      const k = Math.min(box / img.width, box / img.height);
      ctx.drawImage(img, cx - (img.width * k) / 2, cy - (img.height * k) / 2, img.width * k, img.height * k);
    } else if (p.label) {
      ctx.fillStyle = "#ffffff";
      ctx.font = `700 20px ${CHART_FONT_FAMILY}`;
      ctx.textAlign = "center";
      ctx.fillText(p.label, cx, cy + 7);
    }
  });
  ctx.globalAlpha = 1;

  // photos: try the point itself, then spiral outwards to the first spot that overlaps no other card and stays on the plot
  const placed: Box[] = [];
  const area: Box = { x: PL + 6, y: PT - 6, w: W - PL - PR - 12, h: PB - PT + 6 };
  ctx.font = `700 25px ${CHART_FONT_FAMILY}`;
  points.forEach((p, i) => {
    if (p.kind !== "photo") return;
    const px = sx(p.x);
    const py = sy(p.y);
    const labelW = ctx.measureText(p.label ?? "").width;
    const w = Math.max(PHOTO, labelW + 6);
    const h = PHOTO + 36;
    let best: { cx: number; cy: number; d: number } | null = null;
    search: for (const d of [0, 78, 112, 150, 195, 250, 320]) {
      const steps = d === 0 ? 1 : 12;
      for (let a = 0; a < steps; a += 1) {
        const ang = (a / steps) * Math.PI * 2 - Math.PI / 4;
        const cx = px + Math.cos(ang) * d * 1.25;
        const cy = py + Math.sin(ang) * d;
        const box = { x: cx - w / 2, y: cy - PHOTO / 2, w, h };
        const inside = box.x >= area.x && box.y >= area.y && box.x + w <= area.x + area.w && box.y + h <= area.y + area.h;
        if (inside && !placed.some((o) => overlaps(box, o))) {
          best = { cx, cy, d };
          break search;
        }
        if (!best && d >= 320) best = { cx, cy, d };
      }
    }
    if (!best) best = { cx: px, cy: py, d: 0 };
    const box = { x: best.cx - w / 2, y: best.cy - PHOTO / 2, w, h };
    placed.push(box);
    ctx.globalAlpha = p.alpha ?? 1;
    if (best.d > 0) {
      const lx = Math.min(Math.max(px, best.cx - PHOTO / 2), best.cx + PHOTO / 2);
      const ly = Math.min(Math.max(py, best.cy - PHOTO / 2), best.cy + PHOTO / 2);
      ctx.strokeStyle = p.color;
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(px, py);
      ctx.lineTo(lx, ly);
      ctx.stroke();
      ctx.fillStyle = p.color;
      ctx.beginPath();
      ctx.arc(px, py, 10, 0, Math.PI * 2);
      ctx.fill();
    }
    const x0 = best.cx - PHOTO / 2;
    const y0 = best.cy - PHOTO / 2;
    ctx.fillStyle = "#0f2236";
    ctx.fillRect(x0, y0, PHOTO, PHOTO);
    const img = images[i];
    if (img) ctx.drawImage(img, x0, y0, PHOTO, PHOTO);
    ctx.strokeStyle = p.color;
    ctx.lineWidth = 6;
    ctx.strokeRect(x0 - 1, y0 - 1, PHOTO + 2, PHOTO + 2);
    if (p.label) {
      ctx.textAlign = "center";
      ctx.lineJoin = "round";
      ctx.lineWidth = 7;
      ctx.strokeStyle = "rgba(8,18,30,0.85)";
      ctx.font = `700 25px ${CHART_FONT_FAMILY}`;
      ctx.strokeText(p.label, best.cx, y0 + PHOTO + 28);
      ctx.fillStyle = "#ffffff";
      ctx.fillText(p.label, best.cx, y0 + PHOTO + 28);
    }
  });
  ctx.globalAlpha = 1;

  // legend + note, then footer
  ctx.textAlign = "left";
  const rowY = H - 76;
  let lx = 30;
  ctx.font = `500 24px ${CHART_FONT_FAMILY}`;
  for (const item of legend ?? []) {
    ctx.fillStyle = item.color;
    ctx.beginPath();
    ctx.arc(lx + 9, rowY - 8, 9, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#e2e8f0";
    ctx.fillText(item.label, lx + 28, rowY);
    lx += 28 + ctx.measureText(item.label).width + 36;
  }
  if (note) {
    ctx.fillStyle = EXPORT_MUTED;
    ctx.fillText(note, lx + (legend?.length ? 20 : 0), rowY);
  }
  drawFooter(ctx, { left: 30, right: W - 30, baseline: H - 26, size: 24 });
  return canvas.toDataURL("image/png");
}
