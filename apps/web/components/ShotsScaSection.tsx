"use client";

import { DownloadPngButton, type SideTable, type SideTableRow } from "./DownloadPngButton";

import { useSyncFiltersToUrl } from "../lib/analysisUrl";

import { useMemo, useState } from "react";

import { fallbackTeamColor, num } from "../lib/theme";
import { PlayerAvatar, getCachedPlayerImage } from "./PlayerAvatar";
import { ShotsPlotly } from "./ShotsPlotly";

type ShotRow = Record<string, string | number | boolean | null | undefined | Array<Record<string, unknown>>>;
type PlayerRow = Record<string, string | number | boolean | null | undefined>;

type TeamTotal = {
  team?: string;
  shots?: number;
  goals?: number;
  shots_on_target?: number;
  xg?: number;
  xgot?: number;
  sca?: number;
  sca_xt?: number;
  assists?: number;
  xa?: number;
};

type Props = {
  teams: string[];
  initialTeam: string;
  initialPlayer?: string;
  shotRows: ShotRow[];
  playerRows: PlayerRow[];
  teamTotals: TeamTotal[];
  teamColors: Record<string, string>;
  gameStateOptions: Array<{ value?: string; label?: string }>;
  timeRangeOptions: Array<{ value?: string; label?: string; minute_start?: number; minute_end?: number }>;
  teamStateControls?: Record<string, unknown>;
  initialGameState?: string;
  initialTimeRange?: string;
};

const sortOptions = [
  ["Total xG", "xG"],
  ["Total xGOT", "xGOT"],
  ["SCA Count", "SCA"],
  ["Total Shots", "Shots"],
  ["Shots On Target", "SOT"],
  ["Avg Shot Distance", "Avg Dist"],
  ["SCA xT", "SCA xT"],
] as const;

function format(value: unknown, digits = 0) {
  return num(value).toFixed(digits);
}

function selectedShotPanel() {
  const panel = document.querySelector<HTMLElement>(".shot-detail-panel");
  return panel?.dataset.player ? panel : null;
}

function readSelectedShotTable(): SideTable | null {
  const panel = selectedShotPanel();
  const title = panel?.querySelector(".shot-detail-panel-title");
  if (!panel || !title) return null;
  const shotNo = title.querySelector("strong")?.textContent?.trim() ?? "";
  const player = title.querySelector("h3")?.textContent?.trim() ?? "";
  const rows: SideTableRow[] = [{ header: `${shotNo} · ${player}` }];
  const grid = panel.querySelector(".shot-detail-grid");
  if (grid) {
    const cells = [...grid.children].map((cell) => cell.textContent?.trim() ?? "");
    for (let i = 0; i + 1 < cells.length; i += 2) rows.push({ label: cells[i], value: cells[i + 1] });
  }
  const events = [...panel.querySelectorAll(".shot-sca-event")].filter(
    (eventEl) => !eventEl.classList.contains("is-shot-end"),
  );
  if (events.length) rows.push({ header: "Shot-creating actions" });
  events.forEach((eventEl) => {
    const tag = eventEl.querySelector("span")?.textContent?.trim() ?? "SCA";
    const body = eventEl.querySelector("p")?.textContent?.trim() ?? "";
    const metric = eventEl.querySelector("small")?.textContent?.trim() ?? "";
    // body reads "9:42 · Lesley Ugochukwu · Pass (Successful)"
    const parts = body.split(" · ");
    const time = parts[0] ?? "";
    const scaPlayer = parts[1] ?? "";
    const action = parts.slice(2).join(" · ");
    const image = eventEl.querySelector("img.player-avatar")?.getAttribute("src") ?? null;
    rows.push({
      image,
      label: scaPlayer || body,
      value: tag,
      sub: [time, action, metric].filter(Boolean).join(" · "),
    });
  });
  return { title: "Selected shot", rows, large: true };
}

export function ShotsScaSection({
  teams,
  initialTeam,
  initialPlayer,
  shotRows,
  playerRows,
  teamTotals,
  teamColors,
  gameStateOptions,
  timeRangeOptions,
  teamStateControls = {},
  initialGameState = "all",
  initialTimeRange = "all",
}: Props) {
  const [selectedTeam, setSelectedTeam] = useState(initialTeam || teams[0] || "");
  const [selectedPlayer, setSelectedPlayer] = useState(initialPlayer ?? "");
  const [tableFilter, setTableFilter] = useState<"all" | "shots" | "sca">("all");
  const [sortKey, setSortKey] = useState<(typeof sortOptions)[number][0]>("Total xG");
  const [selectedGameState, setSelectedGameState] = useState(initialGameState);
  const [selectedTimeRange, setSelectedTimeRange] = useState(initialTimeRange);
  const [mapOrientation, setMapOrientation] = useState<"stacked" | "side-by-side">("stacked");

  useSyncFiltersToUrl({
    team: selectedTeam,
    player: selectedPlayer,
    gameState: selectedGameState,
    timeRange: selectedTimeRange,
  });

  const selectedTeamColor = teamColors[selectedTeam] ?? fallbackTeamColor(selectedTeam);
  const teamControls = (teamStateControls[selectedTeam] ?? {}) as {
    game_state_options?: Array<{ value?: string; label?: string }>;
    state_time_ranges?: Record<string, { value?: string; label?: string; minute_start?: number; minute_end?: number }>;
  };
  const availableGameStates = teamControls.game_state_options?.length
    ? teamControls.game_state_options
    : gameStateOptions.length
      ? gameStateOptions
      : [{ value: "all", label: "All states" }];
  const stateRange = teamControls.state_time_ranges?.[selectedGameState];
  const availableTimeRanges = stateRange
    ? [{ ...stateRange, value: selectedGameState === "all" ? "all" : stateRange.value, label: selectedGameState === "all" ? "Full match" : stateRange.label ?? "State span" }]
    : timeRangeOptions.length
      ? timeRangeOptions
      : [{ value: "all", label: "Full match" }];
  const filteredShots = useMemo(() => shotRows.filter((row) => {
    const state = String(row.game_state ?? "level");
    const diff = num(row.goal_diff_before);
    const minute = num(row.minute, -1);
    const timeOption = availableTimeRanges.find((option) => String(option.value ?? "all") === selectedTimeRange);
    const inState = selectedGameState === "all"
      ? true
      : selectedGameState === "leading"
        ? diff > 0
        : selectedGameState === "trailing"
          ? diff < 0
          : state === selectedGameState;
    const inTime = selectedTimeRange === "all"
      ? true
      : minute >= num(timeOption?.minute_start, 0) && minute < num(timeOption?.minute_end, 90);
    return inState && inTime;
  }), [availableTimeRanges, selectedGameState, selectedTimeRange, shotRows]);
  const teamShots = useMemo(
    () => filteredShots.filter((row) => String(row.team ?? "") === selectedTeam && (!selectedPlayer || String(row.player ?? "") === selectedPlayer)),
    [filteredShots, selectedTeam, selectedPlayer],
  );
  const teamPlayers = useMemo(() => {
    const filtered = playerRows.filter((row) => {
      if (String(row.Team ?? "") !== selectedTeam) return false;
      if (tableFilter === "shots" && num(row["Total Shots"]) <= 0) return false;
      if (tableFilter === "sca" && num(row["SCA Count"]) <= 0) return false;
      return true;
    });
    return [...filtered].sort((a, b) => num(b[sortKey]) - num(a[sortKey]));
  }, [playerRows, selectedTeam, tableFilter, sortKey]);
  const selectedTotal = useMemo(() => {
    const rows = filteredShots.filter((row) => String(row.team ?? "") === selectedTeam);
    if (selectedGameState === "all" && selectedTimeRange === "all") return teamTotals.find((row) => row.team === selectedTeam);
    return {
      team: selectedTeam,
      shots: rows.filter((row) => !Boolean(row.own_goal)).length,
      goals: rows.filter((row) => String(row.type ?? "") === "Goal").length,
      shots_on_target: rows.filter((row) => Boolean(row.on_target) && !Boolean(row.own_goal)).length,
      xg: rows.reduce((sum, row) => sum + (Boolean(row.own_goal) ? 0 : num(row.xg)), 0),
      xgot: rows.reduce((sum, row) => sum + (Boolean(row.own_goal) ? 0 : num(row.xgot ?? row.xGOT)), 0),
      sca: rows.reduce((sum, row) => sum + ((row.leadup_events as Array<Record<string, unknown>> | undefined)?.length ?? 0), 0),
      sca_xt: rows.reduce((sum, row) => sum + ((row.leadup_events as Array<{ xT?: number }> | undefined) ?? []).reduce((total, event) => total + num(event.xT), 0), 0),
      assists: rows.reduce((sum, row) => sum + ((row.leadup_events as Array<{ is_assist?: boolean }> | undefined) ?? []).filter((event) => event.is_assist).length, 0),
      xa: rows.reduce((sum, row) => sum + ((row.leadup_events as Array<{ xA?: number }> | undefined) ?? []).reduce((total, event) => total + num(event.xA), 0), 0),
    };
  }, [filteredShots, selectedGameState, selectedTeam, selectedTimeRange, teamTotals]);

  return (
    <>
      <section className="card stack">
        <div className="row shots-section-heading" style={{ justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <span className="eyebrow">Shots and SCA</span>
            <div className="chart-card-head">
              <h2 style={{ margin: "6px 0 0" }}>Shots and SCA - {selectedTeam}</h2>
              <DownloadPngButton
                filename={`${selectedTeam}-shots-sca`}
                title={() => {
                  const player = selectedShotPanel()?.dataset.player;
                  return player ? `Shots & SCA — ${player}` : "Shots & SCA";
                }}
                filters={[selectedTeam]}
                titleImages={() => {
                  const panel = selectedShotPanel();
                  const src = panel?.dataset.player
                    ? getCachedPlayerImage(panel.dataset.player, panel.dataset.team || undefined)
                    : null;
                  return src ? [src] : [];
                }}
                scopeSelector="section.card"
                maxCharts={2}
                chartGroupSelector=".shots-plotly-shell"
                sideTable={() => {
                  const selectedShotTable = readSelectedShotTable();
                  if (selectedShotTable) return selectedShotTable;
                  const topShooters = playerRows
                    .filter((row) => String(row.Team ?? "") === selectedTeam && num(row["Total Shots"]) > 0)
                    .sort((a, b) => num(b["Total Shots"]) - num(a["Total Shots"]) || num(b["Total xG"]) - num(a["Total xG"]))
                    .slice(0, 3);
                  const rows: SideTableRow[] = [
                    { label: "Shots", value: String(selectedTotal?.shots ?? 0) },
                    { label: "Goals", value: String(selectedTotal?.goals ?? 0) },
                    { label: "Shots on target", value: String(selectedTotal?.shots_on_target ?? 0) },
                    { label: "xG", value: format(selectedTotal?.xg, 2) },
                    { label: "xGOT", value: format(selectedTotal?.xgot, 2) },
                    { label: "SCA", value: String(selectedTotal?.sca ?? 0) },
                    { label: "SCA xT", value: format(selectedTotal?.sca_xt, 2) },
                    { label: "Assists", value: String(selectedTotal?.assists ?? 0) },
                    { label: "xA", value: format(selectedTotal?.xa, 2) },
                  ];
                  if (topShooters.length) {
                    rows.push({ header: "Top shot takers" });
                    topShooters.forEach((row) => {
                      const name = String(row.playerName ?? "").replace(/\s*\(OG\)$/, "");
                      rows.push({
                        image: getCachedPlayerImage(name, selectedTeam),
                        label: name,
                        value: `${num(row["Total Shots"])} shots`,
                        sub: `xG ${format(row["Total xG"], 2)} · xGOT ${format(row["Total xGOT"], 2)} · ${num(row.Goals)} goals · ${num(row["Shots On Target"])} on target`,
                      });
                    });
                  }
                  return { title: `${selectedTeam} · Match totals`, rows, large: true };
                }}
              />
            </div>
          </div>
          <div className="row shots-top-controls">
            {teams.filter(Boolean).map((team) => (
              <button
                key={team}
                type="button"
                className={team === selectedTeam ? "button" : "ghost-button"}
                onClick={() => {
                  setSelectedTeam(team);
                  setSelectedPlayer("");
                  setSelectedGameState("all");
                  setSelectedTimeRange("all");
                }}
              >
                {team}
              </button>
            ))}
            <select
              className="select"
              value={selectedGameState}
              onChange={(event) => {
                setSelectedGameState(event.target.value);
                const nextRange = ((teamStateControls[selectedTeam] ?? {}) as {
                  state_time_ranges?: Record<string, { value?: string }>;
                }).state_time_ranges?.[event.target.value]?.value;
                setSelectedTimeRange(event.target.value === "all" ? "all" : String(nextRange ?? "all"));
                setSelectedPlayer("");
              }}
              aria-label="Shot map game state"
            >
              {availableGameStates.map((row) => (
                <option key={row.value} value={row.value}>
                  {row.label}
                </option>
              ))}
            </select>
            <select
              className="select"
              value={selectedTimeRange}
              onChange={(event) => {
                setSelectedTimeRange(event.target.value);
                setSelectedPlayer("");
              }}
              aria-label="Shot map time range"
            >
              {availableTimeRanges.map((row) => (
                <option key={row.value} value={row.value}>
                  {row.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="shot-team-total-strip">
          {[
            ["Shots", selectedTotal?.shots],
            ["Goals", selectedTotal?.goals],
            ["SOT", selectedTotal?.shots_on_target],
            ["xG", format(selectedTotal?.xg, 2)],
            ["xGOT", format(selectedTotal?.xgot, 2)],
            ["SCA", selectedTotal?.sca],
            ["SCA xT", format(selectedTotal?.sca_xt, 2)],
            ["Assists", selectedTotal?.assists],
            ["xA", format(selectedTotal?.xa, 2)],
          ].map(([label, value]) => (
            <div key={label} className="shot-team-total">
              <span>{label}</span>
              <strong>{value ?? 0}</strong>
            </div>
          ))}
        </div>

        <div className="shot-hero shot-hero-single">
          <article className="card shot-panel">
            <div className="shot-map-toolbar">
              <strong>Shots and SCA map</strong>
              <div className="shot-map-toolbar-actions">
                {selectedPlayer && <button type="button" className="pill" onClick={() => setSelectedPlayer("")}>{selectedPlayer} x</button>}
                <div className="segmented-control shot-map-orientation" aria-label="Shot map orientation">
                  <button
                    type="button"
                    className={mapOrientation === "stacked" ? "is-active" : ""}
                    aria-pressed={mapOrientation === "stacked"}
                    onClick={() => setMapOrientation("stacked")}
                  >
                    Stacked
                  </button>
                  <button
                    type="button"
                    className={mapOrientation === "side-by-side" ? "is-active" : ""}
                    aria-pressed={mapOrientation === "side-by-side"}
                    onClick={() => setMapOrientation("side-by-side")}
                  >
                    Side by side
                  </button>
                </div>
              </div>
            </div>
            <ShotsPlotly
              shots={teamShots}
              team={selectedTeam}
              teamColor={selectedTeamColor}
              orientation={mapOrientation}
            />
          </article>
        </div>
      </section>

      <section className="card stack">
        <div className="shot-table-toolbar">
          <div>
            <h2 style={{ margin: 0 }}>Shot and SCA Player Summary</h2>
            <p className="muted" style={{ margin: "6px 0 0" }}>Players with shots or shot-creating actions are included.</p>
          </div>
          <div className="shot-table-controls">
            {(["all", "shots", "sca"] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                className={tableFilter === mode ? "button" : "ghost-button"}
                onClick={() => setTableFilter(mode)}
              >
                {mode === "all" ? "All" : mode === "shots" ? "Shot takers" : "SCA players"}
              </button>
            ))}
            <select className="select" value={sortKey} onChange={(event) => setSortKey(event.target.value as typeof sortKey)}>
              {sortOptions.map(([key, label]) => <option key={key} value={key}>Sort: {label}</option>)}
            </select>
          </div>
        </div>

        <div className="shot-summary-table-wrap">
          <table className="table shot-summary-table">
            <thead>
              <tr>
                <th>Player</th>
                <th>Shots</th>
                <th>Goals</th>
                <th>On Target</th>
                <th>Off Target</th>
                <th>Blocked</th>
                <th>Avg Dist</th>
                <th>xG</th>
                <th>xGOT</th>
                <th>xG/Shot</th>
                <th>xGOT/Shot</th>
                <th>SCA</th>
                <th>SCA xT</th>
                <th>Ast</th>
                <th>xA</th>
              </tr>
            </thead>
            <tbody>
              {teamPlayers.map((row) => {
                const isCreatorOnly = num(row["Total Shots"]) === 0 && num(row["SCA Count"]) > 0;
                return (
                  <tr key={`${row.playerName}-${row.Team}`} className={isCreatorOnly ? "is-creator-only" : ""}>
                    <td>
                      <span className="shot-player-cell">
                        <PlayerAvatar
                          name={String(row.playerName ?? "").replace(/\s*\(OG\)$/, "")}
                          team={String(row.Team ?? "")}
                          size={26}
                        />
                        <button
                          type="button"
                          className="shot-player-link"
                          onClick={() => setSelectedPlayer(String(row.playerName ?? ""))}
                        >
                          {row.playerName}
                        </button>
                        {isCreatorOnly && <span className="shot-player-badge">SCA only</span>}
                      </span>
                    </td>
                    <td>{row["Total Shots"]}</td>
                    <td>{row.Goals}</td>
                    <td>{row["Shots On Target"]}</td>
                    <td>{row["Off Target"]}</td>
                    <td>{row.BlockedShots}</td>
                    <td>{num(row["Total Shots"]) > 0 ? `${format(row["Avg Shot Distance"], 1)}m` : "-"}</td>
                    <td>{format(row["Total xG"], 2)}</td>
                    <td>{format(row["Total xGOT"], 2)}</td>
                    <td>{format(row["xG/Shot"], 3)}</td>
                    <td>{format(row["xGOT/Shot"], 3)}</td>
                    <td>
                      <details>
                        <summary>{row["SCA Count"] ?? 0}</summary>
                        <div className="shot-sca-breakdown">
                          <span>Passes: {row["SCA Passes"] ?? 0}</span>
                          <span>Carries: {row["SCA Carries"] ?? 0}</span>
                          <span>TakeOns: {row["SCA TakeOns"] ?? 0}</span>
                          <span>Shots: {row["SCA Shots"] ?? 0}</span>
                          <span>Def Actions: {row["SCA Def Actions"] ?? 0}</span>
                        </div>
                      </details>
                    </td>
                    <td>{format(row["SCA xT"], 3)}</td>
                    <td>{row.Assists ?? 0}</td>
                    <td>{format(row.xA, 3)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
