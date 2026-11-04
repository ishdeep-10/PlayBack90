"use client";

import { useMemo, useState } from "react";

import { LEAGUE_PRESENTATION } from "../../lib/leagues";
import type { PlayerSlices, SeasonPlayerMetrics } from "../../lib/api";
import { getCachedPlayerImage, PlayerAvatar } from "../PlayerAvatar";
import { DownloadPngButton } from "../DownloadPngButton";
import { AgeChips, inAgeBand, type AgeBand } from "./AgeFilter";
import { MetricSelect } from "./MetricSelect";
import { PlayerActionsMap, usePlayerActions } from "./pitch";
import { GROUPS, GROUP_COLORS, SUB_ONLY, VALUE_MODES, groupOf, modeSuffix, playerSliceValue, playerValue, sliceMinutes, type ValueMode } from "./playerValues";
import { ALL_SELECTED, SliceFilters, describeSelection, isFiltered, phaseOnly, type SliceSelection } from "./SliceFilters";
import { renderLeaderboardPng } from "./leaderboardExport";
import { fmtNum, useSeasonFile } from "./useSeasonChart";

type Props = { league: string; season: string };

export function SeasonLeaderboard({ league, season }: Props) {
  const { data, error } = useSeasonFile<SeasonPlayerMetrics>(league, season, "player-metrics");
  const [metric, setMetric] = useState("key_passes");
  const [mode, setMode] = useState<ValueMode>("p90");
  const [minMinutes, setMinMinutes] = useState(270);
  const [top, setTop] = useState(12);
  const [groups, setGroups] = useState<string[]>([...GROUPS, SUB_ONLY]);
  const [team, setTeam] = useState("");
  const [selected, setSelected] = useState<number | null>(null);
  const [filters, setFilters] = useState<SliceSelection>(ALL_SELECTED);
  const filtered = isFiltered(filters);
  const { data: slices, error: sliceError } = useSeasonFile<PlayerSlices>(league, season, "player-slices", filtered);
  const sliceById = useMemo(() => new Map((slices?.players ?? []).map((p) => [p.id, p])), [slices]);
  const [ageBand, setAgeBand] = useState<AgeBand>("all");
  const ageActive = Boolean(data?.has_age) && ageBand !== "all";

  const metrics = useMemo(() => [...(data?.metrics ?? [])].sort((a, b) => a.label.localeCompare(b.label)), [data]);
  const label = metrics.find((m) => m.key === metric)?.label ?? metric;
  const teams = useMemo(() => [...new Set((data?.players ?? []).map((p) => p.team))].sort(), [data]);

  const rows = useMemo(
    () =>
      (data?.players ?? [])
        .filter((p) => {
          const s = sliceById.get(p.id);
          const minutes = filtered ? sliceMinutes(s, filters) : p.minutes;
          return minutes >= minMinutes && groups.includes(groupOf(p)) && (!team || p.team === team) && (!filtered || Boolean(s)) &&
            (!ageActive || inAgeBand(p.age, ageBand));
        })
        .map((p) => ({ p, v: filtered ? playerSliceValue(sliceById.get(p.id), metric, mode, filters, data?.padj?.[p.team] ?? 1) : playerValue(p, metric, mode, data?.padj) }))
        .sort((a, b) => b.v - a.v)
        .slice(0, top),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [data, minMinutes, groups, team, metric, mode, top, filtered, filters, sliceById, ageActive, ageBand],
  );

  const action = data?.metric_action?.[metric];
  const chosen = rows.find((r) => r.p.id === selected)?.p ?? null;
  const { actions, error: actionsError } = usePlayerActions(league, season, chosen?.id ?? null);
  const toggle = (g: string) => setGroups((prev) => (prev.includes(g) ? prev.filter((x) => x !== g) : [...prev, g]));

  return (
    <section className="card stack">
      <div className="chart-card-head">
        <div>
          <h2>Leaderboard</h2>
          <p className="muted">The top players on any metric. Select a player to see where {action ? "the actions behind this metric happened" : "their actions happened"} on the pitch.</p>
        </div>
        <DownloadPngButton
          filename={`${league}-leaderboard-${metric}`}
          title={`Top players: ${label}${modeSuffix(mode)}`}
          filters={() => [...(team ? [team] : []), ...(groups.length < GROUPS.length + 1 ? [groups.join(" + ")] : []), ...(ageActive ? [ageBand.toUpperCase()] : []), ...describeSelection(filters), `Min ${minMinutes} min`, `Top ${top}`]}
          renderImage={() => {
            const leagueInfo = LEAGUE_PRESENTATION[league];
            const subtitle = [
              VALUE_MODES.find((m) => m.id === mode)?.label ?? "",
              `min ${minMinutes} minutes`,
              ...(team ? [team] : []),
              ...(groups.length < GROUPS.length + 1 ? [groups.join(" + ")] : []),
              ...(ageActive ? [ageBand.toUpperCase()] : []),
              ...describeSelection(filters),
              `${leagueInfo?.name ?? league} ${season.replace("-", "/")}`,
            ];
            return renderLeaderboardPng({
              title: `Top ${rows.length} players: ${label}`,
              subtitle: subtitle.join("  |  "),
              leagueLogo: leagueInfo?.logo,
              rows: rows.map(({ p, v }) => ({
                name: p.name,
                sub: `${p.team}  |  ${filtered ? sliceMinutes(sliceById.get(p.id), filters) : p.minutes} min`,
                value: v,
                valueText: fmtNum(v),
                photo: getCachedPlayerImage(p.name, p.team) ?? null,
              })),
            });
          }}
        />
      </div>

      {error ? <p className="inline-warning">{error}</p> : null}

      <div className="season-scatter-controls">
        <label>
          <span>Metric</span>
          <MetricSelect metrics={metrics} value={metric} onChange={(k) => { setMetric(k); setSelected(null); }} disabled={!data} />
        </label>
        <label>
          <span>Values</span>
          <select className="select" value={mode} onChange={(e) => setMode(e.target.value as ValueMode)}>
            {VALUE_MODES.map((m) => (
              <option key={m.id} value={m.id}>{m.label}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Team</span>
          <select className="select" value={team} onChange={(e) => setTeam(e.target.value)} disabled={!data}>
            <option value="">All teams</option>
            {teams.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Minimum minutes{filtered ? " in selection" : ""}: {minMinutes}</span>
          <input type="range" min={0} max={1800} step={30} value={minMinutes} onChange={(e) => setMinMinutes(Number(e.target.value))} />
        </label>
        <label>
          <span>Players shown: {top}</span>
          <input type="range" min={4} max={30} step={1} value={top} onChange={(e) => setTop(Number(e.target.value))} />
        </label>
      </div>

      <SliceFilters value={filters} onChange={(f) => { setFilters(f); setMinMinutes(isFiltered(f) ? 60 : 270); }} note={filtered ? (sliceError ? "Could not load the filtered figures." : !slices ? "Loading filtered figures…" : undefined) : undefined} />

      <div className="season-chip-row" role="group" aria-label="Position">
        {[...GROUPS, SUB_ONLY].map((g) => (
          <button key={g} type="button" className={`season-chip${groups.includes(g) ? " is-on" : ""}`} style={{ "--chip": GROUP_COLORS[g] } as React.CSSProperties} onClick={() => toggle(g)} aria-pressed={groups.includes(g)}>
            {g}
          </button>
        ))}
        {data?.has_age ? <><span className="season-chip-sep" aria-hidden="true" /><AgeChips value={ageBand} onChange={setAgeBand} /></> : null}
      </div>

      {!data && !error ? <p className="muted">Loading players…</p> : null}
      {data && !rows.length ? <p className="muted">No players match these filters.</p> : null}

      <ol className="season-player-grid">
        {rows.map(({ p, v }, i) => (
          <li key={p.id}>
            <button type="button" className={`season-player-card${selected === p.id ? " is-selected" : ""}`} onClick={() => setSelected(selected === p.id ? null : p.id)} aria-pressed={selected === p.id}>
              <span className="season-player-rank">{i + 1}</span>
              <PlayerAvatar name={p.name} team={p.team} size={68} />
              <strong className="season-player-name">{p.name}</strong>
              <span className="muted season-player-team">{p.team}</span>
              <span className="season-player-value">{fmtNum(v)}</span>
              <span className="muted season-player-metric">{label}{modeSuffix(mode)}</span>
            </button>
          </li>
        ))}
      </ol>

      {chosen ? (
        <div className="season-player-detail stack">
          <div className="season-player-detail-head">
            <PlayerAvatar name={chosen.name} team={chosen.team} size={48} />
            <div>
              <h3>{chosen.name}</h3>
              <p className="muted">{chosen.team} · {chosen.minutes} min · {chosen.matches} matches</p>
            </div>
          </div>
          {!action ? <p className="muted">This metric is a rating, not a single action, so there is no pitch view for it.</p> : null}
          {action && actionsError ? <p className="inline-warning">Could not load this player's actions.</p> : null}
          {action && !actions && !actionsError ? <p className="muted">Loading actions…</p> : null}
          {action && actions ? (
            actions[action]?.length ? (
              <PlayerActionsMap events={actions[action]} phase={phaseOnly(filters)} title={`${chosen.name}: ${data?.metrics.find((m) => m.key === action)?.label ?? label}`} subtitle={metric !== action ? `behind ${label}` : undefined} />
            ) : (
              <p className="muted">No recorded {label.toLowerCase()} for this player.</p>
            )
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
