"use client";

import { useEffect, useMemo, useState } from "react";

import type { PlayerSlices, SeasonPlayer, SeasonPlayerMetrics } from "../../lib/api";
import { LEAGUE_PRESENTATION } from "../../lib/leagues";
import { Plot } from "../../lib/plotly";
import { CHART_FONT_FAMILY } from "../../lib/theme";
import { DownloadPngButton } from "../DownloadPngButton";
import { getCachedPlayerImage, prefetchPlayerImages, subscribePlayerImages } from "../PlayerAvatar";
import { AgeChips, inAgeBand, type AgeBand } from "./AgeFilter";
import { MetricSelect } from "./MetricSelect";
import { PlayerActionsMap, usePlayerActions } from "./pitch";
import { GROUPS, GROUP_COLORS, SUB_ONLY, VALUE_MODES, groupOf, modeSuffix, playerSliceValue, playerValue, sliceMinutes, type ValueMode } from "./playerValues";
import { ALL_SELECTED, SliceFilters, describeSelection, isFiltered, phaseOnly, type SliceSelection } from "./SliceFilters";
import { renderScatterPng } from "./scatterExport";
import { fmtNum, useChartFrame, useInlineImages, useSeasonFile } from "./useSeasonChart";

type Props = { league: string; season: string };

const NONE = "";
const PHOTO_PX = 26; // the photo sits inside a round bubble with a margin all round it
const BUBBLE_PX = 40;
const plotConfig = { responsive: true, displayModeBar: false };

export function SeasonPlayerScatter({ league, season }: Props) {
  const { data, error } = useSeasonFile<SeasonPlayerMetrics>(league, season, "player-metrics");
  const [filters, setFilters] = useState<SliceSelection>(ALL_SELECTED);
  const filtered = isFiltered(filters);
  const { data: slices, error: sliceError } = useSeasonFile<PlayerSlices>(league, season, "player-slices", filtered);

  const [mode, setMode] = useState<ValueMode>("p90");
  const [x, setX] = useState("key_passes_ft");
  const [y, setY] = useState("dribbles_ft");
  const [z, setZ] = useState(NONE);
  const [minMinutes, setMinMinutes] = useState(270);
  const [groups, setGroups] = useState<string[]>([...GROUPS, SUB_ONLY]);
  const [team, setTeam] = useState(NONE);
  const [highlight, setHighlight] = useState("");
  const [labelTop, setLabelTop] = useState(8);
  const [selected, setSelected] = useState<number | null>(null);
  const [ageBand, setAgeBand] = useState<AgeBand>("all");
  const ageActive = Boolean(data?.has_age) && ageBand !== "all";
  const { themeColors, width, setHost, compact } = useChartFrame();
  const [imageTick, bumpImages] = useState(0); // re-draws the chart when a batch of player photos arrives

  useEffect(() => subscribePlayerImages(() => bumpImages((n) => n + 1)), []);
  // A game-state or time selection leaves each player fewer minutes, so the minutes bar starts lower; clearing it restores it.
  useEffect(() => setMinMinutes(filtered ? 60 : 270), [filtered]);

  const metrics = useMemo(() => [...(data?.metrics ?? [])].sort((a, b) => a.label.localeCompare(b.label)), [data]);
  const labels = useMemo(() => Object.fromEntries(metrics.map((m) => [m.key, m.label])), [metrics]);
  const axisLabel = (m: string) => `${labels[m] ?? m}${modeSuffix(mode)}`;

  const sliceById = useMemo(() => new Map((slices?.players ?? []).map((s) => [s.id, s])), [slices]);
  const waitingForSlices = filtered && !slices && !sliceError;

  // One value per player: from the season table, or re-added from the game-state / time slices when a filter is on.
  const minutesOf = (p: SeasonPlayer) => (filtered ? sliceMinutes(sliceById.get(p.id), filters) : p.minutes);
  const value = (p: SeasonPlayer, m: string) =>
    filtered ? playerSliceValue(sliceById.get(p.id), m, mode, filters, data?.padj?.[p.team] ?? 1) : playerValue(p, m, mode, data?.padj);

  const teams = useMemo(() => [...new Set((data?.players ?? []).map((p) => p.team))].sort(), [data]);
  const maxMinutes = useMemo(() => Math.max(90, ...(data?.players ?? []).map((p) => p.minutes)), [data]);
  const players = useMemo(
    () =>
      (data?.players ?? []).filter(
        (p) =>
          groups.includes(groupOf(p)) && (!team || p.team === team) && minutesOf(p) >= minMinutes && (!filtered || sliceById.has(p.id)) &&
          (!ageActive || inAgeBand(p.age, ageBand)),
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [data, minMinutes, groups, team, filtered, sliceById, filters, ageActive, ageBand],
  );

  const height = z ? (compact ? 460 : 620) : compact ? 440 : 600;
  const q = highlight.trim().toLowerCase();
  const isHi = (p: SeasonPlayer) => q.length > 1 && p.name.toLowerCase().includes(q);

  // Players who get a name and a photo: the highlighted ones plus the most extreme on either axis.
  const labelled = useMemo(() => {
    const top = new Set<number>();
    if (labelTop > 0 && players.length) {
      for (const m of [x, y]) [...players].sort((a, b) => value(b, m) - value(a, m)).slice(0, labelTop).forEach((p) => top.add(p.id));
    }
    return players.filter((p) => top.has(p.id) || isHi(p));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [players, x, y, labelTop, q, mode, filters, slices]);

  const photoUrls = labelled.map((p) => getCachedPlayerImage(p.name, p.team)).filter((u): u is string => Boolean(u));
  const inlinePhotos = useInlineImages(photoUrls);

  useEffect(() => {
    const byTeam = new Map<string, string[]>();
    for (const p of labelled) byTeam.set(p.team, [...(byTeam.get(p.team) ?? []), p.name]);
    byTeam.forEach((names, t) => prefetchPlayerImages(names, t));
  }, [labelled]);

  const figure = useMemo(() => {
    if (!data || !players.length || !x || !y) return null;
    const font = { color: themeColors.text, family: CHART_FONT_FAMILY, size: compact ? 11 : 13 };
    const hoverlabel = { bgcolor: themeColors.hoverBg, font: { color: themeColors.hoverText, family: CHART_FONT_FAMILY } };
    const hoverText = (p: SeasonPlayer) =>
      `<b>${p.name}</b><br>${p.team} · ${groupOf(p)}<br>${Math.round(minutesOf(p))} min${filtered ? " in selection" : `, ${p.matches} matches`}<br>` +
      `${axisLabel(x)}: ${fmtNum(value(p, x))}<br>${axisLabel(y)}: ${fmtNum(value(p, y))}` + (z ? `<br>${axisLabel(z)}: ${fmtNum(value(p, z))}` : "") + `<br><i>Click for pitch actions</i>`;
    const size = (p: SeasonPlayer) => 7 + (Math.min(minutesOf(p), 3000) / 3000) * 14;
    const shown = new Set(labelled.map((p) => p.id));
    const sets = [...GROUPS, SUB_ONLY].filter((g) => players.some((p) => groupOf(p) === g));
    const noPhoto = (p: SeasonPlayer) => !getCachedPlayerImage(p.name, p.team);

    const traces = sets.map((g) => {
      const ps = players.filter((p) => groupOf(p) === g);
      const common = {
        name: g, customdata: ps.map((p) => p.id), hovertext: ps.map(hoverText), hoverinfo: "text", hoverlabel,
        textposition: "top center", textfont: { color: themeColors.text, family: CHART_FONT_FAMILY, size: compact ? 9 : 11 },
      };
      if (z) {
        return {
          ...common, type: "scatter3d", mode: "markers+text",
          text: ps.map((p) => (shown.has(p.id) ? p.name.split(" ").slice(-1)[0] : "")),
          x: ps.map((p) => value(p, x)), y: ps.map((p) => value(p, y)), z: ps.map((p) => value(p, z)),
          marker: { size: ps.map((p) => (isHi(p) ? 9 : 4.5)), color: GROUP_COLORS[g], opacity: q.length > 1 ? ps.map((p) => (isHi(p) ? 1 : 0.35)) : 0.85, line: { color: themeColors.text, width: 0.3 } },
        };
      }
      return {
        ...common, type: "scatter", mode: "markers+text",
        // photos stand in for the dot of labelled players; the name goes under the photo
        text: ps.map((p) => (shown.has(p.id) ? p.name.split(" ").slice(-1)[0] : "")),
        x: ps.map((p) => value(p, x)), y: ps.map((p) => value(p, y)),
        marker: {
          size: ps.map((p) => (shown.has(p.id) && !noPhoto(p) ? BUBBLE_PX : isHi(p) ? size(p) + 5 : size(p))),
          color: ps.map((p) => (shown.has(p.id) && !noPhoto(p) ? "rgba(255,255,255,0.96)" : GROUP_COLORS[g])),
          opacity: ps.map((p) => (q.length > 1 && !isHi(p) ? 0.18 : shown.has(p.id) && !noPhoto(p) ? 1 : 0.72)),
          // labelled players get a ring in their position colour; everyone else keeps the thin outline
          line: { color: ps.map((p) => (shown.has(p.id) && !noPhoto(p) ? GROUP_COLORS[g] : isHi(p) ? themeColors.text : "rgba(255,255,255,0.35)")), width: ps.map((p) => (shown.has(p.id) && !noPhoto(p) ? 3 : isHi(p) ? 2 : 0.6)) },
        },
      };
    });
    const legend = { orientation: "h", y: 1.06, x: 0, font: { color: themeColors.text, family: CHART_FONT_FAMILY, size: 12 } };

    if (z) {
      const axis = (m: string) => ({ title: { text: axisLabel(m), font: { size: 11 } }, gridcolor: themeColors.pitchLine, color: themeColors.muted });
      return { data: traces, layout: { width, height, margin: { l: 0, r: 0, t: 30, b: 0 }, paper_bgcolor: "rgba(0,0,0,0)", font, legend, scene: { bgcolor: "rgba(0,0,0,0)", xaxis: axis(x), yaxis: axis(y), zaxis: axis(z), camera: { eye: { x: 1.6, y: -1.6, z: 0.9 } } } } };
    }

    const xs = players.map((p) => value(p, x));
    const ys = players.map((p) => value(p, y));
    const median = (a: number[]) => [...a].sort((m, n) => m - n)[Math.floor(a.length / 2)];
    const [mx, my] = [median(xs), median(ys)];
    const pad = (a: number[]): [number, number] => {
      const lo = Math.min(...a);
      const hi = Math.max(...a);
      const d = (hi - lo || 1) * 0.07;
      return [lo < 0 ? lo - d : Math.max(0, lo - d), hi + d * 2.5]; // extra room on top for the photo bubbles and names
    };
    const [x0, x1] = pad(xs);
    const [y0, y1] = pad(ys);
    const margin = { l: compact ? 52 : 70, r: 20, t: 40, b: compact ? 54 : 66 };
    const plotW = width - margin.l - margin.r;
    const plotH = height - margin.t - margin.b;
    const images = labelled
      .map((p) => ({ p, src: getCachedPlayerImage(p.name, p.team) }))
      .filter((r): r is { p: SeasonPlayer; src: string } => Boolean(r.src))
      .map(({ p, src }) => ({
        source: inlinePhotos[src] ?? src, xref: "x", yref: "y", x: value(p, x), y: value(p, y),
        sizex: ((x1 - x0) * PHOTO_PX) / plotW, sizey: ((y1 - y0) * PHOTO_PX) / plotH,
        xanchor: "center", yanchor: "middle", sizing: "contain", layer: "above", opacity: q.length > 1 && !isHi(p) ? 0.35 : 1,
      }));
    const axis = (m: string, range: [number, number]) => ({
      range, gridcolor: themeColors.pitchLine, zeroline: false, linecolor: themeColors.pitchLine,
      tickfont: { color: themeColors.muted, family: CHART_FONT_FAMILY, size: compact ? 10 : 12 },
      title: { text: axisLabel(m), font: { color: themeColors.text, family: CHART_FONT_FAMILY, size: compact ? 11 : 13 }, standoff: 10 },
    });
    return {
      data: traces,
      layout: {
        width, height, margin, paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: themeColors.surface, font, legend, hovermode: "closest",
        xaxis: axis(x, [x0, x1]), yaxis: axis(y, [y0, y1]), images,
        shapes: [
          { type: "line", x0: mx, x1: mx, y0, y1, line: { color: themeColors.muted, width: 1, dash: "dash" } },
          { type: "line", x0, x1, y0: my, y1: my, line: { color: themeColors.muted, width: 1, dash: "dash" } },
        ],
      },
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, players, labelled, x, y, z, mode, q, themeColors, width, height, compact, filters, slices, imageTick, inlinePhotos]);

  const toggleGroup = (g: string) => setGroups((prev) => (prev.includes(g) ? prev.filter((item) => item !== g) : [...prev, g]));
  const chosen = data?.players.find((p) => p.id === selected) ?? null;
  const { actions, error: actionsError } = usePlayerActions(league, season, chosen?.id ?? null);
  const shownMetrics = [...new Set([x, y, ...(z ? [z] : [])])];

  return (
    <section className="card stack">
      <div className="chart-card-head">
        <div>
          <h2>Player scatter explorer</h2>
          <p className="muted">
            Compare players on any two metrics, or add a third to rotate in 3D. Dot size is minutes played; labelled players show
            their photo. Click a player to see where those actions happened.
          </p>
        </div>
        <DownloadPngButton
          filename={`${league}-player-scatter`}
          title={() => `${data?.league_name ?? ""}: ${labels[x] ?? x} vs ${labels[y] ?? y}`}
          filters={() => [
            VALUE_MODES.find((m) => m.id === mode)?.label ?? "",
            ...(z ? [`Z: ${labels[z] ?? z}`] : []),
            ...(team ? [team] : []),
            ...(groups.length < GROUPS.length + 1 ? [groups.join(" + ")] : []),
            ...(ageActive ? [ageBand.toUpperCase()] : []),
            ...(q.length > 1 ? [`Highlight: ${highlight}`] : []),
            ...describeSelection(filters),
            `Min ${minMinutes} min`,
          ]}
          scopeSelector="section.card"
          maxCharts={1}
          renderImage={z ? undefined : () => {
            const leagueInfo = LEAGUE_PRESENTATION[league];
            const xs = players.map((p) => value(p, x));
            const ys = players.map((p) => value(p, y));
            const median = (a: number[]) => [...a].sort((m, n) => m - n)[Math.floor(a.length / 2)];
            const range = (a: number[]): [number, number] => {
              const lo = Math.min(...a);
              const hi = Math.max(...a);
              const d = (hi - lo || 1) * 0.07;
              return [lo < 0 ? lo - d : Math.max(0, lo - d), hi + d * 2.5];
            };
            const shown = new Set(labelled.map((p) => p.id));
            const present = [...GROUPS, SUB_ONLY].filter((g) => players.some((p) => groupOf(p) === g));
            return renderScatterPng({
              title: `${labels[x] ?? x} vs ${labels[y] ?? y}`,
              subtitle: [
                VALUE_MODES.find((m) => m.id === mode)?.label ?? "",
                `min ${minMinutes} minutes`,
                ...(team ? [team] : []),
                ...(groups.length < GROUPS.length + 1 ? [groups.join(" + ")] : []),
                ...(ageActive ? [ageBand.toUpperCase()] : []),
                ...(q.length > 1 ? [`Highlight: ${highlight}`] : []),
                ...describeSelection(filters),
                `${leagueInfo?.name ?? league} ${season.replace("-", "/")}`,
              ].join("  |  "),
              leagueLogo: leagueInfo?.logo,
              xTitle: axisLabel(x),
              yTitle: axisLabel(y),
              xRange: range(xs),
              yRange: range(ys),
              refX: median(xs),
              refY: median(ys),
              legend: present.map((g) => ({ label: g, color: GROUP_COLORS[g] })),
              note: "Marker size = minutes played  |  dashed lines = league medians",
              // highlighted players first so their cards get the best spots
              points: [...players].sort((a, b) => Number(isHi(b)) - Number(isHi(a))).map((p) => {
                const src = getCachedPlayerImage(p.name, p.team);
                const dim = q.length > 1 && !isHi(p);
                const name = p.name.split(" ").slice(-1)[0];
                return {
                  x: value(p, x), y: value(p, y), color: GROUP_COLORS[groupOf(p)],
                  kind: shown.has(p.id) && src ? ("photo" as const) : ("dot" as const),
                  r: ((7 + (Math.min(minutesOf(p), 3000) / 3000) * 14) / 2) * 1.5,
                  alpha: dim ? 0.18 : shown.has(p.id) ? 1 : 0.72,
                  imageUrl: src,
                  label: shown.has(p.id) ? name : undefined,
                };
              }),
            });
          }}
        />
      </div>

      {error ? <p className="inline-warning">{error}</p> : null}

      <div className="season-scatter-controls">
        <label>
          <span>X axis</span>
          <MetricSelect metrics={metrics} value={x} onChange={setX} disabled={!data} />
        </label>
        <label>
          <span>Y axis</span>
          <MetricSelect metrics={metrics} value={y} onChange={setY} disabled={!data} />
        </label>
        <label>
          <span>Z axis (3D)</span>
          <MetricSelect metrics={metrics} value={z} onChange={setZ} disabled={!data} allowNone="None (2D)" />
        </label>
        <label>
          <span>Values</span>
          <select className="select" value={mode} onChange={(e) => setMode(e.target.value as ValueMode)}>
            {VALUE_MODES.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
          </select>
        </label>
        <label>
          <span>Minimum minutes{filtered ? " in selection" : ""}: {minMinutes}</span>
          <input type="range" min={0} max={filtered ? 900 : Math.min(maxMinutes, 1800)} step={filtered ? 15 : 30} value={minMinutes} onChange={(e) => setMinMinutes(Number(e.target.value))} />
        </label>
        <label>
          <span>Team</span>
          <select className="select" value={team} onChange={(e) => setTeam(e.target.value)} disabled={!data}>
            <option value={NONE}>All teams</option>
            {teams.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
        <label>
          <span>Highlight player</span>
          <input className="select" type="search" placeholder="Type a name" value={highlight} onChange={(e) => setHighlight(e.target.value)} />
        </label>
        <label>
          <span>Names on chart: {labelTop === 0 ? "off" : `top ${labelTop}`}</span>
          <input type="range" min={0} max={15} step={1} value={labelTop} onChange={(e) => setLabelTop(Number(e.target.value))} />
        </label>
      </div>

      <SliceFilters value={filters} onChange={setFilters} note={filtered ? (sliceError ? "Could not load the game-state figures." : waitingForSlices ? "Loading game-state figures…" : undefined) : undefined} />

      <div className="season-chip-row" role="group" aria-label="Position">
        {[...GROUPS, SUB_ONLY].map((g) => (
          <button key={g} type="button" className={`season-chip${groups.includes(g) ? " is-on" : ""}`} style={{ "--chip": GROUP_COLORS[g] } as React.CSSProperties} onClick={() => toggleGroup(g)} aria-pressed={groups.includes(g)}>
            {g}
          </button>
        ))}
        {data?.has_age ? <><span className="season-chip-sep" aria-hidden="true" /><AgeChips value={ageBand} onChange={setAgeBand} /></> : null}
        <span className="muted season-count">{players.length} players</span>
      </div>

      <div ref={setHost} className="plotly-chart-shell season-scatter-shell">
        {!data && !error ? <p className="muted">Loading players…</p> : null}
        {data && !figure && !waitingForSlices ? <p className="muted">No players match these filters.</p> : null}
        {figure ? (
          <Plot
            data={figure.data} layout={figure.layout} config={plotConfig} className="plotly-chart" style={{ width: "100%", height }}
            onClick={(event: { points?: { customdata?: number }[] }) => {
              const id = event.points?.[0]?.customdata;
              if (typeof id === "number") setSelected(id);
            }}
          />
        ) : null}
      </div>

      {chosen ? (
        <div className="season-player-detail stack">
          <div className="season-player-detail-head">
            <h3>{chosen.name}</h3>
            <p className="muted">{chosen.team} · {chosen.minutes} min · {chosen.matches} matches</p>
            <DownloadPngButton
              filename={`${chosen.name}-actions`}
              title={`${chosen.name}: where it happens`}
              filters={() => [chosen.team, ...describeSelection({ ...ALL_SELECTED, phases: filters.phases })]}
              scopeSelector=".season-player-detail"
              chartGroupSelector=".season-pitch-map"
              maxCharts={3}
            />
            <button type="button" className="season-chip" onClick={() => setSelected(null)}>Close</button>
          </div>
          {actionsError ? <p className="inline-warning">Could not load this player's actions.</p> : null}
          {!actions && !actionsError ? <p className="muted">Loading actions…</p> : null}
          {actions ? (
            <div className="season-pitch-pair">
              {shownMetrics.map((m) => {
                const action = data?.metric_action?.[m];
                const events = action ? actions[action] : undefined;
                return events?.length ? (
                  <PlayerActionsMap key={m} events={events} phase={phaseOnly(filters)} title={labels[m] ?? m} subtitle={action !== m ? `shown as ${labels[action ?? ""] ?? action}` : undefined} />
                ) : (
                  <p key={m} className="muted">{labels[m] ?? m}: {action ? "no recorded actions" : "a rating, so no pitch view"}.</p>
                );
              })}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
