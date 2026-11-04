"use client";

import { useMemo, useState } from "react";

import type { SeasonZones } from "../../lib/api";
import { LEAGUE_PRESENTATION } from "../../lib/leagues";
import { Plot } from "../../lib/plotly";
import { DownloadPngButton } from "../DownloadPngButton";
import { zoneCells, zoneFigure, type ZoneValue } from "./pitch";
import { renderZonesPng } from "./zonesExport";
import { useChartFrame, useSeasonFile } from "./useSeasonChart";

type Props = { league: string; season: string };
const plotConfig = { responsive: true, displayModeBar: false };

export function SeasonZonesChart({ league, season }: Props) {
  const { data, error } = useSeasonFile<SeasonZones>(league, season, "zones");
  const { themeColors, width, setHost, compact } = useChartFrame();
  const [metric, setMetric] = useState("turnovers");
  const [value, setValue] = useState<ZoneValue>("share");
  const [phase, setPhase] = useState<"" | "__o" | "__s">("");
  const [team, setTeam] = useState("");

  const teams = useMemo(() => (data?.teams ?? []).map((t) => t.team).sort((a, b) => a.localeCompare(b)), [data]);
  const current = team || teams[0] || "";
  const grouped = useMemo(() => {
    const out = new Map<string, { key: string; label: string }[]>();
    for (const m of data?.metrics ?? []) out.set(m.group ?? "Other", [...(out.get(m.group ?? "Other") ?? []), m]);
    return [...out.entries()];
  }, [data]);

  const cells = useMemo(() => (data ? zoneCells(data, current, metric + phase, value) : null), [data, current, metric, phase, value]);
  const pitchW = Math.min(width, 820); // a full-width pitch would be taller than the screen
  const figure = useMemo(
    () => (data && cells ? zoneFigure({ zones: data, cells, value, themeColors, width: pitchW, compact, title: current }) : null),
    [data, cells, value, themeColors, pitchW, compact, current],
  );

  return (
    <section className="card stack">
      <div className="chart-card-head">
        <div>
          <h2>Pitch zones</h2>
          <p className="muted">Where a team does something on the pitch, on a six-band, five-lane grid. Pick any of {data?.metrics.length ?? "the"} actions. Attacking left to right.</p>
        </div>
        {figure ? (
          <DownloadPngButton
            filename={`${current}-${metric}-zones`}
            title={`${current}: ${data?.metrics.find((m) => m.key === metric)?.label ?? metric}`}
            filters={() => [phase === "__o" ? "Open play" : phase === "__s" ? "Set pieces" : "All play", value === "share" ? "Share of total" : value === "perMatch" ? "Per match" : "Vs league average"]}
            renderImage={() => {
              if (!data || !cells) return Promise.resolve(null);
              const leagueInfo = LEAGUE_PRESENTATION[league];
              return renderZonesPng({
                title: `${current}: ${data.metrics.find((m) => m.key === metric)?.label ?? metric}`,
                subtitle: [
                  value === "share" ? "Share of the team's total" : value === "perMatch" ? "Per match" : "Difference vs league average",
                  phase === "__o" ? "open play" : phase === "__s" ? "set pieces" : "all play",
                  `${cells.total} events in ${cells.matches} matches (${(cells.total / Math.max(cells.matches, 1)).toFixed(1)} per match)`,
                  `${leagueInfo?.name ?? league} ${season.replace("-", "/")}`,
                ].join("  |  "),
                leagueLogo: leagueInfo?.logo,
                grid: data.grid,
                shown: cells.shown,
                own: cells.own,
                league: cells.league,
                value,
              });
            }}
          />
        ) : null}
      </div>

      {error ? <p className="inline-warning">{error}</p> : null}

      <div className="season-scatter-controls">
        <label>
          <span>Team</span>
          <select className="select" value={current} onChange={(e) => setTeam(e.target.value)} disabled={!data}>
            {teams.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Action</span>
          <select className="select" value={metric} onChange={(e) => setMetric(e.target.value)} disabled={!data}>
            {grouped.map(([group, items]) => (
              <optgroup key={group} label={group}>
                {items.map((m) => (
                  <option key={m.key} value={m.key}>{m.label}</option>
                ))}
              </optgroup>
            ))}
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
          <select className="select" value={value} onChange={(e) => setValue(e.target.value as ZoneValue)}>
            <option value="share">Share of the team's total</option>
            <option value="perMatch">Per match</option>
            <option value="vsLeague">Difference vs league average</option>
          </select>
        </label>
      </div>

      {cells ? (
        <p className="muted">
          {current}: {cells.total} events in {cells.matches} matches ({(cells.total / Math.max(cells.matches, 1)).toFixed(1)} per match).
        </p>
      ) : null}

      <div ref={setHost} className="plotly-chart-shell season-scatter-shell">
        {!data && !error ? <p className="muted">Loading…</p> : null}
        {figure ? <Plot data={figure.data} layout={figure.layout} config={plotConfig} className="plotly-chart" style={{ width: pitchW, height: figure.height, margin: "0 auto" }} /> : null}
      </div>
    </section>
  );
}
