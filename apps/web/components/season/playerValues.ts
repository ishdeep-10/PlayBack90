import type { PlayerSlices, SeasonPlayer, SeasonPlayerMetrics } from "../../lib/api";
import { selectedCells, selectedMinuteCells, sumCells, type SliceSelection } from "./SliceFilters";

export type ValueMode = "p90" | "padj" | "total";

export const VALUE_MODES: { id: ValueMode; label: string }[] = [
  { id: "p90", label: "Per 90 minutes" },
  { id: "padj", label: "Per 90, possession-adjusted" },
  { id: "total", label: "Season total" },
];

export const modeSuffix = (mode: ValueMode) => (mode === "p90" ? " per 90" : mode === "padj" ? " per 90 (poss. adj.)" : "");

/** One player's value for a metric. Possession adjustment scales per-90 values to a 50% possession team. */
export function playerValue(p: SeasonPlayer, metric: string, mode: ValueMode, padj?: SeasonPlayerMetrics["padj"]) {
  const raw = p[mode === "total" ? metric : `${metric}_p90`];
  const v = typeof raw === "number" ? raw : 0; // the export leaves zeros out
  return mode === "padj" ? v * (padj?.[p.team] ?? 1) : v;
}

export const GROUP_COLORS: Record<string, string> = {
  Goalkeeper: "#f59e0b",
  Defender: "#38bdf8",
  Midfielder: "#a3e635",
  Forward: "#f472b6",
  "Substitute only": "#94a3b8",
};
export const GROUPS = ["Goalkeeper", "Defender", "Midfielder", "Forward"] as const;
export const SUB_ONLY = "Substitute only";
export const groupOf = (p: SeasonPlayer) => p.group ?? SUB_ONLY;

type PlayerSlice = PlayerSlices["players"][number];

/** Minutes a player spent in the selected game states and match periods. */
export const sliceMinutes = (s: PlayerSlice | undefined, sel: SliceSelection) => sumCells(s?.m, selectedMinuteCells(sel));

/** A player's value re-added from the game-state / time / play-phase slices (counts), per 90 over the minutes in the selection. */
export function playerSliceValue(s: PlayerSlice | undefined, metric: string, mode: ValueMode, sel: SliceSelection, padjFactor: number) {
  const total = sumCells(s?.v[metric], selectedCells(sel));
  if (mode === "total") return total;
  const mins = sliceMinutes(s, sel);
  const per90 = mins > 0 ? (total / mins) * 90 : 0;
  return mode === "padj" ? per90 * padjFactor : per90;
}
