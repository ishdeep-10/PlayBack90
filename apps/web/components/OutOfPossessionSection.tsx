"use client";

import { DownloadPngButton, type SideTableRow } from "./DownloadPngButton";

import { useSyncFiltersToUrl } from "../lib/analysisUrl";

import { useState } from "react";

import { getAnalysisView } from "../lib/api";
import { fallbackTeamColor, num, parseRange } from "../lib/theme";
import { AttackDirectionCue } from "./AttackDirectionCue";
import { DefenderAccountabilityPanel } from "./DefenderAccountabilityPanel";
import { DefensiveActionsPlotly } from "./DefensiveActionsPlotly";
import { DefensiveVulnerabilityPanel } from "./DefensiveVulnerabilityPanel";
import { PlayerAvatar, getCachedPlayerImage } from "./PlayerAvatar";
import { SeasonDeltaChip } from "./season/SeasonDeltaChip";
import { metricByKey, type PlayerBaseline } from "./season/baselineTypes";

type OptionRow = { value?: string; label?: string; minute_start?: number; minute_end?: number };
type SummaryRow = Record<string, string | number | boolean | null | undefined>;

type Props = {
  matchId: string;
  source: string;
  filePath?: string;
  jobId?: string;
  teams: string[];
  selectedTeam: string;
  payload: Record<string, unknown>;
  teamColors: Record<string, string>;
  playerBaselines?: Record<string, PlayerBaseline>;
};

export function OutOfPossessionSection({
  matchId,
  source,
  filePath,
  jobId,
  teams,
  selectedTeam,
  payload,
  teamColors,
  playerBaselines,
}: Props) {
  const [currentTeam, setCurrentTeam] = useState(selectedTeam);
  const [currentPayload, setCurrentPayload] = useState(payload);
  const [gameState, setGameState] = useState(String(payload.score_state ?? "all"));
  const [timeRange, setTimeRange] = useState(String(payload.time_range ?? "all"));
  const [isLoading, setIsLoading] = useState(false);

  useSyncFiltersToUrl({ team: currentTeam, gameState, timeRange });
  const [visualMode, setVisualMode] = useState<"zones" | "actions">("zones");
  const [actionContext, setActionContext] = useState<"all" | "counterpress" | "high-press" | "settled">("all");
  const [startInput, setStartInput] = useState<string | null>(null);
  const [endInput, setEndInput] = useState<string | null>(null);
  const [showSeasonDeltas, setShowSeasonDeltas] = useState(false);
  const hasBaselines = Boolean(playerBaselines && Object.values(playerBaselines).some((b) => !b.lowSample));

  const actions = (currentPayload.actions as SummaryRow[] | undefined) ?? [];
  const rows = (currentPayload.player_summary as SummaryRow[] | undefined) ?? [];
  const transitionSummary = (currentPayload.transition_summary as SummaryRow | undefined) ?? {};
  const transitionSequences = (currentPayload.transition_sequences as SummaryRow[] | undefined) ?? [];
  const gameStateOptions = ((currentPayload.game_state_options as OptionRow[] | undefined) ?? [{ value: "all", label: "All states" }]);
  const timeRangeOptions = ((currentPayload.time_range_options as OptionRow[] | undefined) ?? [{ value: "all", label: "Full match" }]);
  const windowRange = timeRangeOptions[0] ?? { minute_start: 0, minute_end: 90 };
  const minMinute = num(windowRange.minute_start, 0);
  const maxMinute = Math.max(minMinute + 1, num(windowRange.minute_end, 90));
  const [initialStart, initialEnd] = parseRange(String(currentPayload.time_range ?? timeRange), minMinute, maxMinute);
  const [draftRange, setDraftRange] = useState<[number, number]>([initialStart, initialEnd]);
  const displayStart = startInput ?? String(Math.round(draftRange[0]));
  const displayEnd = endInput ?? String(Math.round(draftRange[1]));
  const teamColor = teamColors[currentTeam] ?? fallbackTeamColor(currentTeam);

  const buildBody = (team: string, state: string, range: string) => {
    const filters: Record<string, string | undefined> = { team, gameState: state, timeRange: range };
    if (source !== "r2") filters.job_id = jobId;
    return source !== "r2"
      ? { match_id: matchId, source, filters }
      : { match_id: matchId, source: "r2", file_path: filePath, filters };
  };

  const loadView = async (next: { team?: string; gameState?: string; timeRange?: string }) => {
    const nextTeam = next.team ?? currentTeam;
    const nextState = next.gameState ?? gameState;
    const nextRange = next.timeRange ?? timeRange;
    setIsLoading(true);
    try {
      const response = await getAnalysisView("defensive-actions", buildBody(nextTeam, nextState, nextRange));
      const nextPayload = response.payload ?? {};
      setCurrentTeam(String(nextPayload.team ?? nextTeam));
      setCurrentPayload(nextPayload);
      setGameState(String(nextPayload.score_state ?? nextState));
      setTimeRange(String(nextPayload.time_range ?? nextRange));
      const nextOptions = (nextPayload.time_range_options as OptionRow[] | undefined) ?? timeRangeOptions;
      const nextWindow = nextOptions[0] ?? { minute_start: minMinute, minute_end: maxMinute };
      const nextMin = num(nextWindow.minute_start, minMinute);
      const nextMax = num(nextWindow.minute_end, maxMinute);
      const [start, end] = parseRange(String(nextPayload.time_range ?? nextRange), nextMin, nextMax);
      setDraftRange([start, end]);
      setStartInput(null);
      setEndInput(null);
    } finally {
      setIsLoading(false);
    }
  };

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

  return (
    <>
    <section className={`card stack${isLoading ? " is-loading-soft" : ""}`}>
      {isLoading && <div className="analysis-loading-bar" aria-label="Loading defensive actions" />}
      <div className="analysis-section-toolbar">
        <div>
          <span className="eyebrow">Out of Possession</span>
          <div className="chart-card-head">
            <h2 style={{ margin: "6px 0 0" }}>Defensive Actions - {currentTeam}</h2>
            <DownloadPngButton
              filename={`${currentTeam}-defensive-actions`}
              title="Defensive Actions"
              scopeSelector=".card"
              filters={() => [
                currentTeam,
                ...(gameState !== "all" ? [gameStateOptions.find((option) => String(option.value) === gameState)?.label ?? gameState] : []),
                ...(timeRange !== "all" ? [`${timeRange}'`] : []),
              ]}
              sideTable={() => {
                const totals: Array<[string, keyof SummaryRow & string]> = [
                  ["Tackles", "tackles"],
                  ["Interceptions", "interceptions"],
                  ["Recoveries", "recoveries"],
                  ["Clearances", "clearances"],
                  ["Blocked passes", "blocked_passes"],
                ];
                const tableRows: SideTableRow[] = [
                  { label: "Actions", value: String(actions.length) },
                  ...totals.map(([label, key]): SideTableRow => ({
                    label,
                    value: String(rows.reduce((sum, row) => sum + num(row[key]), 0)),
                  })),
                  { label: "Counterpress regains", value: String(num(transitionSummary.counterpress_regains)) },
                  { label: "Counterpress success", value: `${num(transitionSummary.counterpress_success_pct).toFixed(1)}%` },
                  {
                    label: "Average recovery",
                    value: transitionSummary.avg_recovery_seconds == null ? "N/A" : `${num(transitionSummary.avg_recovery_seconds).toFixed(1)}s`,
                  },
                ];
                const topDefenders = [...rows]
                  .sort((a, b) => num(b.total) - num(a.total))
                  .slice(0, 5);
                if (topDefenders.length) {
                  tableRows.push({ header: "Top defensive players" });
                  topDefenders.forEach((row) => {
                    const player = String(row.player ?? "");
                    tableRows.push({
                      image: getCachedPlayerImage(player, currentTeam),
                      label: player,
                      value: `${num(row.total)} actions`,
                      sub: `${num(row.tackles)} tkl · ${num(row.interceptions)} int · ${num(row.recoveries)} rec · Def ${num(row.defensive_third)} / Mid ${num(row.middle_third)} / Att ${num(row.attacking_third)}`,
                    });
                  });
                }
                return { title: `${currentTeam} · Defensive Actions`, rows: tableRows, large: true };
              }}
            />
          </div>
        </div>
        <div className="analysis-section-controls">
          <div className="segmented-control" aria-label="Defensive visual mode">
            <button type="button" className={visualMode === "zones" ? "is-active" : ""} onClick={() => setVisualMode("zones")}>
              Zone %
            </button>
            <button type="button" className={visualMode === "actions" ? "is-active" : ""} onClick={() => setVisualMode("actions")}>
              Actions
            </button>
          </div>
          <div className="row" style={{ gap: 8 }}>
            {teams.map((team) => (
              <button
                key={team}
                type="button"
                className={team === currentTeam ? "button" : "ghost-button"}
                onClick={() => loadView({ team, gameState: "all", timeRange: "all" })}
                disabled={isLoading}
              >
                {team}
              </button>
            ))}
          </div>
          <select
            className="select"
            value={gameState}
            onChange={(event) => loadView({ gameState: event.target.value, timeRange: "all" })}
            disabled={isLoading}
          >
            {gameStateOptions.map((option) => (
              <option key={String(option.value)} value={String(option.value)}>
                {option.label}
              </option>
            ))}
          </select>
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
              onClick={() => loadView({ timeRange: `${Math.round(draftRange[0])}-${Math.round(draftRange[1])}` })}
              disabled={isLoading}
            >
              Apply
            </button>
          </div>
        </div>
      </div>

      <div className="shot-team-total-strip">
        {[
          ["Actions", actions.length],
          ["Tackles", rows.reduce((sum, row) => sum + num(row.tackles), 0)],
          ["Interceptions", rows.reduce((sum, row) => sum + num(row.interceptions), 0)],
          ["Recoveries", rows.reduce((sum, row) => sum + num(row.recoveries), 0)],
          ["Counterpress Regains", num(transitionSummary.counterpress_regains)],
          ["Counterpress %", `${num(transitionSummary.counterpress_success_pct).toFixed(1)}%`],
          ["Avg Recovery", transitionSummary.avg_recovery_seconds == null ? "N/A" : `${num(transitionSummary.avg_recovery_seconds).toFixed(1)}s`],
        ].map(([label, value]) => (
          <div key={label} className="shot-team-total">
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>

      {visualMode === "actions" && (
        <div className="defensive-context-toolbar">
          <span className="eyebrow">Action Context</span>
          <div className="segmented-control" aria-label="Defensive action context">
            {[
              ["all", "All actions"],
              ["counterpress", "Counterpress"],
              ["high-press", "High press"],
              ["settled", "Settled defence"],
            ].map(([value, label]) => (
              <button
                key={value}
                type="button"
                className={actionContext === value ? "is-active" : ""}
                onClick={() => setActionContext(value as typeof actionContext)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      )}
      <AttackDirectionCue team={currentTeam} label="Team attack direction" />
      <DefensiveActionsPlotly
        actions={actions}
        team={currentTeam}
        teamColor={teamColor}
        mode={visualMode}
        contextFilter={actionContext}
      />

      {hasBaselines ? (
        <div className="row" style={{ justifyContent: "flex-end" }}>
          <button
            type="button"
            className={showSeasonDeltas ? "button" : "ghost-button"}
            onClick={() => setShowSeasonDeltas((current) => !current)}
          >
            vs season
          </button>
        </div>
      ) : null}
      <div className="shot-summary-table-wrap">
        <table className="table shot-summary-table">
          <thead>
            <tr>
              <th>Player</th>
              <th>Total</th>
              <th>Tackles</th>
              <th>Interceptions</th>
              <th>Recoveries</th>
              <th>Clearances</th>
              <th>Blocked Passes</th>
              <th>Def 3rd</th>
              <th>Mid 3rd</th>
              <th>Att 3rd</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const baseline = playerBaselines?.[String(row.player ?? "")];
              const chip = (key: string) =>
                showSeasonDeltas && baseline && !baseline.lowSample ? (
                  <SeasonDeltaChip metric={metricByKey(baseline, key)} per90 />
                ) : null;
              return (
                <tr key={String(row.player)}>
                  <td>
                    <span className="shot-player-cell">
                      <PlayerAvatar name={String(row.player ?? "")} team={currentTeam} size={24} />
                      <strong>{row.player}</strong>
                    </span>
                  </td>
                  <td>{row.total}{chip("def_actions_total")}</td>
                  <td>{row.tackles}{chip("tackles")}</td>
                  <td>{row.interceptions}{chip("interceptions")}</td>
                  <td>{row.recoveries}{chip("recoveries")}</td>
                  <td>{row.clearances}{chip("clearances")}</td>
                  <td>{row.blocked_passes}{chip("blocked_passes")}</td>
                  <td>{row.defensive_third}{chip("def_actions_def_third")}</td>
                  <td>{row.middle_third}{chip("def_actions_mid_third")}</td>
                  <td>{row.attacking_third}{chip("def_actions_att_third")}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <details className="defensive-transition-details">
        <summary>
          <span>
            <strong>Defensive Transitions</strong>
            <small>Loss-to-regain timing and counterpress sequences</small>
          </span>
          <span>{transitionSequences.length} opportunities</span>
        </summary>
        <div className="defensive-transition-body">
          <div className="defensive-transition-metrics">
            <div><span>Average</span><strong>{transitionSummary.avg_recovery_seconds == null ? "N/A" : `${num(transitionSummary.avg_recovery_seconds).toFixed(1)}s`}</strong></div>
            <div><span>Median</span><strong>{transitionSummary.median_recovery_seconds == null ? "N/A" : `${num(transitionSummary.median_recovery_seconds).toFixed(1)}s`}</strong></div>
            <div><span>Fastest</span><strong>{transitionSummary.fastest_recovery_seconds == null ? "N/A" : `${num(transitionSummary.fastest_recovery_seconds).toFixed(1)}s`}</strong></div>
            <div><span>Within 5s</span><strong>{num(transitionSummary.within_5_seconds)}</strong></div>
            <div><span>Within 10s</span><strong>{num(transitionSummary.within_10_seconds)}</strong></div>
            <div><span>Within 15s</span><strong>{num(transitionSummary.within_15_seconds)}</strong></div>
          </div>
          <div className="shot-summary-table-wrap">
            <table className="table shot-summary-table defensive-transition-table">
              <thead>
                <tr>
                  <th>Possession Lost</th>
                  <th>Lost By</th>
                  <th>Regain</th>
                  <th>Regained By</th>
                  <th>Recovery Time</th>
                  <th>Counterpress</th>
                </tr>
              </thead>
              <tbody>
                {transitionSequences.map((sequence) => (
                  <tr key={String(sequence.sequence_id)}>
                    <td>{num(sequence.loss_minute)}' {num(sequence.loss_second)}s · {String(sequence.loss_type ?? "Loss")}</td>
                    <td>{String(sequence.loss_player ?? "Unknown")}</td>
                    <td>{sequence.regain_minute == null ? "Not recovered within 60s" : `${num(sequence.regain_minute)}' ${num(sequence.regain_second)}s · ${String(sequence.regain_type ?? "Regain")}`}</td>
                    <td>{String(sequence.regain_player ?? "") || "—"}</td>
                    <td>{sequence.recovery_seconds == null ? "—" : `${num(sequence.recovery_seconds).toFixed(1)}s`}</td>
                    <td>
                      <span className={sequence.counterpress_success ? "transition-status is-success" : "transition-status"}>
                        {sequence.counterpress_success ? "Regained" : num(sequence.counterpress_actions) ? "Attempted" : "No action"}
                      </span>
                    </td>
                  </tr>
                ))}
                {!transitionSequences.length && (
                  <tr><td colSpan={6}>No possession-loss sequences are available for these filters.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </details>
    </section>
    <DefensiveVulnerabilityPanel
      matchId={matchId}
      source={source}
      filePath={filePath}
      jobId={jobId}
      team={currentTeam}
      teams={teams}
      teamColor={teamColor}
    />
    <DefenderAccountabilityPanel
      matchId={matchId}
      source={source}
      filePath={filePath}
      jobId={jobId}
      team={currentTeam}
      teams={teams}
      teamColor={teamColor}
    />
    </>
  );
}
