import { toProxiedDataUrl } from "../lib/images";
import type { ShareMatchInfo } from "./ShareExportContext";
import { CHART_FONT_FAMILY } from "../lib/theme";

// Shared look of every exported image (matches the social-media visuals): dark canvas, green-underlined title,
// one-line subtitle, brand logo top right, credit footer.
export const EXPORT_BG = "#08121e";
export const EXPORT_ACCENT = "#a3e635";
export const EXPORT_MUTED = "#b4c2d3";
export const EXPORT_CREDIT = "Generated with PlayBack90  |  Data by Dribble (dribble360.com)";

/** Short accent bar under the title; `baseline` is the title's baseline. */
export function drawTitleUnderline(ctx: CanvasRenderingContext2D, x: number, baseline: number, scale: number, color = EXPORT_ACCENT) {
  ctx.fillStyle = color;
  ctx.fillRect(x, baseline + 8 * scale, 140 * scale, 4 * scale);
}

/** The logo tile in the app's brand colours, rounded like the app icon. */
export function drawBrandLogo(ctx: CanvasRenderingContext2D, image: HTMLImageElement, x: number, y: number, size: number) {
  ctx.save();
  ctx.beginPath();
  ctx.roundRect(x, y, size, size, size * 0.15);
  ctx.clip();
  ctx.drawImage(image, x, y, size, size);
  ctx.restore();
}

/** Filter labels joined into one subtitle line, shortened with an ellipsis so it never runs past `maxWidth`. */
export function fitSubtitle(ctx: CanvasRenderingContext2D, parts: string[], maxWidth: number) {
  let text = parts.filter(Boolean).join("  |  ");
  if (ctx.measureText(text).width <= maxWidth) return text;
  while (text.length > 1 && ctx.measureText(`${text}…`).width > maxWidth) text = text.slice(0, -1);
  return `${text}…`;
}

export function drawFooter(ctx: CanvasRenderingContext2D, { left, right, baseline, size, color = EXPORT_MUTED, extra }: { left: number; right: number; baseline: number; size: number; color?: string; extra?: string }) {
  ctx.fillStyle = color;
  ctx.font = `500 ${size}px ${CHART_FONT_FAMILY}`;
  ctx.textAlign = "left";
  ctx.fillText(extra ? `${EXPORT_CREDIT}  |  ${extra}` : EXPORT_CREDIT, left, baseline);
  ctx.textAlign = "right";
  ctx.fillText(new Date().toISOString().slice(0, 10), right, baseline);
  ctx.textAlign = "left";
}

export function loadImage(src: string): Promise<HTMLImageElement | null> {
  return new Promise((resolve) => {
    const image = new window.Image();
    image.onload = () => resolve(image);
    image.onerror = () => resolve(null);
    image.src = src;
  });
}

/** An image from a CDN without CORS headers, fetched through the API image proxy so the canvas stays untainted. */
export async function loadRemoteImage(src: string | null | undefined) {
  if (!src) return null;
  if (src.startsWith("data:") || src.startsWith("/")) return loadImage(src);
  const data = await toProxiedDataUrl(src);
  return data ? loadImage(data) : null;
}

/** The page loads Space Grotesk lazily: make sure the weights the export uses are ready before drawing. */
export async function ensureExportFonts() {
  await Promise.all([700, 600, 500].map((w) => document.fonts?.load(`${w} 24px 'Space Grotesk'`).catch(() => null)));
}

export type ExportMatchLine = { label: string; home: HTMLImageElement | null; away: HTMLImageElement | null };

/** Brand tile, league crest and (on match pages) the two club crests, loaded once for a header. */
export async function loadHeaderImages(leagueLogo?: string, match?: ShareMatchInfo | null) {
  const [brand, league, home, away] = await Promise.all([
    loadImage("/logos/Logo-Dark.png"),
    loadRemoteImage(leagueLogo),
    loadRemoteImage(match?.homeLogoUrl),
    loadRemoteImage(match?.awayLogoUrl),
  ]);
  const matchLine: ExportMatchLine | undefined = match ? { label: `${match.home}${match.score ? ` ${match.score} ` : " vs "}${match.away}`, home, away } : undefined;
  return { brand, league, matchLine };
}

/** "League | date" for a match export's subtitle. */
export const matchMeta = (match?: ShareMatchInfo | null) => [match?.league, match?.dateLabel].filter(Boolean).join("  |  ");

/**
 * Title with accent underline, subtitle, and the logos top right (brand tile, then the league crest in a white circle).
 * On match pages the subtitle line starts with "[crest] Home 2-1 Away [crest]". Everything is sized for a 2000px-wide
 * canvas; the header is 190px tall.
 */
export function drawExportHeader(ctx: CanvasRenderingContext2D, { width, title, subtitle, brand, league, match }: { width: number; title: string; subtitle: string; brand: HTMLImageElement | null; league: HTMLImageElement | null; match?: ExportMatchLine }) {
  ctx.textBaseline = "alphabetic";
  ctx.textAlign = "left";
  ctx.fillStyle = "#ffffff";
  ctx.font = `700 64px ${CHART_FONT_FAMILY}`;
  ctx.fillText(title, 30, 82);
  drawTitleUnderline(ctx, 30, 82, 2);
  const logosW = (brand ? 154 : 0) + (league ? 154 : 0);
  let x = 30;
  if (match) {
    const crest = 46;
    ctx.font = `700 29px ${CHART_FONT_FAMILY}`;
    ctx.fillStyle = "#ffffff";
    if (match.home) {
      ctx.drawImage(match.home, x, 120, crest, crest);
      x += crest + 12;
    }
    ctx.fillText(match.label, x, 158);
    x += ctx.measureText(match.label).width + 12;
    if (match.away) {
      ctx.drawImage(match.away, x, 120, crest, crest);
      x += crest + 12;
    }
    x += 14;
  }
  ctx.fillStyle = EXPORT_MUTED;
  ctx.font = `500 27px ${CHART_FONT_FAMILY}`;
  ctx.fillText(fitSubtitle(ctx, match && subtitle ? ["", subtitle] : [subtitle], width - x - 30 - logosW), x, 158);
  const logoSize = 132;
  let logoRight = width - 30;
  if (brand) {
    drawBrandLogo(ctx, brand, logoRight - logoSize, 30, logoSize);
    logoRight -= logoSize + 22;
  }
  if (league) {
    ctx.fillStyle = "#ffffff";
    ctx.beginPath();
    ctx.arc(logoRight - logoSize / 2, 30 + logoSize / 2, logoSize / 2, 0, Math.PI * 2);
    ctx.fill();
    const inner = logoSize * 0.62;
    ctx.drawImage(league, logoRight - logoSize / 2 - inner / 2, 30 + logoSize / 2 - inner / 2, inner, inner);
  }
}

/** Pitch outline, boxes, centre circle and spots for a 105 x 68 pitch whose top-left corner is (left, top), `scale` pixels per metre. */
export function drawPitchMarkings(ctx: CanvasRenderingContext2D, { left, top, scale, color = "rgba(148,163,184,0.32)" }: { left: number; top: number; scale: number; color?: string }) {
  const [pw, ph] = [105, 68];
  const px = (x: number) => left + x * scale;
  const py = (y: number) => top + (ph - y) * scale;
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  const box = (x0: number, y0: number, x1: number, y1: number) => ctx.strokeRect(px(x0), py(y1), (x1 - x0) * scale, (y1 - y0) * scale);
  box(0, 0, pw, ph);
  box(0, 13.84, 16.5, 54.16);
  box(pw - 16.5, 13.84, pw, 54.16);
  box(0, 24.84, 5.5, 43.16);
  box(pw - 5.5, 24.84, pw, 43.16);
  ctx.beginPath();
  ctx.moveTo(px(pw / 2), py(0));
  ctx.lineTo(px(pw / 2), py(ph));
  ctx.moveTo(px(pw / 2) + 9.15 * scale, py(ph / 2));
  ctx.arc(px(pw / 2), py(ph / 2), 9.15 * scale, 0, Math.PI * 2);
  ctx.stroke();
  ctx.fillStyle = color;
  for (const x of [11, pw - 11, pw / 2]) {
    ctx.beginPath();
    ctx.arc(px(x), py(ph / 2), 4, 0, Math.PI * 2);
    ctx.fill();
  }
}
