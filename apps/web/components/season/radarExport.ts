import { CHART_FONT_FAMILY } from "../../lib/theme";
import { drawExportHeader, drawFooter, ensureExportFonts, EXPORT_BG, EXPORT_MUTED, loadImage, loadRemoteImage } from "../exportFrame";

export type RadarExport = {
  title: string;
  subtitle: string;
  leagueLogo?: string;
  axes: string[];
  /** values 0-100 per axis (league percentile) */
  series: { name: string; color: string; values: number[] }[];
};

const W = 2000;
const H = 1450;
const CX = W / 2;
const CY = 790;
const R = 470;

/** Rings, spokes, one filled polygon per series and the axis labels, centred on (cx, cy). Values are 0-100. */
export function drawRadar(ctx: CanvasRenderingContext2D, { cx: CX, cy: CY, radius: R, labelMax = 330, fontSize = 27 }: { cx: number; cy: number; radius: number; labelMax?: number; fontSize?: number }, axes: string[], series: RadarExport["series"]) {
  const n = axes.length;
  const angle = (i: number) => -Math.PI / 2 + (i / n) * Math.PI * 2;
  const point = (i: number, v: number): [number, number] => [CX + Math.cos(angle(i)) * R * (v / 100), CY + Math.sin(angle(i)) * R * (v / 100)];

  // rings and spokes
  ctx.strokeStyle = "rgba(148,163,184,0.28)";
  ctx.lineWidth = 1.6;
  for (const ring of [25, 50, 75, 100]) {
    ctx.beginPath();
    axes.forEach((_, i) => {
      const [x, y] = point(i, ring);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.closePath();
    ctx.stroke();
  }
  axes.forEach((_, i) => {
    const [x, y] = point(i, 100);
    ctx.beginPath();
    ctx.moveTo(CX, CY);
    ctx.lineTo(x, y);
    ctx.stroke();
  });
  ctx.fillStyle = EXPORT_MUTED;
  ctx.font = `500 20px ${CHART_FONT_FAMILY}`;
  ctx.textAlign = "left";
  for (const ring of [25, 50, 75]) ctx.fillText(String(ring), CX + 8, CY - (R * ring) / 100 - 6);

  // one filled polygon per team
  series.forEach((s) => {
    ctx.beginPath();
    s.values.forEach((v, i) => {
      const [x, y] = point(i, v);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.closePath();
    ctx.fillStyle = `${s.color}33`;
    ctx.fill();
    ctx.strokeStyle = s.color;
    ctx.lineWidth = 5;
    ctx.lineJoin = "round";
    ctx.stroke();
    ctx.fillStyle = s.color;
    s.values.forEach((v, i) => {
      const [x, y] = point(i, v);
      ctx.beginPath();
      ctx.arc(x, y, 8, 0, Math.PI * 2);
      ctx.fill();
    });
  });

  // axis labels
  ctx.font = `600 ${fontSize}px ${CHART_FONT_FAMILY}`;
  ctx.fillStyle = "#ffffff";
  axes.forEach((label, i) => {
    const a = angle(i);
    const c = Math.cos(a);
    const s = Math.sin(a);
    const x = CX + c * (R + 26);
    const y = CY + s * (R + 26) + (s > 0.3 ? 22 : s < -0.3 ? -4 : 8);
    ctx.textAlign = c > 0.25 ? "left" : c < -0.25 ? "right" : "center";
    let text = label;
    while (text.length > 1 && ctx.measureText(text).width > labelMax) text = text.slice(0, -1);
    ctx.fillText(text === label ? text : `${text.trimEnd()}…`, x, y);
  });

}

export async function renderRadarPng({ title, subtitle, leagueLogo, axes, series }: RadarExport): Promise<string | null> {
  const canvas = document.createElement("canvas");
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  await ensureExportFonts();
  const [brand, league] = await Promise.all([loadImage("/logos/Logo-Dark.png"), loadRemoteImage(leagueLogo)]);
  ctx.fillStyle = EXPORT_BG;
  ctx.fillRect(0, 0, W, H);
  drawExportHeader(ctx, { width: W, title, subtitle, brand, league });

  drawRadar(ctx, { cx: CX, cy: CY, radius: R }, axes, series);

  // legend
  ctx.font = `600 28px ${CHART_FONT_FAMILY}`;
  const widths = series.map((s) => 40 + ctx.measureText(s.name).width);
  let lx = CX - (widths.reduce((a, b) => a + b, 0) + 44 * (series.length - 1)) / 2;
  series.forEach((s, i) => {
    ctx.fillStyle = s.color;
    ctx.beginPath();
    ctx.arc(lx + 11, 213, 11, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#ffffff";
    ctx.textAlign = "left";
    ctx.fillText(s.name, lx + 34, 223);
    lx += widths[i] + 44;
  });

  drawFooter(ctx, { left: 30, right: W - 30, baseline: H - 26, size: 24, extra: "100 = best in the league" });
  return canvas.toDataURL("image/png");
}
