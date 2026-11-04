import { CHART_FONT_FAMILY } from "../../lib/theme";
import { drawExportHeader, drawFooter, drawPitchMarkings, ensureExportFonts, EXPORT_BG, EXPORT_MUTED, loadImage, loadRemoteImage } from "../exportFrame";
import { PITCH_H, PITCH_W } from "./pitch";

export type MarkerKind = "pass" | "carry" | "takeon" | "defensive" | "shot" | "other";

export const MARKER_LABELS: Record<MarkerKind, string> = { pass: "Pass", carry: "Carry", takeon: "Take-on", defensive: "Defensive action", shot: "Shot (rebound)", other: "Action" };

export type ZoneLeaderExportItem = {
  /** where this leader's counted actions happened inside the zone, in pitch units */
  points?: { x: number; y: number; kind: MarkerKind }[];
  zone: { x1: number; x2: number; y1: number; y2: number };
  name: string;
  color: string;
  valueText: string;
  photo: string | null;
};

export type ZoneLeadersExport = {
  title: string;
  subtitle: string;
  leagueLogo?: string;
  leaders: ZoneLeaderExportItem[];
  /** legend text for plain dots (every action that is not split by type) */
  dotLabel?: string;
};

// Same look as the social-media zone-leaders map: dark canvas, full-width pitch, big ringed photos, coloured zones.
const W = 2000;
const PITCH_X = 30;
const PITCH_Y = 212;
const PITCH_PX_W = W - PITCH_X * 2;
const PX = PITCH_PX_W / PITCH_W;
const H = Math.round(PITCH_Y + PITCH_H * PX + 130);
const PITCH_LINE = "rgba(148,163,184,0.32)";
const PHOTO = 6 * PX;

function drawMarker(ctx: CanvasRenderingContext2D, kind: MarkerKind, x: number, y: number, r: number) {
  ctx.beginPath();
  if (kind === "carry") {
    ctx.moveTo(x - r * 0.8, y - r);
    ctx.lineTo(x + r * 1.1, y);
    ctx.lineTo(x - r * 0.8, y + r);
  } else if (kind === "defensive") {
    ctx.moveTo(x - r, y + r * 0.8);
    ctx.lineTo(x, y - r * 1.1);
    ctx.lineTo(x + r, y + r * 0.8);
  } else if (kind === "takeon") {
    ctx.moveTo(x, y - r * 1.2);
    ctx.lineTo(x + r * 1.2, y);
    ctx.lineTo(x, y + r * 1.2);
    ctx.lineTo(x - r * 1.2, y);
  } else if (kind === "shot") {
    for (let i = 0; i < 10; i += 1) {
      const rad = i % 2 === 0 ? r * 1.4 : r * 0.6;
      const a = -Math.PI / 2 + (i * Math.PI) / 5;
      ctx[i === 0 ? "moveTo" : "lineTo"](x + Math.cos(a) * rad, y + Math.sin(a) * rad);
    }
  } else {
    ctx.arc(x, y, r, 0, Math.PI * 2);
  }
  ctx.closePath();
  ctx.fill();
}

export async function renderZoneLeadersPng({ title, subtitle, leagueLogo, leaders, dotLabel }: ZoneLeadersExport): Promise<string | null> {
  const canvas = document.createElement("canvas");
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  await ensureExportFonts();

  const [brand, league, ...photos] = await Promise.all([
    loadImage("/logos/Logo-Dark.png"),
    loadRemoteImage(leagueLogo),
    ...leaders.map((l) => loadRemoteImage(l.photo)),
  ]);

  ctx.fillStyle = EXPORT_BG;
  ctx.fillRect(0, 0, W, H);

  drawExportHeader(ctx, { width: W, title, subtitle, brand, league });

  // zones, then pitch markings on top
  const px = (x: number) => PITCH_X + x * PX;
  const py = (y: number) => PITCH_Y + (PITCH_H - y) * PX;
  for (const l of leaders) {
    ctx.fillStyle = `${l.color}1f`;
    ctx.fillRect(px(l.zone.x1), py(l.zone.y2), (l.zone.x2 - l.zone.x1) * PX, (l.zone.y2 - l.zone.y1) * PX);
    ctx.strokeStyle = PITCH_LINE;
    ctx.lineWidth = 1.5;
    ctx.strokeRect(px(l.zone.x1), py(l.zone.y2), (l.zone.x2 - l.zone.x1) * PX, (l.zone.y2 - l.zone.y1) * PX);
  }
  drawPitchMarkings(ctx, { left: PITCH_X, top: PITCH_Y, scale: PX, color: PITCH_LINE });

  // the leader's own actions as scatter points, under the photo and labels
  const usedKinds = new Set<MarkerKind>();
  for (const l of leaders) {
    ctx.fillStyle = l.color;
    ctx.globalAlpha = 0.92;
    for (const pt of l.points ?? []) {
      drawMarker(ctx, pt.kind, px(pt.x), py(pt.y), 7.5);
      usedKinds.add(pt.kind);
    }
  }
  ctx.globalAlpha = 1;

  // photo + surname + value, stacked and centred in each zone
  const nameSize = 25;
  const valueSize = 29;
  const stackH = PHOTO + 14 + nameSize + 14 + valueSize;
  leaders.forEach((l, i) => {
    const cx = px((l.zone.x1 + l.zone.x2) / 2);
    const cy = py((l.zone.y1 + l.zone.y2) / 2);
    const top = cy - stackH / 2;
    const x = cx - PHOTO / 2;
    ctx.fillStyle = "#0f2236";
    ctx.fillRect(x, top, PHOTO, PHOTO);
    const img = photos[i];
    if (img) {
      ctx.drawImage(img, x, top, PHOTO, PHOTO);
    } else {
      ctx.fillStyle = l.color;
      ctx.font = `700 ${PHOTO * 0.34}px ${CHART_FONT_FAMILY}`;
      ctx.textAlign = "center";
      ctx.fillText(l.name.split(" ").map((w) => w[0]).slice(0, 2).join(""), cx, top + PHOTO * 0.6);
    }
    ctx.strokeStyle = l.color;
    ctx.lineWidth = 6;
    ctx.strokeRect(x - 1, top - 1, PHOTO + 2, PHOTO + 2);

    ctx.textAlign = "center";
    ctx.lineJoin = "round";
    ctx.lineWidth = 7;
    ctx.strokeStyle = "rgba(8,18,30,0.85)";
    ctx.font = `700 ${nameSize}px ${CHART_FONT_FAMILY}`;
    const nameY = top + PHOTO + 14 + nameSize;
    const surname = l.name.split(" ").slice(-1)[0];
    ctx.strokeText(surname, cx, nameY);
    ctx.fillStyle = "#ffffff";
    ctx.fillText(surname, cx, nameY);
    ctx.font = `700 ${valueSize}px ${CHART_FONT_FAMILY}`;
    const valueY = nameY + 14 + valueSize;
    ctx.strokeText(l.valueText, cx, valueY);
    ctx.fillStyle = l.color;
    ctx.fillText(l.valueText, cx, valueY);
  });

  // marker legend, then footer
  ctx.textAlign = "left";
  ctx.font = `500 26px ${CHART_FONT_FAMILY}`;
  let legendX = 38;
  const legendY = PITCH_Y + PITCH_H * PX + 52;
  for (const kind of Object.keys(MARKER_LABELS) as MarkerKind[]) {
    if (!usedKinds.has(kind)) continue;
    ctx.fillStyle = "#ffffff";
    drawMarker(ctx, kind, legendX + 8, legendY - 9, 8);
    const text = kind === "other" && dotLabel ? dotLabel : MARKER_LABELS[kind];
    ctx.fillText(text, legendX + 32, legendY);
    legendX += 32 + ctx.measureText(text).width + 44;
  }
  drawFooter(ctx, { left: 30, right: W - 30, baseline: H - 26, size: 24, extra: "Attacking left to right →" });

  return canvas.toDataURL("image/png");
}
