"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import type { SeasonTeamMetrics, SeasonZones, TeamSlices } from "../../lib/api";
import { LEAGUE_PRESENTATION } from "../../lib/leagues";
import { Plot } from "../../lib/plotly";
import { CHART_FONT_FAMILY, readThemeColors } from "../../lib/theme";
import { DownloadPngButton } from "../DownloadPngButton";
import { MetricSelect } from "./MetricSelect";
import { zoneCells, zoneFigure, type ZoneCells, type ZoneValue } from "./pitch";
import { ALL_SELECTED, SliceFilters, describeSelection, isFiltered, selectedCells, selectedMinuteCells, sumCells, type SliceSelection } from "./SliceFilters";
import { renderScatterPng } from "./scatterExport";
import { useInlineImages, useSeasonFile } from "./useSeasonChart";

type Props = {
  data: SeasonTeamMetrics;
  /** team name -> crest URL (standings crest first, then the club-logo table). */
  crests: Record<string, string>;
};

const NONE = "";
const CREST_PX = 34; // every crest gets the same visual area (a CREST_PX square), whatever its proportions
const plotConfig = { responsive: true, displayModeBar: false };

const fmt = (v: number) => (Math.abs(v) >= 100 ? v.toFixed(0) : Math.abs(v) >= 10 ? v.toFixed(1) : v.toFixed(2));

function initials(team: string) {
  const parts = team.replace(/[^A-Za-z0-9 ]/g, "").split(" ").filter(Boolean);
  return (parts.length > 1 ? parts[0][0] + parts[1][0] : team.slice(0, 3)).toUpperCase();
}

function paddedRange(values: number[]): [number, number] {
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const pad = (hi - lo || Math.abs(hi) || 1) * 0.08;
  return [lo - pad, hi + pad];
}

export function SeasonTeamScatter({ data, crests }: Props) {
  const metrics = useMemo(() => [...data.metrics].sort((a, b) => a.label.localeCompare(b.label)), [data.metrics]);
  const byKey = useMemo(() => Object.fromEntries(data.metrics.map((m) => [m.key, m])), [data.metrics]);
  const has = (key: string) => key in byKey;

  const [x, setX] = useState(has("average_ppda") ? "average_ppda" : metrics[0]?.key ?? "");
  const [y, setY] = useState(has("xg_per_shot_conceded") ? "xg_per_shot_conceded" : metrics[1]?.key ?? "");
  const [z, setZ] = useState(NONE);
  const [highlight, setHighlight] = useState(NONE);
  const [showPitch, setShowPitch] = useState(false);
  const [pitchTeam, setPitchTeam] = useState("");
  const [filters, setFilters] = useState<SliceSelection>(ALL_SELECTED);
  const filtered = isFiltered(filters);
  const { data: slices, error: sliceError } = useSeasonFile<TeamSlices>(data.league, data.season.replace("/", "_"), "team-slices", filtered);
  const cells = useMemo(() => selectedCells(filters), [filters]);
  const minuteCells = useMemo(() => selectedMinuteCells(filters), [filters]);
  const sliceByTeam = useMemo(() => new Map((slices?.teams ?? []).map((t) => [t.team, t])), [slices]);
  // Under a game-state / time filter only metrics that are plain sums can be re-added (ratios of other events cannot).
  const FILTER_OK = useMemo(() => new Set([...(slices?.metrics ?? []), "xg_per_shot", "xg_per_shot_conceded"]), [slices]);
  const inlineCrests = useInlineImages(useMemo(() => [...new Set(Object.values(crests))], [crests]));
  const [themeColors, setThemeColors] = useState(readThemeColors);
  const [width, setWidth] = useState(900);
  const hostRef = useRef<HTMLDivElement>(null);
  // width / height of each crest file, so wide and tall crests are scaled to the same area
  const [aspects, setAspects] = useState<Record<string, number>>({});

  useEffect(() => {
    let cancelled = false;
    for (const url of new Set(Object.values(crests))) {
      const img = new window.Image();
      img.onload = () => {
        if (!cancelled && img.naturalHeight) setAspects((prev) => ({ ...prev, [url]: img.naturalWidth / img.naturalHeight }));
      };
      img.src = url;
    }
    return () => {
      cancelled = true;
    };
  }, [crests]);

  useEffect(() => {
    const update = () => setThemeColors(readThemeColors());
    update();
    const observer = new MutationObserver(update);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "data-theme"] });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const host = hostRef.current;
    if (!host || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(280, Math.floor(entry.contentRect.width))));
    observer.observe(host);
    return () => observer.disconnect();
  }, []);

  const compact = width < 560;
  const height = z ? (compact ? 440 : 600) : compact ? 420 : 580;
  const rows = data.teams;
  const val = (team: (typeof rows)[number], key: string) => {
    if (!filtered) {
      const v = team[key];
      return typeof v === "number" ? v : null;
    }
    const sl = sliceByTeam.get(team.team);
    if (!sl || !FILTER_OK.has(key)) return null;
    const sum = (k: string) => sumCells(sl.v[k], cells);
    if (key === "xg_per_shot") return sum("shots") > 0 ? sum("xg_for") / sum("shots") : null;
    if (key === "xg_per_shot_conceded") return sum("shots_conceded") > 0 ? sum("xg_against") / sum("shots_conceded") : null;
    const minutes = sumCells(sl.m, minuteCells);
    return minutes >= 45 ? (sum(key) / minutes) * 90 : null; // under 45 minutes in the selection is too little to compare
  };
  const metricLabel = (m: { key: string; label: string }) => (filtered && slices && !FILTER_OK.has(m.key) ? `${m.label} (not available with filters)` : m.label);
  const metricDisabled = (key: string) => filtered && Boolean(slices) && !FILTER_OK.has(key);
  const usable = rows.filter((t) => val(t, x) !== null && val(t, y) !== null && (!z || val(t, z) !== null));
  const label = (key: string) => byKey[key]?.label ?? key;
  const axisTitle = (key: string) => {
    const text = label(key);
    return byKey[key]?.higher_is_better === false && !/lower/i.test(text) ? `${text} (lower is better)` : text;
  };

  const figure = useMemo(() => {
    if (!usable.length || !x || !y) return null;
    const font = { color: themeColors.text, family: CHART_FONT_FAMILY, size: compact ? 11 : 13 };
    const hover = (t: (typeof rows)[number]) =>
      `<b>${t.team}</b><br>${label(x)}: ${fmt(val(t, x)!)}<br>${label(y)}: ${fmt(val(t, y)!)}` +
      (z ? `<br>${label(z)}: ${fmt(val(t, z)!)}` : "") +
      (filtered ? `<br>per 90 in the selection` : `<br>${t.matches} matches`) + `<br><i>Click to compare on the pitch</i>`;
    const hoverlabel = { bgcolor: themeColors.hoverBg, font: { color: themeColors.hoverText, family: CHART_FONT_FAMILY } };

    if (z) {
      const isHi = (t: (typeof rows)[number]) => t.team === highlight;
      return {
        data: [
          {
            type: "scatter3d",
            mode: "markers+text",
            x: usable.map((t) => val(t, x)),
            y: usable.map((t) => val(t, y)),
            z: usable.map((t) => val(t, z)),
            text: usable.map((t) => t.team),
            textposition: "top center",
            textfont: { color: themeColors.text, family: CHART_FONT_FAMILY, size: 10 },
            customdata: usable.map((t) => t.team),
            hovertext: usable.map(hover),
            hoverinfo: "text",
            hoverlabel,
            marker: {
              size: usable.map((t) => (isHi(t) ? 10 : 6)),
              color: usable.map((t) => (isHi(t) ? themeColors.accent2 : themeColors.accent)),
              opacity: 0.95,
              line: { color: themeColors.text, width: 0.5 },
            },
          },
        ],
        layout: {
          width,
          height,
          margin: { l: 0, r: 0, t: 0, b: 0 },
          paper_bgcolor: "rgba(0,0,0,0)",
          font,
          showlegend: false,
          scene: {
            bgcolor: "rgba(0,0,0,0)",
            xaxis: { title: { text: axisTitle(x), font: { size: 11 } }, gridcolor: themeColors.pitchLine, color: themeColors.muted },
            yaxis: { title: { text: axisTitle(y), font: { size: 11 } }, gridcolor: themeColors.pitchLine, color: themeColors.muted },
            zaxis: { title: { text: axisTitle(z), font: { size: 11 } }, gridcolor: themeColors.pitchLine, color: themeColors.muted },
            camera: { eye: { x: 1.6, y: -1.6, z: 0.9 } },
          },
        },
      };
    }

    const margin = { l: compact ? 56 : 76, r: 24, t: 20, b: compact ? 56 : 68 };
    const plotW = width - margin.l - margin.r;
    const plotH = height - margin.t - margin.b;
    const xs = usable.map((t) => val(t, x)!);
    const ys = usable.map((t) => val(t, y)!);
    const [x0, x1] = paddedRange(xs);
    const [y0, y1] = paddedRange(ys);
    // Each crest is sized to the same area (CREST_PX squared) in screen pixels, converted to axis units; "contain" keeps
    // its aspect ratio, so a tall or wide crest is not drawn smaller or larger than a square one.
    const crestSize = (url: string) => {
      const r = Math.min(Math.max(aspects[url] ?? 1, 0.55), 1.8);
      const w = CREST_PX * 0.86 * Math.sqrt(r);
      const h = CREST_PX * 0.86 / Math.sqrt(r);
      return { sizex: ((x1 - x0) * w) / plotW, sizey: ((y1 - y0) * h) / plotH };
    };
    const meanX = xs.reduce((a, b) => a + b, 0) / xs.length;
    const meanY = ys.reduce((a, b) => a + b, 0) / ys.length;
    const dim = (t: (typeof rows)[number]) => (highlight && t.team !== highlight ? 0.28 : 1);
    const noCrest = usable.filter((t) => !crests[t.team]);
    const axis = {
      gridcolor: themeColors.pitchLine,
      zeroline: false,
      linecolor: themeColors.pitchLine,
      tickfont: { color: themeColors.muted, family: CHART_FONT_FAMILY, size: compact ? 10 : 12 },
      title: { font: { color: themeColors.text, family: CHART_FONT_FAMILY, size: compact ? 11 : 13 }, standoff: 10 },
    };
    return {
      data: [
        {
          type: "scatter",
          mode: "markers",
          x: xs,
          y: ys,
          customdata: usable.map((t) => t.team),
          hovertext: usable.map(hover),
          hoverinfo: "text",
          hoverlabel,
          // A light badge behind every crest keeps dark crests readable and gives all clubs the same footprint.
          marker: {
            size: CREST_PX + 8,
            color: usable.map((t) => `rgba(255,255,255,${0.92 * dim(t)})`),
            line: { color: usable.map((t) => `rgba(148,163,184,${0.5 * dim(t)})`), width: 1 },
          },
        },
        {
          type: "scatter",
          mode: "markers+text",
          x: noCrest.map((t) => val(t, x)),
          y: noCrest.map((t) => val(t, y)),
          text: noCrest.map((t) => initials(t.team)),
          textfont: { color: "#fff", family: CHART_FONT_FAMILY, size: 10 },
          hoverinfo: "skip",
          marker: { size: CREST_PX - 4, color: noCrest.map((t) => `rgba(100,116,139,${dim(t)})`) },
        },
      ],
      layout: {
        width,
        height,
        margin,
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: themeColors.surface,
        font,
        showlegend: false,
        hovermode: "closest",
        xaxis: { ...axis, range: [x0, x1], title: { ...axis.title, text: axisTitle(x) } },
        yaxis: { ...axis, range: [y0, y1], title: { ...axis.title, text: axisTitle(y) } },
        shapes: [
          { type: "line", x0: meanX, x1: meanX, y0, y1, line: { color: themeColors.muted, width: 1, dash: "dash" } },
          { type: "line", x0, x1, y0: meanY, y1: meanY, line: { color: themeColors.muted, width: 1, dash: "dash" } },
        ],
        images: usable
          .filter((t) => crests[t.team])
          .map((t) => ({
            source: inlineCrests[crests[t.team]] ?? crests[t.team],
            xref: "x",
            yref: "y",
            x: val(t, x),
            y: val(t, y),
            ...crestSize(crests[t.team]),
            xanchor: "center",
            yanchor: "middle",
            sizing: "contain",
            opacity: dim(t),
            layer: "above",
          })),
      },
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [usable.length, x, y, z, highlight, themeColors, width, height, crests, compact, aspects, filters, slices, cells, minuteCells, inlineCrests]);

  const teamsSorted = useMemo(() => rows.map((t) => t.team).sort((a, b) => a.localeCompare(b)), [rows]);

  return (
    <section className="card stack">
      <div className="chart-card-head">
        <div>
          <h2>Team scatter explorer</h2>
          <p className="muted">
            Pick any two metrics to compare every team{z ? "" : ", or add a third to rotate the view in 3D"}. Figures are
            per match across {data.matches} matches; dashed lines mark the league average.
          </p>
        </div>
        <DownloadPngButton
          filename={`${data.league}-team-scatter`}
          title={() => `${data.league_name}: ${label(x)} vs ${label(y)}`}
          filters={() => [...(z ? [`Z: ${label(z)}`] : []), ...(highlight ? [`Highlight: ${highlight}`] : []), ...describeSelection(filters), ...(filtered ? ["Per 90"] : ["Per match"])]}
          scopeSelector="section.card"
          maxCharts={1}
          renderImage={z ? undefined : () => {
            const leagueInfo = LEAGUE_PRESENTATION[data.league];
            const xs = usable.map((t) => val(t, x)!);
            const ys = usable.map((t) => val(t, y)!);
            const mean = (a: number[]) => a.reduce((m, n) => m + n, 0) / a.length;
            return renderScatterPng({
              title: `${label(x)} vs ${label(y)}`,
              subtitle: [
                filtered ? "Per 90" : "Per match",
                ...(highlight ? [`Highlight: ${highlight}`] : []),
                ...describeSelection(filters),
                `${data.league_name} ${data.season.replace("_", "/")}`,
              ].join("  |  "),
              leagueLogo: leagueInfo?.logo,
              xTitle: axisTitle(x),
              yTitle: axisTitle(y),
              xRange: paddedRange(xs),
              yRange: paddedRange(ys),
              refX: mean(xs),
              refY: mean(ys),
              note: "Dashed lines = league average",
              points: usable.map((t) => ({
                x: val(t, x)!, y: val(t, y)!, color: "#ffffff", kind: "crest" as const,
                imageUrl: crests[t.team] ?? null, label: initials(t.team),
                alpha: highlight && t.team !== highlight ? 0.28 : 1,
              })),
            });
          }}
        />
      </div>

      <div className="season-scatter-controls">
        <label>
          <span>X axis</span>
          <MetricSelect metrics={metrics} value={x} onChange={setX} describe={metricLabel} isDisabled={(m) => metricDisabled(m.key)} />
        </label>
        <label>
          <span>Y axis</span>
          <MetricSelect metrics={metrics} value={y} onChange={setY} describe={metricLabel} isDisabled={(m) => metricDisabled(m.key)} />
        </label>
        <label>
          <span>Z axis (3D)</span>
          <MetricSelect metrics={metrics} value={z} onChange={setZ} describe={metricLabel} isDisabled={(m) => metricDisabled(m.key)} allowNone="None (2D)" />
        </label>
        <label>
          <span>Highlight team</span>
          <select className="select" value={highlight} onChange={(e) => setHighlight(e.target.value)}>
            <option value={NONE}>None</option>
            {teamsSorted.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </label>
      </div>

      <SliceFilters
        value={filters}
        onChange={setFilters}
        note={filtered ? (sliceError ? "Could not load the game-state figures." : !slices ? "Loading game-state figures…" : "Per 90 in the selection; teams with under 45 minutes in it are left out, and ratio metrics are unavailable.") : undefined}
      />

      <div ref={hostRef} className="plotly-chart-shell season-scatter-shell">
        {figure ? (
          <Plot
            data={figure.data}
            layout={figure.layout}
            config={plotConfig}
            className="plotly-chart"
            style={{ width: "100%", height }}
            onClick={(event: { points?: { customdata?: string }[] }) => {
              const picked = event.points?.[0]?.customdata;
              if (typeof picked === "string") {
                setPitchTeam(picked);
                setShowPitch(true);
              }
            }}
          />
        ) : (
          <p className="muted">{filtered && !slices ? "Loading…" : "No teams have values for this combination."}</p>
        )}
      </div>

      <div className="season-chip-row">
        <button type="button" className={`season-chip${showPitch ? " is-on" : ""}`} style={{ "--chip": "var(--accent)" } as React.CSSProperties} onClick={() => setShowPitch((v) => !v)} aria-pressed={showPitch}>
          {showPitch ? "Hide pitch comparison" : "Where does it happen on the pitch?"}
        </button>
        <span className="muted season-count">Click a crest to compare that team</span>
      </div>

      {showPitch ? (
        <TeamPitchCompare
          data={data}
          metricKeys={[...new Set([x, y, ...(z ? [z] : [])])]}
          label={label}
          teams={teamsSorted}
          teamA={pitchTeam || highlight || teamsSorted[0]}
          onTeamA={setPitchTeam}
          themeColors={themeColors}
          width={width}
        />
      ) : null}
    </section>
  );
}


type CompareProps = {
  data: SeasonTeamMetrics;
  metricKeys: string[];
  label: (key: string) => string;
  teams: string[];
  teamA: string;
  onTeamA: (t: string) => void;
  themeColors: ReturnType<typeof readThemeColors>;
  width: number;
};

const LEAGUE_AVG = "__league__";

/** The scatter's metrics drawn on the pitch: one team against another team or the league average, same colour scale. */
function TeamPitchCompare({ data, metricKeys, label, teams, teamA, onTeamA, themeColors, width }: CompareProps) {
  const { data: zones, error } = useSeasonFile<SeasonZones>(data.league, data.season.replace("/", "_"), "zones");
  const [metric, setMetric] = useState(metricKeys[0]);
  const [teamB, setTeamB] = useState(LEAGUE_AVG);
  const [value, setValue] = useState<"share" | "perMatch" | "diff">("share");
  const [phase, setPhase] = useState<"" | "__o" | "__s">("");
  const active = metricKeys.includes(metric) ? metric : metricKeys[0];
  const action = data.metric_action?.[active];
  const actionKey = action ? action + phase : undefined; // zones.json holds <action>, <action>__o (open play), <action>__s (set pieces)
  const half = Math.max(280, Math.floor((Math.min(width, 1100) - 16) / (value === "diff" ? 1.6 : 2)));
  const compact = half < 420;

  const figures = useMemo(() => {
    if (!zones || !actionKey) return null;
    const zoneValue: ZoneValue = value === "perMatch" ? "perMatch" : "share";
    const a = zoneCells(zones, teamA, actionKey, zoneValue);
    const b = zoneCells(zones, teamB === LEAGUE_AVG ? null : teamB, actionKey, zoneValue);
    if (!a || !b) return null;
    const nameB = teamB === LEAGUE_AVG ? "League average" : teamB;
    if (value === "diff") {
      const diff: ZoneCells = { ...a, shown: a.own.map((v, i) => v - b.own[i]), league: b.own };
      return [zoneFigure({ zones, cells: diff, value: "vsLeague", themeColors, width: half, compact, title: `${teamA} minus ${nameB}` })];
    }
    const scaleMax = Math.max(0.01, ...a.shown, ...b.shown);
    return [
      zoneFigure({ zones, cells: a, value: zoneValue, themeColors, width: half, compact, title: teamA, scaleMax }),
      zoneFigure({ zones, cells: b, value: zoneValue, themeColors, width: half, compact, title: nameB, scaleMax }),
    ];
  }, [zones, actionKey, teamA, teamB, value, themeColors, half, compact]);

  return (
    <div className="season-player-detail stack">
      <div className="season-scatter-controls">
        <label>
          <span>Metric on the pitch</span>
          <select className="select" value={active} onChange={(e) => setMetric(e.target.value)}>
            {metricKeys.map((k) => <option key={k} value={k}>{label(k)}</option>)}
          </select>
        </label>
        <label>
          <span>Team</span>
          <select className="select" value={teamA} onChange={(e) => onTeamA(e.target.value)}>
            {teams.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
        <label>
          <span>Compare with</span>
          <select className="select" value={teamB} onChange={(e) => setTeamB(e.target.value)}>
            <option value={LEAGUE_AVG}>League average</option>
            {teams.filter((t) => t !== teamA).map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
        <label>
          <span>Play phase</span>
          <select className="select" value={phase} onChange={(e) => setPhase(e.target.value as typeof phase)}>
            <option value="">All play</option>
            <option value="__o">Open play</option>
            <option value="__s">Set pieces</option>
          </select>
        </label>
        <label>
          <span>Show</span>
          <select className="select" value={value} onChange={(e) => setValue(e.target.value as typeof value)}>
            <option value="share">Share of each team's total</option>
            <option value="perMatch">Per match</option>
            <option value="diff">Difference (team minus comparison)</option>
          </select>
        </label>
      </div>
      {error ? <p className="inline-warning">{error}</p> : null}
      {!zones && !error ? <p className="muted">Loading pitch figures…</p> : null}
      {zones && !action ? <p className="muted">{label(active)} is a rating, not a single kind of action, so it has no pitch view. Pick another metric.</p> : null}
      {zones && action ? <p className="muted">Showing {zones.metrics.find((m) => m.key === action)?.label ?? action}{action !== active ? ` (the events behind ${label(active)})` : ""}. Attacking left to right. Season totals, not filtered by game state.</p> : null}
      {figures ? (
        <div className="season-compare-head">
          <DownloadPngButton
            filename={`${teamA}-${active}-pitch`}
            title={`${label(active)}: where it happens`}
            filters={() => [teamA, teamB === LEAGUE_AVG ? "vs league average" : `vs ${teamB}`, phase === "__o" ? "Open play" : phase === "__s" ? "Set pieces" : "All play"]}
            scopeSelector=".season-player-detail"
            maxCharts={2}
            captureAspect={figures[0].height / (figures[0].layout.width as number)}
          />
        </div>
      ) : null}
      {figures ? (
        <div className="season-pitch-pair">
          {figures.map((f, i) => (
            <Plot key={i} data={f.data} layout={f.layout} config={plotConfig} className="plotly-chart" style={{ width: f.layout.width, height: f.height }} />
          ))}
        </div>
      ) : null}
    </div>
  );
}
