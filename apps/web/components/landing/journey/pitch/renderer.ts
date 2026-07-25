import {
  buildTimeline,
  type CameraFraming,
  type ChapterSequence,
  type ChapterTreatment,
  type SequenceTimeline,
  type SequenceTimelineEvent,
} from "../../../../lib/landing-sequences";
import { loadedImage, preloadImages } from "./images";
import { createProjection, type Projection } from "./projection";
import { drawTreatment } from "./treatments";

export type ChapterConfig = {
  treatment: ChapterTreatment;
  sequence: ChapterSequence;
};

export type FrameState = {
  vt: number; // virtual seconds into the sequence
  t: number; // 0-1 progress
  timeline: SequenceTimeline;
  sequence: ChapterSequence;
  ball: { x: number; y: number } | null;
  activeEvent: SequenceTimelineEvent | null;
  now: number;
  width: number;
  height: number;
  alpha: number;
};

const LINE_COLOR = "rgba(163, 230, 53, 0.24)";
const LINE_SOFT = "rgba(163, 230, 53, 0.12)";
const TURF_TOP = "rgba(8, 30, 32, 0.92)";
const TURF_BOTTOM = "rgba(4, 16, 20, 0.95)";
const FADE_MS = 280;

export const easeOutCubic = (t: number) => 1 - Math.pow(1 - t, 3);
export const clamp01 = (t: number) => Math.max(0, Math.min(1, t));

// Straight lines in pitch space bend correctly under perspective when sampled.
export function tracePath(
  ctx: CanvasRenderingContext2D,
  proj: Projection,
  points: Array<[number, number]>,
) {
  points.forEach(([x, y], i) => {
    const p = proj(x, y);
    if (i === 0) ctx.moveTo(p.sx, p.sy);
    else ctx.lineTo(p.sx, p.sy);
  });
}

export function sampleSegment(
  x0: number,
  y0: number,
  x1: number,
  y1: number,
  fraction = 1,
  samples = 14,
): Array<[number, number]> {
  const out: Array<[number, number]> = [];
  for (let i = 0; i <= samples; i += 1) {
    const t = (i / samples) * fraction;
    out.push([x0 + (x1 - x0) * t, y0 + (y1 - y0) * t]);
  }
  return out;
}

// rx/ry in Opta units; the real 9.15m centre circle is 8.7 x-units by
// 13.5 y-units (105x68m pitch), which the projection's aspect renders round
function ellipsePoints(cx: number, cy: number, rx: number, ry: number, samples = 40) {
  const out: Array<[number, number]> = [];
  for (let i = 0; i <= samples; i += 1) {
    const a = (i / samples) * Math.PI * 2;
    out.push([cx + Math.cos(a) * rx, cy + Math.sin(a) * ry]);
  }
  return out;
}

function eventLerp(event: SequenceTimelineEvent, vt: number) {
  if (event.end_x == null || event.end_y == null) return { x: event.x, y: event.y };
  const f = easeOutCubic(clamp01((vt - event.start) / (event.end - event.start)));
  return {
    x: event.x + (event.end_x - event.x) * f,
    y: event.y + (event.end_y - event.y) * f,
  };
}

type PlayerMarker = {
  player: string;
  team: string;
  x: number;
  y: number;
  isActor: boolean;
};

const MOVER_TYPES = new Set(["Carry", "TakeOn"]);

// A player stands at their next event's origin before it fires; movers
// (carries, take-ons) travel with the ball during their event.
function playerPositions(
  timeline: SequenceTimeline,
  vt: number,
  activeEvent: SequenceTimelineEvent | null,
): PlayerMarker[] {
  const markers = new Map<string, PlayerMarker>();
  for (const event of timeline.events) {
    const existing = markers.get(event.player);
    if (event.start > vt) {
      if (!existing) {
        markers.set(event.player, {
          player: event.player,
          team: event.team,
          x: event.x,
          y: event.y,
          isActor: false,
        });
      }
      continue;
    }
    const moved =
      MOVER_TYPES.has(event.type) && event.end_x != null && event.end_y != null;
    const pos =
      event.end <= vt
        ? moved
          ? { x: event.end_x as number, y: event.end_y as number }
          : { x: event.x, y: event.y }
        : moved
          ? eventLerp(event, vt)
          : { x: event.x, y: event.y };
    markers.set(event.player, {
      player: event.player,
      team: event.team,
      ...pos,
      isActor: activeEvent?.player === event.player,
    });
  }
  return [...markers.values()];
}

function ballPosition(timeline: SequenceTimeline, vt: number) {
  let ball: { x: number; y: number } | null = null;
  for (const event of timeline.events) {
    if (event.start > vt) break;
    if (event.end <= vt) {
      ball =
        event.end_x != null && event.end_y != null
          ? { x: event.end_x, y: event.end_y }
          : { x: event.x, y: event.y };
    } else {
      ball = eventLerp(event, vt);
    }
  }
  return ball ?? (timeline.events[0] ? { x: timeline.events[0].x, y: timeline.events[0].y } : null);
}

function initials(name: string) {
  return name
    .split(/\s+/)
    .map((part) => part[0] ?? "")
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

export class PitchRenderer {
  camera: CameraFraming;

  private chapter: ChapterConfig | null = null;
  private prevChapter: ChapterConfig | null = null;
  private timeline: SequenceTimeline | null = null;
  private prevTimeline: SequenceTimeline | null = null;
  private prevProgress = 0;
  private fadeStart = 0;
  private progress = 0;
  private dim = 0;

  constructor(camera: CameraFraming) {
    this.camera = { ...camera, center: [...camera.center] };
  }

  setCamera(camera: CameraFraming) {
    this.camera = { ...camera, center: [...camera.center] };
  }

  setProgress(t: number) {
    this.progress = clamp01(t);
  }

  setDim(v: number) {
    this.dim = clamp01(v);
  }

  get isFading() {
    return this.prevChapter != null;
  }

  beginChapter(config: ChapterConfig, now: number) {
    if (this.chapter?.treatment === config.treatment) return;
    this.prevChapter = this.chapter;
    this.prevTimeline = this.timeline;
    this.prevProgress = this.progress;
    this.fadeStart = now;
    this.chapter = config;
    this.timeline = buildTimeline(config.sequence.events);
    preloadImages(config.sequence.playerImages);
  }

  draw(ctx: CanvasRenderingContext2D, width: number, height: number, now: number) {
    ctx.clearRect(0, 0, width, height);
    const proj = createProjection(this.camera, width, height);

    this.drawPitch(ctx, proj, height);

    const fade = this.prevChapter
      ? clamp01((now - this.fadeStart) / FADE_MS)
      : 1;
    if (this.prevChapter && this.prevTimeline && fade < 1) {
      this.drawChapter(
        ctx, proj, width, height, now,
        this.prevChapter, this.prevTimeline, this.prevProgress, 1 - fade,
      );
    } else if (fade >= 1) {
      this.prevChapter = null;
      this.prevTimeline = null;
    }
    if (this.chapter && this.timeline) {
      this.drawChapter(
        ctx, proj, width, height, now,
        this.chapter, this.timeline, this.progress, fade,
      );
    }

    if (this.dim > 0) {
      ctx.fillStyle = `rgba(2, 11, 18, ${this.dim})`;
      ctx.fillRect(0, 0, width, height);
    }
  }

  private drawChapter(
    ctx: CanvasRenderingContext2D,
    proj: Projection,
    width: number,
    height: number,
    now: number,
    chapter: ChapterConfig,
    timeline: SequenceTimeline,
    progress: number,
    alpha: number,
  ) {
    if (alpha <= 0.01) return;
    const vt = progress * timeline.duration;
    const activeEvent =
      timeline.events.find((e) => e.start <= vt && vt < e.end) ?? null;
    const frame: FrameState = {
      vt,
      t: progress,
      timeline,
      sequence: chapter.sequence,
      ball: ballPosition(timeline, vt),
      activeEvent,
      now,
      width,
      height,
      alpha,
    };

    ctx.save();
    ctx.globalAlpha = alpha;
    this.drawTrails(ctx, proj, frame);
    this.drawPlayers(ctx, proj, frame);
    drawTreatment(chapter.treatment, ctx, proj, frame);
    this.drawBall(ctx, proj, frame);
    ctx.restore();
  }

  private drawPitch(
    ctx: CanvasRenderingContext2D,
    proj: Projection,
    height: number,
  ) {
    // turf quad, slightly oversized so edges never show under camera moves
    const corners: Array<[number, number]> = [
      [-8, -8], [108, -8], [108, 108], [-8, 108],
    ];
    const gradient = ctx.createLinearGradient(0, 0, 0, height);
    gradient.addColorStop(0, TURF_TOP);
    gradient.addColorStop(1, TURF_BOTTOM);
    ctx.beginPath();
    tracePath(ctx, proj, [...corners, corners[0]]);
    ctx.fillStyle = gradient;
    ctx.fill();

    // mowing stripes
    ctx.strokeStyle = LINE_SOFT;
    for (let x = 10; x < 100; x += 10) {
      ctx.beginPath();
      tracePath(ctx, proj, sampleSegment(x, 0, x, 100, 1, 10));
      ctx.globalAlpha = 0.28;
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.globalAlpha = 1;
    }

    ctx.strokeStyle = LINE_COLOR;
    ctx.lineWidth = 1.4;
    const stroke = (points: Array<[number, number]>) => {
      ctx.beginPath();
      tracePath(ctx, proj, points);
      ctx.stroke();
    };
    // outline + halfway line
    stroke([[0, 0], [100, 0], [100, 100], [0, 100], [0, 0]]);
    stroke(sampleSegment(50, 0, 50, 100, 1, 10));
    stroke(ellipsePoints(50, 50, 8.7, 13.5));
    // penalty areas + six-yard boxes (Opta-ish proportions)
    stroke([[0, 21.1], [17, 21.1], [17, 78.9], [0, 78.9]]);
    stroke([[100, 21.1], [83, 21.1], [83, 78.9], [100, 78.9]]);
    stroke([[0, 36.8], [5.8, 36.8], [5.8, 63.2], [0, 63.2]]);
    stroke([[100, 36.8], [94.2, 36.8], [94.2, 63.2], [100, 63.2]]);
    // goals
    ctx.lineWidth = 2.2;
    stroke([[0, 45.2], [-1.8, 45.2], [-1.8, 54.8], [0, 54.8]]);
    stroke([[100, 45.2], [101.8, 45.2], [101.8, 54.8], [100, 54.8]]);
  }

  private drawTrails(
    ctx: CanvasRenderingContext2D,
    proj: Projection,
    frame: FrameState,
  ) {
    for (const event of frame.timeline.events) {
      if (event.start > frame.vt) break;
      if (event.end_x == null || event.end_y == null) continue;
      const fraction =
        event.end <= frame.vt
          ? 1
          : easeOutCubic(clamp01((frame.vt - event.start) / (event.end - event.start)));
      const color = frame.sequence.teamColors[event.team] ?? "#a3e635";
      const done = event.end <= frame.vt;
      const start = proj(event.x, event.y);
      const head = proj(
        event.x + (event.end_x - event.x) * fraction,
        event.y + (event.end_y - event.y) * fraction,
      );
      const grad = ctx.createLinearGradient(start.sx, start.sy, head.sx, head.sy);
      grad.addColorStop(0, "rgba(163, 230, 53, 0)");
      grad.addColorStop(1, done ? `${color}aa` : color);
      ctx.beginPath();
      tracePath(
        ctx,
        proj,
        sampleSegment(event.x, event.y, event.end_x, event.end_y, fraction),
      );
      ctx.strokeStyle = grad;
      ctx.lineWidth = done ? 2 : 3.2;
      ctx.lineCap = "round";
      ctx.globalAlpha = frame.alpha * (done ? 0.55 : 1);
      ctx.stroke();
      ctx.globalAlpha = frame.alpha;
    }
  }

  private drawPlayers(
    ctx: CanvasRenderingContext2D,
    proj: Projection,
    frame: FrameState,
  ) {
    const focus = frame.sequence.focusPlayer;
    const markers = playerPositions(frame.timeline, frame.vt, frame.activeEvent)
      .map((m) => ({ ...m, p: proj(m.x, m.y) }))
      .sort((a, b) => a.p.sy - b.p.sy); // far-to-near
    for (const marker of markers) {
      const dimmed = focus != null && marker.player !== focus;
      const avatar = loadedImage(frame.sequence.playerImages?.[marker.player]);
      const boost = frame.sequence.avatarScale ?? 1;
      const r = Math.min(
        Math.max((avatar ? 20 : 9) * boost * marker.p.scale, avatar ? 13 : 5),
        52,
      );
      const color = frame.sequence.teamColors[marker.team] ?? "#94a3b8";
      ctx.globalAlpha = frame.alpha * (dimmed ? 0.25 : 1);
      // grounding shadow sells the 2.5D
      ctx.beginPath();
      ctx.ellipse(marker.p.sx, marker.p.sy + r * 0.75, r * 1.15, r * 0.4, 0, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(0, 0, 0, 0.45)";
      ctx.fill();
      if (avatar) {
        ctx.save();
        ctx.beginPath();
        ctx.arc(marker.p.sx, marker.p.sy, r, 0, Math.PI * 2);
        ctx.fillStyle = "#0b1c28";
        ctx.fill();
        ctx.clip();
        ctx.drawImage(avatar, marker.p.sx - r, marker.p.sy - r, r * 2, r * 2);
        ctx.restore();
        ctx.beginPath();
        ctx.arc(marker.p.sx, marker.p.sy, r, 0, Math.PI * 2);
        ctx.strokeStyle = color;
        ctx.lineWidth = 2.2;
        ctx.stroke();
      } else {
        ctx.beginPath();
        ctx.arc(marker.p.sx, marker.p.sy, r, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
      }
      if (marker.isActor || marker.player === focus) {
        ctx.beginPath();
        ctx.arc(marker.p.sx, marker.p.sy, r + 3, 0, Math.PI * 2);
        ctx.strokeStyle = "#a3e635";
        ctx.lineWidth = 2;
        ctx.stroke();
      }
      const fontSize = Math.min(Math.max(10 * marker.p.scale, 8), 14);
      ctx.font = `600 ${fontSize}px "JetBrains Mono", monospace`;
      ctx.textAlign = "center";
      ctx.fillStyle = "rgba(244, 247, 251, 0.85)";
      ctx.fillText(initials(marker.player), marker.p.sx, marker.p.sy - r - 5);
    }
    ctx.globalAlpha = frame.alpha;
  }

  private drawBall(
    ctx: CanvasRenderingContext2D,
    proj: Projection,
    frame: FrameState,
  ) {
    if (!frame.ball) return;
    const p = proj(frame.ball.x, frame.ball.y);
    const r = Math.min(Math.max(4.5 * p.scale, 3), 15);
    ctx.beginPath();
    ctx.arc(p.sx, p.sy, r + 4, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(255, 255, 255, 0.14)";
    ctx.fill();
    ctx.beginPath();
    ctx.arc(p.sx, p.sy, r, 0, Math.PI * 2);
    ctx.fillStyle = "#f8fafc";
    ctx.fill();
  }
}
