import { CHART_FONT_FAMILY } from "../../lib/theme";
import { drawExportHeader, drawFooter, drawPitchMarkings, ensureExportFonts, EXPORT_BG, EXPORT_MUTED, loadImage, loadRemoteImage } from "../exportFrame";
import { BANDS, LANES, mix, PITCH_H, PITCH_W, type ZoneValue } from "./pitch";

export type ZonesExport = {
  title: string;
  subtitle: string;
  leagueLogo?: string;
  grid: { x: number[]; y: number[] };
  /** per cell, lane * BANDS + band: what is shown, the team's own value and the league average */
  shown: number[];
  own: number[];
  league: number[];
  value: ZoneValue;
};

// Full-width pitch like the zone-leaders map, one coloured cell per zone with its value and the league figure beneath.
const W = 2000;
const PITCH_X = 30;
const PITCH_Y = 212;
const PX = (W - PITCH_X * 2) / PITCH_W;
const H = Math.round(PITCH_Y + PITCH_H * PX + 165);
const LOW = "#10304a";
const HIGH = "#a3e635";
const FG = "#0b1623";
const UP = "#34d399";
const DOWN = "#f87171";

export async function renderZonesPng({ title, subtitle, leagueLogo, grid, shown, own, league, value }: ZonesExport): Promise<string | null> {
  const canvas = document.createElement("canvas");
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  await ensureExportFonts();
  const [brand, leagueImg] = await Promise.all([loadImage("/logos/Logo-Dark.png"), loadRemoteImage(leagueLogo)]);
  ctx.fillStyle = EXPORT_BG;
  ctx.fillRect(0, 0, W, H);
  drawExportHeader(ctx, { width: W, title, subtitle, brand, league: leagueImg });

  const diff = value === "vsLeague";
  const max = Math.max(0.01, ...shown);
  const diffMax = Math.max(0.01, ...shown.map((v) => Math.abs(v)));
  const fmt = (v: number) => (diff ? `${v > 0 ? "+" : ""}${v.toFixed(1)}%` : value === "perMatch" ? v.toFixed(1) : `${v.toFixed(0)}%`);
  const sub = (i: number) => (diff ? `${own[i].toFixed(1)}% vs ${league[i].toFixed(1)}%` : `league ${league[i].toFixed(value === "perMatch" ? 1 : 0)}${value === "perMatch" ? "" : "%"}`);
  const colorOf = (v: number) => (diff ? (v >= 0 ? mix(FG, UP, Math.min(1, v / diffMax)) : mix(FG, DOWN, Math.min(1, -v / diffMax))) : mix(LOW, HIGH, v / max));
  const light = (v: number) => (diff ? Math.abs(v) / diffMax > 0.55 : v / max > 0.55);

  const px = (x: number) => PITCH_X + x * PX;
  const py = (y: number) => PITCH_Y + (PITCH_H - y) * PX;
  ctx.textAlign = "center";
  for (let lane = 0; lane < LANES; lane += 1) {
    for (let band = 0; band < BANDS; band += 1) {
      const i = lane * BANDS + band;
      const [x0, x1, y0, y1] = [grid.x[band], grid.x[band + 1], grid.y[lane], grid.y[lane + 1]];
      ctx.fillStyle = colorOf(shown[i]);
      ctx.fillRect(px(x0), py(y1), (x1 - x0) * PX, (y1 - y0) * PX);
      ctx.strokeStyle = "rgba(148,163,184,0.35)";
      ctx.lineWidth = 1.5;
      ctx.strokeRect(px(x0), py(y1), (x1 - x0) * PX, (y1 - y0) * PX);
    }
  }
  drawPitchMarkings(ctx, { left: PITCH_X, top: PITCH_Y, scale: PX, color: "rgba(226,232,240,0.4)" });
  for (let lane = 0; lane < LANES; lane += 1) {
    for (let band = 0; band < BANDS; band += 1) {
      const i = lane * BANDS + band;
      const cx = px((grid.x[band] + grid.x[band + 1]) / 2);
      const cy = py((grid.y[lane] + grid.y[lane + 1]) / 2);
      const dark = light(shown[i]);
      ctx.lineJoin = "round";
      ctx.lineWidth = 6;
      ctx.strokeStyle = dark ? "rgba(255,255,255,0.0)" : "rgba(8,18,30,0.55)";
      ctx.font = `700 40px ${CHART_FONT_FAMILY}`;
      ctx.strokeText(fmt(shown[i]), cx, cy + 6);
      ctx.fillStyle = dark ? FG : "#ffffff";
      ctx.fillText(fmt(shown[i]), cx, cy + 6);
      ctx.font = `500 22px ${CHART_FONT_FAMILY}`;
      ctx.fillStyle = dark ? "rgba(11,22,35,0.78)" : "rgba(226,232,240,0.75)";
      ctx.fillText(sub(i), cx, cy + 40);
    }
  }

  // colour scale
  const barX = 38;
  const barY = PITCH_Y + PITCH_H * PX + 34;
  const barW = 380;
  const grad = ctx.createLinearGradient(barX, 0, barX + barW, 0);
  if (diff) {
    grad.addColorStop(0, DOWN);
    grad.addColorStop(0.5, FG);
    grad.addColorStop(1, UP);
  } else {
    grad.addColorStop(0, LOW);
    grad.addColorStop(1, HIGH);
  }
  ctx.fillStyle = grad;
  ctx.fillRect(barX, barY, barW, 18);
  ctx.strokeStyle = "rgba(148,163,184,0.4)";
  ctx.lineWidth = 1.5;
  ctx.strokeRect(barX, barY, barW, 18);
  ctx.fillStyle = EXPORT_MUTED;
  ctx.font = `500 22px ${CHART_FONT_FAMILY}`;
  ctx.textAlign = "left";
  ctx.fillText(fmt(diff ? -diffMax : 0), barX, barY + 46);
  ctx.textAlign = "right";
  ctx.fillText(fmt(diff ? diffMax : max), barX + barW, barY + 46);
  ctx.textAlign = "left";
  ctx.fillText(diff ? "red = below the league average, green = above" : "darker = fewer, brighter = more", barX + barW + 30, barY + 16);

  drawFooter(ctx, { left: 30, right: W - 30, baseline: H - 26, size: 24, extra: "Attacking left to right →" });
  return canvas.toDataURL("image/png");
}
