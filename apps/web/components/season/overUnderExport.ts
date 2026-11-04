import { CHART_FONT_FAMILY } from "../../lib/theme";
import { drawExportHeader, drawFooter, ensureExportFonts, EXPORT_BG, EXPORT_MUTED, loadImage, loadRemoteImage } from "../exportFrame";

export type OverUnderExportRow = {
  name: string;
  /** team, minutes and the actual-vs-expected figures */
  sub: string;
  photo: string | null;
  diff: number;
  diffText: string;
};

export type OverUnderExport = {
  title: string;
  subtitle: string;
  leagueLogo?: string;
  /** one line under the bars explaining the measure */
  note?: string;
  /** rows best (most over) first */
  rows: OverUnderExportRow[];
};

const W = 2000;
const GOOD = "#34d399";
const BAD = "#f87171";

// Diverging bars like the "most improved" export, with a headshot and the actual-vs-expected figures for each player.
export async function renderOverUnderPng({ title, subtitle, leagueLogo, note, rows }: OverUnderExport): Promise<string | null> {
  const rowH = 76;
  const top = 235;
  const H = top + rows.length * rowH + 190;
  const canvas = document.createElement("canvas");
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  await ensureExportFonts();
  const [brand, league, ...photos] = await Promise.all([loadImage("/logos/Logo-Dark.png"), loadRemoteImage(leagueLogo), ...rows.map((r) => loadRemoteImage(r.photo))]);
  ctx.fillStyle = EXPORT_BG;
  ctx.fillRect(0, 0, W, H);
  drawExportHeader(ctx, { width: W, title, subtitle, brand, league });

  const photoSize = 58;
  const textX = 30 + 70 + photoSize + 18;
  const left = 820;
  const right = W - 200;
  const maxAbs = Math.max(0.01, ...rows.map((r) => Math.abs(r.diff)));
  const lo = rows.some((r) => r.diff < 0) ? -maxAbs : 0;
  const hi = rows.some((r) => r.diff > 0) ? maxAbs : 0;
  const scale = (right - left) / (hi - lo || 1);
  const zeroX = left - lo * scale;

  ctx.strokeStyle = "rgba(180,194,211,0.55)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(zeroX, top - 12);
  ctx.lineTo(zeroX, top + rows.length * rowH);
  ctx.stroke();

  rows.forEach((r, i) => {
    const cy = top + i * rowH + rowH / 2;
    const color = r.diff >= 0 ? GOOD : BAD;
    if (i % 2 === 0) {
      ctx.fillStyle = "rgba(148,163,184,0.06)";
      ctx.fillRect(30, cy - rowH / 2, W - 60, rowH);
    }
    ctx.textAlign = "left";
    ctx.fillStyle = EXPORT_MUTED;
    ctx.font = `700 26px ${CHART_FONT_FAMILY}`;
    ctx.fillText(String(i + 1), 44, cy + 9);

    const px = 100;
    const img = photos[i];
    ctx.save();
    ctx.beginPath();
    ctx.arc(px + photoSize / 2, cy, photoSize / 2 - 2, 0, Math.PI * 2);
    ctx.clip();
    ctx.fillStyle = "#0f2236";
    ctx.fillRect(px, cy - photoSize / 2, photoSize, photoSize);
    if (img) ctx.drawImage(img, px, cy - photoSize / 2, photoSize, photoSize);
    ctx.restore();
    ctx.beginPath();
    ctx.arc(px + photoSize / 2, cy, photoSize / 2 - 2, 0, Math.PI * 2);
    ctx.lineWidth = 4;
    ctx.strokeStyle = color;
    ctx.stroke();
    if (!img) {
      ctx.fillStyle = color;
      ctx.textAlign = "center";
      ctx.font = `700 ${photoSize * 0.34}px ${CHART_FONT_FAMILY}`;
      ctx.fillText(r.name.split(" ").map((w) => w[0]).slice(0, 2).join(""), px + photoSize / 2, cy + photoSize * 0.12);
      ctx.textAlign = "left";
    }

    const fit = (text: string, font: string, maxWidth: number) => {
      ctx.font = font;
      let t = text;
      while (t.length > 1 && ctx.measureText(t).width > maxWidth) t = t.slice(0, -1);
      return t === text ? t : `${t.trimEnd()}…`;
    };
    const textW = left - textX - 30;
    ctx.fillStyle = "#ffffff";
    ctx.fillText(fit(r.name, `700 27px ${CHART_FONT_FAMILY}`, textW), textX, cy - 3);
    ctx.fillStyle = EXPORT_MUTED;
    ctx.fillText(fit(r.sub, `500 20px ${CHART_FONT_FAMILY}`, textW), textX, cy + 24);

    const w = Math.abs(r.diff) * scale;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.roundRect(r.diff >= 0 ? zeroX : zeroX - w, cy - 17, Math.max(w, 3), 34, 4);
    ctx.fill();
    ctx.font = `700 28px ${CHART_FONT_FAMILY}`;
    ctx.textAlign = r.diff >= 0 ? "left" : "right";
    ctx.fillText(r.diffText, r.diff >= 0 ? zeroX + w + 14 : zeroX - w - 14, cy + 10);
  });

  ctx.textAlign = "left";
  ctx.fillStyle = EXPORT_MUTED;
  ctx.font = `500 24px ${CHART_FONT_FAMILY}`;
  ctx.fillText("Green = doing more than the chances or passes they were given suggest, red = less. Small samples swing a lot early in the season.", 30, H - 112);
  if (note) ctx.fillText(note, 30, H - 76);
  drawFooter(ctx, { left: 30, right: W - 30, baseline: H - 26, size: 24 });
  return canvas.toDataURL("image/png");
}
