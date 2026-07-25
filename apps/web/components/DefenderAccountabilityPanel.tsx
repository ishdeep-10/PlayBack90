"use client";

import { useEffect, useMemo, useState } from "react";

import { getAnalysisView } from "../lib/api";
import { colorWithAlpha, num } from "../lib/theme";
import { DownloadPngButton, type SideTable, type SideTableRow } from "./DownloadPngButton";
import { BreachPitch } from "./DefensiveVulnerabilityPanel";
import { type EntryRow } from "./EntriesPenetrationPanel";
import { PlayerAvatar, getCachedPlayerImage } from "./PlayerAvatar";

type Props = {
  matchId: string;
  source: string;
  filePath?: string;
  jobId?: string;
  team: string;
  teams: string[];
  teamColor: string;
};

type Scope = "final_third" | "box";

const SCOPE_LABELS: Record<Scope, string> = {
  final_third: "Final third conceded",
  box: "Box conceded",
};

// Defending team zones in mirrored coordinates (same as DefensiveVulnerabilityPanel)
const DEFENSIVE_LANES = [
  { key: "left", label: "Left flank", low: 54.16, high: 68.01 },
  { key: "left_hs", label: "Left half-space", low: 43.16, high: 54.16 },
  { key: "center", label: "Central", low: 24.84, high: 43.16 },
  { key: "right_hs", label: "Right half-space", low: 13.84, high: 24.84 },
  { key: "right", label: "Right flank", low: 0, high: 13.84 },
] as const;

type LaneKey = (typeof DEFENSIVE_LANES)[number]["key"];

function laneOf(endY: number): LaneKey {
  return (DEFENSIVE_LANES.find((lane) => endY >= lane.low && endY < lane.high)?.key ?? "center") as LaneKey;
}

function mirror(entry: EntryRow): EntryRow {
  return { ...entry, x: 105 - entry.x, y: 68 - entry.y, end_x: 105 - entry.end_x, end_y: 68 - entry.end_y };
}

type DefenderStats = {
  beaten: number;
  shots_allowed: number;
  goals_allowed: number;
  zones: Partial<Record<LaneKey, number>>;
  attackers: Record<string, number>;
  minutes: number[];
};

type ActionRow = Record<string, string | number | boolean | null | undefined>;

type ActiveDefender = {
  player: string;
  total: number;
  tackles: number;
  interceptions: number;
  recoveries: number;
  clearances: number;
  defensive_third: number;
};


export function DefenderAccountabilityPanel({ matchId, source, filePath, jobId, team, teams, teamColor }: Props) {
  const [entries, setEntries] = useState<{ final_third: EntryRow[]; box: EntryRow[] } | null>(null);
  const [activeDefenders, setActiveDefenders] = useState<ActiveDefender[]>([]);
  const [defensiveActions, setDefensiveActions] = useState<ActionRow[]>([]);
  const [scope, setScope] = useState<Scope>("final_third");
  const [selectedDefender, setSelectedDefender] = useState("");
  const [timeRange, setTimeRange] = useState("all");
  const [isLoading, setIsLoading] = useState(true);

  const opponent = teams.find((candidate) => candidate && candidate !== team) ?? "";

  const fetchData = (range: string) => {
    if (!opponent) return;
    setIsLoading(true);
    setTimeRange(range);
    setSelectedDefender("");

    const entriesFilters: Record<string, string | undefined> = { team: opponent, timeRange: range };
    const defFilters: Record<string, string | undefined> = { team, timeRange: range };
    if (source !== "r2") {
      entriesFilters.job_id = jobId;
      defFilters.job_id = jobId;
    }
    const makeBody = (filters: Record<string, string | undefined>) =>
      source !== "r2"
        ? { match_id: matchId, source, filters }
        : { match_id: matchId, source: "r2", file_path: filePath, filters };

    Promise.all([
      getAnalysisView("territory-entries", makeBody(entriesFilters)),
      getAnalysisView("defensive-actions", makeBody(defFilters)),
    ])
      .then(([entriesView, defView]) => {
        const raw = (entriesView.payload ?? {}) as { final_third?: EntryRow[]; box?: EntryRow[] };
        setEntries({
          final_third: (raw.final_third ?? []).map(mirror),
          box: (raw.box ?? []).map(mirror),
        });
        const defPayload = (defView.payload ?? {}) as Record<string, unknown>;
        const summary = (defPayload.player_summary ?? []) as ActiveDefender[];
        setActiveDefenders(summary.filter((p) => p.defensive_third > 0).sort((a, b) => b.defensive_third - a.defensive_third));
        setDefensiveActions((defPayload.actions ?? []) as ActionRow[]);
      })
      .catch(() => {
        setEntries(null);
        setActiveDefenders([]);
        setDefensiveActions([]);
      })
      .finally(() => setIsLoading(false));
  };

  useEffect(() => {
    fetchData("all");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [matchId, source, filePath, jobId, opponent]);

  const scopedEntries = useMemo(() => entries?.[scope] ?? [], [entries, scope]);

  // Per-zone: contested vs uncontested breach counts
  const zoneStats = useMemo(() => {
    return DEFENSIVE_LANES.map((lane) => {
      const lane_entries = scopedEntries.filter((e) => laneOf(e.end_y) === lane.key);
      const contested = lane_entries.filter((e) => e.last_defender && !e.uncontested).length;
      const uncontested = lane_entries.filter((e) => e.uncontested).length;
      const shots = lane_entries.filter((e) => e.led_to_shot).length;
      return { ...lane, total: lane_entries.length, contested, uncontested, shots };
    });
  }, [scopedEntries]);

  // Per defender: aggregated beaten counts and zone breakdown
  const beatenDefenders = useMemo(() => {
    const byPlayer = new Map<string, DefenderStats>();
    for (const entry of scopedEntries) {
      const def = entry.last_defender;
      if (!def || entry.uncontested) continue;
      const zone = laneOf(entry.end_y);
      const current = byPlayer.get(def) ?? { beaten: 0, shots_allowed: 0, goals_allowed: 0, zones: {}, attackers: {}, minutes: [] };
      current.beaten += 1;
      if (entry.led_to_shot) current.shots_allowed += 1;
      if (entry.led_to_goal) current.goals_allowed += 1;
      current.zones[zone] = (current.zones[zone] ?? 0) + 1;
      if (entry.player) current.attackers[entry.player] = (current.attackers[entry.player] ?? 0) + 1;
      current.minutes.push(entry.minute);
      byPlayer.set(def, current);
    }
    return [...byPlayer.entries()].sort((a, b) => b[1].beaten - a[1].beaten);
  }, [scopedEntries]);

  // Uncontested breach count (no defender close by)
  const uncontestedCount = useMemo(
    () => scopedEntries.filter((e) => e.uncontested).length,
    [scopedEntries],
  );

  const maxZoneTotal = Math.max(1, ...zoneStats.map((z) => z.total));

  // Interventions per defender, for net accountability (stops vs beaten).
  const stopsByPlayer = useMemo(() => {
    const map = new Map<string, number>();
    activeDefenders.forEach((p) => map.set(p.player, num(p.total)));
    return map;
  }, [activeDefenders]);
  const beatenByPlayer = useMemo(() => new Map(beatenDefenders), [beatenDefenders]);

  // Nominal home lane per defender, inferred from where they made their
  // defensive actions in the own defensive third (needs 2+ actions to count).
  const homeLanes = useMemo(() => {
    const positions = new Map<string, number[]>();
    defensiveActions.forEach((row) => {
      const player = String(row.player ?? "").trim();
      const x = num(row.x);
      const y = num(row.y);
      if (!player || x > 35) return;
      const ys = positions.get(player) ?? [];
      ys.push(y);
      positions.set(player, ys);
    });
    const map = new Map<string, LaneKey>();
    positions.forEach((ys, player) => {
      if (ys.length < 2) return;
      map.set(player, laneOf(ys.reduce((sum, y) => sum + y, 0) / ys.length));
    });
    return map;
  }, [defensiveActions]);

  // Uncontested breaches grouped by arrival lane, with the lane's nominal owners.
  const uncontestedByLane = useMemo(() => {
    const counts = new Map<LaneKey, number>();
    scopedEntries.filter((e) => e.uncontested).forEach((e) => {
      const lane = laneOf(e.end_y);
      counts.set(lane, (counts.get(lane) ?? 0) + 1);
    });
    return DEFENSIVE_LANES
      .filter((lane) => (counts.get(lane.key) ?? 0) > 0)
      .map((lane) => ({
        ...lane,
        count: counts.get(lane.key) ?? 0,
        owners: [...homeLanes.entries()].filter(([, key]) => key === lane.key).map(([player]) => player),
      }));
  }, [scopedEntries, homeLanes]);

  const stopRateLine = (player: string, beaten: number) => {
    const stops = stopsByPlayer.get(player) ?? 0;
    if (!stops && !beaten) return "";
    return `stop rate ${Math.round((stops / Math.max(1, stops + beaten)) * 100)}% (${stops} stops)`;
  };
  const topAttackerLine = (stats: DefenderStats) => {
    const top = Object.entries(stats.attackers).sort((a, b) => b[1] - a[1])[0];
    return top ? `most by ${top[0]}${top[1] > 1 ? ` (${top[1]}×)` : ""}` : "";
  };
  const minutesLine = (stats: DefenderStats) => {
    if (!stats.minutes.length) return "";
    const late = stats.minutes.filter((minute) => minute >= 60).length;
    if (stats.minutes.length >= 3 && late / stats.minutes.length >= 0.65) {
      return `${late} of ${stats.minutes.length} after 60'`;
    }
    return [...stats.minutes].sort((a, b) => a - b).slice(0, 5).map((minute) => `${Math.round(minute)}'`).join(", ");
  };

  const pitchEntries = useMemo(
    () => selectedDefender
      ? scopedEntries.filter((e) => e.last_defender === selectedDefender && !e.uncontested)
      : scopedEntries,
    [scopedEntries, selectedDefender],
  );

  if (!isLoading && (!entries || (!entries.final_third.length && !entries.box.length))) return null;

  // The export canvas has limited room — keep this to headline numbers and a
  // short player list so the pitch stays the hero of the image.
  const buildSideTable = (): SideTable | null => {
    const shots = scopedEntries.filter((e) => e.led_to_shot).length;
    const goals = scopedEntries.filter((e) => e.led_to_goal).length;
    const rows: SideTableRow[] = [
      { label: "Breaches", value: String(scopedEntries.length) },
      { label: "Contested / Uncontested", value: `${scopedEntries.length - uncontestedCount} / ${uncontestedCount}` },
      { label: "Led to shot", value: String(shots) },
      { label: "Goals conceded", value: String(goals) },
    ];
    if (beatenDefenders.length) {
      rows.push({ header: "Most beaten" });
      beatenDefenders.slice(0, 3).forEach(([player, stats]) => {
        const topZone = (Object.entries(stats.zones) as [LaneKey, number][])
          .sort((a, b) => b[1] - a[1])[0];
        const zoneName = topZone ? DEFENSIVE_LANES.find((l) => l.key === topZone[0])?.label : undefined;
        rows.push({
          image: getCachedPlayerImage(player, team),
          label: player,
          value: `${stats.beaten}×${stats.goals_allowed ? ` · ${stats.goals_allowed}⚽` : ""}`,
          sub: [zoneName, stopRateLine(player, stats.beaten)].filter(Boolean).join(" · "),
        });
      });
    }
    const topStopper = activeDefenders[0];
    if (topStopper) {
      rows.push({ header: "Busiest defender" });
      rows.push({
        image: getCachedPlayerImage(topStopper.player, team),
        label: topStopper.player,
        value: `${topStopper.defensive_third} in def 3rd`,
        sub: (beatenByPlayer.get(topStopper.player)?.beaten ?? 0) > 0
          ? stopRateLine(topStopper.player, beatenByPlayer.get(topStopper.player)?.beaten ?? 0)
          : "never beaten",
      });
    }
    return { title: `${team} · ${SCOPE_LABELS[scope]}`, rows, large: true };
  };

  return (
    <section className={`card stack${isLoading ? " is-loading-soft" : ""}`}>
      <div className="chart-card-head">
        <div>
          <span className="eyebrow">Defensive Accountability</span>
          <h2 style={{ margin: "6px 0 0" }}>Who handled the danger — {team}</h2>
        </div>
        <div className="channel-mode-controls">
          <div className="channel-mode-toggle" role="group" aria-label="Breach scope">
            {(["final_third", "box"] as Scope[]).map((value) => (
              <button
                key={value}
                type="button"
                className={scope === value ? "button" : "ghost-button"}
                onClick={() => {
                  setScope(value);
                  setSelectedDefender("");
                }}
              >
                {SCOPE_LABELS[value]} ({(entries?.[value] ?? []).length})
              </button>
            ))}
          </div>
          <div className="time-range-presets" role="group" aria-label="Time period">
            <button type="button" className={timeRange === "all" ? "button" : "ghost-button"} onClick={() => fetchData("all")} disabled={isLoading}>Full</button>
            <button type="button" className={timeRange === "0-45" ? "button" : "ghost-button"} onClick={() => fetchData("0-45")} disabled={isLoading}>1st H</button>
            <button type="button" className={timeRange === "45-90" ? "button" : "ghost-button"} onClick={() => fetchData("45-90")} disabled={isLoading}>2nd H</button>
          </div>
          <DownloadPngButton
            filename={`${team}-defender-accountability`}
            title={() => `Defensive Accountability — ${SCOPE_LABELS[scope]}`}
            filters={() => [
              team,
              SCOPE_LABELS[scope],
              ...(timeRange !== "all" ? [`${timeRange}'`] : []),
            ]}
            sideTable={buildSideTable}
            captureAspect={71 / 108}
          />
        </div>
      </div>

      <p className="muted-copy" style={{ margin: 0 }}>
        Where and by whom {team}'s defensive line was beaten. <strong>Contested</strong> = a defender tried but the entry still happened.{" "}
        <strong>Uncontested</strong> = no defensive action in the possession before the breach ({uncontestedCount} of {scopedEntries.length}).
      </p>

      <div className="entries-panel-card">
        <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
          <span className="eyebrow">
            Breach map{selectedDefender ? ` — beaten past ${selectedDefender}` : ""}
          </span>
          {selectedDefender && (
            <button type="button" className="pill" onClick={() => setSelectedDefender("")}>
              {selectedDefender} ✕
            </button>
          )}
        </div>
        <BreachPitch entries={pitchEntries} team={team} teamColor={teamColor} />
        <small className="muted chart-footnote">
          Defending the left goal — attacks arrive right → left. Red = became a shot; ✕ = goal conceded.
        </small>
        {beatenDefenders.length > 0 && (
          <small className="muted">Click a defender below to isolate the breaches they were beaten on.</small>
        )}
      </div>

      <div className="accountability-grid">
        {/* Left: zone exposure heatmap */}
        <div className="accountability-left">
          <div className="entries-panel-card">
            <span className="eyebrow">Zone exposure</span>
            {zoneStats.map((zone) => (
              <div key={zone.key} className="entries-channel-row">
                <span style={{ minWidth: 120 }}>{zone.label}</span>
                <div className="entries-bar entries-bar-team breach-bar" style={{ flex: 1 }}>
                  {/* Contested segment */}
                  <i
                    style={{
                      width: `${Math.max(zone.contested > 0 ? 2 : 0, (zone.contested / maxZoneTotal) * 100)}%`,
                      background: colorWithAlpha(teamColor, 0.7),
                    }}
                    title={`${zone.contested} contested`}
                  />
                  {/* Uncontested segment */}
                  <i
                    style={{
                      width: `${Math.max(zone.uncontested > 0 ? 2 : 0, (zone.uncontested / maxZoneTotal) * 100)}%`,
                      background: "rgba(248,113,113,0.8)",
                    }}
                    title={`${zone.uncontested} uncontested`}
                  />
                  <b>
                    {zone.total > 0
                      ? `${zone.total}${zone.shots ? ` · ${zone.shots}⚠` : ""}`
                      : "–"}
                  </b>
                </div>
              </div>
            ))}
            <small className="muted">
              <span style={{ display: "inline-flex", alignItems: "center", gap: 4, marginRight: 12 }}>
                <i style={{ display: "inline-block", width: 10, height: 10, borderRadius: 2, background: colorWithAlpha(teamColor, 0.7) }} />
                Contested (defender tried)
              </span>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                <i style={{ display: "inline-block", width: 10, height: 10, borderRadius: 2, background: "rgba(248,113,113,0.8)" }} />
                Uncontested
              </span>
            </small>
          </div>

          {beatenDefenders.length > 0 && (
            <div className="entries-panel-card">
              <span className="eyebrow">Defender zone breakdown</span>
              <div style={{ overflowX: "auto" }}>
                <table className="table" style={{ fontSize: 12, minWidth: 320 }}>
                  <thead>
                    <tr>
                      <th style={{ textAlign: "left", paddingRight: 8 }}>Defender</th>
                      {DEFENSIVE_LANES.map((lane) => (
                        <th key={lane.key} style={{ textAlign: "center", fontSize: 10, opacity: 0.7, whiteSpace: "nowrap" }}>
                          {lane.label.split(" ")[0]}
                        </th>
                      ))}
                      <th style={{ textAlign: "center" }}>Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {beatenDefenders.map(([player, stats]) => (
                      <tr key={player}>
                        <td style={{ paddingRight: 8 }}>
                          <button
                            type="button"
                            className="table-sort-button"
                            onClick={() => setSelectedDefender((current) => (current === player ? "" : player))}
                            style={selectedDefender === player ? { color: teamColor } : undefined}
                          >
                            <span className="shot-player-cell">
                              <PlayerAvatar name={player} team={team} size={18} />
                              <span style={{ fontSize: 12 }}>{player.split(" ").at(-1)}</span>
                            </span>
                          </button>
                        </td>
                        {DEFENSIVE_LANES.map((lane) => {
                          const count = stats.zones[lane.key] ?? 0;
                          return (
                            <td key={lane.key} style={{ textAlign: "center" }}>
                              {count > 0 ? (
                                <span
                                  style={{
                                    display: "inline-block",
                                    width: 22,
                                    height: 22,
                                    lineHeight: "22px",
                                    borderRadius: 4,
                                    background: colorWithAlpha(teamColor, Math.min(0.9, 0.25 + (count / Math.max(1, stats.beaten)) * 0.65)),
                                    fontSize: 11,
                                    fontWeight: 600,
                                    textAlign: "center",
                                  }}
                                >
                                  {count}
                                </span>
                              ) : (
                                <span style={{ opacity: 0.25 }}>–</span>
                              )}
                            </td>
                          );
                        })}
                        <td style={{ textAlign: "center", fontWeight: 700 }}>{stats.beaten}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        {/* Right: beaten defenders + active defenders */}
        <div className="accountability-right">
          {beatenDefenders.length > 0 && (
            <div className="entries-panel-card">
              <span className="eyebrow">Beaten — entry still happened after their action</span>
              {beatenDefenders.slice(0, 6).map(([player, stats]) => {
                const zoneLabels = (Object.entries(stats.zones) as [LaneKey, number][])
                  .sort((a, b) => b[1] - a[1])
                  .map(([key]) => DEFENSIVE_LANES.find((l) => l.key === key)?.label ?? key)
                  .slice(0, 2)
                  .join(", ");
                const context = [topAttackerLine(stats), minutesLine(stats)].filter(Boolean).join(" · ");
                const netLine = stopRateLine(player, stats.beaten);
                const isSelected = selectedDefender === player;
                return (
                  <div
                    key={player}
                    className="setpiece-won-row"
                    role="button"
                    tabIndex={0}
                    aria-pressed={isSelected}
                    style={{ cursor: "pointer", ...(isSelected ? { outline: `1.5px solid ${colorWithAlpha(teamColor, 0.7)}`, borderRadius: 8 } : {}) }}
                    onClick={() => setSelectedDefender((current) => (current === player ? "" : player))}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        setSelectedDefender((current) => (current === player ? "" : player));
                      }
                    }}
                  >
                    <PlayerAvatar name={player} team={team} size={22} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <span style={{ display: "block", fontWeight: 600, fontSize: 13 }}>{player}</span>
                      {zoneLabels && <span style={{ display: "block", fontSize: 11, opacity: 0.6 }}>{zoneLabels}</span>}
                      {context && <span style={{ display: "block", fontSize: 11, opacity: 0.6 }}>{context}</span>}
                      {netLine && <span style={{ display: "block", fontSize: 11, opacity: 0.75 }}>{netLine}</span>}
                    </div>
                    <div style={{ textAlign: "right", fontSize: 12, flexShrink: 0 }}>
                      <strong>{stats.beaten}×</strong>
                      {stats.shots_allowed > 0 && (
                        <span style={{ display: "block", color: "#ef4444", fontSize: 11 }}>{stats.shots_allowed} led to shot</span>
                      )}
                      {stats.goals_allowed > 0 && (
                        <span style={{ display: "block", color: "#ef4444", fontSize: 11, fontWeight: 700 }}>
                          {stats.goals_allowed} goal{stats.goals_allowed > 1 ? "s" : ""} conceded
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
              {uncontestedCount > 0 && (
                <small className="muted" style={{ marginTop: 6, display: "block" }}>
                  + {uncontestedCount} breach{uncontestedCount !== 1 ? "es" : ""} with no defensive action in the possession
                </small>
              )}
            </div>
          )}

          {uncontestedByLane.some((lane) => lane.owners.length > 0) && (
            <div className="entries-panel-card">
              <span className="eyebrow">Uncontested breaches — zonal context</span>
              {uncontestedByLane.map((lane) => (
                <div key={lane.key} className="entries-channel-row" style={{ alignItems: "baseline" }}>
                  <span style={{ minWidth: 120 }}>{lane.label}</span>
                  <span style={{ fontWeight: 700 }}>{lane.count}</span>
                  <span style={{ fontSize: 11, opacity: 0.6 }}>
                    {lane.owners.length ? `zone of ${lane.owners.map((owner) => owner.split(" ").at(-1)).join(", ")}` : "no regular occupant"}
                  </span>
                </div>
              ))}
              <small className="muted" style={{ marginTop: 6, display: "block" }}>
                Zone occupants are inferred from where each defender made their own-third defensive actions — zonal context, not individual blame.
              </small>
            </div>
          )}

          {activeDefenders.length > 0 && (
            <div className="entries-panel-card">
              <span className="eyebrow">Active in own third — defensive interventions</span>
              {activeDefenders.slice(0, 6).map((player) => {
                const breakdown = [
                  player.tackles > 0 ? `${player.tackles}T` : null,
                  player.interceptions > 0 ? `${player.interceptions}I` : null,
                  player.recoveries > 0 ? `${player.recoveries}R` : null,
                  player.clearances > 0 ? `${player.clearances}C` : null,
                ]
                  .filter(Boolean)
                  .join(" · ");
                return (
                  <div key={player.player} className="setpiece-won-row">
                    <PlayerAvatar name={player.player} team={team} size={22} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <span style={{ display: "block", fontWeight: 600, fontSize: 13 }}>{player.player}</span>
                      {breakdown && <span style={{ display: "block", fontSize: 11, opacity: 0.6 }}>{breakdown}</span>}
                    </div>
                    <div style={{ textAlign: "right", fontSize: 12, flexShrink: 0 }}>
                      <strong>{player.defensive_third}</strong>
                      <span style={{ display: "block", opacity: 0.5, fontSize: 11 }}>in def 3rd</span>
                      <span style={{ display: "block", fontSize: 11, opacity: 0.75 }}>
                        {(beatenByPlayer.get(player.player)?.beaten ?? 0) > 0
                          ? stopRateLine(player.player, beatenByPlayer.get(player.player)?.beaten ?? 0)
                          : "never beaten"}
                      </span>
                    </div>
                  </div>
                );
              })}
              <small className="muted" style={{ marginTop: 6, display: "block" }}>
                T = tackles · I = interceptions · R = recoveries · C = clearances
              </small>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
