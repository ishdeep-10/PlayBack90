"use client";

import { Plot } from "../lib/plotly";

import { type CSSProperties, useEffect, useMemo, useState } from "react";
import { num, readThemeColors } from "../lib/theme";
import { horizontalPitchShapes } from "../lib/pitch";


type Row = Record<string, string | number | boolean | null | undefined>;
type PlotlyClickEvent = {
  points?: Array<{
    customdata?: unknown;
    pointIndex?: number;
    pointNumber?: number;
  }>;
};

type Props = {
  duels: Row[];
  transitions: Row[];
  team: string;
  teamColor: string;
  teams: string[];
  teamColors: Record<string, string>;
  duelType: string;
  transitionType: string;
  mode?: "all" | "duels" | "transitions";
  duelVisualMode?: "zones" | "actions";
  transitionVisualMode?: "zones" | "actions";
  onSelectedPlayerChange?: (player: string) => void;
  onTransitionTypeChange?: (transitionType: string) => void;
  selectedDuelProfile?: string;
};

const plotConfig = { responsive: true, displayModeBar: false };

function pitchY(value: unknown) {
  return 68 - Math.max(0, Math.min(68, num(value)));
}

function colorWithAlpha(color: string, alpha: number) {
  const trimmed = color.trim();
  if (trimmed.startsWith("#")) {
    const hex = trimmed.slice(1);
    const fullHex = hex.length === 3 ? hex.split("").map((char) => char + char).join("") : hex;
    const red = Number.parseInt(fullHex.slice(0, 2), 16);
    const green = Number.parseInt(fullHex.slice(2, 4), 16);
    const blue = Number.parseInt(fullHex.slice(4, 6), 16);
    return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
  }
  return color;
}

function pitchShapes(lineColor: string) {
  return horizontalPitchShapes(lineColor, {
    outerWidth: 1.3,
    midlineWidth: 1.3,
    circleWidth: 1.3,
    boxWidth: 1.3,
    transparentFill: true,
  });
}

function baseLayout(themeColors: ReturnType<typeof readThemeColors>, title = "") {
  return {
    ...(title ? { title: { text: title, x: 0, xanchor: "left", font: { color: themeColors.text, size: 14, family: themeColors.font } } } : {}),
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: themeColors.surface,
    font: { color: themeColors.text, family: themeColors.font },
    margin: { l: 8, r: 8, t: title ? 38 : 8, b: 8 },
    height: 420,
    xaxis: { range: [0, 105], visible: false, fixedrange: true },
    yaxis: { range: [68, 0], visible: false, fixedrange: true, scaleanchor: "x", scaleratio: 1 },
    shapes: pitchShapes(themeColors.muted),
    showlegend: true,
    legend: {
      orientation: "h",
      x: 0,
      y: -0.04,
      font: { color: themeColors.text, size: 11, family: themeColors.font },
      bgcolor: "rgba(0,0,0,0)",
    },
    hoverlabel: {
      bgcolor: themeColors.mode === "dark" ? "#0f172a" : "#ffffff",
      bordercolor: themeColors.muted,
      font: { color: themeColors.text, family: themeColors.font },
    },
  };
}

function combinedLayout(
  themeColors: ReturnType<typeof readThemeColors>,
  title: string,
  shapes: Array<Record<string, unknown>>,
) {
  return {
    ...baseLayout(themeColors, title),
    height: 640,
    margin: { l: 10, r: 10, t: title ? 42 : 10, b: 10 },
    shapes,
    showlegend: false,
  };
}

function duelActionLayout(themeColors: ReturnType<typeof readThemeColors>) {
  return {
    ...baseLayout(themeColors, ""),
    height: 640,
    margin: { l: 10, r: 10, t: 10, b: 10 },
    showlegend: true,
  };
}

function transitionActionLayout(themeColors: ReturnType<typeof readThemeColors>) {
  return {
    ...baseLayout(themeColors, ""),
    height: 640,
    margin: { l: 10, r: 10, t: 10, b: 10 },
    showlegend: true,
  };
}

function duelHover(row: Row) {
  const second = num(row.second);
  return [
    `<b>${String(row.player ?? "Unknown")}</b>`,
    `${String(row.category ?? "Duel")} | ${row.won ? "Won" : "Lost"}`,
    String(row.classification ?? ""),
    `${num(row.minute)}'${second ? ` ${second}s` : ""} | ${String(row.game_state_label ?? "Level")} (${String(row.score_before ?? "0-0")})`,
    String(row.zone ?? ""),
    row.previous_event ? `Before: ${String(row.previous_event_label ?? row.previous_event)} by ${String(row.previous_player ?? "Unknown")}` : "",
  ].filter(Boolean).join("<br>");
}

function transitionHover(row: Row) {
  const second = num(row.second);
  const isDefensive = String(row.transition_type ?? "") === "Defensive";
  return [
    `<b>${String(row.player ?? "Unknown")}</b>`,
    `${String(row.transition_type ?? "Transition")} | ${row.led_to_attack ? (isDefensive ? "Conceded attack" : "Led to attack") : (isDefensive ? "No conceded attack" : "No attack")}`,
    `${num(row.minute)}'${second ? ` ${second}s` : ""} | ${String(row.game_state_label ?? "Level")} (${String(row.score_before ?? "0-0")})`,
    String(row.third ?? ""),
    row.led_to_attack ? `End product: ${String(row.end_product ?? "Attack developed")}` : String(row.end_product ?? "No attacking follow-up"),
  ].filter(Boolean).join("<br>");
}

function zoneIndex(row: Row) {
  const binsX = 6;
  const binsY = 5;
  const x = Math.max(0, Math.min(104.999, num(row.x)));
  const y = Math.max(0, Math.min(67.999, pitchY(row.y)));
  return {
    xBin: Math.floor(x / (105 / binsX)),
    yBin: Math.floor(y / (68 / binsY)),
  };
}

function zoneKey(row: Row) {
  const { xBin, yBin } = zoneIndex(row);
  return `${xBin}-${yBin}`;
}

function duelId(row: Row, index: number) {
  return String(row.id ?? `${row.player ?? "duel"}-${row.minute ?? 0}-${row.second ?? 0}-${index}`);
}

function duelTime(row: Row) {
  const second = num(row.second);
  return `${num(row.minute)}'${second ? ` ${second}s` : ""}`;
}

function playerOptions(rows: Row[]) {
  return [...new Set(rows.map((row) => String(row.player ?? "").trim()).filter(Boolean))].sort((a, b) => a.localeCompare(b));
}

function transitionThirdOptions(rows: Row[]) {
  const preferred = ["Defensive Third", "Middle Third", "Attacking Third"];
  const available = new Set(rows.map((row) => String(row.third ?? "").trim()).filter(Boolean));
  return preferred.filter((third) => available.has(third));
}

function transitionZoneKey(row: Row) {
  const x = Math.max(0, Math.min(104.999, num(row.x)));
  const y = Math.max(0, Math.min(67.999, pitchY(row.y)));
  return `${Math.floor(x / 35)}-${Math.floor(y / (68 / 3))}`;
}

function duelContextDescription(context: string) {
  if (context === "led_to_attack") {
    return "Won duels where the same team creates a shot, wins a corner, enters the opponent box with a pass/carry/take-on, or otherwise progresses into a clear attacking action within the next 15 seconds.";
  }
  if (context === "retained") {
    return "Duels where the next valid action after the duel is a successful action by the same team, but it does not meet the attack-follow-up rule.";
  }
  if (context === "turnover") {
    return "Duels where the next valid action after the duel belongs to the opponent, or the follow-up action shows possession being lost.";
  }
  if (context === "unknown") {
    return "Duels where there is no valid follow-up event close enough after the duel to classify the outcome confidently.";
  }
  return "No context filter is active. The map includes led-to-attack, retained, turnover and no-follow-up duels together.";
}

function duelMatchesProfile(row: Row, profile: string) {
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

function DuelChainSummary({ row, prefix }: { row: Row; prefix: "previous" | "next" }) {
  const category = String(row[`${prefix}_duel_category`] ?? "Duel");
  const winner = String(row[`${prefix}_duel_winner`] ?? "").trim();
  const loser = String(row[`${prefix}_duel_loser`] ?? "").trim();
  const player = String(row[`${prefix}_duel_player`] ?? "Unknown").trim();

  if (winner && loser) {
    return (
      <>
        {category} duel between <span className="duel-winner-name">{winner}</span> and {loser}
      </>
    );
  }

  if (winner) {
    return (
      <>
        {category} duel by <span className="duel-winner-name">{winner}</span>
      </>
    );
  }

  return <>{category} duel by {player}</>;
}

function DuelContextAction({ row, prefix }: { row: Row; prefix: "previous" | "next" }) {
  const label = String(row[`${prefix}_event_label`] ?? row[`${prefix}_event`] ?? "").trim();
  const player = String(row[`${prefix}_player`] ?? "").trim();
  const team = String(row[`${prefix}_team`] ?? "").trim();
  const selectedTeam = String(row.team ?? "").trim();
  const successful = row[`${prefix}_successful`];
  const statusClass = successful === true ? "is-successful" : successful === false ? "is-unsuccessful" : "";

  return (
    <>
      <span className={`duel-context-action ${statusClass}`}>{label}</span>
      {player ? ` by ${player}` : ""}
      {team && team !== selectedTeam ? ` (${team})` : ""}
    </>
  );
}

function DuelAttackDirectionRow({ team, teams, teamColors, teamColor }: { team: string; teams: string[]; teamColors: Record<string, string>; teamColor: string }) {
  const visibleTeams = team === "__both__" ? teams : [team];
  return (
    <div className="duels-attack-direction-row" aria-label="Team attack directions">
      <span className="duels-attack-direction-label">Attack direction</span>
      {visibleTeams.map((teamName, index) => (
        <div key={teamName} className={`duels-attack-direction-cue${team === "__both__" && index === 1 ? " is-reversed" : ""}`}>
          <strong>{teamName}</strong>
          <i style={{ "--team-color": teamColors[teamName] ?? teamColor } as CSSProperties} aria-hidden="true" />
        </div>
      ))}
    </div>
  );
}

export function DuelsTransitionsPlotly({
  duels,
  transitions,
  team,
  teamColor,
  teams,
  teamColors,
  duelType,
  transitionType,
  mode = "all",
  duelVisualMode = "zones",
  transitionVisualMode = "zones",
  onSelectedPlayerChange,
  onTransitionTypeChange,
  selectedDuelProfile = "",
}: Props) {
  const [themeColors, setThemeColors] = useState(readThemeColors);
  const [selectedZone, setSelectedZone] = useState("");
  const [selectedPlayer, setSelectedPlayer] = useState("");
  const [selectedDuelId, setSelectedDuelId] = useState("");
  const [selectedContext, setSelectedContext] = useState("");
  const [selectedTransitionThird, setSelectedTransitionThird] = useState("");
  const [selectedTransitionZone, setSelectedTransitionZone] = useState("");
  const [selectedTransitionId, setSelectedTransitionId] = useState("");
  const showCombinedZoneGlossary = team === "__both__" && duelVisualMode === "zones";
  const isDefensiveTransition = transitionType === "Defensive";
  const transitionAttackLabel = isDefensiveTransition ? "Conceded attack" : "Led to attack";
  const transitionNoAttackLabel = isDefensiveTransition ? "No conceded attack" : "No attack";

  useEffect(() => {
    const updateColors = () => setThemeColors(readThemeColors());
    updateColors();
    const observer = new MutationObserver(updateColors);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "data-theme"] });
    return () => observer.disconnect();
  }, []);

  function rowTeamColor(row: Row) {
    const rowTeam = String(row.team ?? "");
    return teamColors[rowTeam] ?? teamColor;
  }

  const duelPlayers = useMemo(() => playerOptions(duels), [duels]);
  const transitionThirds = useMemo(() => transitionThirdOptions(transitions), [transitions]);
  const indexedTransitions = useMemo(() => transitions.map((row, index) => ({ row, id: String(row.id ?? `${row.player ?? "transition"}-${row.minute ?? 0}-${row.second ?? 0}-${index}`) })), [transitions]);
  const indexedDuels = useMemo(() => duels.map((row, index) => ({ row, id: duelId(row, index) })), [duels]);
  const focusedDuels = useMemo(() => {
    return indexedDuels.filter(({ row, id }) => {
      if (selectedZone && zoneKey(row) !== selectedZone) return false;
      if (selectedPlayer && String(row.player ?? "") !== selectedPlayer) return false;
      if (selectedContext && String(row.duel_context ?? "") !== selectedContext) return false;
      if (selectedDuelProfile && !duelMatchesProfile(row, selectedDuelProfile)) return false;
      return Boolean(id);
    });
  }, [indexedDuels, selectedContext, selectedDuelProfile, selectedPlayer, selectedZone]);
  const selectedDuel = useMemo(() => {
    if (!selectedDuelId) return null;
    return indexedDuels.find(({ id }) => id === selectedDuelId)?.row ?? null;
  }, [indexedDuels, selectedDuelId]);

  useEffect(() => {
    setSelectedZone("");
    setSelectedPlayer("");
    setSelectedDuelId("");
    setSelectedContext("");
    setSelectedTransitionThird("");
    setSelectedTransitionZone("");
    setSelectedTransitionId("");
  }, [duelType, team]);

  useEffect(() => {
    onSelectedPlayerChange?.(selectedPlayer);
  }, [onSelectedPlayerChange, selectedPlayer]);

  const combinedDuelMap = useMemo(() => {
    const binsX = 6;
    const binsY = 5;
    const binW = 105 / binsX;
    const binH = 68 / binsY;
    const teamA = teams[0] ?? "Team 1";
    const teamB = teams[1] ?? "Team 2";
    const isBoth = team === "__both__";
    const wonDuels = duels.filter((row) => row.won === true);
    const counts = new Map<string, Record<string, number>>();
    const outcomeCounts = new Map<string, { won: number; lost: number }>();
    wonDuels.forEach((row) => {
      const { xBin, yBin } = zoneIndex(row);
      const key = `${xBin}-${yBin}`;
      const teamName = String(row.team ?? "");
      const existing = counts.get(key) ?? {};
      existing[teamName] = (existing[teamName] ?? 0) + 1;
      counts.set(key, existing);
    });
    duels.forEach((row) => {
      if (isBoth || String(row.team ?? "") !== team) return;
      const key = zoneKey(row);
      const existing = outcomeCounts.get(key) ?? { won: 0, lost: 0 };
      if (row.won === true) existing.won += 1;
      else existing.lost += 1;
      outcomeCounts.set(key, existing);
    });
    const maxOutcomeCount = Math.max(1, ...[...outcomeCounts.values()].map((entry) => entry.won + entry.lost));
    const shapes: Array<Record<string, unknown>> = [...pitchShapes(themeColors.muted)];
    const annotations: Array<Record<string, unknown>> = [];
    const hoverX: number[] = [];
    const hoverY: number[] = [];
    const hover: Array<{ kind: "zone"; key: string; label: string }> = [];

    for (let xBin = 0; xBin < binsX; xBin += 1) {
      for (let yBin = 0; yBin < binsY; yBin += 1) {
        const x0 = xBin * binW;
        const y0 = yBin * binH;
        const key = `${xBin}-${yBin}`;
        const zoneCounts = counts.get(key) ?? {};
        const teamACount = zoneCounts[teamA] ?? 0;
        const teamBCount = zoneCounts[teamB] ?? 0;
        const total = teamACount + teamBCount;
        const isSelectedZone = selectedZone === key;
        const isDimmedZone = Boolean(selectedZone && !isSelectedZone);
        const shouldDimLabel = Boolean(selectedZone && (isDimmedZone || isSelectedZone));
        const zoneFillScale = isDimmedZone ? 0.22 : 1;
        const labelTextColor = shouldDimLabel ? colorWithAlpha(themeColors.text, isSelectedZone ? 0.22 : 0.34) : themeColors.text;
        const labelBgAlpha = shouldDimLabel ? (isSelectedZone ? 0.08 : 0.16) : 0.72;
        if (isBoth && total > 0) {
          const split = teamACount / total;
          shapes.push({
            type: "rect",
            x0,
            y0,
            x1: x0 + binW * split,
            y1: y0 + binH,
            line: { color: "rgba(0,0,0,0)", width: 0 },
            fillcolor: colorWithAlpha(teamColors[teamA] ?? "#22c55e", 0.64 * zoneFillScale),
            layer: "below",
          });
          shapes.push({
            type: "rect",
            x0: x0 + binW * split,
            y0,
            x1: x0 + binW,
            y1: y0 + binH,
            line: { color: "rgba(0,0,0,0)", width: 0 },
            fillcolor: colorWithAlpha(teamColors[teamB] ?? "#38bdf8", 0.64 * zoneFillScale),
            layer: "below",
          });
          annotations.push({
            x: x0 + binW / 2,
            y: y0 + binH / 2,
            text: `${teamACount}/${teamBCount}`,
            showarrow: false,
            font: { color: labelTextColor, size: 14, family: themeColors.font },
            bgcolor: colorWithAlpha(themeColors.mode === "dark" ? "#020617" : "#ffffff", labelBgAlpha),
            bordercolor: colorWithAlpha(themeColors.text, isDimmedZone ? 0.06 : 0.18),
            borderpad: 3,
          });
          hover.push({ kind: "zone", key, label: `${teamA}: ${teamACount}<br>${teamB}: ${teamBCount}<br>Won duels in zone` });
        } else if (!isBoth) {
          const outcome = outcomeCounts.get(key) ?? { won: 0, lost: 0 };
          const selectedCount = outcome.won + outcome.lost;
          if (selectedCount > 0) {
            const wonSplit = outcome.won / selectedCount;
            const alpha = 0.18 + (selectedCount / maxOutcomeCount) * 0.52;
            shapes.push({
              type: "rect",
              x0,
              y0,
              x1: x0 + binW * wonSplit,
              y1: y0 + binH,
              line: { color: "rgba(0,0,0,0)", width: 0 },
              fillcolor: colorWithAlpha(teamColor, alpha * zoneFillScale),
              layer: "below",
            });
            if (outcome.lost > 0) {
              shapes.push({
                type: "rect",
                x0: x0 + binW * wonSplit,
                y0,
                x1: x0 + binW,
                y1: y0 + binH,
                line: { color: "rgba(0,0,0,0)", width: 0 },
                fillcolor: colorWithAlpha(themeColors.mode === "dark" ? "#ef4444" : "#b91c1c", Math.max(0.18, alpha * 0.86) * zoneFillScale),
                layer: "below",
              });
            }
            annotations.push({
              x: x0 + binW / 2,
              y: y0 + binH / 2,
              text: `${outcome.won}/${outcome.lost}`,
              showarrow: false,
              font: { color: labelTextColor, size: 14, family: themeColors.font },
              bgcolor: colorWithAlpha(themeColors.mode === "dark" ? "#020617" : "#ffffff", labelBgAlpha),
              bordercolor: colorWithAlpha(themeColors.text, isDimmedZone ? 0.06 : 0.18),
              borderpad: 3,
            });
            hover.push({ kind: "zone", key, label: `${team}<br>Won: ${outcome.won}<br>Lost: ${outcome.lost}<br>Total duels in zone: ${selectedCount}` });
          } else {
            hover.push({ kind: "zone", key, label: "No duels in zone" });
          }
        } else {
          hover.push({ kind: "zone", key, label: "No won duels in zone" });
        }
        hoverX.push(x0 + binW / 2);
        hoverY.push(y0 + binH / 2);
        shapes.push({
          type: "rect",
          x0,
          y0,
          x1: x0 + binW,
          y1: y0 + binH,
          line: {
            color: isSelectedZone
              ? (themeColors.mode === "dark" ? "#f8fafc" : "#0f172a")
              : colorWithAlpha(themeColors.text, isDimmedZone ? 0.08 : 0.2),
            width: isSelectedZone ? 3 : 1,
            dash: isSelectedZone ? "solid" : "dot",
          },
          fillcolor: "rgba(0,0,0,0)",
        });
      }
    }

    return {
      data: [{
        type: "scatter",
        mode: "markers",
        x: hoverX,
        y: hoverY,
        marker: { size: 88, color: "rgba(0,0,0,0.01)", symbol: "square" },
        customdata: hover,
        hovertemplate: "%{customdata.label}<extra></extra>",
      }],
      layout: {
        ...combinedLayout(themeColors, "", shapes),
        annotations,
      },
    };
  }, [duels, team, teamColor, teamColors, teams, themeColors, selectedZone]);

  const duelData = useMemo(() => {
    const won = focusedDuels.filter(({ row }) => row.won === true);
    const lost = focusedDuels.filter(({ row }) => row.won !== true);
    const showLostDuels = team !== "__both__";
    const markerOpacity = (id: string) => selectedDuelId && selectedDuelId !== id ? 0.28 : 0.92;
    const selectedPreviousDuelTrace = selectedDuel && selectedDuel.previous_duel === true
      ? [{
          type: "scatter",
          mode: "lines+markers",
          name: "Previous duel",
          x: [num(selectedDuel.previous_duel_x), num(selectedDuel.x)],
          y: [pitchY(selectedDuel.previous_duel_y), pitchY(selectedDuel.y)],
          hovertemplate: `Previous duel: ${String(selectedDuel.previous_duel_player ?? "Player")}<extra></extra>`,
          line: { color: colorWithAlpha(themeColors.text, 0.78), width: 2.2, dash: "dashdot" },
          marker: { color: themeColors.text, size: 8, symbol: "square-open" },
        }]
      : [];
    const selectedNextDuelTrace = selectedDuel && selectedDuel.next_duel === true
      ? [{
          type: "scatter",
          mode: "lines+markers",
          name: "Next duel",
          x: [num(selectedDuel.x), num(selectedDuel.next_duel_x)],
          y: [pitchY(selectedDuel.y), pitchY(selectedDuel.next_duel_y)],
          hovertemplate: `Next duel: ${String(selectedDuel.next_duel_player ?? "Player")}<extra></extra>`,
          line: { color: colorWithAlpha(rowTeamColor(selectedDuel), 0.9), width: 2.4, dash: "dashdot" },
          marker: { color: rowTeamColor(selectedDuel), size: 8, symbol: "square-open" },
        }]
      : [];
    const selectedPreviousTrace = selectedDuel && selectedDuel.previous_event && selectedDuel.previous_can_plot === true
      ? [{
          type: "scatter",
          mode: "lines+markers",
          name: "Previous action",
          x: [
            num(selectedDuel.previous_x),
            num(selectedDuel.previous_end_x),
          ],
          y: [
            pitchY(selectedDuel.previous_y),
            pitchY(selectedDuel.previous_end_y),
          ],
          hovertemplate: `${String(selectedDuel.previous_event_label ?? "Previous action")}<extra></extra>`,
          line: { color: colorWithAlpha(themeColors.text, 0.72), width: 2, dash: "dot" },
          marker: { color: themeColors.text, size: 7, symbol: "circle-open" },
        }]
      : [];
    const selectedNextTrace = selectedDuel && selectedDuel.next_event && selectedDuel.next_can_plot === true
      ? [{
          type: "scatter",
          mode: "lines+markers",
          name: "After duel",
          x: [
            num(selectedDuel.next_x),
            num(selectedDuel.next_end_x),
          ],
          y: [
            pitchY(selectedDuel.next_y),
            pitchY(selectedDuel.next_end_y),
          ],
          hovertemplate: `${String(selectedDuel.next_event_label ?? "After duel")}<extra></extra>`,
          line: { color: colorWithAlpha(rowTeamColor(selectedDuel), 0.86), width: 2.4, dash: "dash" },
          marker: { color: rowTeamColor(selectedDuel), size: 8, symbol: "diamond-open" },
        }]
      : [];
    const traces: Array<Record<string, unknown>> = [
      ...selectedPreviousTrace,
      ...selectedPreviousDuelTrace,
      ...selectedNextTrace,
      ...selectedNextDuelTrace,
      {
        type: "scatter",
        mode: "markers",
        name: "Won",
        x: won.map(({ row }) => num(row.x)),
        y: won.map(({ row }) => pitchY(row.y)),
        text: won.map(({ row }) => duelHover(row)),
        customdata: won.map(({ id }) => ({ kind: "duel", id })),
        hovertemplate: "%{text}<extra></extra>",
        marker: {
          color: won.map(({ row }) => rowTeamColor(row)),
          size: won.map(({ id }) => selectedDuelId === id ? 17 : 12),
          line: { color: themeColors.mode === "dark" ? "#f8fafc" : "#0f172a", width: 1.4 },
          opacity: won.map(({ id }) => markerOpacity(id)),
          symbol: "circle",
        },
      },
    ];
    if (showLostDuels) {
      traces.push({
        type: "scatter",
        mode: "markers",
        name: "Lost",
        x: lost.map(({ row }) => num(row.x)),
        y: lost.map(({ row }) => pitchY(row.y)),
        text: lost.map(({ row }) => duelHover(row)),
        customdata: lost.map(({ id }) => ({ kind: "duel", id })),
        hovertemplate: "%{text}<extra></extra>",
        marker: {
          color: lost.map(({ row }) => colorWithAlpha(rowTeamColor(row), themeColors.mode === "dark" ? 0.28 : 0.38)),
          size: lost.map(({ id }) => selectedDuelId === id ? 15 : 10),
          line: { color: themeColors.mode === "dark" ? "#f87171" : "#b91c1c", width: 1.4 },
          opacity: lost.map(({ id }) => markerOpacity(id)),
          symbol: "x",
        },
      });
    }
    return traces;
  }, [focusedDuels, selectedDuel, selectedDuelId, team, teamColor, teamColors, themeColors]);

  const transitionMapScope = useMemo(() => {
    return indexedTransitions.filter(({ row }) => {
      if (selectedTransitionThird && String(row.third ?? "") !== selectedTransitionThird) return false;
      return true;
    });
  }, [indexedTransitions, selectedTransitionThird]);
  const focusedTransitions = useMemo(() => {
    return transitionMapScope.filter(({ row }) => {
      if (selectedTransitionZone && transitionZoneKey(row) !== selectedTransitionZone) return false;
      return true;
    });
  }, [selectedTransitionZone, transitionMapScope]);
  const selectedTransition = useMemo(() => {
    if (!selectedTransitionId) return null;
    return indexedTransitions.find(({ id }) => id === selectedTransitionId)?.row ?? null;
  }, [indexedTransitions, selectedTransitionId]);

  const transitionZoneMap = useMemo(() => {
    const thirds = ["Defensive Third", "Middle Third", "Attacking Third"];
    const lanes = ["Left", "Central", "Right"];
    const binW = 35;
    const binH = 68 / 3;
    const counts = new Map<string, number>();
    transitionMapScope.forEach(({ row }) => {
      const key = transitionZoneKey(row);
      counts.set(key, (counts.get(key) ?? 0) + 1);
    });
    const maxCount = Math.max(1, ...counts.values());
    const total = Math.max(1, transitionMapScope.length);
    const shapes: Array<Record<string, unknown>> = [...pitchShapes(themeColors.muted)];
    const annotations: Array<Record<string, unknown>> = [];
    const hoverX: number[] = [];
    const hoverY: number[] = [];
    const hover: Array<{ kind: "transition-zone"; key: string; label: string }> = [];

    for (let xBin = 0; xBin < 3; xBin += 1) {
      for (let yBin = 0; yBin < 3; yBin += 1) {
        const key = `${xBin}-${yBin}`;
        const count = counts.get(key) ?? 0;
        const pctValue = Math.round((count / total) * 100);
        const isSelectedTransitionZone = selectedTransitionZone === key;
        const isDimmedTransitionZone = Boolean(selectedTransitionZone && !isSelectedTransitionZone);
        const zoneFillScale = isDimmedTransitionZone ? 0.22 : 1;
        const alpha = count ? (0.16 + (count / maxCount) * 0.54) * zoneFillScale : 0.03;
        const x0 = xBin * binW;
        const y0 = yBin * binH;
        shapes.push({
          type: "rect",
          x0,
          y0,
          x1: x0 + binW,
          y1: y0 + binH,
          line: {
            color: isSelectedTransitionZone
              ? (themeColors.mode === "dark" ? "#f8fafc" : "#0f172a")
              : colorWithAlpha(themeColors.text, isDimmedTransitionZone ? 0.08 : 0.18),
            width: isSelectedTransitionZone ? 3 : 1,
            dash: isSelectedTransitionZone ? "solid" : "dot",
          },
          fillcolor: colorWithAlpha(teamColor, alpha),
          layer: "below",
        });
        annotations.push({
          x: x0 + binW / 2,
          y: y0 + binH / 2,
          text: count ? `${pctValue}%<br><span style="font-size:10px">${count}</span>` : "",
          showarrow: false,
          font: { color: colorWithAlpha(themeColors.text, isDimmedTransitionZone || isSelectedTransitionZone ? 0.34 : 1), size: 15, family: themeColors.font },
          bgcolor: count ? colorWithAlpha(themeColors.mode === "dark" ? "#020617" : "#ffffff", isDimmedTransitionZone || isSelectedTransitionZone ? 0.16 : 0.7) : "rgba(0,0,0,0)",
          bordercolor: count ? colorWithAlpha(themeColors.text, isDimmedTransitionZone ? 0.06 : 0.16) : "rgba(0,0,0,0)",
          borderpad: 3,
        });
        hoverX.push(x0 + binW / 2);
        hoverY.push(y0 + binH / 2);
        hover.push({ kind: "transition-zone", key, label: `${thirds[xBin]} · ${lanes[yBin]} lane<br>${count} transitions<br>${pctValue}% of filtered transitions` });
      }
    }

    return {
      data: [{
        type: "scatter",
        mode: "markers",
        x: hoverX,
        y: hoverY,
        marker: { size: 120, color: "rgba(0,0,0,0.01)", symbol: "square" },
        customdata: hover,
        hovertemplate: "%{customdata.label}<extra></extra>",
      }],
      layout: {
        ...combinedLayout(themeColors, "", shapes),
        annotations,
        showlegend: false,
      },
    };
  }, [selectedTransitionZone, teamColor, themeColors, transitionMapScope]);

  const transitionData = useMemo(() => {
    const attack = focusedTransitions.filter(({ row }) => row.led_to_attack === true);
    const stalled = focusedTransitions.filter(({ row }) => row.led_to_attack !== true);
    const markerOpacity = (id: string) => selectedTransitionId && selectedTransitionId !== id ? 0.2 : 0.94;
    return [
      {
        type: "scatter",
        mode: "markers",
        name: transitionAttackLabel,
        x: attack.map(({ row }) => num(row.x)),
        y: attack.map(({ row }) => pitchY(row.y)),
        text: attack.map(({ row }) => transitionHover(row)),
        customdata: attack.map(({ id }) => ({ kind: "transition", id })),
        hovertemplate: "%{text}<extra></extra>",
        marker: { color: teamColor, size: attack.map(({ id }) => selectedTransitionId === id ? 17 : 13), line: { color: themeColors.text, width: 1.3 }, opacity: attack.map(({ id }) => markerOpacity(id)), symbol: "diamond" },
      },
      {
        type: "scatter",
        mode: "markers",
        name: transitionNoAttackLabel,
        x: stalled.map(({ row }) => num(row.x)),
        y: stalled.map(({ row }) => pitchY(row.y)),
        text: stalled.map(({ row }) => transitionHover(row)),
        customdata: stalled.map(({ id }) => ({ kind: "transition", id })),
        hovertemplate: "%{text}<extra></extra>",
        marker: { color: themeColors.mode === "dark" ? "#cbd5e1" : "#64748b", size: stalled.map(({ id }) => selectedTransitionId === id ? 15 : 10), line: { color: themeColors.text, width: 1 }, opacity: stalled.map(({ id }) => markerOpacity(id)), symbol: "circle-open" },
      },
    ];
  }, [focusedTransitions, selectedTransition, selectedTransitionId, teamColor, themeColors, transitionAttackLabel, transitionNoAttackLabel]);

  return (
    <div className="duels-transitions-stack">
      {(mode === "all" || mode === "duels") && (
        <div className="duels-interactive-layout">
          <div className="duels-visual-stack">
            <DuelAttackDirectionRow team={team} teams={teams} teamColors={teamColors} teamColor={teamColor} />
            <div className="plotly-chart-shell duels-combined-map-shell">
              {duelVisualMode === "zones" ? (
                <Plot
                  data={[...combinedDuelMap.data, ...((selectedZone || selectedPlayer || selectedContext || selectedDuelProfile) ? duelData : [])] as never}
                  layout={{ ...combinedDuelMap.layout, showlegend: false } as never}
                  config={plotConfig}
                  style={{ width: "100%", height: "100%" }}
                  useResizeHandler
                  onClick={(event: PlotlyClickEvent) => {
                    const custom = event.points?.[0]?.customdata as { kind?: string; key?: string; id?: string } | undefined;
                    if (custom?.kind === "zone" && custom.key) {
                      setSelectedZone((current) => current === custom.key ? "" : custom.key ?? "");
                      setSelectedDuelId("");
                      return;
                    }
                    if (custom?.kind === "duel" && custom.id) {
                      setSelectedDuelId((current) => current === custom.id ? "" : custom.id ?? "");
                    }
                  }}
                />
              ) : (
                <Plot
                  data={duelData as never}
                  layout={duelActionLayout(themeColors) as never}
                  config={plotConfig}
                  style={{ width: "100%", height: "100%" }}
                  useResizeHandler
                  onClick={(event: PlotlyClickEvent) => {
                    const custom = event.points?.[0]?.customdata as { kind?: string; id?: string } | undefined;
                    if (custom?.kind !== "duel" || !custom.id) return;
                    setSelectedDuelId((current) => current === custom.id ? "" : custom.id ?? "");
                  }}
                />
              )}
            </div>
          </div>
          <aside className="duels-detail-panel">
            <div>
              <span className="eyebrow">Duel Focus</span>
              <h3>{selectedDuel ? String(selectedDuel.player ?? "Selected duel") : selectedPlayer || (selectedZone ? "Selected zone" : "All duels")}</h3>
            </div>
            {showCombinedZoneGlossary ? (
              <div className="duels-glossary-card">
                <span className="eyebrow">Duel Types</span>
                <dl>
                  <div><dt>Ground</dt><dd>Take-on attempts, fouls won, tackles and challenges contested on the ground.</dd></div>
                  <div><dt>Aerial</dt><dd>Headers and aerial contests marked as won or lost in the event data.</dd></div>
                </dl>
              </div>
            ) : (
              <>
                <label>
                  <span>Player</span>
                  <select
                    value={selectedPlayer}
                    onChange={(event) => {
                      setSelectedPlayer(event.target.value);
                      setSelectedDuelId("");
                    }}
                  >
                    <option value="">All players</option>
                    {duelPlayers.map((player) => (
                      <option key={player} value={player}>{player}</option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>Duel context</span>
                  <select
                    value={selectedContext}
                    onChange={(event) => {
                      setSelectedContext(event.target.value);
                      setSelectedDuelId("");
                    }}
                  >
                    <option value="">All outcomes</option>
                    <option value="led_to_attack">Led to attack</option>
                    <option value="retained">Ball retained</option>
                    <option value="turnover">Turnover</option>
                    <option value="unknown">No follow-up</option>
                  </select>
                </label>
                <p className="duels-context-definition">{duelContextDescription(selectedContext)}</p>
              </>
            )}
            {selectedZone && (
              <button type="button" className="ghost-button" onClick={() => {
                setSelectedZone("");
                setSelectedDuelId("");
              }}>
                Clear zone
              </button>
            )}
            {selectedPlayer && (
              <button type="button" className="ghost-button" onClick={() => {
                setSelectedPlayer("");
                setSelectedDuelId("");
              }}>
                Clear player
              </button>
            )}
            {selectedContext && (
              <button type="button" className="ghost-button" onClick={() => {
                setSelectedContext("");
                setSelectedDuelId("");
              }}>
                Clear context
              </button>
            )}
            {selectedDuel ? (
              <div className="duels-detail-card">
                <span className="eyebrow">Selected Duel</span>
                <h4>{String(selectedDuel.player ?? "Unknown")}</h4>
                <p>{duelTime(selectedDuel)} · {String(selectedDuel.team ?? "")}</p>
                <div className="duels-context-legend" aria-label="Selected duel line legend">
                  <span><i className="is-before" />Before duel</span>
                  <span><i className="is-chain" />Duel chain</span>
                  <span><i className="is-after" style={{ "--team-color": rowTeamColor(selectedDuel) } as CSSProperties} />After duel</span>
                </div>
                <dl>
                  <div><dt>Type</dt><dd>{String(selectedDuel.category ?? selectedDuel.type ?? "Duel")}</dd></div>
                  <div><dt>Classified as</dt><dd>{String(selectedDuel.classification ?? "duel")}</dd></div>
                  <div><dt>Outcome</dt><dd>{selectedDuel.won ? "Won" : "Lost"}</dd></div>
                  <div><dt>Context</dt><dd>{String(selectedDuel.duel_context_label ?? "No follow-up")}</dd></div>
                  <div><dt>Zone</dt><dd>{String(selectedDuel.zone ?? "")}</dd></div>
                  <div><dt>Game state</dt><dd>{String(selectedDuel.game_state_label ?? "Level")} ({String(selectedDuel.score_before ?? "0-0")})</dd></div>
                  <div>
                    <dt>Before duel</dt>
                    <dd>
                      {selectedDuel.previous_duel === true
                        ? <DuelChainSummary row={selectedDuel} prefix="previous" />
                        : selectedDuel.previous_event
                        ? <DuelContextAction row={selectedDuel} prefix="previous" />
                        : "No valid lead-in action found"}
                    </dd>
                  </div>
                  <div>
                    <dt>After duel</dt>
                    <dd>
                      {selectedDuel.next_duel === true
                        ? <DuelChainSummary row={selectedDuel} prefix="next" />
                        : selectedDuel.next_event
                        ? <DuelContextAction row={selectedDuel} prefix="next" />
                        : String(selectedDuel.duel_context_label ?? "No follow-up")}
                    </dd>
                  </div>
                </dl>
                <button type="button" className="ghost-button" onClick={() => setSelectedDuelId("")}>Clear duel</button>
              </div>
            ) : (
              <p className="muted-copy">Click a zone to reveal its duel actions, or click any duel marker to inspect the event.</p>
            )}
          </aside>
        </div>
      )}
      {(mode === "all" || mode === "transitions") && (
        <div className="duels-interactive-layout">
          <div className="duels-visual-stack">
            <DuelAttackDirectionRow team={team} teams={teams} teamColors={teamColors} teamColor={teamColor} />
            <div className="plotly-chart-shell duels-combined-map-shell">
              <Plot
                data={(transitionVisualMode === "zones" ? [...transitionZoneMap.data, ...(selectedTransitionZone ? transitionData : [])] : transitionData) as never}
                layout={(transitionVisualMode === "zones" ? transitionZoneMap.layout : transitionActionLayout(themeColors)) as never}
                config={plotConfig}
                style={{ width: "100%", height: "100%" }}
                useResizeHandler
                onClick={(event: PlotlyClickEvent) => {
                  const custom = event.points?.[0]?.customdata as { kind?: string; key?: string; id?: string } | undefined;
                  if (custom?.kind === "transition-zone" && custom.key) {
                    setSelectedTransitionZone((current) => current === custom.key ? "" : custom.key ?? "");
                    setSelectedTransitionId("");
                    return;
                  }
                  if (custom?.kind === "transition" && custom.id) {
                    setSelectedTransitionId((current) => current === custom.id ? "" : custom.id ?? "");
                  }
                }}
              />
            </div>
          </div>
          <aside className="duels-detail-panel">
            <div>
              <span className="eyebrow">Transition Focus</span>
              <h3>{selectedTransition ? String(selectedTransition.player ?? "Selected transition") : selectedTransitionZone ? "Selected zone" : selectedTransitionThird || `${transitionType} transitions`}</h3>
            </div>
            <label>
              <span>Transition type</span>
              <select
                value={transitionType}
                onChange={(event) => {
                  setSelectedTransitionZone("");
                  setSelectedTransitionId("");
                  onTransitionTypeChange?.(event.target.value);
                }}
              >
                <option value="Offensive">Offensive</option>
                <option value="Defensive">Defensive</option>
              </select>
            </label>
            <label>
              <span>Pitch third</span>
              <select
                value={selectedTransitionThird}
                onChange={(event) => {
                  setSelectedTransitionThird(event.target.value);
                  setSelectedTransitionZone("");
                  setSelectedTransitionId("");
                }}
              >
                <option value="">All thirds</option>
                {transitionThirds.map((third) => (
                  <option key={third} value={third}>{third}</option>
                ))}
              </select>
            </label>
            <p className="duels-context-definition">
              {isDefensiveTransition
                ? "Defensive transitions start from selected-team dispossessed or turnover events, then track the opponent follow-up."
                : "Offensive transitions start after opponent dispossessed or turnover events, then track the selected-team follow-up."}
            </p>
            {selectedTransitionZone && (
              <button type="button" className="ghost-button" onClick={() => {
                setSelectedTransitionZone("");
                setSelectedTransitionId("");
              }}>
                Clear zone
              </button>
            )}
            {selectedTransitionThird && (
              <button type="button" className="ghost-button" onClick={() => setSelectedTransitionThird("")}>
                Clear third
              </button>
            )}
            {selectedTransition ? (
              <div className="duels-detail-card">
                <span className="eyebrow">Selected Transition</span>
                <h4>{String(selectedTransition.player ?? "Unknown")}</h4>
                <p>{duelTime(selectedTransition)} · {String(selectedTransition.team ?? "")}</p>
                <dl>
                  <div><dt>Type</dt><dd>{String(selectedTransition.type ?? "Transition")}</dd></div>
                  <div><dt>Context</dt><dd>{selectedTransition.led_to_attack ? transitionAttackLabel : transitionNoAttackLabel}</dd></div>
                  <div><dt>Pitch third</dt><dd>{String(selectedTransition.third ?? "")}</dd></div>
                  <div><dt>Game state</dt><dd>{String(selectedTransition.game_state_label ?? "Level")} ({String(selectedTransition.score_before ?? "0-0")})</dd></div>
                  <div><dt>End product</dt><dd>{String(selectedTransition.end_product ?? "No attacking follow-up") || "No attacking follow-up"}</dd></div>
                  <div><dt>Action chain</dt><dd>{String(selectedTransition.followup ?? "No follow-up") || "No follow-up"}</dd></div>
                </dl>
                <button type="button" className="ghost-button" onClick={() => setSelectedTransitionId("")}>Clear transition</button>
              </div>
            ) : (
              <p className="muted-copy">
                {transitionVisualMode === "zones"
                  ? "Click a zone to reveal transition actions from that lane, then select a marker for event detail."
                  : "Click a marker to inspect the transition and dim other actions."}
              </p>
            )}
            <p className="muted-copy">
              Showing {focusedTransitions.length} of {transitions.length} transitions for the current top-level filters.
            </p>
          </aside>
        </div>
      )}
    </div>
  );
}
