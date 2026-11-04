import { CHART_FONT_FAMILY } from "../../lib/theme";
import { drawExportHeader, drawFooter, ensureExportFonts, EXPORT_ACCENT, EXPORT_BG, EXPORT_MUTED, loadImage, loadRemoteImage } from "../exportFrame";

export type LeaderboardExportRow = { name: string; sub: string; value: number; valueText: string; photo: string | null };

export type LeaderboardExport = {
  title: string;
  subtitle: string;
  leagueLogo?: string;
  rows: LeaderboardExportRow[];
  note?: string;
};

// Ranked bars as in the social-media "who creates the best chances" visual, with the headshots from the app cards.
const W = 2000;
const HEADER_H = 210;
const BAR = "#22d3ee";

export async function renderLeaderboardPng({ title, subtitle, leagueLogo, rows, note }: LeaderboardExport): Promise<string | null> {
  const cols = rows.length > 12 ? 2 : 1;
  const perCol = Math.ceil(rows.length / cols);
  const rowH = cols === 1 ? 100 : 92;
  const noteH = note ? 46 : 0;
  const H = HEADER_H + perCol * rowH + noteH + 110;
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

  const gutter = 60;
  const colW = (W - 60 - gutter * (cols - 1)) / cols;
  const photoSize = 68;
  const nameSize = 30;
  const subSize = 22;
  const valueSize = 34;
  const valueRoom = 120;
  const max = Math.max(...rows.map((r) => r.value), 0);
  ctx.font = `700 ${nameSize}px ${CHART_FONT_FAMILY}`;
  const widest = Math.max(...rows.map((r) => ctx.measureText(r.name).width));
  const nameW = Math.min(Math.max(widest + 16, 220), colW * 0.38);
  const fit = (text: string, font: string, maxWidth: number) => {
    ctx.font = font;
    let t = text;
    while (t.length > 1 && ctx.measureText(t).width > maxWidth) t = t.slice(0, -1);
    return t === text ? t : `${t.trimEnd()}…`;
  };

  rows.forEach((r, i) => {
    const col = Math.floor(i / perCol);
    const x0 = 30 + col * (colW + gutter);
    const rowTop = HEADER_H + (i % perCol) * rowH;
    const cy = rowTop + rowH / 2;
    const color = i === 0 ? EXPORT_ACCENT : BAR;

    ctx.textAlign = "left";
    ctx.fillStyle = EXPORT_MUTED;
    ctx.font = `700 ${nameSize}px ${CHART_FONT_FAMILY}`;
    ctx.fillText(String(i + 1), x0, cy + 11);

    const px = x0 + 56;
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

    const tx = px + photoSize + 22;
    ctx.fillStyle = "#ffffff";
    ctx.fillText(fit(r.name, `700 ${nameSize}px ${CHART_FONT_FAMILY}`, nameW), tx, cy - 2);
    ctx.fillStyle = EXPORT_MUTED;
    ctx.fillText(fit(r.sub, `500 ${subSize}px ${CHART_FONT_FAMILY}`, nameW), tx, cy + 28);

    const barX = tx + nameW + 20;
    const barMax = x0 + colW - valueRoom - barX;
    const barW = max > 0 ? Math.max(4, (Math.max(r.value, 0) / max) * barMax) : 4;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.roundRect(barX, cy - 19, barW, 38, 5);
    ctx.fill();
    ctx.font = `700 ${valueSize}px ${CHART_FONT_FAMILY}`;
    ctx.fillText(r.valueText, barX + barW + 16, cy + 12);
  });

  if (note) {
    ctx.textAlign = "left";
    ctx.fillStyle = EXPORT_MUTED;
    ctx.font = `500 24px ${CHART_FONT_FAMILY}`;
    ctx.fillText(note, 30, H - 104);
  }
  drawFooter(ctx, { left: 30, right: W - 30, baseline: H - 36, size: 24 });
  return canvas.toDataURL("image/png");
}
