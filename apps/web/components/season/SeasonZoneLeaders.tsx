"use client";

import { useEffect, useMemo, useState } from "react";

import type { ActionPoint, SeasonPlayerMetrics, ZoneLeadersFile } from "../../lib/api";
import { LEAGUE_PRESENTATION } from "../../lib/leagues";
import { Plot } from "../../lib/plotly";
import { CHART_FONT_FAMILY } from "../../lib/theme";
import { DownloadPngButton } from "../DownloadPngButton";
import { getCachedPlayerImage, prefetchPlayerImages, subscribePlayerImages } from "../PlayerAvatar";
import { AgeChips, inAgeBand, type AgeBand } from "./AgeFilter";
import { MetricSelect } from "./MetricSelect";
import { loadPlayerActions, PITCH_H, PITCH_W } from "./pitch";
import { VALUE_MODES, type ValueMode } from "./playerValues";
import { renderZoneLeadersPng, type MarkerKind } from "./zoneLeadersExport";
import { fmtNum, useChartFrame, useInlineImages, useSeasonFile } from "./useSeasonChart";

type Props = { league: string; season: string };

const plotConfig = { responsive: true, displayModeBar: false };
const PALETTE = ["#a3e635", "#22d3ee", "#fbbf24", "#f472b6", "#a78bfa", "#fb923c", "#38bdf8", "#2dd4bf", "#fb7185", "#34d399", "#facc15", "#818cf8", "#f97316", "#e879f9", "#4ade80", "#60a5fa", "#fda4af", "#5eead4"];
// shot-creating actions split by type; every other action is plotted as plain dots
const TYPED_KEYS: Record<string, [string, MarkerKind][]> = {
  sca: [["sca_pass", "pass"], ["sca_carry", "carry"], ["sca_takeon", "takeon"], ["sca_defensive", "defensive"], ["sca_shot", "shot"]],
};
// rarer actions need a lower bar for a zone to have a leader
// half the side of every zone photo, in pitch units: fits the shortest zone (13.84 high) with the name and value under it
const PHOTO_HALF = 3.2;
const MIN_ZONE_DEFAULT: Record<string, number> = { sca: 2, gca: 1, assists: 1, goals: 1, shots: 2, shots_on_target: 1, shots_box: 2, big_chances_created: 1, key_passes_ft: 3, saves: 2, saves_pen_area: 2, saves_outside_box: 1 };

type Leader = { zone: number; pid: number; name: string; team: string; n: number; value: number; color: string };

export function SeasonZoneLeaders({ league, season }: Props) {
  const { data, error } = useSeasonFile<ZoneLeadersFile>(league, season, "zone-leaders");
  const { data: players } = useSeasonFile<SeasonPlayerMetrics>(league, season, "player-metrics");
  const { themeColors, width, setHost, compact } = useChartFrame();
  const [action, setAction] = useState("sca");
  const [mode, setMode] = useState<ValueMode>("padj");
  const [minMinutes, setMinMinutes] = useState(350);
  const [minZone, setMinZone] = useState(2);
  const [team, setTeam] = useState("");
  const [phase, setPhase] = useState<"all" | "open" | "set">("all");
  const [withGk, setWithGk] = useState(false);
  const [ageBand, setAgeBand] = useState<AgeBand>("all");
  const [, bump] = useState(0);
  useEffect(() => subscribePlayerImages(() => bump((n) => n + 1)), []);

  const byId = useMemo(() => new Map((players?.players ?? []).map((p) => [p.id, p])), [players]);
  const teams = useMemo(() => [...new Set((players?.players ?? []).map((p) => p.team))].sort(), [players]);

  const leaders = useMemo<Leader[]>(() => {
    if (!data || !players) return [];
    const table = data.actions[action] ?? {};
    const perZone = new Map<number, { pid: number; n: number }[]>();
    for (const [pidText, cells] of Object.entries(table)) {
      const p = byId.get(Number(pidText));
      if (!p || p.minutes < minMinutes || (!withGk && p.group === "Goalkeeper") || (team && p.team !== team) || !inAgeBand(p.age, ageBand)) continue;
      for (const [zone, open, set] of cells) {
        const n = phase === "open" ? open : phase === "set" ? set : open + set;
        if (n > 0) perZone.set(zone, [...(perZone.get(zone) ?? []), { pid: p.id, n }]);
      }
    }
    const out: Leader[] = [];
    for (const [zone, list] of perZone) {
      // as in the social visual: a player qualifies in a zone with at least the minimum, and at least the median for that zone
      const sorted = [...list].map((r) => r.n).sort((a, b) => a - b);
      const median = sorted[Math.floor(sorted.length / 2)];
      const thr = Math.max(minZone, median);
      let best: Leader | null = null;
      for (const r of list) {
        if (r.n < thr) continue;
        const p = byId.get(r.pid)!;
        const per90 = (r.n / p.minutes) * 90;
        const value = mode === "total" ? r.n : mode === "padj" ? per90 * (players.padj?.[p.team] ?? 1) : per90;
        if (!best || value > best.value) best = { zone, pid: p.id, name: p.name, team: p.team, n: r.n, value, color: "" };
      }
      if (best) out.push(best);
    }
    const ranked = [...out].sort((a, b) => b.value - a.value);
    const colors = new Map<number, string>();
    ranked.forEach((l) => !colors.has(l.pid) && colors.set(l.pid, PALETTE[colors.size % PALETTE.length]));
    return out.map((l) => ({ ...l, color: colors.get(l.pid)! }));
  }, [data, players, byId, action, mode, minMinutes, minZone, team, phase, withGk, ageBand]);

  useEffect(() => {
    const byTeam = new Map<string, string[]>();
    for (const l of leaders) byTeam.set(l.team, [...(byTeam.get(l.team) ?? []), l.name]);
    byTeam.forEach((names, t) => prefetchPlayerImages(names, t));
  }, [leaders]);
  const photoUrls = leaders.map((l) => getCachedPlayerImage(l.name, l.team)).filter((u): u is string => Boolean(u));
  const inline = useInlineImages(photoUrls);

  const pitchW = Math.min(width, 1100);
  const figure = useMemo(() => {
    if (!data) return null;
    const font = { color: themeColors.text, family: CHART_FONT_FAMILY };
    const plotW = pitchW - 20;
    const ppu = plotW / (PITCH_W + 2); // pixels per pitch unit
    const shapes: unknown[] = [];
    const annotations: unknown[] = [];
    const images: unknown[] = [];
    const lines = (c: string) => ({ color: c, width: 1.4 });
    // pitch markings
    const rect = (x0: number, y0: number, x1: number, y1: number) => ({ type: "rect", x0, y0, x1, y1, line: lines(themeColors.pitchLine), fillcolor: "rgba(0,0,0,0)", layer: "below" });
    shapes.push(rect(0, 0, PITCH_W, PITCH_H), { type: "line", x0: PITCH_W / 2, x1: PITCH_W / 2, y0: 0, y1: PITCH_H, line: lines(themeColors.pitchLine) },
      { type: "circle", x0: PITCH_W / 2 - 9.15, x1: PITCH_W / 2 + 9.15, y0: PITCH_H / 2 - 9.15, y1: PITCH_H / 2 + 9.15, line: lines(themeColors.pitchLine) },
      rect(0, 13.84, 16.5, 54.16), rect(PITCH_W - 16.5, 13.84, PITCH_W, 54.16));
    const traces: Record<string, unknown>[] = [];
    const hoverX: number[] = [];
    const hoverY: number[] = [];
    const hoverText: string[] = [];

    for (const l of leaders) {
      const z = data.zones[l.zone];
      const cx = (z.x1 + z.x2) / 2;
      const cy = (z.y1 + z.y2) / 2;
      shapes.push({ type: "rect", x0: z.x1, y0: z.y1, x1: z.x2, y1: z.y2, fillcolor: `${l.color}1a`, line: { color: themeColors.pitchLine, width: 1 }, layer: "below" });
      // every photo is the same size, small enough for the shortest zone; photo + name + value are stacked and centred in the zone
      const half = PHOTO_HALF;
      const py = cy + (2 * half + 5.4) / 2 - half;
      const src = getCachedPlayerImage(l.name, l.team);
      shapes.push({ type: "rect", x0: cx - half - 0.45, x1: cx + half + 0.45, y0: py - half - 0.45, y1: py + half + 0.45, fillcolor: "rgba(0,0,0,0)", line: { color: l.color, width: 3 }, layer: "above" });
      if (src) images.push({ source: inline[src] ?? src, xref: "x", yref: "y", x: cx, y: py, sizex: half * 2, sizey: half * 2, xanchor: "center", yanchor: "middle", sizing: "contain", layer: "above" });
      else annotations.push({ x: cx, y: py, text: l.name.split(" ").map((w) => w[0]).slice(0, 2).join(""), showarrow: false, font: { ...font, size: compact ? 10 : 14, color: l.color } });
      annotations.push({ x: cx, y: py - half - 1.7, text: `<b>${l.name.split(" ").slice(-1)[0]}</b>`, showarrow: false, font: { ...font, size: compact ? 9 : 12 } });
      annotations.push({ x: cx, y: py - half - 4.2, text: `<b>${mode === "total" ? l.value.toFixed(0) : fmtNum(l.value)}</b>`, showarrow: false, font: { family: CHART_FONT_FAMILY, size: compact ? 9 : 12, color: l.color } });
      hoverX.push(cx); hoverY.push(cy);
      hoverText.push(`<b>${l.name}</b><br>${l.team}<br>${l.n} in this zone<br>${mode === "total" ? "Total" : mode === "padj" ? "Per 90, possession-adjusted" : "Per 90"}: ${fmtNum(l.value)}`);
    }

    traces.push({ type: "scatter", mode: "markers", x: hoverX, y: hoverY, hovertext: hoverText, hoverinfo: "text", marker: { size: 40, color: "rgba(0,0,0,0)" },
      hoverlabel: { bgcolor: themeColors.hoverBg, font: { color: themeColors.hoverText, family: CHART_FONT_FAMILY } } });
    const height = Math.round(plotW * (PITCH_H / PITCH_W)) + 40;
    return {
      data: traces,
      height,
      layout: {
        width: pitchW, height, margin: { l: 10, r: 10, t: 10, b: 30 }, paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)", showlegend: false, font, shapes, annotations, images,
        xaxis: { range: [-1, PITCH_W + 1], visible: false, fixedrange: true, constrain: "domain" },
        yaxis: { range: [-1, PITCH_H + 1], visible: false, fixedrange: true, scaleanchor: "x", scaleratio: 1 },
      },
    };
  }, [data, leaders, themeColors, pitchW, compact, mode, phase, action, inline]);

  const label = data?.metrics.find((m) => m.key === action)?.label ?? action;
  const actionMetrics = (data?.metrics ?? []).map((m) => ({ key: m.key, label: m.label, category: m.group }));

  return (
    <section className="card stack">
      <div className="chart-card-head">
        <div>
          <h2>Zone leaders</h2>
          <p className="muted">
            Who leads each part of the pitch for an action: the player with the most per 90 in that zone (at least the zone median and the
            minimum you set). Goalkeepers are left out unless you include them.
          </p>
        </div>
        {figure && leaders.length ? (
          <DownloadPngButton
            filename={`${league}-zone-leaders-${action}`}
            renderImage={async () => {
              const leagueInfo = LEAGUE_PRESENTATION[league];
              const valueText = (v: number) => (mode === "total" ? v.toFixed(0) : fmtNum(v));
              const parts = [
                mode === "total" ? "Season totals" : mode === "padj" ? "Zone leaders, per 90 (possession-adjusted to 50%)" : "Zone leaders, per 90",
                `min ${minMinutes} minutes`,
                `min ${minZone} in a zone`,
                ...(phase === "open" ? ["open play"] : phase === "set" ? ["set pieces"] : []),
                ...(withGk ? ["incl. GKs"] : ["excl. GKs"]),
                ...(team ? [team] : []),
                ...(ageBand !== "all" ? [ageBand.toUpperCase()] : []),
                `${leagueInfo?.name ?? league} ${season.replace("-", "/")}`,
              ];
              const actionsById = new Map(await Promise.all(leaders.map(async (l) => [l.pid, await loadPlayerActions(league, season, l.pid).catch(() => ({} as Record<string, ActionPoint[]>))] as const)));
              const pointsFor = (l: Leader) => {
                const z = data!.zones[l.zone];
                const sets = TYPED_KEYS[action] ?? [[action, "other" as MarkerKind]];
                const actions = actionsById.get(l.pid) ?? {};
                return sets.flatMap(([key, kind]) => (actions[key] ?? []).map((a) => ({ x: a[0], y: a[1], set: a[4], kind })))
                  .filter((p) => p.x >= z.x1 && p.x < z.x2 && p.y >= z.y1 && p.y < z.y2 && (phase === "all" || (phase === "set") === (p.set === 1)));
              };
              return renderZoneLeadersPng({
                title: `${label} per zone`,
                dotLabel: label,
                subtitle: parts.join("  |  "),
                leagueLogo: leagueInfo?.logo,
                leaders: leaders.map((l) => ({ points: pointsFor(l), zone: data!.zones[l.zone], name: l.name, color: l.color, valueText: valueText(l.value), photo: getCachedPlayerImage(l.name, l.team) ?? null })),
              });
            }}
          />
        ) : null}
      </div>

      {error ? <p className="inline-warning">{error}</p> : null}

      <div className="season-scatter-controls">
        <label>
          <span>Action</span>
          <MetricSelect metrics={actionMetrics} value={action} onChange={(k) => { setAction(k); setMinZone(MIN_ZONE_DEFAULT[k] ?? 5); setMinMinutes((m) => m); }} disabled={!data} />
        </label>
        <label>
          <span>Values</span>
          <select className="select" value={mode} onChange={(e) => setMode(e.target.value as ValueMode)}>
            {VALUE_MODES.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
          </select>
        </label>
        <label>
          <span>Team</span>
          <select className="select" value={team} onChange={(e) => setTeam(e.target.value)} disabled={!players}>
            <option value="">All teams</option>
            {teams.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
        <label>
          <span>Play phase</span>
          <select className="select" value={phase} onChange={(e) => setPhase(e.target.value as typeof phase)}>
            <option value="all">All play</option>
            <option value="open">Open play</option>
            <option value="set">Set pieces</option>
          </select>
        </label>
        <label>
          <span>Minimum minutes: {minMinutes}</span>
          <input type="range" min={0} max={1800} step={30} value={minMinutes} onChange={(e) => setMinMinutes(Number(e.target.value))} />
        </label>
        <label>
          <span>Minimum actions in a zone: {minZone}</span>
          <input type="range" min={1} max={20} step={1} value={minZone} onChange={(e) => setMinZone(Number(e.target.value))} />
        </label>
      </div>
      <div className="season-chip-row">
        <button type="button" className={`season-chip${withGk ? " is-on" : ""}`} style={{ "--chip": "#f59e0b" } as React.CSSProperties} onClick={() => setWithGk((v) => !v)} aria-pressed={withGk}>
          Include goalkeepers
        </button>
        {players?.has_age ? <><span className="season-chip-sep" aria-hidden="true" /><AgeChips value={ageBand} onChange={setAgeBand} /></> : null}
        <span className="muted season-count">{leaders.length} zones with a leader</span>
      </div>

      <div ref={setHost} className="plotly-chart-shell season-scatter-shell">
        {(!data || !players) && !error ? <p className="muted">Loading…</p> : null}
        {data && players && !leaders.length ? <p className="muted">No zone has a leader with these settings: lower the minimum minutes or actions.</p> : null}
        {figure && leaders.length ? <Plot data={figure.data} layout={figure.layout} config={plotConfig} className="plotly-chart" style={{ width: pitchW, height: figure.height, margin: "0 auto" }} /> : null}
      </div>
      {leaders.length ? <p className="muted season-zone-legend"><span>Attacking left to right →</span></p> : null}
    </section>
  );
}
