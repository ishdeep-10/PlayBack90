"use client";

import { useEffect, useMemo, useState } from "react";

import type { PlayerSlices, SeasonPlayerMetrics } from "../../lib/api";
import { LEAGUE_PRESENTATION } from "../../lib/leagues";
import { Plot } from "../../lib/plotly";
import { CHART_FONT_FAMILY } from "../../lib/theme";
import { DownloadPngButton } from "../DownloadPngButton";
import { getCachedPlayerImage, prefetchPlayerImages } from "../PlayerAvatar";
import { AgeChips, inAgeBand, type AgeBand } from "./AgeFilter";
import { renderOverUnderPng } from "./overUnderExport";
import { sliceMinutes } from "./playerValues";
import { ALL_SELECTED, SliceFilters, describeSelection, isFiltered, selectedCells, sumCells, type SliceSelection } from "./SliceFilters";
import { useChartFrame, useSeasonFile } from "./useSeasonChart";

type Props = { league: string; season: string };
type Kind = "goals" | "assists" | "ga" | "conversion" | "keyconv" | "passes" | "passrate";

type Measure = {
  label: string;
  note: string;
  actual: string[];
  expected: string[];
  actualName: string;
  expectedName: string;
  /** a rate measure: both sides are divided by this metric (e.g. shots) and shown in percentage points */
  per?: string;
  perName?: string;
  minPer?: number;
};

const KINDS: Record<Kind, Measure> = {
  goals: { label: "Goals vs xG", note: "Non-penalty goals against the xG of the shots taken.", actual: ["goals"], expected: ["xg"], actualName: "Goals", expectedName: "xG" },
  assists: { label: "Assists vs xA", note: "Assists against the xA of the passes made.", actual: ["assists"], expected: ["xa"], actualName: "Assists", expectedName: "xA" },
  ga: { label: "Goals + assists vs xG + xA", note: "Goal involvements against the chances they came from.", actual: ["goals", "assists"], expected: ["xg", "xa"], actualName: "Goals + assists", expectedName: "xG + xA" },
  conversion: { label: "Shot conversion vs expected (%)", note: "Share of shots that became goals against the share the xG predicted, in percentage points.", actual: ["goals"], expected: ["xg"], per: "shots", perName: "shots", minPer: 15, actualName: "Conversion", expectedName: "Expected conversion" },
  keyconv: { label: "Key passes turned into assists vs expected (%)", note: "Assists per key pass against xA per key pass, in percentage points.", actual: ["assists"], expected: ["xa"], per: "key_passes", perName: "key passes", minPer: 10, actualName: "Assists per key pass", expectedName: "xA per key pass" },
  passes: { label: "Completed passes vs xPass", note: "Passes completed against the number the model expected to complete.", actual: ["passes_ok"], expected: ["xpass"], actualName: "Completed passes", expectedName: "Expected completed" },
  passrate: { label: "Pass completion vs expected (%)", note: "Completion rate against the model's expected rate for the passes attempted, in percentage points.", actual: ["passes_ok"], expected: ["xpass"], per: "passes", perName: "passes", minPer: 150, actualName: "Completion", expectedName: "Expected completion" },
};
const GOOD = "#34d399";
const BAD = "#f87171";
const plotConfig = { responsive: true, displayModeBar: false };
const num = (v: unknown) => (typeof v === "number" ? v : 0);

export function SeasonOverUnder({ league, season }: Props) {
  const { data, error } = useSeasonFile<SeasonPlayerMetrics>(league, season, "player-metrics");
  const { themeColors, width, setHost, compact } = useChartFrame();
  const [kind, setKind] = useState<Kind>("goals");
  const [minMinutes, setMinMinutes] = useState(180);
  const [count, setCount] = useState(8);
  const k = KINDS[kind];
  const [filters, setFilters] = useState<SliceSelection>(ALL_SELECTED);
  const filtered = isFiltered(filters);
  const { data: slices, error: sliceError } = useSeasonFile<PlayerSlices>(league, season, "player-slices", filtered);
  const sliceById = useMemo(() => new Map((slices?.players ?? []).map((p) => [p.id, p])), [slices]);
  const [ageBand, setAgeBand] = useState<AgeBand>("all");
  const ageActive = Boolean(data?.has_age) && ageBand !== "all";

  const rows = useMemo(() => {
    const cells = selectedCells(filters);
    const total = (p: SeasonPlayerMetrics["players"][number], keys: string[]) =>
      keys.reduce((a, key) => a + (filtered ? sumCells(sliceById.get(p.id)?.v[key], cells) : num(p[key])), 0);
    const all = (data?.players ?? [])
      .filter((p) => (filtered ? sliceMinutes(sliceById.get(p.id), filters) : p.minutes) >= minMinutes && (!filtered || sliceById.has(p.id)) && (!ageActive || inAgeBand(p.age, ageBand)))
      .map((p) => {
        const den = k.per ? total(p, [k.per]) : 0;
        const a = total(p, k.actual);
        const e = total(p, k.expected);
        // rate measures are shown as percent, and need enough attempts to mean anything
        return k.per ? { p, den, actual: den ? (a / den) * 100 : 0, exp: den ? (e / den) * 100 : 0, valid: den >= (k.minPer ?? 1) } : { p, den, actual: a, exp: e, valid: true };
      })
      .filter((r) => r.valid)
      .map((r) => ({ ...r, diff: r.actual - r.exp }))
      .filter((r) => r.exp > 0 || r.actual > 0);
    const sorted = [...all].sort((a, b) => b.diff - a.diff);
    const over = sorted.slice(0, count);
    const under = sorted.slice(-count);
    return [...over, ...under.filter((u) => !over.includes(u))].sort((a, b) => a.diff - b.diff);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, minMinutes, count, k, filtered, filters, sliceById, ageActive, ageBand]);

  // photos for the Share image: the chart itself shows none, so warm the cache for whoever is listed
  useEffect(() => {
    const byTeam = new Map<string, string[]>();
    for (const r of rows) byTeam.set(r.p.team, [...(byTeam.get(r.p.team) ?? []), r.p.name]);
    byTeam.forEach((names, t) => prefetchPlayerImages(names, t));
  }, [rows]);

  const figure = useMemo(() => {
    if (!rows.length) return null;
    return {
      data: [
        {
          type: "bar", orientation: "h", x: rows.map((r) => r.diff), y: rows.map((r) => `${r.p.name} · ${r.p.team}`),
          marker: { color: rows.map((r) => (r.diff >= 0 ? GOOD : BAD)) },
          text: rows.map((r) => `${r.diff > 0 ? "+" : ""}${r.diff.toFixed(1)}${k.per ? " pts" : ""}`), textposition: "outside",
          textfont: { color: themeColors.text, family: CHART_FONT_FAMILY, size: 11 },
          hovertext: rows.map((r) => `<b>${r.p.name}</b><br>${r.p.team}<br>${r.p.minutes} min<br>${k.actualName}: ${k.per ? `${r.actual.toFixed(1)}% of ${r.den} ${k.perName}` : r.actual.toFixed(r.actual % 1 === 0 ? 0 : 1)}<br>${k.expectedName}: ${k.per ? `${r.exp.toFixed(1)}%` : r.exp.toFixed(2)}<br>Difference: ${r.diff > 0 ? "+" : ""}${r.diff.toFixed(2)}${k.per ? " points" : ""}`),
          hoverinfo: "text", hoverlabel: { bgcolor: themeColors.hoverBg, font: { color: themeColors.hoverText, family: CHART_FONT_FAMILY } },
        },
      ],
      layout: {
        width, height: Math.max(360, rows.length * (compact ? 24 : 30) + 90), margin: { l: compact ? 150 : 230, r: 50, t: 16, b: 52 },
        paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: themeColors.surface, font: { color: themeColors.text, family: CHART_FONT_FAMILY }, showlegend: false,
        xaxis: { range: [Math.min(0, ...rows.map((r) => r.diff)) * 1.22, Math.max(0, ...rows.map((r) => r.diff)) * 1.22], title: { text: k.per ? `${k.actualName} minus ${k.expectedName} (percentage points)` : `${k.actualName} minus ${k.expectedName}`, font: { color: themeColors.text, family: CHART_FONT_FAMILY, size: 13 }, standoff: 10 }, gridcolor: themeColors.pitchLine, zerolinecolor: themeColors.muted, tickfont: { color: themeColors.muted, size: 11 } },
        yaxis: { tickfont: { color: themeColors.text, family: CHART_FONT_FAMILY, size: compact ? 10 : 12 }, automargin: true },
      },
    };
  }, [rows, themeColors, width, compact, k]);

  return (
    <section className="card stack">
      <div className="chart-card-head">
        <div>
          <h2>Over and under performers</h2>
          <p className="muted">
            Who is doing more (green) or less (red) than the chances or passes they were given suggest. {k.note} Small samples swing
            a lot early in the season.
          </p>
        </div>
        <DownloadPngButton
          filename={`${league}-${kind}-vs-expected`}
          title={`${k.label}: over and under performers`}
          filters={() => [`Min ${minMinutes} min`, ...(ageActive ? [ageBand.toUpperCase()] : []), ...describeSelection(filters), `${count} each side`]}
          renderImage={() => {
            const leagueInfo = LEAGUE_PRESENTATION[league];
            const unit = k.per ? " pts" : "";
            const figures = (r: (typeof rows)[number]) =>
              k.per
                ? `${r.actual.toFixed(1)}% vs ${r.exp.toFixed(1)}% expected (${r.den} ${k.perName})`
                : `${r.actual.toFixed(r.actual % 1 === 0 ? 0 : 1)} ${k.actualName.toLowerCase()} vs ${r.exp.toFixed(1)} expected`;
            return renderOverUnderPng({
              title: k.label,
              subtitle: [
                "Over and under performers",
                `min ${minMinutes} minutes`,
                ...(ageActive ? [ageBand.toUpperCase()] : []),
                ...describeSelection(filters),
                `${leagueInfo?.name ?? league} ${season.replace("-", "/")}`,
              ].join("  |  "),
              leagueLogo: leagueInfo?.logo,
              note: k.note,
              rows: [...rows].reverse().map((r) => ({
                name: r.p.name,
                sub: `${r.p.team}  |  ${Math.round(r.p.minutes)} min  |  ${figures(r)}`,
                photo: getCachedPlayerImage(r.p.name, r.p.team) ?? null,
                diff: r.diff,
                diffText: `${r.diff > 0 ? "+" : ""}${r.diff.toFixed(1)}${unit}`,
              })),
            });
          }}
        />
      </div>

      {error ? <p className="inline-warning">{error}</p> : null}

      <div className="season-scatter-controls">
        <label>
          <span>Measure</span>
          <select className="select" value={kind} onChange={(e) => setKind(e.target.value as Kind)}>
            {(Object.keys(KINDS) as Kind[]).map((key) => (
              <option key={key} value={key}>{KINDS[key].label}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Minimum minutes{filtered ? " in selection" : ""}: {minMinutes}</span>
          <input type="range" min={0} max={1500} step={30} value={minMinutes} onChange={(e) => setMinMinutes(Number(e.target.value))} />
        </label>
        <label>
          <span>Each side: {count} players</span>
          <input type="range" min={4} max={15} step={1} value={count} onChange={(e) => setCount(Number(e.target.value))} />
        </label>
      </div>

      <SliceFilters value={filters} onChange={(f) => { setFilters(f); setMinMinutes(isFiltered(f) ? 60 : 180); }} note={filtered ? (sliceError ? "Could not load the filtered figures." : !slices ? "Loading filtered figures…" : undefined) : undefined} />

      {data?.has_age ? (
        <div className="season-chip-row" role="group" aria-label="Age">
          <AgeChips value={ageBand} onChange={setAgeBand} />
        </div>
      ) : null}

      <div ref={setHost} className="plotly-chart-shell season-scatter-shell">
        {!data && !error ? <p className="muted">Loading players…</p> : null}
        {data && !figure ? <p className="muted">No players match these filters.</p> : null}
        {figure ? <Plot data={figure.data} layout={figure.layout} config={plotConfig} className="plotly-chart" style={{ width: "100%", height: figure.layout.height }} /> : null}
      </div>
    </section>
  );
}
