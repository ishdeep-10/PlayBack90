"use client";

import { DownloadPngButton, type ProfileCard, type SideTable } from "./DownloadPngButton";
import { PlayerAvatar, getCachedPlayerImage } from "./PlayerAvatar";

import { useSyncFiltersToUrl } from "../lib/analysisUrl";
import { ChannelAnalysisPanel } from "./ChannelAnalysisPanel";
import { EntriesPenetrationPanel } from "./EntriesPenetrationPanel";
import { SetPiecesPanel } from "./SetPiecesPanel";

import { useEffect, useMemo, useRef, useState } from "react";

import { getAnalysisView } from "../lib/api";
import { num, parseRange } from "../lib/theme";
import { AttackDirectionCue } from "./AttackDirectionCue";
import { InPossessionMetricsTable } from "./InPossessionMetricsTable";
import type { PlayerBaseline } from "./season/baselineTypes";
import { PassNetworkPlotly } from "./PassNetworkPlotly";

type WindowRow = {
  value?: string;
  label?: string;
  minute_start?: number;
  minute_end?: number;
};

type OptionRow = {
  value?: string;
  label?: string;
  minute_start?: number;
  minute_end?: number;
};

type NetworkNodeRow = Record<string, string | number | boolean | undefined>;
type NetworkEdgeRow = Record<string, string | number | boolean | undefined>;
type ActionRow = Record<string, string | number | boolean | null | undefined>;
type ActionScope = "filtered" | "all";

type Props = {
  matchId: string;
  source: string;
  league?: string;
  season?: string;
  jobId?: string;
  situation: string;
  player?: string;
  teams: string[];
  selectedTeam: string;
  selectedWindow: string;
  selectedGameState: string;
  selectedTimeRange: string;
  gameStateOptions: OptionRow[];
  timeRangeOptions: OptionRow[];
  windows: WindowRow[];
  payload: Record<string, unknown>;
  metricRows: Array<Record<string, string | number | boolean | undefined>>;
  teamColor: string;
  teamColors: Record<string, string>;
  playerBaselines?: Record<string, PlayerBaseline>;
};

function windowLabel(row: WindowRow) {
  const start = Number(row.minute_start ?? 0);
  const end = Number(row.minute_end ?? 90);
  return `${row.label ?? "Window"} (${start}'-${end}')`;
}

function fallbackTeamColor(team: string) {
  const palette = ["#22c55e", "#60a5fa", "#f59e0b", "#ef4444", "#a78bfa", "#14b8a6", "#f97316", "#ec4899"];
  let hash = 0;
  for (let index = 0; index < team.length; index += 1) {
    hash = (hash * 31 + team.charCodeAt(index)) % palette.length;
  }
  return palette[hash];
}

export function InPossessionNetworkSection({
  matchId,
  source,
  league,
  season,
  jobId,
  situation,
  player,
  teams,
  selectedTeam,
  selectedWindow,
  selectedGameState,
  selectedTimeRange,
  gameStateOptions,
  timeRangeOptions,
  windows,
  payload,
  metricRows,
  teamColors,
  playerBaselines,
}: Props) {
  const [currentTeam, setCurrentTeam] = useState(selectedTeam);
  const [currentWindow, setCurrentWindow] = useState(selectedWindow);
  const [currentGameState, setCurrentGameState] = useState(selectedGameState);
  const [currentThird, setCurrentThird] = useState(String(payload.third ?? "all"));
  const [currentPayload, setCurrentPayload] = useState(payload);
  const [currentOpponentPayload, setCurrentOpponentPayload] = useState<Record<string, unknown>>({});
  const [currentActionsPayload, setCurrentActionsPayload] = useState<Record<string, unknown>>({ actions: [] });
  const [currentRows, setCurrentRows] = useState(metricRows);
  const [currentGameOptions, setCurrentGameOptions] = useState(gameStateOptions);
  const [currentTimeOptions, setCurrentTimeOptions] = useState(timeRangeOptions);
  const [currentWindows, setCurrentWindows] = useState(windows);
  const [isLoading, setIsLoading] = useState(false);

  useSyncFiltersToUrl({
    team: currentTeam,
    subWindow: currentWindow,
    gameState: currentGameState,
    timeRange: String(currentPayload.time_range ?? "all"),
    third: currentThird === "all" ? "" : currentThird,
  });

  const [startInput, setStartInput] = useState<string | null>(null);
  const [endInput, setEndInput] = useState<string | null>(null);
  const [selectedNetworkPlayerId, setSelectedNetworkPlayerId] = useState<string | null>(null);
  const [showNetworkPlayerActions, setShowNetworkPlayerActions] = useState(false);
  const [networkOverlayActionTypes, setNetworkOverlayActionTypes] = useState<string[]>([]);
  const [networkOverlayShowUnsuccessful, setNetworkOverlayShowUnsuccessful] = useState(false);
  const [networkActionScope, setNetworkActionScope] = useState<ActionScope>("filtered");
  const responseCache = useRef(new Map<string, Promise<{ payload: Record<string, unknown> }>>());
  const availableGameStates = currentGameOptions.length ? currentGameOptions : [{ value: "all", label: "All states" }];
  const availableTimeRanges = currentTimeOptions.length ? currentTimeOptions : [{ value: "all", label: "Full match", minute_start: 0, minute_end: 90 }];
  const windowRange = availableTimeRanges[0] ?? { minute_start: 0, minute_end: 90 };
  const minMinute = num(windowRange.minute_start, 0);
  const maxMinute = Math.max(minMinute + 1, num(windowRange.minute_end, 90));
  const initialPayloadRange = String(currentPayload.time_range ?? selectedTimeRange);
  const normalizedSelectedRange = initialPayloadRange === "all" ? `${minMinute}-${maxMinute}` : initialPayloadRange;
  const [selectedStart, selectedEnd] = parseRange(normalizedSelectedRange, minMinute, maxMinute);
  const [draftRange, setDraftRange] = useState<[number, number]>([selectedStart, selectedEnd]);
  const displayStart = startInput ?? String(Math.round(draftRange[0]));
  const displayEnd = endInput ?? String(Math.round(draftRange[1]));
  const activeTeamColor = teamColors[currentTeam] ?? fallbackTeamColor(currentTeam);
  const networkNodes = useMemo(() => (currentPayload.nodes as NetworkNodeRow[] | undefined) ?? [], [currentPayload.nodes]);
  const networkEdges = useMemo(() => (currentPayload.edges as NetworkEdgeRow[] | undefined) ?? [], [currentPayload.edges]);
  const selectedNetworkPlayer = useMemo(() => {
    if (!selectedNetworkPlayerId) return null;
    return networkNodes.find((node) => String(node.player_id ?? node.player ?? "") === selectedNetworkPlayerId) ?? null;
  }, [networkNodes, selectedNetworkPlayerId]);
  const networkTeamBaseline = useMemo(() => {
    if (!selectedNetworkPlayer) return null;
    const totalMade = Math.max(1, networkNodes.reduce((sum, node) => sum + num(node.passes_made), 0));
    const totalReceived = Math.max(1, networkNodes.reduce((sum, node) => sum + num(node.passes_received), 0));
    const totalProg = networkNodes.reduce((sum, node) => sum + num(node.progressive_passes_made), 0);
    const playerMade = Math.max(1, num(selectedNetworkPlayer.passes_made));
    return {
      progressivePct: Math.round((num(selectedNetworkPlayer.progressive_passes_made) / playerMade) * 100),
      teamProgressivePct: Math.round((totalProg / totalMade) * 100),
      receivedPct: Math.round((num(selectedNetworkPlayer.passes_received) / totalReceived) * 100),
    };
  }, [networkNodes, selectedNetworkPlayer]);
  const selectedNetwork = useMemo(() => {
    if (!selectedNetworkPlayerId) {
      return {
        outgoingXt: 0,
        incomingXt: 0,
        connections: [] as Array<{ id: string; player: string; passes: number; xt: number; direction: string }>,
      };
    }
    const playerLookup = new Map(networkNodes.map((node) => [String(node.player_id ?? node.player ?? ""), String(node.player ?? "Player")]));
    const selectedEdges = networkEdges.filter((edge) => {
      const sourceId = String(edge.source_id ?? "");
      const targetId = String(edge.target_id ?? "");
      return sourceId === selectedNetworkPlayerId || targetId === selectedNetworkPlayerId;
    });
    const outgoingXt = selectedEdges
      .filter((edge) => String(edge.source_id ?? "") === selectedNetworkPlayerId)
      .reduce((sum, edge) => sum + num(edge.total_xt), 0);
    const incomingXt = selectedEdges
      .filter((edge) => String(edge.target_id ?? "") === selectedNetworkPlayerId)
      .reduce((sum, edge) => sum + num(edge.total_xt), 0);
    const connectionMap = new Map<string, { id: string; player: string; passes: number; xt: number; made: number; received: number }>();
    selectedEdges.forEach((edge) => {
      const sourceId = String(edge.source_id ?? "");
      const targetId = String(edge.target_id ?? "");
      const otherId = sourceId === selectedNetworkPlayerId ? targetId : sourceId;
      const existing = connectionMap.get(otherId) ?? {
        id: otherId,
        player: playerLookup.get(otherId) ?? "Player",
        passes: 0,
        xt: 0,
        made: 0,
        received: 0,
      };
      const passCount = num(edge.pass_count);
      existing.passes += passCount;
      existing.xt += num(edge.total_xt);
      if (sourceId === selectedNetworkPlayerId) existing.made += passCount;
      if (targetId === selectedNetworkPlayerId) existing.received += passCount;
      connectionMap.set(otherId, existing);
    });
    const connections = Array.from(connectionMap.values())
      .sort((first, second) => second.passes - first.passes)
      .map((connection) => ({
        id: connection.id,
        player: connection.player,
        passes: connection.passes,
        xt: connection.xt,
        direction: connection.made && connection.received
          ? `${connection.made} made / ${connection.received} received`
          : connection.made
            ? `${connection.made} made`
            : `${connection.received} received`,
      }));
    return { outgoingXt, incomingXt, connections };
  }, [networkEdges, networkNodes, selectedNetworkPlayerId]);
  const selectedNetworkPlayerActionCount = useMemo(() => {
    if (!selectedNetworkPlayerId || !selectedNetworkPlayer) return 0;
    const rows = (currentActionsPayload.actions as ActionRow[] | undefined) ?? [];
    const playerName = String(selectedNetworkPlayer.player ?? "");
    return rows.filter((row) => {
      const samePlayer = String(row.player_id ?? "") === selectedNetworkPlayerId || String(row.player ?? "") === playerName;
      if (!samePlayer) return false;
      if (!networkOverlayShowUnsuccessful && row.is_successful === false) return false;
      if (networkOverlayActionTypes.length && !networkOverlayActionTypes.includes(String(row.type ?? ""))) return false;
      return true;
    }).length;
  }, [currentActionsPayload.actions, networkOverlayActionTypes, networkOverlayShowUnsuccessful, selectedNetworkPlayer, selectedNetworkPlayerId]);

  const clearNetworkPlayerSelection = () => {
    setSelectedNetworkPlayerId(null);
    setShowNetworkPlayerActions(false);
    setNetworkOverlayActionTypes([]);
    setNetworkOverlayShowUnsuccessful(false);
  };

  const handleNetworkPlayerSelection = (id: string | null) => {
    setSelectedNetworkPlayerId(id);
    if (!id) {
      setShowNetworkPlayerActions(false);
      setNetworkOverlayActionTypes([]);
      setNetworkOverlayShowUnsuccessful(false);
    }
  };

  const buildViewBody = (nextTeam: string, nextWindow: string, nextGameState: string, nextTimeRange: string, nextThird: string = currentThird) => {
    const filters: Record<string, string | undefined> = {
      team: nextTeam,
      situation,
      player,
      subWindow: nextWindow,
      gameState: nextGameState,
      timeRange: nextTimeRange,
      third: nextThird,
    };
    if (source !== "r2") filters.job_id = jobId;
    return source !== "r2"
      ? { match_id: matchId, source, filters }
      : { match_id: matchId, source: "r2", league, season, filters };
  };

  const buildActionsBody = (
    nextTeam: string,
    nextWindow: string,
    nextGameState: string,
    nextTimeRange: string,
    scope: ActionScope,
  ) => buildViewBody(
    nextTeam,
    scope === "all" ? "all" : nextWindow,
    scope === "all" ? "all" : nextGameState,
    scope === "all" ? "all" : nextTimeRange,
  );

  const getCachedView = (viewId: string, body: Record<string, unknown>) => {
    const key = `${viewId}:${JSON.stringify(body)}`;
    const cached = responseCache.current.get(key);
    if (cached) return cached;
    const request = getAnalysisView(viewId, body);
    responseCache.current.set(key, request);
    return request;
  };

  const buildMetricsBody = (nextTeam: string) => buildViewBody(nextTeam, "all", "all", "all");

  const getOpponentTeam = (team: string) => teams.find((candidate) => candidate !== team) ?? "";

  const fetchActionsPayload = async (
    nextTeam: string,
    nextWindow: string,
    nextGameState: string,
    nextTimeRange: string,
    scope: ActionScope,
    windowsForScope: WindowRow[] = currentWindows,
  ) => {
    if (scope !== "all") {
      const body = buildActionsBody(nextTeam, nextWindow, nextGameState, nextTimeRange, scope);
      const actionsView = await getCachedView("in-possession-actions", body);
      return actionsView.payload ?? { actions: [] };
    }
    const windowValues = (windowsForScope.length ? windowsForScope : [{ value: nextWindow }])
      .map((row) => String(row.value ?? "0"))
      .filter((value, index, values) => value !== "all" && values.indexOf(value) === index);
    const views = await Promise.all(windowValues.map((windowValue) => (
      getCachedView("in-possession-actions", buildViewBody(nextTeam, windowValue, "all", "all")).catch(() => ({ payload: { actions: [] } }))
    )));
    const seen = new Set<string>();
    const mergedActions: ActionRow[] = [];
    views.forEach((view) => {
      const actions = ((view.payload ?? {}).actions as ActionRow[] | undefined) ?? [];
      actions.forEach((action) => {
        const key = String(action.id ?? `${action.player_id ?? action.player}-${action.minute}-${action.second}-${action.type}-${action.x}-${action.y}`);
        if (seen.has(key)) return;
        seen.add(key);
        mergedActions.push(action);
      });
    });
    mergedActions.sort((first, second) => num(first.minute) - num(second.minute) || num(first.second) - num(second.second));
    return {
      team: nextTeam,
      actions: mergedActions,
      time_range: "all",
      window: { value: "all", label: "All minutes" },
    };
  };

  const loadCurrentActions = async (scope: ActionScope = networkActionScope) => {
    try {
      setCurrentActionsPayload(await fetchActionsPayload(currentTeam, currentWindow, currentGameState, String(currentPayload.time_range ?? selectedTimeRange), scope));
    } catch {
      setCurrentActionsPayload({ actions: [] });
    }
  };

  const loadCurrentOpponent = async () => {
    const opponentTeam = getOpponentTeam(currentTeam);
    if (!opponentTeam) {
      setCurrentOpponentPayload({});
      return;
    }
    const body = buildViewBody(opponentTeam, currentWindow, currentGameState, String(currentPayload.time_range ?? selectedTimeRange));
    try {
      const opponentView = await getCachedView("pass-network", body);
      setCurrentOpponentPayload(opponentView.payload ?? {});
    } catch {
      setCurrentOpponentPayload({});
    }
  };

  const loadInPossession = async (next: { team?: string; subWindow?: string; gameState?: string; timeRange?: string; third?: string }) => {
    const nextTeam = next.team ?? currentTeam;
    const nextWindow = next.subWindow ?? currentWindow;
    const nextGameState = next.gameState ?? currentGameState;
    const nextTimeRange = next.timeRange ?? `${Math.round(draftRange[0])}-${Math.round(draftRange[1])}`;
    const nextThird = next.third ?? currentThird;
    const body = buildViewBody(nextTeam, nextWindow, nextGameState, nextTimeRange, nextThird);
    const opponentTeam = getOpponentTeam(nextTeam);
    const opponentBody = opponentTeam ? buildViewBody(opponentTeam, nextWindow, nextGameState, nextTimeRange) : null;
    const shouldRefreshMetrics = nextTeam !== currentTeam;
    setIsLoading(true);
    try {
      const [network, metrics, actionsView, opponentView] = await Promise.all([
        getCachedView("pass-network", body),
        shouldRefreshMetrics ? getCachedView("in-possession-player-metrics", buildMetricsBody(nextTeam)) : Promise.resolve(null),
        fetchActionsPayload(nextTeam, nextWindow, nextGameState, nextTimeRange, networkActionScope),
        opponentBody ? getCachedView("pass-network", opponentBody) : Promise.resolve(null),
      ]);
      const nextPayload = network.payload ?? {};
      setCurrentTeam(String(nextPayload.team ?? nextTeam));
      setCurrentWindow(nextWindow);
      setCurrentGameState(String(nextPayload.score_state ?? nextGameState));
      setCurrentThird(String(nextPayload.third ?? nextThird));
      setCurrentPayload(nextPayload);
      setCurrentOpponentPayload(opponentView?.payload ?? {});
      setCurrentActionsPayload(actionsView ?? { actions: [] });
      if (metrics) {
        const nextRows = ((metrics.payload ?? {}).rows as Array<Record<string, string | number | boolean | undefined>> | undefined) ?? [];
        setCurrentRows(nextRows);
      }
      setCurrentGameOptions((nextPayload.game_state_options as OptionRow[] | undefined) ?? []);
      setCurrentTimeOptions((nextPayload.time_range_options as OptionRow[] | undefined) ?? []);
      setCurrentWindows((nextPayload.windows as WindowRow[] | undefined) ?? currentWindows);
      clearNetworkPlayerSelection();
      const nextTimeOptions = (nextPayload.time_range_options as OptionRow[] | undefined) ?? currentTimeOptions;
      const nextWindowRange = nextTimeOptions[0] ?? { minute_start: minMinute, minute_end: maxMinute };
      const nextMin = num(nextWindowRange.minute_start, minMinute);
      const nextMax = num(nextWindowRange.minute_end, maxMinute);
      const [start, end] = parseRange(String(nextPayload.time_range ?? nextTimeRange), nextMin, nextMax);
      setDraftRange([start, end]);
      setStartInput(null);
      setEndInput(null);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    const priorityStates = new Set(["all", "level", "leading", "trailing"]);
    const warmStates = availableGameStates
      .map((row) => String(row.value ?? "all"))
      .filter((value) => priorityStates.has(value) && value !== currentGameState)
      .slice(0, 4);
    if (!warmStates.length) return;
    const timeout = window.setTimeout(() => {
      warmStates.forEach((state) => {
        const body = buildViewBody(currentTeam, currentWindow, state, "all");
        void getCachedView("pass-network", body).catch(() => undefined);
      });
    }, 250);
    return () => window.clearTimeout(timeout);
  }, [availableGameStates, currentGameState, currentPayload.time_range, currentTeam, currentWindow]);

  useEffect(() => {
    void loadCurrentActions();
    void loadCurrentOpponent();
  }, []);

  const updateStart = (value: number) => {
    if (!Number.isFinite(value)) return;
    setDraftRange((current) => [Math.max(minMinute, Math.min(value, current[1] - 1)), current[1]]);
  };

  const updateEnd = (value: number) => {
    if (!Number.isFinite(value)) return;
    setDraftRange((current) => [current[0], Math.min(maxMinute, Math.max(value, current[0] + 1))]);
  };

  const commitStartInput = () => {
    if (startInput?.trim()) updateStart(Number(startInput));
    setStartInput(null);
  };

  const commitEndInput = () => {
    if (endInput?.trim()) updateEnd(Number(endInput));
    setEndInput(null);
  };

  const readProfileCards = (): ProfileCard[] =>
    [...document.querySelectorAll<HTMLElement>(".possession-profile-panel .defensive-profile-cards button")]
      .map((card) => {
        const smalls = card.querySelectorAll("small");
        return {
          name: card.querySelector("strong")?.textContent?.trim() ?? "",
          score: Number(card.querySelector("div > span")?.textContent ?? 0),
          description: smalls[0]?.textContent?.trim(),
          detail: smalls[1]?.textContent?.trim(),
        };
      })
      .filter((card) => card.name);

  const buildNetworkSideTable = (): SideTable | null => {
    if (!selectedNetworkPlayer) return null;
    const rows: SideTable["rows"] = [
      { label: "Passes made", value: String(num(selectedNetworkPlayer.passes_made)) },
      { label: "Passes received", value: String(num(selectedNetworkPlayer.passes_received)) },
      { label: "Avg pass distance", value: `${num(selectedNetworkPlayer.avg_pass_distance).toFixed(1)}m` },
      { label: "Progressive made", value: String(num(selectedNetworkPlayer.progressive_passes_made)) },
      { label: "Progressive received", value: String(num(selectedNetworkPlayer.progressive_passes_received)) },
      { label: "xT made", value: selectedNetwork.outgoingXt.toFixed(3) },
      { label: "xT received", value: selectedNetwork.incomingXt.toFixed(3) },
    ];
    if (networkTeamBaseline) {
      rows.push({ label: "Prog pass rate", value: `${networkTeamBaseline.progressivePct}% · team ${networkTeamBaseline.teamProgressivePct}%` });
    }
    const connections = selectedNetwork.connections.slice(0, 5);
    if (connections.length) {
      rows.push({ header: "Top connections" });
      connections.forEach((connection) => {
        rows.push({
          image: getCachedPlayerImage(connection.player, currentTeam),
          label: connection.player,
          value: `${connection.passes} passes`,
          sub: `${connection.direction} · xT ${connection.xt.toFixed(3)}`,
        });
      });
    }
    return { title: "Selected player", rows, large: true };
  };

  return (
    <>
    <section className={`card stack${isLoading ? " is-loading-soft" : ""}`}>
      {isLoading && <div className="analysis-loading-bar" aria-label="Loading in-possession view" />}
      <div className="analysis-section-heading">
        <div>
          <span className="eyebrow">In Possession</span>
          <div className="chart-card-head">
            <h2 style={{ margin: "6px 0 0" }}>Passing Network - {currentTeam}</h2>
            <DownloadPngButton
              filename={`${currentTeam}-passing-network`}
              title={() => selectedNetworkPlayer ? `Passing Network — ${String(selectedNetworkPlayer.player ?? "")}` : "Passing Network"}
              filters={[currentTeam]}
              titleImages={() => {
                if (!selectedNetworkPlayer) return [];
                const src = getCachedPlayerImage(String(selectedNetworkPlayer.player ?? ""), currentTeam);
                return src ? [src] : [];
              }}
              scopeSelector=".card"
              sideTable={buildNetworkSideTable}
              profileCards={readProfileCards}
            />
          </div>
        </div>
      </div>
      <div className="in-possession-top-controls">
        <div className="in-possession-team-strip">
          <span>Team</span>
          <div className="in-possession-team-buttons">
            {teams.map((team) => (
              <button
                key={team}
                type="button"
                className={team === currentTeam ? "button" : "ghost-button"}
                onClick={() => loadInPossession({ team, subWindow: "0", gameState: "all", timeRange: "all" })}
                disabled={isLoading}
              >
                {team}
              </button>
            ))}
          </div>
        </div>
        <div className="in-possession-filter-strip">
          <label>
            <span>Sub-window</span>
            <select
              className="select"
              value={currentWindow}
              onChange={(event) => loadInPossession({ subWindow: event.target.value, gameState: "all", timeRange: "all" })}
              aria-label="Passing network sub window"
              disabled={isLoading}
            >
              {currentWindows.map((row) => {
                const value = String(row.value ?? "0");
                return (
                  <option key={value} value={value}>
                    {windowLabel(row)}
                  </option>
                );
              })}
            </select>
          </label>
          <label>
            <span>Game state</span>
            <select
              className="select"
              value={currentGameState}
              onChange={(event) => loadInPossession({ gameState: event.target.value, timeRange: "all" })}
              aria-label="Game state"
              disabled={isLoading}
            >
              {availableGameStates.map((row) => (
                <option key={row.value} value={row.value}>
                  {row.label}
                </option>
              ))}
            </select>
          </label>
          <div className="time-range-control">
            <div className="time-range-control-head">
              <span>Minute Range</span>
              <strong>{Math.round(draftRange[0])}'-{Math.round(draftRange[1])}'</strong>
            </div>
            <div className="time-range-rail" aria-hidden="true">
              <span
                style={{
                  left: `${((draftRange[0] - minMinute) / Math.max(1, maxMinute - minMinute)) * 100}%`,
                  width: `${((draftRange[1] - draftRange[0]) / Math.max(1, maxMinute - minMinute)) * 100}%`,
                }}
              />
            </div>
            <div className="time-range-inputs">
              <label>
                <span>From</span>
                <input
                  inputMode="numeric"
                  value={displayStart}
                  onChange={(event) => setStartInput(event.target.value)}
                  onBlur={commitStartInput}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") commitStartInput();
                  }}
                />
              </label>
              <label>
                <span>To</span>
                <input
                  inputMode="numeric"
                  value={displayEnd}
                  onChange={(event) => setEndInput(event.target.value)}
                  onBlur={commitEndInput}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") commitEndInput();
                  }}
                />
              </label>
            </div>
            <div className="time-range-presets">
              <button type="button" onClick={() => setDraftRange([minMinute, maxMinute])}>Full</button>
              <button type="button" onClick={() => setDraftRange([minMinute, Math.min(maxMinute, 45)])}>1st H</button>
              <button type="button" onClick={() => setDraftRange([Math.max(minMinute, 45), maxMinute])}>2nd H</button>
              <button type="button" onClick={() => setDraftRange([minMinute, Math.min(maxMinute, minMinute + 15)])}>Open 15</button>
              <button type="button" onClick={() => setDraftRange([Math.max(minMinute, maxMinute - 15), maxMinute])}>Close 15</button>
            </div>
            <button
              type="button"
              className="ghost-button time-range-apply"
              onClick={() => loadInPossession({ timeRange: `${Math.round(draftRange[0])}-${Math.round(draftRange[1])}` })}
              disabled={isLoading}
            >
              Apply
            </button>
          </div>
        </div>
      </div>
      <div className="analysis-workspace in-possession-workspace">
        <aside className="analysis-workspace-rail in-possession-filter-rail">
          <section className="pass-network-selected-panel is-in-rail">
            {selectedNetworkPlayer ? (
              <>
                <div className="pass-network-selected-header">
                  <div className="pass-network-selected-identity">
                    <PlayerAvatar name={String(selectedNetworkPlayer.player ?? "")} team={currentTeam} size={38} />
                    <div>
                      <span className="eyebrow">Selected Player</span>
                      <strong>{selectedNetworkPlayer.player}</strong>
                    </div>
                  </div>
                  <button type="button" onClick={clearNetworkPlayerSelection}>Clear</button>
                </div>
                <div className="pass-network-selected-stats">
                  <div><span>Passes made</span><strong>{num(selectedNetworkPlayer.passes_made)}</strong></div>
                  <div><span>Passes received</span><strong>{num(selectedNetworkPlayer.passes_received)}</strong></div>
                  <div><span>Avg pass distance</span><strong>{num(selectedNetworkPlayer.avg_pass_distance).toFixed(1)}m</strong></div>
                  <div><span>Prog made</span><strong>{num(selectedNetworkPlayer.progressive_passes_made)}</strong></div>
                  <div><span>Prog received</span><strong>{num(selectedNetworkPlayer.progressive_passes_received)}</strong></div>
                  <div><span>xT made</span><strong>{selectedNetwork.outgoingXt.toFixed(3)}</strong></div>
                  <div><span>xT received</span><strong>{selectedNetwork.incomingXt.toFixed(3)}</strong></div>
                </div>
              </>
            ) : (
              <div className="pass-network-selected-empty">
                <span className="eyebrow">Selected Player</span>
                <strong>Select a node to inspect passing connections</strong>
              </div>
            )}
          </section>
          {selectedNetworkPlayer && (
            <div className="in-possession-rail-player-tools">
              {networkTeamBaseline && <div className="defensive-baseline-card possession-baseline-card">
                <span className="eyebrow">Vs Team Baseline</span>
                <div><span>Progressive pass rate</span><strong>{networkTeamBaseline.progressivePct}%</strong><small>Team {networkTeamBaseline.teamProgressivePct}%</small></div>
                <div><span>Share of received passes</span><strong>{networkTeamBaseline.receivedPct}%</strong><small>Within selected team/window</small></div>
              </div>}
              <div className="pass-network-action-overlay-controls">
                <button
                  type="button"
                  className={showNetworkPlayerActions ? "button" : "ghost-button"}
                  onClick={() => setShowNetworkPlayerActions((current) => !current)}
                >
                  {showNetworkPlayerActions ? "Hide individual actions" : "Show individual actions"}
                </button>
                {showNetworkPlayerActions && <div className="in-possession-action-type-grid">
                  <button
                    type="button"
                    className={!networkOverlayActionTypes.length ? "button" : "ghost-button"}
                    onClick={() => setNetworkOverlayActionTypes([])}
                  >
                    All
                  </button>
                  {(["Pass", "Carry", "TakeOn"] as string[]).map((type) => (
                    <button
                      key={type}
                      type="button"
                      className={networkOverlayActionTypes.includes(type) ? "button" : "ghost-button"}
                      onClick={() => setNetworkOverlayActionTypes((current) => current.includes(type)
                        ? current.filter((value) => value !== type)
                        : [...current, type])}
                    >
                      {type === "TakeOn" ? "Take-ons" : type === "Carry" ? "Carries" : "Passes"}
                    </button>
                  ))}
                </div>}
                {showNetworkPlayerActions && <div className="in-possession-action-scope">
                  <span>Action range</span>
                  <div>
                    {([
                      ["filtered", "Filtered"],
                      ["all", "All minutes"],
                    ] as Array<[ActionScope, string]>).map(([scope, label]) => (
                      <button
                        key={scope}
                        type="button"
                        className={networkActionScope === scope ? "button" : "ghost-button"}
                        onClick={() => {
                          setNetworkActionScope(scope);
                          void loadCurrentActions(scope);
                        }}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>}
                {showNetworkPlayerActions && <label className="in-possession-action-toggle">
                  <input
                    type="checkbox"
                    checked={networkOverlayShowUnsuccessful}
                    onChange={(event) => setNetworkOverlayShowUnsuccessful(event.target.checked)}
                  />
                  <span>Unsuccessful actions</span>
                </label>}
                {showNetworkPlayerActions && <p className="muted-copy">
                  Showing {selectedNetworkPlayerActionCount} actions for {selectedNetworkPlayer.player} from {networkActionScope === "all" ? "all minutes" : "the selected filters"}.
                </p>}
              </div>
            </div>
          )}
        </aside>
        <div className="analysis-workspace-main">
          <AttackDirectionCue team={currentTeam} />
          <div className="phase-filter-row" role="group" aria-label="Possession phase filter">
            <button
              type="button"
              className={currentThird === "all" ? "phase-chip is-active" : "phase-chip"}
              onClick={() => loadInPossession({ third: "all" })}
            >
              <strong>All Phases</strong>
              <span>Full pitch</span>
            </button>
            {(((currentPayload.third_kpis as Array<Record<string, string | number>> | undefined) ?? [])).map((kpi) => (
              <button
                key={String(kpi.third)}
                type="button"
                className={currentThird === String(kpi.third) ? "phase-chip is-active" : "phase-chip"}
                onClick={() => loadInPossession({ third: String(kpi.third) })}
              >
                <strong>{String(kpi.label)}</strong>
                <span>
                  {String(kpi.completed)}/{String(kpi.passes)} passes · {String(kpi.completion_pct)}% · xT {String(kpi.xt)} · {String(kpi.progressive)} prog.
                </span>
              </button>
            ))}
          </div>
          <PassNetworkPlotly
            payload={currentPayload}
            opponentPayload={currentOpponentPayload}
            actionsPayload={currentActionsPayload}
            teamColor={activeTeamColor}
            selectedPlayerId={selectedNetworkPlayerId}
            onSelectedPlayerChange={handleNetworkPlayerSelection}
            showPlayerActions={showNetworkPlayerActions}
            overlayActionTypes={networkOverlayActionTypes}
            overlayShowUnsuccessful={networkOverlayShowUnsuccessful}
            highlightThird={currentThird}
          />
        </div>
      </div>
    </section>
    <InPossessionMetricsTable rows={currentRows} team={currentTeam} playerBaselines={playerBaselines} />
    <ChannelAnalysisPanel
      matchId={matchId}
      source={source}
      league={league}
      season={season}
      jobId={jobId}
      team={currentTeam}
      teamColor={activeTeamColor}
    />
    <EntriesPenetrationPanel
      matchId={matchId}
      source={source}
      league={league}
      season={season}
      jobId={jobId}
      team={currentTeam}
      teams={teams}
      teamColor={activeTeamColor}
    />
    <SetPiecesPanel
      matchId={matchId}
      source={source}
      league={league}
      season={season}
      jobId={jobId}
      team={currentTeam}
      teamColor={activeTeamColor}
    />
    </>
  );
}
