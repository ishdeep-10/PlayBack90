"use client";

import { DownloadPngButton, type SideTableRow } from "./DownloadPngButton";

import { useSyncFiltersToUrl } from "../lib/analysisUrl";

import { useEffect, useMemo, useRef, useState } from "react";

import { getAnalysisView } from "../lib/api";
import { num, parseRange } from "../lib/theme";
import { DuelsTransitionsPlotly } from "./DuelsTransitionsPlotly";
import { MobileAnalysisControls } from "./MobileAnalysisControls";
import { PlayerAvatar, getCachedPlayerImage, prefetchPlayerImages } from "./PlayerAvatar";
import { SeasonDeltaChip } from "./season/SeasonDeltaChip";
import { metricByKey, type PlayerBaseline } from "./season/baselineTypes";

type OptionRow = { value?: string; label?: string; minute_start?: number; minute_end?: number };
type SummaryRow = Record<string, string | number | boolean | null | undefined>;
type DuelPlayerRow = {
  player: string;
  team: string;
  duels: number;
  duels_won: number;
  duels_lost: number;
  duel_win_pct: number;
  ground: number;
  aerial: number;
};
type TransitionPlayerRow = {
  player: string;
  team: string;
  transitions: number;
  transitions_to_attack: number;
  transitions_stalled: number;
  transition_hit_pct: number;
  defensive_third: number;
  middle_third: number;
  attacking_third: number;
};
type DuelProfile = {
  name: string;
  score: number;
  detail: string;
  description: string;
};

type DuelSortKey = keyof Pick<DuelPlayerRow, "player" | "duels" | "duels_won" | "duels_lost" | "duel_win_pct" | "ground" | "aerial">;
type TransitionSortKey = keyof Pick<TransitionPlayerRow, "player" | "transitions" | "transitions_to_attack" | "transitions_stalled" | "transition_hit_pct" | "defensive_third" | "middle_third" | "attacking_third">;

type Props = {
  matchId: string;
  source: string;
  league?: string;
  season?: string;
  jobId?: string;
  teams: string[];
  selectedTeam: string;
  selectedDuelType: string;
  selectedTransitionType: string;
  payload: Record<string, unknown>;
  teamColors: Record<string, string>;
  playerBaselines?: Record<string, PlayerBaseline>;
};

const DUEL_TYPES = ["Total", "Ground Duels", "Aerial Duels"];

// duels table column -> season-baseline metric key
const DUEL_BASELINE_KEYS: Record<string, string> = {
  duels: "duels",
  duels_won: "duels_won",
  duels_lost: "duels_lost",
  duel_win_pct: "duel_win_pct",
  ground: "ground_duels",
  aerial: "aerial_duels",
};

function viewCacheKey(team: string, duelType: string, transitionType: string, gameState: string, timeRange: string) {
  return [team, normalizeDuelType(duelType), transitionType, team === "__both__" ? "all" : gameState, timeRange].join("::");
}

function normalizeDuelType(value: unknown) {
  const raw = String(value ?? "Total");
  if (raw === "Offensive" || raw === "Defensive" || raw === "Ground") return "Ground Duels";
  if (raw === "Aerial") return "Aerial Duels";
  return DUEL_TYPES.includes(raw) ? raw : "Total";
}

function fallbackTeamColor(team: string, teams: string[]) {
  if (team === teams[0]) return "#22c55e";
  if (team === teams[1]) return "#38bdf8";
  return "#a78bfa";
}

function teamFilterLabel(team: string) {
  return team === "__both__" ? "Both Teams" : team;
}

function playerKey(row: { team?: string | number | null; player?: string | number | null }) {
  return `${String(row.team ?? "")}::${String(row.player ?? "")}`;
}

function buildDuelPlayerRows(duels: SummaryRow[]): DuelPlayerRow[] {
  const map = new Map<string, Omit<DuelPlayerRow, "duels_lost" | "duel_win_pct">>();
  duels.forEach((row) => {
    const player = String(row.player ?? "").trim();
    if (!player) return;
    const key = playerKey(row);
    const item = map.get(key) ?? {
      player,
      team: String(row.team ?? ""),
      duels: 0,
      duels_won: 0,
      ground: 0,
      aerial: 0,
    };
    item.duels = num(item.duels) + 1;
    item.duels_won = num(item.duels_won) + (row.won === true ? 1 : 0);
    const category = String(row.category ?? "").toLowerCase();
    if (category === "ground") item.ground = num(item.ground) + 1;
    if (category === "aerial") item.aerial = num(item.aerial) + 1;
    map.set(key, item);
  });
  return [...map.values()]
    .map((row) => ({
      ...row,
      duels_lost: num(row.duels) - num(row.duels_won),
      duel_win_pct: num(row.duels) ? Math.round((num(row.duels_won) / num(row.duels)) * 100) : 0,
    } satisfies DuelPlayerRow))
    .sort((a, b) => num(b.duels_won) - num(a.duels_won) || num(b.duels) - num(a.duels));
}

function buildTransitionPlayerRows(transitions: SummaryRow[]): TransitionPlayerRow[] {
  const map = new Map<string, Omit<TransitionPlayerRow, "transitions_stalled" | "transition_hit_pct">>();
  transitions.forEach((row) => {
    const player = String(row.player ?? "").trim();
    if (!player) return;
    const key = playerKey(row);
    const item = map.get(key) ?? {
      player,
      team: String(row.team ?? ""),
      transitions: 0,
      transitions_to_attack: 0,
      defensive_third: 0,
      middle_third: 0,
      attacking_third: 0,
    };
    item.transitions = num(item.transitions) + 1;
    item.transitions_to_attack = num(item.transitions_to_attack) + (row.led_to_attack === true ? 1 : 0);
    const third = String(row.third ?? "").toLowerCase();
    if (third.includes("defensive")) item.defensive_third = num(item.defensive_third) + 1;
    if (third.includes("middle")) item.middle_third = num(item.middle_third) + 1;
    if (third.includes("attacking")) item.attacking_third = num(item.attacking_third) + 1;
    map.set(key, item);
  });
  return [...map.values()]
    .map((row) => ({
      ...row,
      transitions_stalled: num(row.transitions) - num(row.transitions_to_attack),
      transition_hit_pct: num(row.transitions) ? Math.round((num(row.transitions_to_attack) / num(row.transitions)) * 100) : 0,
    } satisfies TransitionPlayerRow))
    .sort((a, b) => num(b.transitions_to_attack) - num(a.transitions_to_attack) || num(b.transitions) - num(a.transitions));
}

function pct(part: number, total: number) {
  return total ? Math.round((part / total) * 100) : 0;
}

function duelMatchesProfile(row: SummaryRow, profile: string) {
  const category = String(row.category ?? "").toLowerCase();
  const zone = String(row.zone ?? "");
  const context = String(row.duel_context ?? "");
  const won = row.won === true;

  if (profile === "Ground Duel Edge") return category === "ground" && won;
  if (profile === "Aerial Control") return category === "aerial" && won;
  if (profile === "Attack Starter") return won && context === "led_to_attack";
  if (profile === "Risk Zone Losses") return !won && ["Defensive Third", "Middle Third"].includes(zone);
  return true;
}

function buildDuelProfiles(rows: SummaryRow[]): { profiles: DuelProfile[]; insight: string } {
  const ground = rows.filter((row) => String(row.category ?? "").toLowerCase() === "ground");
  const groundWon = ground.filter((row) => row.won === true);
  const aerial = rows.filter((row) => String(row.category ?? "").toLowerCase() === "aerial");
  const aerialWon = aerial.filter((row) => row.won === true);
  const won = rows.filter((row) => row.won === true);
  const attackStarters = rows.filter((row) => duelMatchesProfile(row, "Attack Starter"));
  const riskLosses = rows.filter((row) => duelMatchesProfile(row, "Risk Zone Losses"));
  const defensiveMiddle = rows.filter((row) => ["Defensive Third", "Middle Third"].includes(String(row.zone ?? "")));

  const profiles: DuelProfile[] = [
    {
      name: "Ground Duel Edge",
      score: pct(groundWon.length, ground.length),
      detail: `${groundWon.length}/${ground.length} ground duels won`,
      description: "Shows how often the team comes out ahead in tackles, take-ons and fouls on the ground.",
    },
    {
      name: "Aerial Control",
      score: pct(aerialWon.length, aerial.length),
      detail: `${aerialWon.length}/${aerial.length} aerial duels won`,
      description: "Highlights aerial dominance and the players/zones winning first contact.",
    },
    {
      name: "Attack Starter",
      score: pct(attackStarters.length, Math.max(1, won.length)),
      detail: `${attackStarters.length} won duels led to attack`,
      description: "Focuses duels that become shots, corners or box entries within the next phase.",
    },
    {
      name: "Risk Zone Losses",
      score: pct(riskLosses.length, Math.max(1, defensiveMiddle.length)),
      detail: `${riskLosses.length} losses in defensive/middle thirds`,
      description: "Shows the costly duel losses before the attacking third. Higher means more exposure.",
    },
  ];

  const strongest = [...profiles].sort((a, b) => b.score - a.score)[0];
  return {
    profiles,
    insight: strongest
      ? `Duel profile strongest as ${strongest.name.toLowerCase()} (${strongest.score}/100).`
      : "No duel profile available for this filter.",
  };
}

export function DuelsTransitionsSection({
  matchId,
  source,
  league,
  season,
  jobId,
  teams,
  selectedTeam,
  selectedDuelType,
  selectedTransitionType,
  payload,
  teamColors,
  playerBaselines,
}: Props) {
  const [currentTeam, setCurrentTeam] = useState(String(payload.team ?? selectedTeam));
  const [showSeasonDeltas, setShowSeasonDeltas] = useState(false);
  const hasBaselines = Boolean(playerBaselines && Object.values(playerBaselines).some((b) => !b.lowSample));
  const [currentPayload, setCurrentPayload] = useState(payload);
  const [duelType, setDuelType] = useState(normalizeDuelType(payload.duel_type ?? selectedDuelType));
  const [transitionType, setTransitionType] = useState(String(payload.transition_type ?? selectedTransitionType));
  const [gameState, setGameState] = useState(String(payload.score_state ?? "all"));
  const [timeRange, setTimeRange] = useState(String(payload.time_range ?? "all"));
  const [isLoading, setIsLoading] = useState(false);

  useSyncFiltersToUrl({ duelType, transitionType, gameState, timeRange });
  const [duelVisualMode, setDuelVisualMode] = useState<"zones" | "actions">("zones");
  const [transitionVisualMode, setTransitionVisualMode] = useState<"zones" | "actions">("zones");
  const [duelSort, setDuelSort] = useState<{ key: DuelSortKey; direction: "asc" | "desc" }>({ key: "duels_won", direction: "desc" });
  const [transitionSort, setTransitionSort] = useState<{ key: TransitionSortKey; direction: "asc" | "desc" }>({ key: "transitions", direction: "desc" });
  const [startInput, setStartInput] = useState<string | null>(null);
  const [endInput, setEndInput] = useState<string | null>(null);
  const [selectedDuelPlayer, setSelectedDuelPlayer] = useState("");
  const [selectedDuelProfile, setSelectedDuelProfile] = useState("");
  const payloadCacheRef = useRef(new Map<string, Record<string, unknown>>());
  const hasSeededCacheRef = useRef(false);

  const duels = (currentPayload.duels as SummaryRow[] | undefined) ?? [];
  const transitions = (currentPayload.transitions as SummaryRow[] | undefined) ?? [];
  const duelPlayerRows = useMemo(() => buildDuelPlayerRows(duels), [duels]);
  const transitionPlayerRows = useMemo(() => buildTransitionPlayerRows(transitions), [transitions]);
  const isBothTeams = currentTeam === "__both__";
  useEffect(() => {
    const byTeam = new Map<string, string[]>();
    [...duelPlayerRows, ...transitionPlayerRows].forEach((row) => {
      const names = byTeam.get(row.team) ?? [];
      names.push(row.player);
      byTeam.set(row.team, names);
    });
    byTeam.forEach((names, team) => prefetchPlayerImages(names, team || undefined));
  }, [duelPlayerRows, transitionPlayerRows]);
  if (!hasSeededCacheRef.current) {
    payloadCacheRef.current.set(
      viewCacheKey(currentTeam, duelType, transitionType, gameState, timeRange),
      currentPayload,
    );
    hasSeededCacheRef.current = true;
  }
  const duelPlayerRowsByTeam = useMemo(() => {
    const map = new Map<string, DuelPlayerRow[]>();
    duelPlayerRows.forEach((row) => {
      const rows = map.get(row.team) ?? [];
      rows.push(row);
      map.set(row.team, rows);
    });
    return map;
  }, [duelPlayerRows]);
  const gameStateOptions = isBothTeams
    ? [{ value: "all", label: "All states" }]
    : (currentPayload.game_state_options as OptionRow[] | undefined) ?? [{ value: "all", label: "All states" }];
  const timeRangeOptions = (currentPayload.time_range_options as OptionRow[] | undefined) ?? [{ value: "all", label: "Full match", minute_start: 0, minute_end: 90 }];
  const windowRange = timeRangeOptions[0] ?? { minute_start: 0, minute_end: 90 };
  const minMinute = num(windowRange.minute_start, 0);
  const maxMinute = Math.max(minMinute + 1, num(windowRange.minute_end, 90));
  const [initialStart, initialEnd] = parseRange(String(currentPayload.time_range ?? timeRange), minMinute, maxMinute);
  const [draftRange, setDraftRange] = useState<[number, number]>([initialStart, initialEnd]);
  const displayStart = startInput ?? String(Math.round(draftRange[0]));
  const displayEnd = endInput ?? String(Math.round(draftRange[1]));
  const teamColor = currentTeam === "__both__"
    ? teamColors[teams[0]] ?? fallbackTeamColor(teams[0] ?? currentTeam, teams)
    : teamColors[currentTeam] ?? fallbackTeamColor(currentTeam, teams);
  const transitionHits = transitions.filter((row) => row.led_to_attack === true).length;
  const selectedPlayerDuelRows = useMemo(
    () => selectedDuelPlayer ? duels.filter((row) => String(row.player ?? "") === selectedDuelPlayer) : [],
    [duels, selectedDuelPlayer],
  );
  const duelTotalsScope = selectedPlayerDuelRows.length ? selectedPlayerDuelRows : duels;
  const scopedDuelsWon = duelTotalsScope.filter((row) => row.won === true).length;
  const duelTotalsLabel = selectedPlayerDuelRows.length ? selectedDuelPlayer : "Team";
  const duelProfileRows = useMemo(
    () => selectedPlayerDuelRows.length ? selectedPlayerDuelRows : duels.filter((row) => String(row.team ?? "") === currentTeam),
    [currentTeam, duels, selectedPlayerDuelRows],
  );
  const duelProfiles = useMemo(() => buildDuelProfiles(duelProfileRows), [duelProfileRows]);
  const selectedTeamTransitionRows = useMemo(
    () => transitionPlayerRows.filter((row) => row.team === currentTeam),
    [currentTeam, transitionPlayerRows],
  );
  const sortDuelRows = (rows: DuelPlayerRow[]) => {
    return [...rows].sort((a, b) => {
      const aValue = a[duelSort.key];
      const bValue = b[duelSort.key];
      const direction = duelSort.direction === "asc" ? 1 : -1;
      if (typeof aValue === "string" || typeof bValue === "string") {
        return String(aValue).localeCompare(String(bValue)) * direction;
      }
      return (num(aValue) - num(bValue)) * direction;
    });
  };
  const toggleDuelSort = (key: DuelSortKey) => {
    setDuelSort((current) => ({
      key,
      direction: current.key === key && current.direction === "desc" ? "asc" : "desc",
    }));
  };
  const sortIndicator = (key: DuelSortKey) => duelSort.key === key ? (duelSort.direction === "asc" ? " ↑" : " ↓") : "";
  const sortTransitionRows = (rows: TransitionPlayerRow[]) => {
    return [...rows].sort((a, b) => {
      const aValue = a[transitionSort.key];
      const bValue = b[transitionSort.key];
      const direction = transitionSort.direction === "asc" ? 1 : -1;
      if (typeof aValue === "string" || typeof bValue === "string") {
        return String(aValue).localeCompare(String(bValue)) * direction;
      }
      return (num(aValue) - num(bValue)) * direction;
    });
  };
  const toggleTransitionSort = (key: TransitionSortKey) => {
    setTransitionSort((current) => ({
      key,
      direction: current.key === key && current.direction === "desc" ? "asc" : "desc",
    }));
  };
  const transitionSortIndicator = (key: TransitionSortKey) => transitionSort.key === key ? (transitionSort.direction === "asc" ? " ↑" : " ↓") : "";

  const buildBody = (team: string, nextDuelType: string, nextTransitionType: string, state: string, range: string) => {
    const filters: Record<string, string | undefined> = {
      team,
      duelType: nextDuelType,
      transitionType: nextTransitionType,
      gameState: state,
      timeRange: range,
    };
    if (source !== "r2") filters.job_id = jobId;
    return source !== "r2"
      ? { match_id: matchId, source, filters }
      : { match_id: matchId, source: "r2", league, season, filters };
  };

  const applyPayload = (
    nextPayload: Record<string, unknown>,
    nextTeam: string,
    nextDuelType: string,
    nextTransitionType: string,
    nextState: string,
    nextRange: string,
  ) => {
    setCurrentTeam(String(nextPayload.team ?? nextTeam));
    setCurrentPayload(nextPayload);
    setDuelType(normalizeDuelType(nextPayload.duel_type ?? nextDuelType));
    setTransitionType(String(nextPayload.transition_type ?? nextTransitionType));
    setGameState(String(nextPayload.score_state ?? nextState));
    setTimeRange(String(nextPayload.time_range ?? nextRange));
    setSelectedDuelProfile("");
    const nextOptions = (nextPayload.time_range_options as OptionRow[] | undefined) ?? timeRangeOptions;
    const nextWindow = nextOptions[0] ?? { minute_start: minMinute, minute_end: maxMinute };
    const nextMin = num(nextWindow.minute_start, minMinute);
    const nextMax = num(nextWindow.minute_end, maxMinute);
    const [start, end] = parseRange(String(nextPayload.time_range ?? nextRange), nextMin, nextMax);
    setDraftRange([start, end]);
    setStartInput(null);
    setEndInput(null);
  };

  const loadView = async (next: { team?: string; duelType?: string; transitionType?: string; gameState?: string; timeRange?: string }) => {
    const nextTeam = next.team ?? currentTeam;
    const nextDuelType = normalizeDuelType(next.duelType ?? duelType);
    const nextTransitionType = next.transitionType ?? transitionType;
    const nextState = nextTeam === "__both__" ? "all" : next.gameState ?? gameState;
    const nextRange = next.timeRange ?? timeRange;
    const cacheKey = viewCacheKey(nextTeam, nextDuelType, nextTransitionType, nextState, nextRange);
    const cachedPayload = payloadCacheRef.current.get(cacheKey);
    if (cachedPayload) {
      applyPayload(cachedPayload, nextTeam, nextDuelType, nextTransitionType, nextState, nextRange);
      return;
    }
    setIsLoading(true);
    try {
      const response = await getAnalysisView("duels-transitions", buildBody(nextTeam, nextDuelType, nextTransitionType, nextState, nextRange));
      const nextPayload = response.payload ?? {};
      payloadCacheRef.current.set(cacheKey, nextPayload);
      applyPayload(nextPayload, nextTeam, nextDuelType, nextTransitionType, nextState, nextRange);
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
    <section className={`card stack${isLoading ? " is-loading-soft" : ""}`}>
      {isLoading && <div className="analysis-loading-bar" aria-label="Loading duels and transitions" />}
      <div className="analysis-section-heading">
        <div>
          <span className="eyebrow">Duels &amp; Transitions</span>
          <h2 style={{ margin: "6px 0 0" }}>{teamFilterLabel(currentTeam)}</h2>
        </div>
      </div>

      <MobileAnalysisControls summary={`${teamFilterLabel(currentTeam)} · ${duelType}`}>
      <div className="analysis-top-controls">
        <div className="analysis-team-strip">
          <span>Team</span>
          <div className="analysis-team-buttons">
            {["__both__", ...teams].map((team) => (
              <button
                key={team}
                type="button"
                className={team === currentTeam ? "button" : "ghost-button"}
                onClick={() => loadView({ team, gameState: "all", timeRange: "all" })}
                disabled={isLoading}
              >
                {teamFilterLabel(team)}
              </button>
            ))}
          </div>
        </div>

        <div className="analysis-filter-strip-grid duels-transitions-filter-strip">
          <div className="analysis-filter-control">
            <span>Duel type</span>
            <div className="segmented-control" aria-label="Duel type">
              {DUEL_TYPES.map((type) => (
                <button
                  key={type}
                  type="button"
                  className={type === duelType ? "is-active" : ""}
                  onClick={() => loadView({ duelType: type })}
                  disabled={isLoading}
                >
                  {type}
                </button>
              ))}
            </div>
          </div>
          <label>
            <span>Game state</span>
          <select
            className="select"
            value={isBothTeams ? "all" : gameState}
            onChange={(event) => loadView({ gameState: event.target.value, timeRange: "all" })}
            disabled={isLoading || isBothTeams}
          >
            {gameStateOptions.map((option) => (
              <option key={String(option.value)} value={String(option.value)}>
                {option.label}
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
              onClick={() => loadView({ timeRange: `${Math.round(draftRange[0])}-${Math.round(draftRange[1])}` })}
              disabled={isLoading}
            >
              Apply
            </button>
          </div>
        </div>
      </div>
      </MobileAnalysisControls>

      <section className="duels-transitions-section-block">
        <div className="analysis-section-toolbar">
          <div className="chart-card-head">
            <h3 className="duels-section-title">Duels</h3>
            <DownloadPngButton
              filename="duels-zone-map"
              title={() => selectedDuelPlayer ? `Duels — ${selectedDuelPlayer}` : "Duels Zone Map"}
              scopeSelector=".duels-transitions-section-block, .card"
              filters={() => [
                teamFilterLabel(currentTeam),
                duelType,
                ...(gameState !== "all" ? [gameStateOptions.find((option) => String(option.value) === gameState)?.label ?? gameState] : []),
                ...(timeRange !== "all" ? [`${timeRange}'`] : []),
              ]}
              titleImages={() => {
                if (!selectedDuelPlayer) return [];
                const row = duelPlayerRows.find((item) => item.player === selectedDuelPlayer);
                const src = getCachedPlayerImage(selectedDuelPlayer, row?.team || undefined);
                return src ? [src] : [];
              }}
              sideTable={() => {
                const duelLine = (rowsIn: SummaryRow[]) => {
                  const won = rowsIn.filter((row) => row.won === true).length;
                  return `${won}/${rowsIn.length} won · ${rowsIn.length ? Math.round((won / rowsIn.length) * 100) : 0}%`;
                };
                const rows: SideTableRow[] = [];
                if (isBothTeams) {
                  teams.forEach((teamName) => {
                    const teamDuels = duels.filter((row) => String(row.team ?? "") === teamName);
                    rows.push({ header: teamName });
                    rows.push({ label: "All duels", value: duelLine(teamDuels) });
                    rows.push({ label: "Ground", value: duelLine(teamDuels.filter((row) => String(row.category ?? "").toLowerCase() === "ground")) });
                    rows.push({ label: "Aerial", value: duelLine(teamDuels.filter((row) => String(row.category ?? "").toLowerCase() === "aerial")) });
                  });
                } else {
                  rows.push(
                    { label: "Duels", value: String(duelTotalsScope.length) },
                    { label: "Won", value: String(scopedDuelsWon) },
                    { label: "Lost", value: String(Math.max(0, duelTotalsScope.length - scopedDuelsWon)) },
                    { label: "Win %", value: duelTotalsScope.length ? `${Math.round((scopedDuelsWon / duelTotalsScope.length) * 100)}%` : "0%" },
                    { label: "Ground", value: duelLine(duelTotalsScope.filter((row) => String(row.category ?? "").toLowerCase() === "ground")) },
                    { label: "Aerial", value: duelLine(duelTotalsScope.filter((row) => String(row.category ?? "").toLowerCase() === "aerial")) },
                  );
                }
                const topDuelers = (isBothTeams ? teams : [currentTeam]).flatMap((teamName) =>
                  (duelPlayerRowsByTeam.get(teamName) ?? []).slice(0, isBothTeams ? 3 : 5)
                );
                if (topDuelers.length) {
                  rows.push({ header: "Top duel players" });
                  topDuelers.forEach((row) => {
                    rows.push({
                      image: getCachedPlayerImage(row.player, row.team || undefined),
                      label: row.player,
                      value: `${row.duels_won}/${row.duels} won`,
                      sub: `${row.duel_win_pct}% win · ${row.ground} ground · ${row.aerial} aerial${isBothTeams ? ` · ${row.team}` : ""}`,
                    });
                  });
                }
                return { title: `${duelTotalsLabel === "Team" ? teamFilterLabel(currentTeam) : duelTotalsLabel} · Duels`, rows, large: !isBothTeams };
              }}
            />
          </div>
          <div className="segmented-control" aria-label="Duel visual mode">
            <button type="button" className={duelVisualMode === "zones" ? "is-active" : ""} onClick={() => setDuelVisualMode("zones")}>
              Zone Map
            </button>
            <button type="button" className={duelVisualMode === "actions" ? "is-active" : ""} onClick={() => setDuelVisualMode("actions")}>
              Actions
            </button>
          </div>
        </div>
        {!isBothTeams && <div className="shot-team-total-strip">
          {[
            [duelTotalsLabel, duelTotalsScope.length],
            ["Won", scopedDuelsWon],
            ["Lost", Math.max(0, duelTotalsScope.length - scopedDuelsWon)],
            ["Win %", duelTotalsScope.length ? `${Math.round((scopedDuelsWon / duelTotalsScope.length) * 100)}%` : "0%"],
          ].map(([label, value]) => (
            <div key={label} className="shot-team-total">
              <span>{label}</span>
              <strong>{value}</strong>
            </div>
          ))}
        </div>}
        <DuelsTransitionsPlotly
          duels={duels}
          transitions={[]}
          team={currentTeam}
          teamColor={teamColor}
          teams={teams}
          teamColors={teamColors}
          duelType={duelType}
          transitionType={transitionType}
          mode="duels"
          duelVisualMode={duelVisualMode}
          onSelectedPlayerChange={setSelectedDuelPlayer}
          selectedDuelProfile={selectedDuelProfile}
        />
        {!isBothTeams && (
          <section className="defensive-profile-panel duel-profile-panel">
            <div>
              <span className="eyebrow">Duel Profile</span>
              <p>{selectedDuelProfile ? `${selectedDuelProfile}: ${duelProfiles.profiles.find((profile) => profile.name === selectedDuelProfile)?.description ?? ""}` : duelProfiles.insight}</p>
            </div>
            <div className="defensive-profile-cards">
              {duelProfiles.profiles.map((profile) => {
                const isExposureProfile = profile.name === "Risk Zone Losses";
                const isStrong = isExposureProfile ? profile.score > 0 && profile.score <= 20 : profile.score >= 55;
                return (
                  <button
                    key={profile.name}
                    type="button"
                    className={`${isStrong ? "is-strong" : ""}${selectedDuelProfile === profile.name ? " is-selected" : ""}`}
                    onClick={() => setSelectedDuelProfile((current) => current === profile.name ? "" : profile.name)}
                  >
                    <div>
                      <strong>{profile.name}</strong>
                      <span>{profile.score}</span>
                    </div>
                    <meter min={0} max={100} value={profile.score} />
                    <small>{profile.description}</small>
                    <small>{profile.detail}</small>
                  </button>
                );
              })}
            </div>
            {selectedDuelProfile && <button type="button" className="ghost-button" onClick={() => setSelectedDuelProfile("")}>Clear profile highlight</button>}
          </section>
        )}
        {hasBaselines && normalizeDuelType(duelType) === "Total" ? (
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
        <div className={`duels-player-table-grid${isBothTeams ? "" : " is-single-team"}`}>
          {(isBothTeams ? teams : [currentTeam]).map((teamName) => {
            const teamRows = duelPlayerRowsByTeam.get(teamName) ?? [];
            const rows = sortDuelRows(isBothTeams ? teamRows.slice(0, 5) : teamRows);
            const showChips = showSeasonDeltas && normalizeDuelType(duelType) === "Total";
            return (
              <div key={`duel-table-${teamName}`} className="shot-summary-table-wrap">
                <div className="duels-table-title">
                  <span>{isBothTeams ? "Top 5 Duel Players" : "All Duel Players"}</span>
                  <strong>{teamName}</strong>
                </div>
                <table className="table shot-summary-table">
                  <thead>
                    <tr>
                      <th><button type="button" className="table-sort-button" onClick={() => toggleDuelSort("player")}>Player{sortIndicator("player")}</button></th>
                      <th><button type="button" className="table-sort-button" onClick={() => toggleDuelSort("duels")}>Duels{sortIndicator("duels")}</button></th>
                      <th><button type="button" className="table-sort-button" onClick={() => toggleDuelSort("duels_won")}>Won{sortIndicator("duels_won")}</button></th>
                      <th><button type="button" className="table-sort-button" onClick={() => toggleDuelSort("duels_lost")}>Lost{sortIndicator("duels_lost")}</button></th>
                      <th><button type="button" className="table-sort-button" onClick={() => toggleDuelSort("duel_win_pct")}>Win %{sortIndicator("duel_win_pct")}</button></th>
                      <th><button type="button" className="table-sort-button" onClick={() => toggleDuelSort("ground")}>Ground{sortIndicator("ground")}</button></th>
                      <th><button type="button" className="table-sort-button" onClick={() => toggleDuelSort("aerial")}>Aerial{sortIndicator("aerial")}</button></th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => {
                      const baseline = playerBaselines?.[row.player];
                      const chip = (tableKey: string) =>
                        showChips && baseline && !baseline.lowSample ? (
                          <SeasonDeltaChip metric={metricByKey(baseline, DUEL_BASELINE_KEYS[tableKey])} per90 />
                        ) : null;
                      return (
                        <tr key={playerKey(row)}>
                          <td>
                            <span className="shot-player-cell">
                              <PlayerAvatar name={row.player} team={row.team || undefined} size={24} />
                              <strong>{row.player}</strong>
                            </span>
                          </td>
                          <td>{row.duels}{chip("duels")}</td>
                          <td>{row.duels_won}{chip("duels_won")}</td>
                          <td>{row.duels_lost}{chip("duels_lost")}</td>
                          <td>{row.duel_win_pct}%{chip("duel_win_pct")}</td>
                          <td>{row.ground}{chip("ground")}</td>
                          <td>{row.aerial}{chip("aerial")}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            );
          })}
        </div>
      </section>

      <section className="duels-transitions-section-block">
        <div className="analysis-section-toolbar">
          <div className="chart-card-head">
            <h3 className="duels-section-title">Transitions</h3>
            {!isBothTeams && (
              <DownloadPngButton
                filename="transitions-zone-map"
                title={`Transitions — ${transitionType}`}
                scopeSelector=".duels-transitions-section-block, .card"
                filters={() => [
                  teamFilterLabel(currentTeam),
                  `${transitionType} transitions`,
                  ...(gameState !== "all" ? [gameStateOptions.find((option) => String(option.value) === gameState)?.label ?? gameState] : []),
                  ...(timeRange !== "all" ? [`${timeRange}'`] : []),
                ]}
                sideTable={() => {
                  const hitLabel = transitionType === "Offensive" ? "Led to attack" : "Conceded attack";
                  const rows: SideTableRow[] = [
                    { label: "Transitions", value: String(transitions.length) },
                    { label: hitLabel, value: String(transitionHits) },
                    { label: "No attack", value: String(Math.max(0, transitions.length - transitionHits)) },
                    { label: "Hit %", value: transitions.length ? `${Math.round((transitionHits / transitions.length) * 100)}%` : "0%" },
                  ];
                  const topPlayers = sortTransitionRows(selectedTeamTransitionRows).slice(0, 5);
                  if (topPlayers.length) {
                    rows.push({ header: "Top transition players" });
                    topPlayers.forEach((row) => {
                      rows.push({
                        image: getCachedPlayerImage(row.player, row.team || undefined),
                        label: row.player,
                        value: `${row.transitions_to_attack}/${row.transitions} hit`,
                        sub: `${row.transition_hit_pct}% hit · Def ${row.defensive_third} · Mid ${row.middle_third} · Att ${row.attacking_third}`,
                      });
                    });
                  }
                  return { title: `${currentTeam} · ${transitionType} Transitions`, rows, large: true };
                }}
              />
            )}
          </div>
          {!isBothTeams && (
            <div className="segmented-control" aria-label="Transition visual mode">
              <button type="button" className={transitionVisualMode === "zones" ? "is-active" : ""} onClick={() => setTransitionVisualMode("zones")}>
                Zone Map
              </button>
              <button type="button" className={transitionVisualMode === "actions" ? "is-active" : ""} onClick={() => setTransitionVisualMode("actions")}>
                Actions
              </button>
            </div>
          )}
        </div>
        {isBothTeams ? (
          <div className="duels-transitions-empty-note">
            <span className="eyebrow">Team Required</span>
            <p>Transitions are possession-directional, so select one team above to see where their {transitionType.toLowerCase()} transitions start, carry forward, and lead to attacks.</p>
          </div>
        ) : (
          <>
            <div className="shot-team-total-strip">
              {[
                ["Transitions", transitions.length],
                [transitionType === "Offensive" ? "Led To Attack" : "Conceded Attack", transitionHits],
                ["No Attack", Math.max(0, transitions.length - transitionHits)],
                ["Hit %", transitions.length ? `${Math.round((transitionHits / transitions.length) * 100)}%` : "0%"],
              ].map(([label, value]) => (
                <div key={label} className="shot-team-total">
                  <span>{label}</span>
                  <strong>{value}</strong>
                </div>
              ))}
            </div>
            <DuelsTransitionsPlotly
              duels={[]}
              transitions={transitions}
              team={currentTeam}
              teamColor={teamColor}
              teams={teams}
              teamColors={teamColors}
              duelType={duelType}
              transitionType={transitionType}
              mode="transitions"
              transitionVisualMode={transitionVisualMode}
              onTransitionTypeChange={(nextType) => loadView({ transitionType: nextType })}
            />
            <div className="shot-summary-table-wrap">
              <div className="duels-table-title">
                <span>Transition Players</span>
                <strong>{currentTeam}</strong>
              </div>
              <table className="table shot-summary-table">
                <thead>
                  <tr>
                    <th><button type="button" className="table-sort-button" onClick={() => toggleTransitionSort("player")}>Player{transitionSortIndicator("player")}</button></th>
                    <th><button type="button" className="table-sort-button" onClick={() => toggleTransitionSort("transitions")}>Transitions{transitionSortIndicator("transitions")}</button></th>
                    <th><button type="button" className="table-sort-button" onClick={() => toggleTransitionSort("transitions_to_attack")}>{transitionType === "Offensive" ? "Led To Attack" : "Conceded"}{transitionSortIndicator("transitions_to_attack")}</button></th>
                    <th><button type="button" className="table-sort-button" onClick={() => toggleTransitionSort("transitions_stalled")}>No Attack{transitionSortIndicator("transitions_stalled")}</button></th>
                    <th><button type="button" className="table-sort-button" onClick={() => toggleTransitionSort("transition_hit_pct")}>Hit %{transitionSortIndicator("transition_hit_pct")}</button></th>
                    <th><button type="button" className="table-sort-button" onClick={() => toggleTransitionSort("defensive_third")}>Def 3rd{transitionSortIndicator("defensive_third")}</button></th>
                    <th><button type="button" className="table-sort-button" onClick={() => toggleTransitionSort("middle_third")}>Mid 3rd{transitionSortIndicator("middle_third")}</button></th>
                    <th><button type="button" className="table-sort-button" onClick={() => toggleTransitionSort("attacking_third")}>Att 3rd{transitionSortIndicator("attacking_third")}</button></th>
                  </tr>
                </thead>
                <tbody>
                  {sortTransitionRows(selectedTeamTransitionRows).map((row) => (
                    <tr key={playerKey(row)}>
                      <td>
                        <span className="shot-player-cell">
                          <PlayerAvatar name={row.player} team={row.team || undefined} size={24} />
                          <strong>{row.player}</strong>
                        </span>
                      </td>
                      <td>{row.transitions}</td>
                      <td>{row.transitions_to_attack}</td>
                      <td>{row.transitions_stalled}</td>
                      <td>{row.transition_hit_pct}%</td>
                      <td>{row.defensive_third}</td>
                      <td>{row.middle_third}</td>
                      <td>{row.attacking_third}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>
    </section>
  );
}
