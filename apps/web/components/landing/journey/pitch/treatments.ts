import type { ChapterTreatment } from "../../../../lib/landing-sequences";
import { loadedImage } from "./images";
import type { Projection } from "./projection";
import type { FrameState } from "./renderer";

const ACCENT = "#a3e635";
const ACCENT_2 = "#22d3ee";

const clamp01 = (t: number) => Math.max(0, Math.min(1, t));

function trace(
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

// --- Match Dynamics: average positions with a Voronoi control map ---------

type Pt = [number, number];

// Voronoi via half-plane clipping, same approach as LineupsPanel.voronoiCells
// — fine for the ~20 average-position seeds we draw.
function voronoiCells(points: Pt[]): Pt[][] {
  const bounds: Pt[] = [[0, 0], [100, 0], [100, 100], [0, 100]];
  return points.map(([px, py], i) => {
    let cell = bounds;
    for (let j = 0; j < points.length; j += 1) {
      if (j === i || !cell.length) continue;
      const [qx, qy] = points[j];
      const mx = (px + qx) / 2;
      const my = (py + qy) / 2;
      const dx = qx - px;
      const dy = qy - py;
      const inside = ([x, y]: Pt) => (x - mx) * dx + (y - my) * dy <= 0;
      const next: Pt[] = [];
      for (let k = 0; k < cell.length; k += 1) {
        const current = cell[k];
        const previous = cell[(k + cell.length - 1) % cell.length];
        if (inside(current) !== inside(previous)) {
          const t =
            ((mx - previous[0]) * dx + (my - previous[1]) * dy) /
            ((current[0] - previous[0]) * dx + (current[1] - previous[1]) * dy);
          next.push([
            previous[0] + t * (current[0] - previous[0]),
            previous[1] + t * (current[1] - previous[1]),
          ]);
        }
        if (inside(current)) next.push(current);
      }
      cell = next;
    }
    return cell;
  });
}

function drawMomentum(
  ctx: CanvasRenderingContext2D,
  proj: Projection,
  frame: FrameState,
) {
  const seeds = frame.sequence.averagePositions ?? [];
  if (seeds.length < 3) return;
  const cells = voronoiCells(seeds.map((s) => [s.x, s.y] as Pt));

  // cells fade in first, then avatars pop in staggered by index
  const cellReveal = clamp01(frame.t / 0.25);
  ctx.globalAlpha = frame.alpha * cellReveal;
  cells.forEach((cell, i) => {
    if (cell.length < 3) return;
    const color = frame.sequence.teamColors[seeds[i].team] ?? "#94a3b8";
    ctx.beginPath();
    trace(ctx, proj, [...cell, cell[0]]);
    ctx.fillStyle = color;
    ctx.globalAlpha = frame.alpha * cellReveal * 0.13;
    ctx.fill();
    ctx.globalAlpha = frame.alpha * cellReveal;
    ctx.strokeStyle = "rgba(163, 230, 53, 0.3)";
    ctx.lineWidth = 1;
    ctx.stroke();
  });

  const drawOrder = seeds
    .map((seed, i) => ({ seed, i, p: proj(seed.x, seed.y) }))
    .sort((a, b) => a.p.sy - b.p.sy); // far-to-near
  for (const { seed, i, p } of drawOrder) {
    const pop = clamp01((frame.t - 0.15 - (i / seeds.length) * 0.35) / 0.12);
    if (pop <= 0) continue;
    const color = frame.sequence.teamColors[seed.team] ?? "#94a3b8";
    const r = Math.max(seed.size * 0.6 * p.scale, 13) * (0.6 + pop * 0.4);
    ctx.globalAlpha = frame.alpha * pop;
    const avatar = loadedImage(frame.sequence.playerImages?.[seed.player]);
    if (avatar) {
      ctx.save();
      ctx.beginPath();
      ctx.arc(p.sx, p.sy, r, 0, Math.PI * 2);
      ctx.fillStyle = "#0b1c28";
      ctx.fill();
      ctx.clip();
      ctx.drawImage(avatar, p.sx - r, p.sy - r, r * 2, r * 2);
      ctx.restore();
    } else {
      ctx.beginPath();
      ctx.arc(p.sx, p.sy, r, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();
    }
    ctx.beginPath();
    ctx.arc(p.sx, p.sy, r, 0, Math.PI * 2);
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.stroke();
    const surname = seed.player.split(" ").slice(-1)[0];
    ctx.font = '600 9px "JetBrains Mono", monospace';
    ctx.textAlign = "center";
    ctx.fillStyle = "rgba(216, 230, 242, 0.8)";
    ctx.fillText(surname.toUpperCase(), p.sx, p.sy + r + 11);
  }
  ctx.globalAlpha = frame.alpha;
}

// --- Shots + SCA: xG ring + shot cone, then a goal-mouth zoom finale ------

// Tactical goal-mouth panel: frame + net, keeper in place, ball buried in the
// far corner. Zooms in over the pitch once the SCA chain has played out.
function drawGoalMouthZoom(
  ctx: CanvasRenderingContext2D,
  frame: FrameState,
  reveal: number,
) {
  const ease = reveal * reveal * (3 - 2 * reveal);
  const goalEvent = frame.timeline.events.find((e) => e.type === "Goal");

  // dim the pitch behind the panel
  ctx.fillStyle = `rgba(2, 11, 18, ${0.62 * ease})`;
  ctx.fillRect(0, 0, frame.width, frame.height);

  const cx = frame.width * 0.34;
  const cy = frame.height * 0.44;
  const zoom = 0.82 + 0.18 * ease;
  const gw = Math.min(frame.width * 0.44, 620) * zoom;
  const gh = gw * 0.32;
  const left = cx - gw / 2;
  const right = cx + gw / 2;
  const top = cy - gh / 2;
  const ground = cy + gh / 2;

  ctx.globalAlpha = frame.alpha * ease;

  // net
  ctx.strokeStyle = "rgba(216, 230, 242, 0.16)";
  ctx.lineWidth = 1;
  const mesh = gw / 16;
  for (let x = left + mesh; x < right; x += mesh) {
    ctx.beginPath();
    ctx.moveTo(x, top);
    ctx.lineTo(x, ground);
    ctx.stroke();
  }
  for (let y = top + mesh; y < ground; y += mesh) {
    ctx.beginPath();
    ctx.moveTo(left, y);
    ctx.lineTo(right, y);
    ctx.stroke();
  }

  // frame + ground line
  ctx.strokeStyle = "rgba(244, 247, 251, 0.92)";
  ctx.lineWidth = 5;
  ctx.lineCap = "round";
  ctx.beginPath();
  ctx.moveTo(left, ground);
  ctx.lineTo(left, top);
  ctx.lineTo(right, top);
  ctx.lineTo(right, ground);
  ctx.stroke();
  ctx.strokeStyle = "rgba(163, 230, 53, 0.4)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(left - gw * 0.12, ground);
  ctx.lineTo(right + gw * 0.12, ground);
  ctx.stroke();

  // keeper, beaten towards the middle-right
  const keeper = loadedImage(frame.sequence.playerImages?.["Jan Oblak"]);
  const kx = cx + gw * 0.1;
  const kr = gh * 0.24;
  const ky = ground - kr * 1.4;
  if (keeper) {
    ctx.save();
    ctx.beginPath();
    ctx.arc(kx, ky, kr, 0, Math.PI * 2);
    ctx.fillStyle = "#0b1c28";
    ctx.fill();
    ctx.clip();
    ctx.drawImage(keeper, kx - kr, ky - kr, kr * 2, kr * 2);
    ctx.restore();
  } else {
    ctx.beginPath();
    ctx.arc(kx, ky, kr, 0, Math.PI * 2);
    ctx.fillStyle = "#f97316";
    ctx.fill();
  }
  ctx.beginPath();
  ctx.arc(kx, ky, kr, 0, Math.PI * 2);
  ctx.strokeStyle = "#f97316";
  ctx.lineWidth = 2;
  ctx.stroke();
  ctx.font = '600 10px "JetBrains Mono", monospace';
  ctx.textAlign = "center";
  ctx.fillStyle = "rgba(253, 186, 116, 0.9)";
  ctx.fillText("OBLAK · GK", kx, ground + 16);

  // ball trajectory into the low far corner, away from the keeper
  const bx = left + gw * 0.09;
  const by = ground - gh * 0.14;
  const sx = cx - gw * 0.04;
  const sy = ground + gh * 0.85;
  const mx = (sx + bx) / 2 - gw * 0.05;
  const my = (sy + by) / 2 - gh * 0.5;
  ctx.setLineDash([7, 7]);
  ctx.strokeStyle = ACCENT_2;
  ctx.lineWidth = 2.5;
  ctx.beginPath();
  ctx.moveTo(sx, sy);
  ctx.quadraticCurveTo(mx, my, bx, by);
  ctx.stroke();
  ctx.setLineDash([]);
  const pulse = 1 + 0.15 * Math.sin(frame.now / 220);
  ctx.beginPath();
  ctx.arc(bx, by, 7, 0, Math.PI * 2);
  ctx.fillStyle = "#f8fafc";
  ctx.fill();
  ctx.beginPath();
  ctx.arc(bx, by, 13 * pulse, 0, Math.PI * 2);
  ctx.strokeStyle = ACCENT_2;
  ctx.lineWidth = 2;
  ctx.stroke();

  // caption
  ctx.font = '600 12px "JetBrains Mono", monospace';
  ctx.textAlign = "center";
  ctx.fillStyle = "rgba(215, 245, 138, 0.95)";
  const xg = goalEvent?.xg?.toFixed(2) ?? "0.60";
  const xgot = goalEvent?.xgot?.toFixed(2) ?? "0.88";
  ctx.fillText(`MIKAUTADZE 39' · xG ${xg} · xGOT ${xgot}`, cx, top - 18);

  ctx.globalAlpha = frame.alpha;
}

const ACTION_LABELS: Record<string, string> = {
  Pass: "PASS",
  Carry: "CARRY",
  TakeOn: "TAKE-ON",
  Goal: "SHOT",
};

function drawActionLabel(
  ctx: CanvasRenderingContext2D,
  sx: number,
  sy: number,
  text: string,
  alpha: number,
) {
  ctx.font = '600 10px "JetBrains Mono", monospace';
  const w = ctx.measureText(text).width + 14;
  ctx.globalAlpha = alpha * 0.82;
  ctx.fillStyle = "rgba(2, 12, 19, 0.85)";
  ctx.beginPath();
  ctx.roundRect(sx - w / 2, sy - 20, w, 16, 8);
  ctx.fill();
  ctx.globalAlpha = alpha;
  ctx.textAlign = "center";
  ctx.fillStyle = "#d7f58a";
  ctx.fillText(text, sx, sy - 8);
}

function drawShots(
  ctx: CanvasRenderingContext2D,
  proj: Projection,
  frame: FrameState,
) {
  // label every action in the SCA chain as it fires
  for (const event of frame.timeline.events) {
    if (event.start > frame.vt) continue;
    const appear = clamp01((frame.vt - event.start) / 0.3);
    const ex = event.end_x ?? event.x;
    const ey = event.end_y ?? event.y;
    const mid = proj((event.x + ex) / 2, (event.y + ey) / 2);
    const surname = event.player.split(" ").slice(-1)[0].toUpperCase();
    const action = ACTION_LABELS[event.type] ?? event.type.toUpperCase();
    drawActionLabel(ctx, mid.sx, mid.sy - 14, `${surname} · ${action}`, frame.alpha * appear);
  }
  ctx.globalAlpha = frame.alpha;

  for (const event of frame.timeline.events) {
    if (event.xg == null || event.start > frame.vt) continue;
    const origin = proj(event.x, event.y);
    const pulse = 1 + 0.12 * Math.sin(frame.now / 260);
    const ringR = Math.max(event.xg * 90, 14) * origin.scale * pulse;
    ctx.beginPath();
    ctx.arc(origin.sx, origin.sy, ringR, 0, Math.PI * 2);
    ctx.strokeStyle = "rgba(163, 230, 53, 0.85)";
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.font = '600 11px "JetBrains Mono", monospace';
    ctx.textAlign = "center";
    ctx.fillStyle = "rgba(215, 245, 138, 0.9)";
    ctx.fillText(`xG ${event.xg.toFixed(2)}`, origin.sx, origin.sy - ringR - 8);

    // shot cone to the goal mouth
    const reveal = clamp01((frame.vt - event.start) / Math.max(event.end - event.start, 0.01));
    if (reveal > 0) {
      ctx.beginPath();
      trace(ctx, proj, [
        [event.x, event.y],
        [100, 45.2],
        [100, 54.8],
        [event.x, event.y],
      ]);
      ctx.fillStyle = `rgba(34, 211, 238, ${0.14 * reveal})`;
      ctx.fill();
    }
    // goal flash
    if (event.type === "Goal" && event.end <= frame.vt) {
      const since = frame.vt - event.end;
      const flash = Math.max(0, 1 - since / 1.2);
      if (flash > 0) {
        const goal = proj(100, 50);
        const radius = 90 * goal.scale * (1.6 - flash * 0.6);
        const glow = ctx.createRadialGradient(goal.sx, goal.sy, 0, goal.sx, goal.sy, radius);
        glow.addColorStop(0, `rgba(34, 211, 238, ${0.5 * flash})`);
        glow.addColorStop(1, "rgba(34, 211, 238, 0)");
        ctx.fillStyle = glow;
        ctx.beginPath();
        ctx.arc(goal.sx, goal.sy, radius, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }

  // the camera dive (LandingJourney finaleCamera) runs first; once it is
  // near the goal the tactical goal-mouth map fades in over it
  const zoomReveal = clamp01((frame.t - 0.86) / 0.12);
  if (zoomReveal > 0) drawGoalMouthZoom(ctx, frame, zoomReveal);
}

// --- In Possession: the full match passing network ------------------------
// Choreography: nodes pop in -> links draw -> passing triangles glow ->
// the hub player is picked out with a stats readout.

function drawPassNetwork(
  ctx: CanvasRenderingContext2D,
  proj: Projection,
  frame: FrameState,
) {
  const network = frame.sequence.passNetwork;
  if (!network?.nodes || !network.edges) return;
  const nodes = network.nodes;
  const edges = network.edges;
  const nodeById = new Map(nodes.map((n) => [n.player_id, n]));

  // passing triangles: node triples whose three links all exist
  const linked = new Set(
    edges.map((e) => `${Math.min(e.source_id, e.target_id)}-${Math.max(e.source_id, e.target_id)}`),
  );
  const has = (a: number, b: number) => linked.has(`${Math.min(a, b)}-${Math.max(a, b)}`);
  const triangles: Array<[number, number, number]> = [];
  for (let i = 0; i < nodes.length; i += 1)
    for (let j = i + 1; j < nodes.length; j += 1)
      for (let k = j + 1; k < nodes.length; k += 1) {
        const [a, b, c] = [nodes[i].player_id, nodes[j].player_id, nodes[k].player_id];
        if (has(a, b) && has(b, c) && has(a, c)) triangles.push([a, b, c]);
      }

  // triangle glow (behind links): from t 0.35, bold and clearly labeled
  const triReveal = clamp01((frame.t - 0.35) / 0.2);
  if (triReveal > 0) {
    triangles.forEach((tri, idx) => {
      const local = clamp01((triReveal - idx * 0.2) / 0.5);
      if (local <= 0) return;
      const pts = tri.map((id) => nodeById.get(id)!).map((n) => proj(n.x, n.y));
      const pulse = 0.85 + 0.15 * Math.sin(frame.now / 500 + idx * 2);
      ctx.beginPath();
      ctx.moveTo(pts[0].sx, pts[0].sy);
      ctx.lineTo(pts[1].sx, pts[1].sy);
      ctx.lineTo(pts[2].sx, pts[2].sy);
      ctx.closePath();
      ctx.fillStyle = `rgba(34, 211, 238, ${0.2 * local * pulse})`;
      ctx.fill();
      ctx.strokeStyle = `rgba(34, 211, 238, ${0.85 * local * pulse})`;
      ctx.lineWidth = 2.5;
      ctx.setLineDash([6, 5]);
      ctx.stroke();
      ctx.setLineDash([]);
      const cx = (pts[0].sx + pts[1].sx + pts[2].sx) / 3;
      const cy = (pts[0].sy + pts[1].sy + pts[2].sy) / 3;
      ctx.font = '600 10px "JetBrains Mono", monospace';
      ctx.textAlign = "center";
      ctx.fillStyle = `rgba(165, 243, 252, ${0.9 * local})`;
      ctx.fillText(`▲ ${idx + 1}`, cx, cy);
    });
  }

  // links: t 0.14 -> 0.42, staggered
  const maxCount = Math.max(...edges.map((e) => e.pass_count));
  edges.forEach((edge, idx) => {
    const local = clamp01((clamp01((frame.t - 0.14) / 0.28) - idx / edges.length) * 3);
    if (local <= 0) return;
    const a = proj(edge.x0, edge.y0);
    const b = proj(edge.x1, edge.y1);
    const strength = edge.pass_count / maxCount;
    ctx.globalAlpha = frame.alpha * local;
    const grad = ctx.createLinearGradient(a.sx, a.sy, b.sx, b.sy);
    grad.addColorStop(0, "rgba(163, 230, 53, 0.25)");
    grad.addColorStop(0.5, `rgba(163, 230, 53, ${0.4 + strength * 0.4})`);
    grad.addColorStop(1, "rgba(163, 230, 53, 0.25)");
    ctx.beginPath();
    ctx.moveTo(a.sx, a.sy);
    // links draw outward from the source
    ctx.lineTo(a.sx + (b.sx - a.sx) * local, a.sy + (b.sy - a.sy) * local);
    ctx.strokeStyle = grad;
    ctx.lineWidth = 1.5 + strength * 6;
    ctx.lineCap = "round";
    ctx.stroke();
    if (strength > 0.55 && local >= 1) {
      ctx.font = '600 10px "JetBrains Mono", monospace';
      ctx.textAlign = "center";
      ctx.fillStyle = "rgba(215, 245, 138, 0.85)";
      ctx.fillText(String(edge.pass_count), (a.sx + b.sx) / 2, (a.sy + b.sy) / 2 - 6);
    }
  });
  ctx.globalAlpha = frame.alpha;

  // nodes: t 0 -> 0.25, staggered pop — the whole XI reads as one structure
  nodes.forEach((node, idx) => {
    const pop = clamp01((clamp01(frame.t / 0.25) - idx / nodes.length) * 3);
    if (pop <= 0) return;
    const p = proj(node.x, node.y);
    const r = Math.max(node.size * 0.52 * p.scale, 15) * (0.7 + pop * 0.3);
    ctx.globalAlpha = frame.alpha * pop;
    const avatar = loadedImage(frame.sequence.playerImages?.[node.player]);
    if (avatar) {
      ctx.save();
      ctx.beginPath();
      ctx.arc(p.sx, p.sy, r, 0, Math.PI * 2);
      ctx.fillStyle = "#0b1c28";
      ctx.fill();
      ctx.clip();
      ctx.drawImage(avatar, p.sx - r, p.sy - r, r * 2, r * 2);
      ctx.restore();
      ctx.beginPath();
      ctx.arc(p.sx, p.sy, r, 0, Math.PI * 2);
      ctx.strokeStyle = ACCENT;
      ctx.lineWidth = 2;
      ctx.stroke();
    } else {
      ctx.beginPath();
      ctx.arc(p.sx, p.sy, r, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(9, 34, 24, 0.9)";
      ctx.fill();
      ctx.strokeStyle = ACCENT;
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.font = `600 ${Math.max(r * 0.62, 9)}px "JetBrains Mono", monospace`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillStyle = "rgba(244, 247, 251, 0.95)";
      ctx.fillText(node.label, p.sx, p.sy);
      ctx.textBaseline = "alphabetic";
    }
    const surname = node.player.split(" ").slice(-1)[0];
    ctx.font = '600 10px "JetBrains Mono", monospace';
    ctx.textAlign = "center";
    ctx.fillStyle = "rgba(216, 230, 242, 0.85)";
    ctx.fillText(surname.toUpperCase(), p.sx, p.sy + r + 13);
  });
  ctx.globalAlpha = frame.alpha;

  // network stats panel, bottom of the action side
  const statsReveal = clamp01((frame.t - 0.5) / 0.15);
  if (statsReveal > 0) {
    const strongest = [...edges].sort((a, b) => b.pass_count - a.pass_count)[0];
    const from = nodeById.get(strongest.source_id)?.player.split(" ").slice(-1)[0] ?? "";
    const to = nodeById.get(strongest.target_id)?.player.split(" ").slice(-1)[0] ?? "";
    const rows: Array<[string, string]> = [
      ["PASSING TRIANGLES", String(triangles.length)],
      ["STRONGEST LINK", `${from.toUpperCase()} → ${to.toUpperCase()} ×${strongest.pass_count}`],
      ["CENTRALIZATION", network.centralization_index?.toFixed(2) ?? "—"],
    ];
    ctx.globalAlpha = frame.alpha * statsReveal;
    const panelW = 330;
    const rowH = 30;
    const panelH = rowH * rows.length + 24;
    const px = frame.width * 0.62;
    const py = frame.height - panelH - 36;
    ctx.fillStyle = "rgba(2, 12, 19, 0.88)";
    ctx.beginPath();
    ctx.roundRect(px, py, panelW, panelH, 14);
    ctx.fill();
    ctx.strokeStyle = "rgba(163, 230, 53, 0.35)";
    ctx.lineWidth = 1.5;
    ctx.stroke();
    let y = py + 32;
    for (const [label, value] of rows) {
      ctx.font = '600 11px "JetBrains Mono", monospace';
      ctx.textAlign = "left";
      ctx.fillStyle = "rgba(158, 176, 196, 0.95)";
      ctx.fillText(label, px + 18, y);
      ctx.font = '700 13px "JetBrains Mono", monospace';
      ctx.textAlign = "right";
      ctx.fillStyle = "#d7f58a";
      ctx.fillText(value, px + panelW - 18, y);
      y += rowH;
    }
    ctx.globalAlpha = frame.alpha;
  }
}

// --- Out of Possession: zonal % pitch resolving into labeled actions -----

// Juego-de-posicion grid from lib/pitch.ts (105x68), scaled to Opta 0-100.
const JUEGO_COLS = [0, 16.7, 33.3, 50, 66.7, 83.3, 100];
const JUEGO_ROWS = [0, 20, 36.5, 63.5, 80, 100];

const DEFENSIVE_ACTION_STYLE: Record<string, { color: string; label: string }> = {
  Tackle: { color: "#a3e635", label: "TACKLE" },
  Interception: { color: "#22d3ee", label: "INTERCEPTION" },
  BallRecovery: { color: "#4ade80", label: "RECOVERY" },
  Clearance: { color: "#f97316", label: "CLEARANCE" },
  BlockedPass: { color: "#a78bfa", label: "BLOCKED PASS" },
};

function drawActionMarker(
  ctx: CanvasRenderingContext2D,
  sx: number,
  sy: number,
  r: number,
  type: string,
  color: string,
) {
  ctx.beginPath();
  if (type === "Interception") {
    // diamond
    ctx.moveTo(sx, sy - r);
    ctx.lineTo(sx + r, sy);
    ctx.lineTo(sx, sy + r);
    ctx.lineTo(sx - r, sy);
    ctx.closePath();
  } else if (type === "Clearance") {
    // triangle
    ctx.moveTo(sx, sy - r);
    ctx.lineTo(sx + r, sy + r * 0.8);
    ctx.lineTo(sx - r, sy + r * 0.8);
    ctx.closePath();
  } else if (type === "BlockedPass") {
    ctx.rect(sx - r * 0.85, sy - r * 0.85, r * 1.7, r * 1.7);
  } else {
    ctx.arc(sx, sy, r, 0, Math.PI * 2);
  }
  ctx.fillStyle = `${color}33`;
  ctx.fill();
  ctx.strokeStyle = color;
  ctx.lineWidth = 2.2;
  ctx.stroke();
  if (type === "Tackle") {
    // cross inside the circle
    ctx.beginPath();
    ctx.moveTo(sx - r * 0.5, sy - r * 0.5);
    ctx.lineTo(sx + r * 0.5, sy + r * 0.5);
    ctx.moveTo(sx + r * 0.5, sy - r * 0.5);
    ctx.lineTo(sx - r * 0.5, sy + r * 0.5);
    ctx.stroke();
  }
}

function drawDefensiveShape(
  ctx: CanvasRenderingContext2D,
  proj: Projection,
  frame: FrameState,
) {
  const zones = frame.sequence.defensiveZoneGrid ?? [];
  const actions = frame.sequence.defensiveActions ?? [];
  const maxShare = Math.max(...zones.map((z) => z.share), 1);

  // phase A: zonal pitch fades in, holds, then dissolves as actions arrive
  const zoneIn = clamp01(frame.t / 0.16);
  const zoneOut = clamp01((frame.t - 0.46) / 0.16);
  const zoneAlpha = zoneIn * (1 - zoneOut);

  if (zoneAlpha > 0) {
    // full grid lines
    ctx.globalAlpha = frame.alpha * zoneAlpha * 0.5;
    ctx.strokeStyle = "rgba(163, 230, 53, 0.35)";
    ctx.lineWidth = 1;
    for (const cx of JUEGO_COLS) {
      ctx.beginPath();
      trace(ctx, proj, [[cx, 0], [cx, 100]]);
      ctx.stroke();
    }
    for (const ry of JUEGO_ROWS) {
      ctx.beginPath();
      trace(ctx, proj, [[0, ry], [100, ry]]);
      ctx.stroke();
    }
    // heat + % per populated zone
    for (const zone of zones) {
      const x0 = JUEGO_COLS[zone.col];
      const x1 = JUEGO_COLS[zone.col + 1];
      const y0 = JUEGO_ROWS[zone.row];
      const y1 = JUEGO_ROWS[zone.row + 1];
      ctx.globalAlpha = frame.alpha * zoneAlpha;
      ctx.beginPath();
      trace(ctx, proj, [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]);
      ctx.fillStyle = `rgba(34, 211, 238, ${0.06 + (zone.share / maxShare) * 0.34})`;
      ctx.fill();
      const mid = proj((x0 + x1) / 2, (y0 + y1) / 2);
      ctx.font = '700 15px "JetBrains Mono", monospace';
      ctx.textAlign = "center";
      ctx.fillStyle = "rgba(244, 247, 251, 0.95)";
      ctx.fillText(`${zone.share}%`, mid.sx, mid.sy + 5);
    }
    ctx.globalAlpha = frame.alpha;
  }

  // phase B: the zones resolve into the individual labeled interventions
  const actionsReveal = clamp01((frame.t - 0.5) / 0.2);
  if (actionsReveal > 0) {
    actions.forEach((action, idx) => {
      const pop = clamp01((actionsReveal - (idx / actions.length) * 0.6) / 0.35);
      if (pop <= 0) return;
      const style =
        DEFENSIVE_ACTION_STYLE[action.type] ?? { color: "#94a3b8", label: action.type.toUpperCase() };
      const p = proj(action.x, action.y);
      const r = Math.max(11 * p.scale, 8) * (0.7 + pop * 0.3);
      ctx.globalAlpha = frame.alpha * pop;
      drawActionMarker(ctx, p.sx, p.sy, r, action.type, style.color);
      // label chip: action type + player surname + minute
      const surname = action.player.split(" ").slice(-1)[0].toUpperCase();
      const text = `${style.label} · ${surname} ${action.minute}'`;
      ctx.font = '600 10px "JetBrains Mono", monospace';
      const w = ctx.measureText(text).width + 14;
      ctx.fillStyle = "rgba(2, 12, 19, 0.85)";
      ctx.beginPath();
      ctx.roundRect(p.sx - w / 2, p.sy + r + 6, w, 17, 8);
      ctx.fill();
      ctx.textAlign = "center";
      ctx.fillStyle = style.color;
      ctx.fillText(text, p.sx, p.sy + r + 18);
    });

    // legend along the bottom
    const legendReveal = clamp01((actionsReveal - 0.5) / 0.4);
    if (legendReveal > 0) {
      ctx.globalAlpha = frame.alpha * legendReveal;
      const entries = Object.entries(DEFENSIVE_ACTION_STYLE);
      ctx.font = '600 10px "JetBrains Mono", monospace';
      const gap = 26;
      const widths = entries.map(([, v]) => 18 + ctx.measureText(v.label).width);
      const totalW = widths.reduce((a, b) => a + b, 0) + gap * (entries.length - 1);
      let x = frame.width * 0.42 - totalW / 2;
      const y = frame.height - 42;
      entries.forEach(([type, style], i) => {
        drawActionMarker(ctx, x + 6, y - 4, 6, type, style.color);
        ctx.font = '600 10px "JetBrains Mono", monospace';
        ctx.textAlign = "left";
        ctx.fillStyle = "rgba(216, 230, 242, 0.85)";
        ctx.fillText(style.label, x + 18, y);
        x += widths[i] + gap;
      });
    }
    ctx.globalAlpha = frame.alpha;
  }
}

// --- Duels & Transitions: duel map resolving into aerial/ground contests --

const DUEL_WON = "#a3e635";
const DUEL_LOST = "#64748b";

function drawDuelMarker(
  ctx: CanvasRenderingContext2D,
  sx: number,
  sy: number,
  r: number,
  kind: "aerial" | "ground",
  color: string,
) {
  ctx.beginPath();
  if (kind === "aerial") {
    // upward chevron-triangle: contested in the air
    ctx.moveTo(sx, sy - r * 1.1);
    ctx.lineTo(sx + r, sy + r * 0.75);
    ctx.lineTo(sx - r, sy + r * 0.75);
    ctx.closePath();
  } else {
    ctx.arc(sx, sy, r, 0, Math.PI * 2);
  }
  ctx.fillStyle = `${color}2e`;
  ctx.fill();
  ctx.strokeStyle = color;
  ctx.lineWidth = 2.2;
  ctx.stroke();
  if (kind === "ground") {
    ctx.beginPath();
    ctx.moveTo(sx - r * 0.5, sy - r * 0.5);
    ctx.lineTo(sx + r * 0.5, sy + r * 0.5);
    ctx.moveTo(sx + r * 0.5, sy - r * 0.5);
    ctx.lineTo(sx - r * 0.5, sy + r * 0.5);
    ctx.stroke();
  }
}

// 6x5 duel-map grid boundaries (uniform bins over 105x68, in Opta 0-100)
const DUEL_COLS = [0, 16.67, 33.33, 50, 66.67, 83.33, 100];
const DUEL_ROWS = [0, 20, 40, 60, 80, 100];

function drawDuels(
  ctx: CanvasRenderingContext2D,
  proj: Projection,
  frame: FrameState,
) {
  const zoneCounts = frame.sequence.duelZoneCounts ?? [];
  const duels = frame.sequence.duelActions ?? [];
  const homeColor = frame.sequence.teamColors[frame.sequence.homeTeam] ?? "#22c55e";
  const awayColor = frame.sequence.teamColors[frame.sequence.awayTeam] ?? "#38bdf8";

  // phase A: the tab's duel map — each zone split by the two teams' won
  // duels, with an A/B count chip — fading out as the contests resolve
  const zoneIn = clamp01(frame.t / 0.16);
  const zoneOut = clamp01((frame.t - 0.44) / 0.16);
  const zoneAlpha = zoneIn * (1 - zoneOut);
  if (zoneAlpha > 0) {
    // grid lines
    ctx.globalAlpha = frame.alpha * zoneAlpha * 0.5;
    ctx.strokeStyle = "rgba(163, 230, 53, 0.3)";
    ctx.lineWidth = 1;
    for (const cx of DUEL_COLS) {
      ctx.beginPath();
      trace(ctx, proj, [[cx, 0], [cx, 100]]);
      ctx.stroke();
    }
    for (const ry of DUEL_ROWS) {
      ctx.beginPath();
      trace(ctx, proj, [[0, ry], [100, ry]]);
      ctx.stroke();
    }
    for (const zone of zoneCounts) {
      const x0 = DUEL_COLS[zone.col];
      const x1 = DUEL_COLS[zone.col + 1];
      const y0 = DUEL_ROWS[zone.row];
      const y1 = DUEL_ROWS[zone.row + 1];
      const total = zone.home + zone.away;
      if (total === 0) continue;
      const split = x0 + (x1 - x0) * (zone.home / total);
      ctx.globalAlpha = frame.alpha * zoneAlpha * 0.55;
      ctx.beginPath();
      trace(ctx, proj, [[x0, y0], [split, y0], [split, y1], [x0, y1], [x0, y0]]);
      ctx.fillStyle = homeColor;
      ctx.fill();
      ctx.beginPath();
      trace(ctx, proj, [[split, y0], [x1, y0], [x1, y1], [split, y1], [split, y0]]);
      ctx.fillStyle = awayColor;
      ctx.fill();
      // A/B count chip, like the tab's annotations
      const mid = proj((x0 + x1) / 2, (y0 + y1) / 2);
      const text = `${zone.home}/${zone.away}`;
      ctx.globalAlpha = frame.alpha * zoneAlpha;
      ctx.font = '600 12px "JetBrains Mono", monospace';
      const w = ctx.measureText(text).width + 12;
      ctx.fillStyle = "rgba(2, 6, 23, 0.72)";
      ctx.beginPath();
      ctx.roundRect(mid.sx - w / 2, mid.sy - 10, w, 19, 5);
      ctx.fill();
      ctx.textAlign = "center";
      ctx.fillStyle = "rgba(244, 247, 251, 0.95)";
      ctx.fillText(text, mid.sx, mid.sy + 4);
    }
    // team legend
    ctx.globalAlpha = frame.alpha * zoneAlpha;
    ctx.font = '600 10px "JetBrains Mono", monospace';
    const ly = frame.height - 42;
    let lx = frame.width * 0.42 - 120;
    ctx.fillStyle = homeColor;
    ctx.fillRect(lx, ly - 9, 11, 11);
    ctx.textAlign = "left";
    ctx.fillStyle = "rgba(216, 230, 242, 0.85)";
    ctx.fillText(frame.sequence.homeTeam.toUpperCase(), lx + 17, ly);
    lx += 130;
    ctx.fillStyle = awayColor;
    ctx.fillRect(lx, ly - 9, 11, 11);
    ctx.fillStyle = "rgba(216, 230, 242, 0.85)";
    ctx.fillText(`${frame.sequence.awayTeam.toUpperCase()} · DUELS WON`, lx + 17, ly);
    ctx.globalAlpha = frame.alpha;
  }

  // phase B: individual duels, aerial vs ground, staggered in
  const actionsReveal = clamp01((frame.t - 0.48) / 0.2);
  // final beat: the transition duel takes over, everything else recedes
  const transitionReveal = clamp01((frame.t - 0.76) / 0.14);
  if (actionsReveal > 0) {
    duels.forEach((duel, idx) => {
      const pop = clamp01((actionsReveal - (idx / duels.length) * 0.6) / 0.35);
      if (pop <= 0) return;
      const isTransition = duel.transitionTo != null;
      const dim = transitionReveal > 0 && !isTransition ? 1 - transitionReveal * 0.55 : 1;
      const color = duel.won ? DUEL_WON : DUEL_LOST;
      const p = proj(duel.x, duel.y);
      const r = Math.max(11 * p.scale, 8) * (0.7 + pop * 0.3);
      ctx.globalAlpha = frame.alpha * pop * dim;
      drawDuelMarker(ctx, p.sx, p.sy, r, duel.kind, color);
      const code = duel.team.slice(0, 3).toUpperCase();
      const text = `${duel.kind === "aerial" ? "AERIAL" : "GROUND"} · ${code} ${duel.player
        .split(" ")
        .slice(-1)[0]
        .toUpperCase()} ${duel.minute}\u2032 · ${duel.won ? "WON" : "LOST"}`;
      ctx.font = '600 10px "JetBrains Mono", monospace';
      const w = ctx.measureText(text).width + 14;
      ctx.fillStyle = "rgba(2, 12, 19, 0.85)";
      ctx.beginPath();
      ctx.roundRect(p.sx - w / 2, p.sy + r + 6, w, 17, 8);
      ctx.fill();
      ctx.textAlign = "center";
      ctx.fillStyle = color;
      ctx.fillText(text, p.sx, p.sy + r + 18);

      // the duel that sprang the counter
      if (isTransition && transitionReveal > 0 && duel.transitionTo) {
        ctx.globalAlpha = frame.alpha * transitionReveal;
        const pulse = 1 + 0.15 * Math.sin(frame.now / 260);
        ctx.beginPath();
        ctx.arc(p.sx, p.sy, (r + 7) * pulse, 0, Math.PI * 2);
        ctx.strokeStyle = ACCENT_2;
        ctx.lineWidth = 2.5;
        ctx.stroke();
        const endP = proj(duel.transitionTo[0], duel.transitionTo[1]);
        const grow = transitionReveal;
        const hx = p.sx + (endP.sx - p.sx) * grow;
        const hy = p.sy + (endP.sy - p.sy) * grow;
        ctx.setLineDash([8, 6]);
        ctx.beginPath();
        ctx.moveTo(p.sx, p.sy);
        ctx.lineTo(hx, hy);
        ctx.strokeStyle = ACCENT_2;
        ctx.lineWidth = 3;
        ctx.stroke();
        ctx.setLineDash([]);
        const angle = Math.atan2(hy - p.sy, hx - p.sx);
        ctx.beginPath();
        ctx.moveTo(hx, hy);
        ctx.lineTo(hx - 13 * Math.cos(angle - 0.4), hy - 13 * Math.sin(angle - 0.4));
        ctx.lineTo(hx - 13 * Math.cos(angle + 0.4), hy - 13 * Math.sin(angle + 0.4));
        ctx.closePath();
        ctx.fillStyle = ACCENT_2;
        ctx.fill();
        if (transitionReveal > 0.5) {
          const midX = (p.sx + hx) / 2;
          const midY = (p.sy + hy) / 2;
          ctx.font = '700 12px "JetBrains Mono", monospace';
          ctx.textAlign = "center";
          ctx.fillStyle = "rgba(165, 243, 252, 0.95)";
          ctx.fillText("TRANSITION \u2192 COUNTER", midX, midY - 12);
        }
      }
    });

    // legend
    const legendReveal = clamp01((actionsReveal - 0.5) / 0.4);
    if (legendReveal > 0) {
      ctx.globalAlpha = frame.alpha * legendReveal;
      const y = frame.height - 42;
      let x = frame.width * 0.42 - 190;
      drawDuelMarker(ctx, x + 6, y - 4, 6, "aerial", "rgba(216,230,242,0.9)");
      ctx.font = '600 10px "JetBrains Mono", monospace';
      ctx.textAlign = "left";
      ctx.fillStyle = "rgba(216, 230, 242, 0.85)";
      ctx.fillText("AERIAL DUEL", x + 18, y);
      x += 130;
      drawDuelMarker(ctx, x + 6, y - 4, 6, "ground", "rgba(216,230,242,0.9)");
      ctx.fillStyle = "rgba(216, 230, 242, 0.85)";
      ctx.textAlign = "left";
      ctx.fillText("GROUND DUEL", x + 18, y);
      x += 130;
      ctx.fillStyle = DUEL_WON;
      ctx.fillText("WON", x, y);
      x += 50;
      ctx.fillStyle = DUEL_LOST;
      ctx.fillText("LOST", x, y);
    }
    ctx.globalAlpha = frame.alpha;
  }
}

// --- Player Analysis: heatmap -> touches -> in-possession actions ---------

function phaseChip(
  ctx: CanvasRenderingContext2D,
  frame: FrameState,
  text: string,
  alpha: number,
) {
  if (alpha <= 0) return;
  ctx.globalAlpha = frame.alpha * alpha;
  ctx.font = '700 12px "JetBrains Mono", monospace';
  const w = ctx.measureText(text).width + 22;
  const x = frame.width * 0.42 - w / 2;
  const y = 86;
  ctx.fillStyle = "rgba(2, 12, 19, 0.85)";
  ctx.beginPath();
  ctx.roundRect(x, y - 16, w, 24, 12);
  ctx.fill();
  ctx.strokeStyle = "rgba(163, 230, 53, 0.4)";
  ctx.lineWidth = 1.5;
  ctx.stroke();
  ctx.textAlign = "center";
  ctx.fillStyle = "#d7f58a";
  ctx.fillText(text, frame.width * 0.42, y + 1);
  ctx.globalAlpha = frame.alpha;
}

// Same colorscale as the Player Analysis tab's heatmap:
// green -> yellow -> orange -> red with an alpha ramp.
const HEAT_STOPS: Array<[number, [number, number, number, number]]> = [
  [0, [34, 197, 94, 0]],
  [0.16, [34, 197, 94, 31]],
  [0.38, [34, 197, 94, 133]],
  [0.62, [250, 204, 21, 184]],
  [0.82, [249, 115, 22, 199]],
  [1, [239, 68, 68, 230]],
];

let heatLut: Uint8ClampedArray | null = null;
function getHeatLut() {
  if (heatLut) return heatLut;
  heatLut = new Uint8ClampedArray(256 * 4);
  for (let i = 0; i < 256; i += 1) {
    const t = i / 255;
    let hi = 1;
    while (hi < HEAT_STOPS.length - 1 && HEAT_STOPS[hi][0] < t) hi += 1;
    const [t0, c0] = HEAT_STOPS[hi - 1];
    const [t1, c1] = HEAT_STOPS[hi];
    const f = t1 === t0 ? 0 : (t - t0) / (t1 - t0);
    for (let ch = 0; ch < 4; ch += 1) {
      heatLut[i * 4 + ch] = c0[ch] + (c1[ch] - c0[ch]) * f;
    }
  }
  return heatLut;
}

// Low-res offscreen density buffer, colorized through the LUT each frame.
let heatCanvas: HTMLCanvasElement | null = null;

function drawHeatField(
  ctx: CanvasRenderingContext2D,
  proj: Projection,
  frame: FrameState,
  touches: Array<[number, number]>,
  alpha: number,
) {
  const scale = 4;
  const w = Math.max(Math.ceil(frame.width / scale), 8);
  const h = Math.max(Math.ceil(frame.height / scale), 8);
  if (!heatCanvas) heatCanvas = document.createElement("canvas");
  if (heatCanvas.width !== w || heatCanvas.height !== h) {
    heatCanvas.width = w;
    heatCanvas.height = h;
  }
  const hctx = heatCanvas.getContext("2d");
  if (!hctx) return;
  hctx.clearRect(0, 0, w, h);
  hctx.globalCompositeOperation = "lighter";
  for (const [x, y] of touches) {
    const p = proj(x, y);
    const r = Math.max((72 * p.scale) / scale, 7);
    const px = p.sx / scale;
    const py = p.sy / scale;
    const glow = hctx.createRadialGradient(px, py, 0, px, py, r);
    glow.addColorStop(0, "rgba(255,255,255,0.2)");
    glow.addColorStop(1, "rgba(255,255,255,0)");
    hctx.fillStyle = glow;
    hctx.beginPath();
    hctx.arc(px, py, r, 0, Math.PI * 2);
    hctx.fill();
  }
  hctx.globalCompositeOperation = "source-over";

  const image = hctx.getImageData(0, 0, w, h);
  const data = image.data;
  const lut = getHeatLut();
  for (let i = 0; i < data.length; i += 4) {
    const intensity = Math.min(Math.round((data[i + 3] / 235) * 255), 255);
    data[i] = lut[intensity * 4];
    data[i + 1] = lut[intensity * 4 + 1];
    data[i + 2] = lut[intensity * 4 + 2];
    data[i + 3] = lut[intensity * 4 + 3];
  }
  hctx.putImageData(image, 0, 0);

  ctx.save();
  ctx.globalAlpha = frame.alpha * alpha;
  ctx.imageSmoothingEnabled = true;
  ctx.drawImage(heatCanvas, 0, 0, frame.width, frame.height);
  ctx.restore();
}

function drawPlayerFocus(
  ctx: CanvasRenderingContext2D,
  proj: Projection,
  frame: FrameState,
) {
  const touches = frame.sequence.heatTouches ?? [];
  const actions = frame.sequence.inPossessionActions ?? [];
  const focus = frame.sequence.focusPlayer ?? "";

  // phase windows
  const heatIn = clamp01(frame.t / 0.14);
  const heatOut = clamp01((frame.t - 0.3) / 0.12);
  const heatAlpha = heatIn * (1 - heatOut);
  const touchIn = clamp01((frame.t - 0.32) / 0.12);
  const touchOut = clamp01((frame.t - 0.6) / 0.12);
  const touchAlpha = touchIn * (1 - touchOut * 0.75); // touches stay faint under actions
  const actionsIn = clamp01((frame.t - 0.62) / 0.15);

  // phase 1: the tab's multi-color density heatmap over every touch
  if (heatAlpha > 0) {
    drawHeatField(ctx, proj, frame, touches, heatAlpha);
  }

  // phase 2: every touch as a dot, staggered in
  if (touchIn > 0 && touchAlpha > 0) {
    touches.forEach(([x, y], idx) => {
      const pop = clamp01((touchIn - (idx / touches.length) * 0.7) / 0.3);
      if (pop <= 0) return;
      const p = proj(x, y);
      ctx.globalAlpha = frame.alpha * pop * touchAlpha;
      ctx.beginPath();
      ctx.arc(p.sx, p.sy, Math.max(3.2 * p.scale, 2.4), 0, Math.PI * 2);
      ctx.fillStyle = "rgba(163, 230, 53, 0.8)";
      ctx.fill();
    });
    ctx.globalAlpha = frame.alpha;
  }

  // phase 3: highest-xT passes and carries as arrows
  if (actionsIn > 0) {
    actions.forEach((action, idx) => {
      const pop = clamp01((actionsIn - (idx / actions.length) * 0.55) / 0.35);
      if (pop <= 0) return;
      const a = proj(action.x, action.y);
      const grow = clamp01(pop * 1.4);
      const bTarget = proj(action.end_x, action.end_y);
      const hx = a.sx + (bTarget.sx - a.sx) * grow;
      const hy = a.sy + (bTarget.sy - a.sy) * grow;
      const isCarry = action.type === "Carry" || action.type === "TakeOn";
      const color = isCarry ? ACCENT_2 : ACCENT;
      ctx.globalAlpha = frame.alpha * pop;
      if (isCarry) ctx.setLineDash([7, 6]);
      ctx.beginPath();
      ctx.moveTo(a.sx, a.sy);
      ctx.lineTo(hx, hy);
      ctx.strokeStyle = color;
      ctx.lineWidth = 2.5;
      ctx.lineCap = "round";
      ctx.stroke();
      ctx.setLineDash([]);
      const angle = Math.atan2(hy - a.sy, hx - a.sx);
      ctx.beginPath();
      ctx.moveTo(hx, hy);
      ctx.lineTo(hx - 10 * Math.cos(angle - 0.42), hy - 10 * Math.sin(angle - 0.42));
      ctx.lineTo(hx - 10 * Math.cos(angle + 0.42), hy - 10 * Math.sin(angle + 0.42));
      ctx.closePath();
      ctx.fillStyle = color;
      ctx.fill();
      // label the strongest three
      if (idx < 3 && pop > 0.7) {
        const text = `${isCarry ? "CARRY" : "PASS"} ${action.minute}\u2032 · xT ${(action.xt ?? 0).toFixed(3)}`;
        ctx.font = '600 10px "JetBrains Mono", monospace';
        const w = ctx.measureText(text).width + 14;
        const mx = (a.sx + hx) / 2;
        const my = (a.sy + hy) / 2;
        ctx.fillStyle = "rgba(2, 12, 19, 0.85)";
        ctx.beginPath();
        ctx.roundRect(mx - w / 2, my - 22, w, 17, 8);
        ctx.fill();
        ctx.textAlign = "center";
        ctx.fillStyle = color;
        ctx.fillText(text, mx, my - 10);
      }
    });

    // the player anchors the story: avatar at his median touch position
    if (touches.length > 0) {
      const xs = [...touches].map((t) => t[0]).sort((u, v) => u - v);
      const ys = [...touches].map((t) => t[1]).sort((u, v) => u - v);
      const mid = proj(xs[Math.floor(xs.length / 2)], ys[Math.floor(ys.length / 2)]);
      const avatar = loadedImage(
        frame.sequence.playerImages?.[focus],
      );
      const r = 26;
      ctx.globalAlpha = frame.alpha * actionsIn;
      if (avatar) {
        ctx.save();
        ctx.beginPath();
        ctx.arc(mid.sx, mid.sy, r, 0, Math.PI * 2);
        ctx.fillStyle = "#0b1c28";
        ctx.fill();
        ctx.clip();
        ctx.drawImage(avatar, mid.sx - r, mid.sy - r, r * 2, r * 2);
        ctx.restore();
      }
      ctx.beginPath();
      ctx.arc(mid.sx, mid.sy, r, 0, Math.PI * 2);
      ctx.strokeStyle = ACCENT;
      ctx.lineWidth = 2.5;
      ctx.stroke();
      ctx.font = '600 10px "JetBrains Mono", monospace';
      ctx.textAlign = "center";
      ctx.fillStyle = "rgba(215, 245, 138, 0.95)";
      ctx.fillText(focus.toUpperCase(), mid.sx, mid.sy + r + 14);
    }
    ctx.globalAlpha = frame.alpha;
  }

  // phase chip narrates the current lens — one visible at a time
  const touchCount =
    frame.sequence.metrics.find((m) => m.label === "Touches")?.value ?? String(touches.length);
  phaseChip(ctx, frame, "HEATMAP", heatIn * (1 - clamp01((frame.t - 0.28) / 0.07)));
  phaseChip(
    ctx, frame, `TOUCHES · ${touchCount}`,
    clamp01((frame.t - 0.37) / 0.08) * (1 - clamp01((frame.t - 0.57) / 0.07)),
  );
  phaseChip(ctx, frame, "IN-POSSESSION ACTIONS", clamp01((frame.t - 0.66) / 0.08));
}

const TREATMENTS: Record<
  ChapterTreatment,
  (ctx: CanvasRenderingContext2D, proj: Projection, frame: FrameState) => void
> = {
  momentum: drawMomentum,
  shots: drawShots,
  "pass-network": drawPassNetwork,
  "defensive-shape": drawDefensiveShape,
  duels: drawDuels,
  "player-focus": drawPlayerFocus,
};

export function drawTreatment(
  kind: ChapterTreatment,
  ctx: CanvasRenderingContext2D,
  proj: Projection,
  frame: FrameState,
) {
  TREATMENTS[kind](ctx, proj, frame);
}
