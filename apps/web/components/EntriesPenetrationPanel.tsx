"use client";

import { DownloadPngButton, type ChartPanel, type SideTable, type SideTableRow } from "./DownloadPngButton";

import { useEffect, useMemo, useState } from "react";

import { getAnalysisView } from "../lib/api";
import { horizontalPitchShapes } from "../lib/pitch";
import { Plot } from "../lib/plotly";
import { CHART_FONT_FAMILY, colorWithAlpha, readThemeColors } from "../lib/theme";
import { PlayerAvatar, getCachedPlayerImage } from "./PlayerAvatar";

export type EntryRow = {
  minute: number;
  player: string;
  passer?: string;
  x: number;
  y: number;
  end_x: number;
  end_y: number;
  method: string;
  channel: string;
  in_box?: boolean;
  led_to_shot: boolean;
  led_to_goal: boolean;
  last_defender?: string;
  uncontested?: boolean;
};

type SequenceStats = {
  shot_possessions?: number;
  avg_passes_to_shot?: number;
  avg_passes_all?: number;
  direct_share?: number;
};

type EntriesPayload = {
  final_third: EntryRow[];
  box: EntryRow[];
  exits: EntryRow[];
  receptions: EntryRow[];
  sequence: SequenceStats;
  time_range?: string;
};

type Props = {
  matchId: string;
  source: string;
  league?: string;
  season?: string;
  jobId?: string;
  team: string;
  teams: string[];
  teamColor: string;
};

type Scope = "final_third" | "box" | "exits";

const SCOPE_LABELS: Record<Scope, string> = {
  final_third: "Final third",
  box: "Penalty box",
  exits: "Build-up exits",
};

export const METHOD_LABELS: Record<string, string> = {
  ground_pass: "Ground pass",
  carry: "Carry",
  cross: "Cross",
  long_ball: "Long ball",
  cutback: "Cutback",
  reception: "Pass received",
};

const METHOD_ORDER = ["ground_pass", "carry", "cross", "long_ball", "cutback"];

const CHANNEL_LABELS: Record<string, string> = {
  left: "Left wing",
  left_hs: "Left half-space",
  center: "Centre",
  right_hs: "Right half-space",
  right: "Right wing",
};

const CHANNEL_ORDER = ["left", "left_hs", "center", "right_hs", "right"];

export function methodColor(method: string, teamColor: string) {
  if (method === "carry") return "#38bdf8";
  if (method === "cross") return "#f59e0b";
  if (method === "long_ball") return "#a78bfa";
  if (method === "cutback") return "#facc15";
  return teamColor;
}

function entryHover(entry: EntryRow) {
  const outcome = entry.led_to_goal ? " · led to a goal" : entry.led_to_shot ? " · led to a shot" : "";
  return `${entry.minute}' · ${entry.player}<br>${METHOD_LABELS[entry.method] ?? entry.method} → ${CHANNEL_LABELS[entry.channel] ?? entry.channel}${outcome}`;
}

function methodShares(rows: EntryRow[]) {
  const total = Math.max(1, rows.length);
  return METHOD_ORDER.map((method) => ({
    method,
    count: rows.filter((row) => row.method === method).length,
  }))
    .filter((row) => row.count > 0 || ["ground_pass", "carry", "cross", "long_ball"].includes(row.method))
    .map((row) => ({ ...row, share: Math.round((row.count / total) * 100) }));
}

function EntriesPitch({ entries, team, teamColor, label }: { entries: EntryRow[]; team: string; teamColor: string; label: string }) {
  const [themeColors, setThemeColors] = useState(readThemeColors);

  useEffect(() => {
    const updateColors = () => setThemeColors(readThemeColors());
    updateColors();
    const observer = new MutationObserver(updateColors);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "data-theme"] });
    return () => observer.disconnect();
  }, []);

  const markerTrace = {
    x: entries.map((entry) => entry.end_x),
    y: entries.map((entry) => entry.end_y),
    mode: "markers",
    type: "scatter",
    marker: {
      size: entries.map((entry) => (entry.led_to_shot || entry.led_to_goal ? 11 : 7.5)),
      color: entries.map((entry) => colorWithAlpha(entry.led_to_goal ? "#22c55e" : methodColor(entry.method, teamColor), entry.led_to_shot || entry.led_to_goal ? 0.95 : 0.7)),
      line: { color: themeColors.mode === "dark" ? "#0f172a" : "#ffffff", width: 1.2 },
    },
    hovertext: entries.map(entryHover),
    hovertemplate: "%{hovertext}<extra></extra>",
    showlegend: false,
  };

  const arrowAnnotations = entries.map((entry) => ({
    x: entry.end_x,
    y: entry.end_y,
    ax: entry.x,
    ay: entry.y,
    xref: "x",
    yref: "y",
    axref: "x",
    ayref: "y",
    text: "",
    showarrow: true,
    arrowhead: 3,
    arrowsize: 1,
    arrowwidth: entry.led_to_shot || entry.led_to_goal ? 2.4 : 1.5,
    arrowcolor: colorWithAlpha(methodColor(entry.method, teamColor), entry.led_to_shot || entry.led_to_goal ? 0.92 : 0.5),
  }));

  return (
    <Plot
      data={[markerTrace]}
      layout={{
        autosize: true,
        height: 470,
        margin: { l: 14, r: 14, t: 8, b: 12 },
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: themeColors.surface,
        font: { color: themeColors.text, family: CHART_FONT_FAMILY },
        showlegend: false,
        xaxis: { range: [-1.5, 106.5], visible: false, fixedrange: true, constrain: "domain" },
        yaxis: { range: [-1.5, 69.5], visible: false, fixedrange: true, scaleanchor: "x", scaleratio: 1, constrain: "domain" },
        shapes: horizontalPitchShapes(themeColors.muted, { zoneLines: true }),
        annotations: arrowAnnotations,
        hoverlabel: {
          bgcolor: themeColors.mode === "dark" ? "#0f2236" : "#ffffff",
          bordercolor: themeColors.mode === "dark" ? "rgba(255,255,255,0.18)" : "rgba(15,23,42,0.16)",
          font: { color: themeColors.text, family: CHART_FONT_FAMILY, size: 12 },
        },
      }}
      config={{ responsive: true, displayModeBar: false }}
      className="plotly-chart entries-pitch-chart"
      aria-label={`${team} ${label} entries map`}
    />
  );
}

export function EntriesPenetrationPanel({ matchId, source, league, season, jobId, team, teams, teamColor }: Props) {
  const [payload, setPayload] = useState<EntriesPayload | null>(null);
  const [opponentPayload, setOpponentPayload] = useState<EntriesPayload | null>(null);
  const [scope, setScope] = useState<Scope>("final_third");
  const [methodFilter, setMethodFilter] = useState("all");
  const [timeRange, setTimeRange] = useState("all");
  const [isLoading, setIsLoading] = useState(true);

  const opponent = teams.find((candidate) => candidate && candidate !== team) ?? "";

  const buildBody = (target: string, range: string) => {
    const filters: Record<string, string | undefined> = { team: target, timeRange: range };
    if (source !== "r2") filters.job_id = jobId;
    return source !== "r2"
      ? { match_id: matchId, source, filters }
      : { match_id: matchId, source: "r2", league, season, filters };
  };

  const loadView = (range: string) => {
    let cancelled = false;
    setIsLoading(true);
    setTimeRange(range);
    Promise.all([
      getAnalysisView("territory-entries", buildBody(team, range)),
      opponent ? getAnalysisView("territory-entries", buildBody(opponent, range)).catch(() => null) : Promise.resolve(null),
    ])
      .then(([own, other]) => {
        if (cancelled) return;
        setPayload((own.payload ?? null) as EntriesPayload | null);
        setOpponentPayload(((other?.payload ?? null) as EntriesPayload | null));
      })
      .catch(() => {
        if (!cancelled) setPayload(null);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => { cancelled = true; };
  };

  useEffect(() => {
    const cancel = loadView("all");
    return cancel;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [matchId, source, league, season, jobId, team, opponent]);

  const scopeRows = useMemo(() => payload?.[scope] ?? [], [payload, scope]);
  const filteredRows = useMemo(
    () => (methodFilter === "all" ? scopeRows : scopeRows.filter((row) => row.method === methodFilter)),
    [scopeRows, methodFilter],
  );
  const shares = useMemo(() => methodShares(scopeRows), [scopeRows]);
  const opponentShares = useMemo(() => methodShares(opponentPayload?.[scope] ?? []), [opponentPayload, scope]);
  const channelCounts = useMemo(() => {
    const total = Math.max(1, scopeRows.length);
    return CHANNEL_ORDER.filter((channel) => scope !== "exits" || ["left", "center", "right"].includes(channel)).map((channel) => {
      const count = scopeRows.filter((row) => row.channel === channel).length;
      return { channel, count, share: Math.round((count / total) * 100) };
    });
  }, [scopeRows, scope]);
  const players = useMemo(() => {
    const byPlayer = new Map<string, { entries: number; shots: number; methods: Map<string, number> }>();
    scopeRows.forEach((row) => {
      if (!row.player) return;
      const current = byPlayer.get(row.player) ?? { entries: 0, shots: 0, methods: new Map<string, number>() };
      current.entries += 1;
      if (row.led_to_shot) current.shots += 1;
      current.methods.set(row.method, (current.methods.get(row.method) ?? 0) + 1);
      byPlayer.set(row.player, current);
    });
    return [...byPlayer.entries()]
      .map(([player, stats]) => ({
        player,
        entries: stats.entries,
        shots: stats.shots,
        topMethod: [...stats.methods.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? "",
      }))
      .sort((a, b) => b.entries - a.entries);
  }, [scopeRows]);
  const sequence = payload?.sequence ?? {};
  const opponentSequence = opponentPayload?.sequence ?? {};
  const styleTag = (stats: SequenceStats) =>
    (stats.direct_share ?? 0) >= 50 || (stats.avg_passes_to_shot ?? 99) <= 4.5 ? "Direct" : "Patient";

  if (!isLoading && !payload) return null;

  const toShotShare = scopeRows.length ? Math.round((scopeRows.filter((row) => row.led_to_shot).length / scopeRows.length) * 100) : 0;

  const buildSideTable = (): SideTable | null => {
    if (!payload) return null;
    const rows: SideTableRow[] = [{ header: "Penetration methods" }];
    shares.forEach((share) => {
      const opponentShare = opponentShares.find((row) => row.method === share.method);
      rows.push({
        label: METHOD_LABELS[share.method],
        value: `${share.count} · ${share.share}%${opponentShare ? ` (opp ${opponentShare.share}%)` : ""}`,
      });
    });
    rows.push({ header: "Entry channels" });
    channelCounts.filter((row) => row.count > 0).forEach((row) => {
      rows.push({ label: CHANNEL_LABELS[row.channel] ?? row.channel, value: `${row.count} · ${row.share}%` });
    });
    if (players.length) {
      rows.push({ header: "Top entry players" });
      players.slice(0, 4).forEach((row) => {
        rows.push({
          image: getCachedPlayerImage(row.player, team),
          label: row.player,
          value: `${row.entries}×`,
          sub: `${row.shots} led to shots · mostly ${METHOD_LABELS[row.topMethod] ?? row.topMethod}`,
        });
      });
    }
    rows.push({ header: "Sequence style" });
    rows.push({ label: "Passes per shot-ending move", value: `${sequence.avg_passes_to_shot ?? 0}${opponentSequence.avg_passes_to_shot !== undefined ? ` (opp ${opponentSequence.avg_passes_to_shot})` : ""}` });
    rows.push({ label: "Direct attacks (≤4 passes)", value: `${sequence.direct_share ?? 0}%` });
    return { title: `${team} · ${SCOPE_LABELS[scope]} entries`, rows };
  };

  // Mirror the HTML method legend into the export (canvas can't see the DOM legend).
  const buildChartPanels = (): ChartPanel[] => [{
    legend: [
      ...shares.filter((share) => share.count > 0).map((share) => ({
        label: METHOD_LABELS[share.method],
        color: methodColor(share.method, teamColor),
        shape: "line" as const,
      })),
      { label: "Led to a shot (thick)", color: "rgba(148,163,184,0.9)", shape: "line" as const },
      { label: "Goal", color: "#22c55e", shape: "circle" as const },
    ],
  }];

  return (
    <section className={`card stack${isLoading ? " is-loading-soft" : ""}`}>
      <div className="chart-card-head">
        <div>
          <span className="eyebrow">Entries &amp; Penetration</span>
          <h2 style={{ margin: "6px 0 0" }}>How {team} breaks through</h2>
        </div>
        <div className="channel-mode-controls">
          <div className="channel-mode-toggle" role="group" aria-label="Entry scope">
            {(Object.keys(SCOPE_LABELS) as Scope[]).map((value) => (
              <button
                key={value}
                type="button"
                className={scope === value ? "button" : "ghost-button"}
                onClick={() => {
                  setScope(value);
                  setMethodFilter("all");
                }}
              >
                {SCOPE_LABELS[value]} ({(payload?.[value] ?? []).length})
              </button>
            ))}
          </div>
          <div className="time-range-presets" role="group" aria-label="Time period">
            <button type="button" className={timeRange === "all" ? "button" : "ghost-button"} onClick={() => loadView("all")} disabled={isLoading}>Full</button>
            <button type="button" className={timeRange === "0-45" ? "button" : "ghost-button"} onClick={() => loadView("0-45")} disabled={isLoading}>1st H</button>
            <button type="button" className={timeRange === "45-90" ? "button" : "ghost-button"} onClick={() => loadView("45-90")} disabled={isLoading}>2nd H</button>
          </div>
          <DownloadPngButton
            filename={`${team}-entries`}
            title={() => `Entries & Penetration — ${SCOPE_LABELS[scope]}`}
            filters={[team]}
            sideTable={buildSideTable}
            chartPanels={buildChartPanels}
            captureAspect={71 / 108}
          />
        </div>
      </div>
      <p className="muted-copy" style={{ margin: 0 }}>
        Successful open-play passes and carries that {scope === "exits" ? "leave the own third" : scope === "box" ? "end inside the penalty box" : "enter the final third"} (attacking left → right), colored by method. Thicker arrows led to a shot in the same possession; {toShotShare}% of these entries did.
      </p>
      <div className="entries-grid">
        <div className="plotly-chart-shell">
          <div className="channel-mode-toggle setpiece-corner-toggle" role="group" aria-label="Method filter">
            <button type="button" className={methodFilter === "all" ? "button" : "ghost-button"} onClick={() => setMethodFilter("all")}>
              All ({scopeRows.length})
            </button>
            {shares.filter((share) => share.count > 0).map((share) => (
              <button
                key={share.method}
                type="button"
                className={methodFilter === share.method ? "button" : "ghost-button"}
                onClick={() => setMethodFilter(share.method)}
              >
                {METHOD_LABELS[share.method]} ({share.count})
              </button>
            ))}
          </div>
          <EntriesPitch entries={filteredRows} team={team} teamColor={teamColor} label={SCOPE_LABELS[scope]} />
          <div className="entries-method-legend">
            {shares.filter((share) => share.count > 0).map((share) => (
              <span key={share.method}>
                <i style={{ background: methodColor(share.method, teamColor) }} /> {METHOD_LABELS[share.method]}
              </span>
            ))}
            <span><i style={{ background: "#22c55e" }} /> goal marker</span>
          </div>
        </div>
        <div className="entries-side">
          <div className="entries-panel-card">
            <span className="eyebrow">Penetration profile{opponent ? ` · vs ${opponent}` : ""}</span>
            {shares.map((share) => {
              const opponentShare = opponentShares.find((row) => row.method === share.method);
              return (
                <div key={share.method} className="entries-method-row">
                  <span>{METHOD_LABELS[share.method]}</span>
                  <div className="entries-method-bars">
                    <div className="entries-bar entries-bar-team">
                      <i style={{ width: `${share.share}%`, background: methodColor(share.method, teamColor) }} />
                      <b>{share.share}%</b>
                    </div>
                    <div className="entries-bar entries-bar-opp">
                      <i style={{ width: `${opponentShare?.share ?? 0}%` }} />
                      <b>{opponentShare?.share ?? 0}%</b>
                    </div>
                  </div>
                </div>
              );
            })}
            <small className="muted">Top bar {team}, bottom bar {opponent || "opponent"} — share of their own entries.</small>
          </div>
          <div className="entries-panel-card">
            <span className="eyebrow">Entry channels</span>
            {channelCounts.map((row) => (
              <div key={row.channel} className="entries-channel-row">
                <span>{CHANNEL_LABELS[row.channel] ?? row.channel}</span>
                <div className="entries-bar entries-bar-team">
                  <i style={{ width: `${row.share}%`, background: colorWithAlpha(teamColor, 0.8) }} />
                  <b>{row.count}</b>
                </div>
              </div>
            ))}
          </div>
          <div className="entries-panel-card">
            <span className="eyebrow">Sequence style</span>
            <div className="entries-seq-row"><span>Passes per shot-ending move</span><b>{sequence.avg_passes_to_shot ?? 0}{opponentSequence.avg_passes_to_shot !== undefined ? ` · opp ${opponentSequence.avg_passes_to_shot}` : ""}</b></div>
            <div className="entries-seq-row"><span>Passes per possession</span><b>{sequence.avg_passes_all ?? 0}</b></div>
            <div className="entries-seq-row"><span>Direct attacks (≤4 passes)</span><b>{sequence.direct_share ?? 0}%</b></div>
            <div className="entries-seq-row"><span>Style</span><b className="entries-style-tag">{styleTag(sequence)}{opponentSequence.avg_passes_to_shot !== undefined ? ` · opp ${styleTag(opponentSequence)}` : ""}</b></div>
          </div>
        </div>
      </div>
      {players.length > 0 && (
        <div className="setpiece-tables">
          <div className="setpiece-table-card">
            <span className="eyebrow">Top entry players — {SCOPE_LABELS[scope]}</span>
            <table className="table setpiece-table">
              <thead>
                <tr><th>Player</th><th>Entries</th><th>Led to shot</th><th>Main method</th></tr>
              </thead>
              <tbody>
                {players.slice(0, 8).map((row) => (
                  <tr key={row.player}>
                    <td>
                      <span className="player-cell">
                        <PlayerAvatar name={row.player} team={team} size={24} />
                        <span>{row.player}</span>
                      </span>
                    </td>
                    <td>{row.entries}</td>
                    <td>{row.shots}</td>
                    <td>{METHOD_LABELS[row.topMethod] ?? row.topMethod}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}
