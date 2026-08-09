"use client";

import { Plot } from "../lib/plotly";

import { useEffect, useMemo, useState } from "react";
import { CHART_FONT_FAMILY, num, readThemeColors } from "../lib/theme";
import { useCompactAnalysis } from "../lib/useCompactAnalysis";
import { horizontalPitchShapes, JUEGO_X as juegoX, JUEGO_Y as juegoY } from "../lib/pitch";


type ActionRow = Record<string, string | number | boolean | null | undefined>;

type Props = {
  actions: ActionRow[];
  team: string;
  teamColor: string;
  mode: "zones" | "actions";
  contextFilter?: "all" | "counterpress" | "high-press" | "settled";
};

const plotConfig = { responsive: true, displayModeBar: false };

const actionStyles: Record<string, { symbol: string; label: string }> = {
  Aerial: { symbol: "x", label: "Aerial" },
  BallRecovery: { symbol: "circle", label: "Recovery" },
  BlockedPass: { symbol: "square", label: "Blocked pass" },
  Challenge: { symbol: "triangle-up", label: "Challenge" },
  Clearance: { symbol: "diamond", label: "Clearance" },
  Error: { symbol: "cross", label: "Error" },
  Foul: { symbol: "hexagon", label: "Foul" },
  Interception: { symbol: "cross-thin", label: "Interception" },
  Tackle: { symbol: "star", label: "Tackle" },
};

const pitchThirds = [
  { value: "all", label: "All thirds" },
  { value: "defensive", label: "Defensive third" },
  { value: "middle", label: "Middle third" },
  { value: "attacking", label: "Attacking third" },
];

function colorWithAlpha(color: string, alpha: number) {
  const hex = color.trim().replace("#", "");
  const fullHex = hex.length === 3 ? hex.split("").map((char) => char + char).join("") : hex;
  const value = Number.parseInt(fullHex.slice(0, 6), 16);
  if (!Number.isFinite(value)) return `rgba(100,116,139,${alpha})`;
  return `rgba(${(value >> 16) & 255}, ${(value >> 8) & 255}, ${value & 255}, ${alpha})`;
}

function binIndex(value: number, boundaries: number[]) {
  for (let index = 0; index < boundaries.length - 1; index += 1) {
    if (value >= boundaries[index] && value < boundaries[index + 1]) return index;
  }
  return boundaries.length - 2;
}

function zoneKey(row: ActionRow) {
  const x = num(row.x);
  const y = num(row.y);
  const xBin = Math.max(0, Math.min(juegoX.length - 2, binIndex(x, juegoX)));
  const yBin = Math.max(0, Math.min(juegoY.length - 2, binIndex(y, juegoY)));
  return `${xBin}-${yBin}`;
}

function zoneLabel(key: string) {
  const [xBinRaw, yBinRaw] = key.split("-").map((part) => Number.parseInt(part, 10));
  if (!Number.isFinite(xBinRaw) || !Number.isFinite(yBinRaw)) return "Selected zone";
  const channels = ["Left wide", "Left half-space", "Central", "Right half-space", "Right wide"];
  return `Band ${xBinRaw + 1} / ${channels[yBinRaw] ?? `Channel ${yBinRaw + 1}`}`;
}

function zoneMatchesThird(key: string, third: string) {
  if (third === "all") return true;
  const xBin = Number.parseInt(key.split("-")[0] ?? "", 10);
  if (!Number.isFinite(xBin)) return false;
  if (third === "defensive") return xBin <= 1;
  if (third === "middle") return xBin >= 2 && xBin <= 3;
  return xBin >= 4;
}

function actionConsequence(row: ActionRow) {
  const type = String(row.type ?? "");
  if (type === "Foul" || type === "Error") return "Risk";
  if (row.next_team_retained === true) return "Retained";
  if (type === "Tackle" || type === "Interception" || type === "BallRecovery") return "Disrupted";
  return "Cleared";
}

function actionPhase(row: ActionRow) {
  const type = String(row.type ?? "");
  const zone = String(row.zone ?? "");
  const retained = row.next_team_retained === true;
  if (row.counterpress_regain === true) return "Counterpress regain";
  if (row.counterpress_action === true) return "Counterpress action";
  if (zone === "Attacking Third" && ["BallRecovery", "Interception", "Tackle", "Challenge"].includes(type)) return "High press";
  if (zone === "Defensive Third" && ["Clearance", "BlockedPass", "Aerial", "Tackle"].includes(type)) return "Settled block";
  if (retained) return "Defensive transition";
  return "Defensive action";
}

function actionMatchesContext(row: ActionRow, context: string) {
  if (context === "all") return true;
  const type = String(row.type ?? "");
  const zone = String(row.zone ?? "");
  if (context === "counterpress") return row.counterpress_action === true;
  if (context === "high-press") {
    return zone === "Attacking Third" && ["BallRecovery", "Interception", "Tackle", "Challenge"].includes(type);
  }
  return zone === "Defensive Third" && ["Clearance", "BlockedPass", "Aerial", "Tackle"].includes(type);
}

function dangerContext(row: ActionRow) {
  const x = num(row.x);
  const y = num(row.y);
  const type = String(row.type ?? "");
  const central = y >= 24.84 && y <= 43.16;
  if (x <= 18 && central) return "Box danger";
  if (x <= 35 && central) return "Central danger";
  if (x <= 35 && ["Clearance", "BlockedPass", "Aerial", "Tackle"].includes(type)) return "Deep pressure";
  return "Low danger";
}

function consequenceColor(row: ActionRow, teamColor: string, mode: string) {
  const consequence = actionConsequence(row);
  if (consequence === "Retained") return mode === "dark" ? "#34d399" : "#047857";
  if (consequence === "Disrupted") return teamColor;
  if (consequence === "Risk") return "#ef4444";
  return mode === "dark" ? "#f8fafc" : "#334155";
}

function actionContextText(row: ActionRow, label: string) {
  const minute = num(row.minute);
  const second = num(row.second);
  const player = String(row.player ?? "").trim() || "Unknown player";
  const outcome = String(row.outcome ?? "").trim();
  const zone = String(row.zone ?? "").trim();
  const nextType = String(row.next_1_type ?? "");
  const nextPlayer = String(row.next_1_player ?? "");
  const nextTeam = String(row.next_1_team ?? "");
  const retained = row.next_team_retained === true ? "Retained by team" : nextTeam ? `Next: ${nextTeam}` : "Next meaningful event unavailable";
  const nextLine = nextType ? `${nextType}${nextPlayer ? ` by ${nextPlayer}` : ""}` : "No meaningful follow-up found";
  const recoverySeconds = Number(row.recovery_seconds);
  const transitionLine = Number.isFinite(recoverySeconds)
    ? `<br>Possession lost ${num(row.loss_minute)}' ${num(row.loss_second)}s | Recovered in ${recoverySeconds.toFixed(1)}s`
    : "";
  return `${player}<br>${label} | ${actionConsequence(row)}${outcome ? ` | ${outcome}` : ""}<br>${minute}'${second ? ` ${second}s` : ""} | ${String(row.game_state_label ?? "Level")} (${String(row.score_before ?? "0-0")})${zone ? `<br>${zone}` : ""}<br>${actionPhase(row)} | ${dangerContext(row)}${transitionLine}<br>${retained}<br>${nextLine}`;
}

function actionKey(row: ActionRow) {
  return [
    row.minute ?? "",
    row.second ?? "",
    row.player ?? "",
    row.type ?? "",
    row.x ?? "",
    row.y ?? "",
  ].join("|");
}

function nextEventRows(row: ActionRow) {
  return [1, 2, 3].map((index) => ({
    team: String(row[`next_${index}_team`] ?? ""),
    player: String(row[`next_${index}_player`] ?? ""),
    type: String(row[`next_${index}_type`] ?? ""),
    minute: num(row[`next_${index}_minute`]),
    second: num(row[`next_${index}_second`]),
    outcome: String(row[`next_${index}_outcome`] ?? ""),
    x: num(row[`next_${index}_x`], NaN),
    y: num(row[`next_${index}_y`], NaN),
  })).filter((event) => event.team || event.type || event.player);
}

function median(values: number[]) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const midpoint = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[midpoint] : (sorted[midpoint - 1] + sorted[midpoint]) / 2;
}

function pct(count: number, total: number) {
  return total ? count / total : 0;
}

function clampScore(value: number) {
  return Math.max(0, Math.min(100, Math.round(value)));
}

function actionMatchesProfile(row: ActionRow, profile: string) {
  const type = String(row.type ?? "");
  const zone = String(row.zone ?? "");
  const retained = row.next_team_retained === true;
  const nextType = String(row.next_1_type ?? "");
  const regain = ["BallRecovery", "Interception", "Tackle"].includes(type);
  const emergency = ["Clearance", "BlockedPass", "Aerial"].includes(type);
  if (["High Press Regains", "Pressing Forward"].includes(profile)) return zone === "Attacking Third" && regain;
  if (profile === "Counterpress Control") return row.counterpress_action === true;
  if (profile === "Ball Winner") return ["Middle Third", "Attacking Third"].includes(zone) && regain;
  if (["Deep Block Volume", "Box Defender"].includes(profile)) return zone === "Defensive Third" && emergency;
  if (["Regain To Attack", "Outlet Regainer"].includes(profile)) return retained && ["Pass", "Carry", "TakeOn", "Shot", "Goal", "MissedShots", "SavedShot"].includes(nextType);
  if (["Defensive Risk", "Risk Aggressor"].includes(profile)) return ["Foul", "Error"].includes(type);
  return false;
}

function convexHull(points: Array<{ x: number; y: number }>) {
  const unique = [...new Map(points.filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y)).map((point) => [`${point.x}-${point.y}`, point])).values()]
    .sort((a, b) => a.x - b.x || a.y - b.y);
  if (unique.length < 3) return unique;
  const cross = (origin: { x: number; y: number }, a: { x: number; y: number }, b: { x: number; y: number }) =>
    (a.x - origin.x) * (b.y - origin.y) - (a.y - origin.y) * (b.x - origin.x);
  const lower: Array<{ x: number; y: number }> = [];
  unique.forEach((point) => {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], point) <= 0) lower.pop();
    lower.push(point);
  });
  const upper: Array<{ x: number; y: number }> = [];
  [...unique].reverse().forEach((point) => {
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], point) <= 0) upper.pop();
    upper.push(point);
  });
  return lower.slice(0, -1).concat(upper.slice(0, -1));
}

function buildDefensiveProfiles(rows: ActionRow[], label: string, scope: "team" | "player") {
  const total = Math.max(1, rows.length);
  const countType = (types: string[]) => rows.filter((row) => types.includes(String(row.type ?? ""))).length;
  const inZone = (zone: string) => rows.filter((row) => String(row.zone ?? "") === zone).length;
  const retained = rows.filter((row) => row.next_team_retained === true).length;
  const retainedActions = rows.filter((row) => row.next_team_retained === true);
  const retainedNext = (types: string[]) => retainedActions.filter((row) => types.includes(String(row.next_1_type ?? ""))).length;
  const attackingThird = inZone("Attacking Third");
  const middleThird = inZone("Middle Third");
  const defensiveThird = inZone("Defensive Third");
  const regainTypes = countType(["BallRecovery", "Interception", "Tackle"]);
  const emergencyTypes = countType(["Clearance", "BlockedPass", "Aerial"]);
  const riskTypes = countType(["Foul", "Error"]);
  const deepEmergency = rows.filter((row) => String(row.zone ?? "") === "Defensive Third" && ["Clearance", "BlockedPass", "Aerial"].includes(String(row.type ?? ""))).length;
  const highRegains = rows.filter((row) => String(row.zone ?? "") === "Attacking Third" && ["BallRecovery", "Interception", "Tackle"].includes(String(row.type ?? ""))).length;
  const midHighRegains = rows.filter((row) => row.counterpress_regain === true).length;
  const counterpressActions = rows.filter((row) => row.counterpress_action === true).length;
  const transitionNext = retainedNext(["Pass", "Carry", "TakeOn", "Shot", "Goal", "MissedShots", "SavedShot"]);
  const deepFouls = rows.filter((row) => String(row.zone ?? "") === "Defensive Third" && ["Foul", "Error"].includes(String(row.type ?? ""))).length;

  const teamProfiles = [
    {
      name: "High Press Regains",
      score: clampScore(pct(highRegains, total) * 58 + pct(retained, total) * 30 + pct(attackingThird, total) * 24),
      detail: `${highRegains} high regains, ${Math.round(pct(attackingThird, total) * 100)}% actions in attacking third`,
    },
    {
      name: "Counterpress Control",
      score: clampScore(pct(midHighRegains, Math.max(1, counterpressActions)) * 56 + pct(counterpressActions, total) * 28 + pct(retained, total) * 16),
      detail: `${midHighRegains}/${counterpressActions} counterpress actions regained possession`,
    },
    {
      name: "Deep Block Volume",
      score: clampScore(pct(deepEmergency, total) * 62 + pct(defensiveThird, total) * 24 + pct(emergencyTypes, total) * 20),
      detail: `${deepEmergency} deep emergency actions, ${emergencyTypes} clear/block/aerial actions`,
    },
    {
      name: "Regain To Attack",
      score: clampScore(pct(retained, total) * 42 + pct(transitionNext, total) * 42 + pct(regainTypes, total) * 16),
      detail: `${transitionNext} retained actions followed by pass/carry/shot, ${retained} retained total`,
    },
    {
      name: "Defensive Risk",
      score: clampScore(pct(riskTypes, total) * 70 + pct(deepFouls, total) * 28),
      detail: `${riskTypes} fouls/errors, ${deepFouls} in defensive third`,
    },
  ].sort((a, b) => b.score - a.score);

  const playerProfiles = [
    {
      name: "Pressing Forward",
      score: clampScore(pct(highRegains, total) * 64 + pct(attackingThird, total) * 24 + pct(retained, total) * 18),
      detail: `${highRegains} high regains, ${Math.round(pct(attackingThird, total) * 100)}% actions high`,
    },
    {
      name: "Ball Winner",
      score: clampScore(pct(regainTypes, total) * 48 + pct(retained, total) * 32 + pct(midHighRegains, total) * 20),
      detail: `${regainTypes} tackles/interceptions/recoveries, ${Math.round(pct(retained, total) * 100)}% retained`,
    },
    {
      name: "Box Defender",
      score: clampScore(pct(deepEmergency, total) * 66 + pct(defensiveThird, total) * 22 + pct(emergencyTypes, total) * 18),
      detail: `${deepEmergency} deep emergency actions, ${emergencyTypes} clear/block/aerial actions`,
    },
    {
      name: "Outlet Regainer",
      score: clampScore(pct(transitionNext, total) * 50 + pct(retained, total) * 34 + pct(regainTypes, total) * 16),
      detail: `${transitionNext} retained actions led into pass/carry/shot, ${retained} retained total`,
    },
    {
      name: "Risk Aggressor",
      score: clampScore(pct(riskTypes, total) * 72 + pct(deepFouls, total) * 26),
      detail: `${riskTypes} fouls/errors, ${deepFouls} in defensive third`,
    },
  ].sort((a, b) => b.score - a.score);

  const profiles = scope === "player" ? playerProfiles : teamProfiles;
  const top = profiles[0];
  const insight = rows.length
    ? scope === "player"
      ? `${label}'s strongest defensive role is ${top.name.toLowerCase()} (${top.score}/100), with ${Math.round(pct(retained, total) * 100)}% of actions followed by team retention.`
      : `${label} profile strongest as ${top.name.toLowerCase()} (${top.score}/100), with ${Math.round(pct(retained, total) * 100)}% of defensive actions followed by team retention.`
    : `No defensive actions available for ${label}.`;

  return { profiles, insight, totals: { total: rows.length, attackingThird, middleThird, defensiveThird, retained } };
}

export function DefensiveActionsPlotly({ actions, team, teamColor, mode, contextFilter = "all" }: Props) {
  const [themeColors, setThemeColors] = useState(readThemeColors);
  const compactAnalysis = useCompactAnalysis();
  const [selectedPlayer, setSelectedPlayer] = useState("");
  const [selectedZone, setSelectedZone] = useState("");
  const [selectedActionKey, setSelectedActionKey] = useState("");
  const [selectedProfile, setSelectedProfile] = useState("");
  const [showLineCues, setShowLineCues] = useState(true);
  const [highlightAction, setHighlightAction] = useState("");
  const [highlightThird, setHighlightThird] = useState("all");
  const isZoneMode = mode === "zones";

  useEffect(() => {
    const updateColors = () => setThemeColors(readThemeColors());
    updateColors();
    const observer = new MutationObserver(updateColors);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "data-theme"] });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    setSelectedZone("");
    setSelectedPlayer("");
    setSelectedActionKey("");
    setSelectedProfile("");
  }, [actions, mode, contextFilter]);

  const players = useMemo(() => {
    const counts = new Map<string, number>();
    actions.forEach((row) => {
      const player = String(row.player ?? "");
      if (player) counts.set(player, (counts.get(player) ?? 0) + 1);
    });
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [actions]);

  const visibleActions = selectedPlayer ? actions.filter((row) => String(row.player ?? "") === selectedPlayer) : actions;
  const selectedAction = selectedActionKey ? actions.find((row) => actionKey(row) === selectedActionKey) : null;
  const selectedActionSequence = selectedAction ? nextEventRows(selectedAction) : [];
  const defensiveProfile = useMemo(
    () => buildDefensiveProfiles(selectedPlayer ? visibleActions : actions, selectedPlayer || team, selectedPlayer ? "player" : "team"),
    [actions, selectedPlayer, team, visibleActions],
  );
  const playerBaseline = useMemo(() => {
    if (!selectedPlayer) return null;
    const playerRows = visibleActions;
    const teamTotal = Math.max(1, actions.length);
    const playerTotal = Math.max(1, playerRows.length);
    const highPct = Math.round(pct(playerRows.filter((row) => String(row.zone ?? "") === "Attacking Third").length, playerTotal) * 100);
    const teamHighPct = Math.round(pct(actions.filter((row) => String(row.zone ?? "") === "Attacking Third").length, teamTotal) * 100);
    const retainedPct = Math.round(pct(playerRows.filter((row) => row.next_team_retained === true).length, playerTotal) * 100);
    const teamRetainedPct = Math.round(pct(actions.filter((row) => row.next_team_retained === true).length, teamTotal) * 100);
    return { highPct, teamHighPct, retainedPct, teamRetainedPct };
  }, [actions, selectedPlayer, visibleActions]);
  const selectedPlayerStats = useMemo(() => {
    if (!selectedPlayer) return null;
    const rows = actions.filter((row) => String(row.player ?? "") === selectedPlayer);
    const countType = (type: string) => rows.filter((row) => String(row.type ?? "") === type).length;
    const retained = rows.filter((row) => row.next_team_retained === true).length;
    const avgX = rows.length ? rows.reduce((sum, row) => sum + num(row.x), 0) / rows.length : 0;
    return {
      total: rows.length,
      tackles: countType("Tackle"),
      interceptions: countType("Interception"),
      recoveries: countType("BallRecovery"),
      clearances: countType("Clearance"),
      blockedPasses: countType("BlockedPass"),
      aerials: countType("Aerial"),
      fouls: countType("Foul"),
      retainedPct: rows.length ? Math.round((retained / rows.length) * 100) : 0,
      avgHeight: Math.round(avgX),
    };
  }, [actions, selectedPlayer]);
  const zoneActions = selectedZone ? actions.filter((row) => zoneKey(row) === selectedZone) : [];
  const zoneActionDistribution = useMemo(() => {
    const counts = new Map<string, number>();
    zoneActions.forEach((row) => {
      const type = String(row.type ?? "Action");
      counts.set(type, (counts.get(type) ?? 0) + 1);
    });
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [zoneActions]);
  const zonePlayerDistribution = useMemo(() => {
    const counts = new Map<string, number>();
    zoneActions.forEach((row) => {
      const player = String(row.player ?? "");
      if (player) counts.set(player, (counts.get(player) ?? 0) + 1);
    });
    return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8);
  }, [zoneActions]);
  const zoneCells = useMemo(() => {
    const counts = new Map<string, number>();
    actions.forEach((row) => counts.set(zoneKey(row), (counts.get(zoneKey(row)) ?? 0) + 1));
    const total = Math.max(1, actions.length);
    const cells = [];
    for (let xBin = 0; xBin < juegoX.length - 1; xBin += 1) {
      for (let yBin = 0; yBin < juegoY.length - 1; yBin += 1) {
        const key = `${xBin}-${yBin}`;
        const count = counts.get(key) ?? 0;
        const pct = count / total;
        cells.push({
          key,
          x0: juegoX[xBin],
          x1: juegoX[xBin + 1],
          y0: juegoY[yBin],
          y1: juegoY[yBin + 1],
          x: (juegoX[xBin] + juegoX[xBin + 1]) / 2,
          y: (juegoY[yBin] + juegoY[yBin + 1]) / 2,
          count,
          pct,
        });
      }
    }
    return cells;
  }, [actions]);

  const topZoneKeys = useMemo(() => {
    if (selectedZone || !highlightAction) return [];
    const counts = new Map<string, number>();
    actions.forEach((row) => {
      if (String(row.type ?? "") !== highlightAction) return;
      const key = zoneKey(row);
      if (!zoneMatchesThird(key, highlightThird)) return;
      counts.set(key, (counts.get(key) ?? 0) + 1);
    });
    return [...counts.entries()]
      .filter(([, count]) => count > 0)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(([key]) => key);
  }, [actions, highlightAction, highlightThird, selectedZone]);

  const zoneHighlightShapes = zoneCells.filter((cell) => selectedZone === cell.key).map((cell) => ({
    type: "rect",
    x0: cell.x0,
    x1: cell.x1,
    y0: cell.y0,
    y1: cell.y1,
    line: { color: themeColors.text, width: 2.2 },
    fillcolor: "rgba(0,0,0,0)",
  }));
  const topZoneHighlightShapes = zoneCells.filter((cell) => topZoneKeys.includes(cell.key)).map((cell, index) => ({
    type: "rect",
    x0: cell.x0,
    x1: cell.x1,
    y0: cell.y0,
    y1: cell.y1,
    line: { color: "#f59e0b", width: index === 0 ? 2.7 : 2, dash: index === 0 ? "solid" : "dash" },
    fillcolor: "rgba(0,0,0,0)",
  }));
  const zoneAnnotations = selectedZone ? [] : zoneCells.filter((cell) => cell.count > 0).map((cell) => ({
    x: cell.x,
    y: cell.y,
    text: `${Math.round(cell.pct * 100)}%<br><span style="font-size:${compactAnalysis ? 8 : 10}px">${cell.count}</span>`,
    showarrow: false,
    captureevents: false,
    font: { color: themeColors.text, size: compactAnalysis ? (cell.pct >= 0.1 ? 11 : 9) : (cell.pct >= 0.1 ? 15 : 12), family: CHART_FONT_FAMILY },
  }));
  const maxZoneCount = Math.max(1, ...zoneCells.map((cell) => cell.count));
  const zoneGrid = juegoY.slice(0, -1).map((_, yBin) => (
    juegoX.slice(0, -1).map((__, xBin) => {
      const cell = zoneCells.find((candidate) => candidate.key === `${xBin}-${yBin}`);
      if (!cell) return 0;
      if (!selectedZone) return cell.count;
      return cell.key === selectedZone ? Math.max(1, cell.count) : Math.min(0.35, cell.count / maxZoneCount);
    })
  ));
  const zoneCustomData = juegoY.slice(0, -1).map((_, yBin) => (
    juegoX.slice(0, -1).map((__, xBin) => `${xBin}-${yBin}`)
  ));
  const zoneText = juegoY.slice(0, -1).map((_, yBin) => (
    juegoX.slice(0, -1).map((__, xBin) => {
      const cell = zoneCells.find((candidate) => candidate.key === `${xBin}-${yBin}`);
      return cell ? `${zoneLabel(cell.key)}<br>${cell.count} actions<br>${Math.round(cell.pct * 100)}%` : "";
    })
  ));
  const zoneHeatmapTrace = {
    x: juegoX,
    y: juegoY,
    z: zoneGrid,
    customdata: zoneCustomData,
    text: zoneText,
    name: "__zone-select__",
    type: "heatmap",
    colorscale: [
      [0, colorWithAlpha(teamColor, 0.025)],
      [1, colorWithAlpha(teamColor, 0.72)],
    ],
    zmin: 0,
    zmax: selectedZone ? 1 : maxZoneCount,
    showscale: false,
    hovertemplate: "%{text}<extra></extra>",
  };
  const zoneClickTrace = {
    x: zoneCells.map((cell) => cell.x),
    y: zoneCells.map((cell) => cell.y),
    customdata: zoneCells.map((cell) => ({ kind: "zone", key: cell.key })),
    text: zoneCells.map((cell) => `${zoneLabel(cell.key)}<br>${cell.count} actions<br>${Math.round(cell.pct * 100)}%`),
    name: "__zone-click__",
    type: "scatter",
    mode: "markers",
    marker: {
      symbol: "square",
      size: 88,
      color: "rgba(0,0,0,0.001)",
      line: { color: "rgba(0,0,0,0)", width: 0 },
    },
    hovertemplate: "%{text}<extra></extra>",
    showlegend: false,
  };

  const defensiveLineCueShapes = !isZoneMode && showLineCues ? [
    { type: "Tackle", color: "#f59e0b", label: "Tackle line" },
    { type: "Interception", color: teamColor, label: "Interception line" },
    { type: "BallRecovery", color: themeColors.mode === "dark" ? "#34d399" : "#047857", label: "Recovery line" },
  ].flatMap((cue) => {
    const lineX = median(actions.filter((row) => String(row.type ?? "") === cue.type).map((row) => num(row.x)).filter((value) => value > 0));
    return lineX === null ? [] : [{
      type: "line",
      x0: lineX,
      x1: lineX,
      y0: 0,
      y1: 68,
      line: { color: colorWithAlpha(cue.color, selectedPlayer ? 0.22 : 0.82), width: selectedPlayer ? 1 : 1.4, dash: "dash" },
    }];
  }) : [];
  const defensiveLineCueAnnotations = !isZoneMode && showLineCues ? [
    { type: "Tackle", color: "#f59e0b", label: "Tackle line" },
    { type: "Interception", color: teamColor, label: "Interception line" },
    { type: "BallRecovery", color: themeColors.mode === "dark" ? "#34d399" : "#047857", label: "Recovery line" },
  ].flatMap((cue, index) => {
    const lineX = median(actions.filter((row) => String(row.type ?? "") === cue.type).map((row) => num(row.x)).filter((value) => value > 0));
    return lineX === null ? [] : [{
      x: lineX,
      y: 67 - index * 4.2,
      text: cue.label,
      showarrow: false,
      xanchor: "left",
      opacity: selectedPlayer ? 0.28 : 1,
      bgcolor: themeColors.mode === "dark" ? "rgba(15,23,42,0.82)" : "rgba(255,255,255,0.82)",
      bordercolor: colorWithAlpha(cue.color, selectedPlayer ? 0.22 : 0.82),
      borderpad: 3,
      font: { color: themeColors.text, size: 10, family: CHART_FONT_FAMILY },
    }];
  }) : [];

  const profileScopeRows = selectedPlayer ? visibleActions : actions;
  const profileFilteredKeys = new Set(selectedProfile ? profileScopeRows.filter((row) => actionMatchesProfile(row, selectedProfile)).map(actionKey) : []);
  const contextFilteredKeys = new Set(actions.filter((row) => actionMatchesContext(row, contextFilter)).map(actionKey));
  const actionTraceRows = isZoneMode ? zoneActions : actions;
  const traces = Object.entries(actionStyles).map(([type, style]) => {
    const rows = actionTraceRows.filter((row) => String(row.type ?? "") === type);
    return {
      x: rows.map((row) => num(row.x)),
      y: rows.map((row) => num(row.y)),
      text: rows.map((row) => actionContextText(row, style.label)),
      customdata: rows.map((row) => ({ kind: "action", key: actionKey(row) })),
      name: style.label,
      type: "scatter",
      mode: "markers",
      marker: {
        symbol: style.symbol,
        size: rows.map((row) => selectedActionKey === actionKey(row) ? 17 : selectedPlayer && String(row.player ?? "") === selectedPlayer ? 15 : type === "Tackle" ? 12 : 10),
        color: rows.map((row) => consequenceColor(row, teamColor, themeColors.mode)),
        opacity: rows.map((row) => {
          if (selectedProfile) return profileFilteredKeys.has(actionKey(row)) ? 0.95 : 0.12;
          if (selectedActionKey) return selectedActionKey === actionKey(row) ? 1 : 0.18;
          if (contextFilter !== "all") return contextFilteredKeys.has(actionKey(row)) ? 0.96 : 0.1;
          return !selectedPlayer || String(row.player ?? "") === selectedPlayer ? 0.9 : 0.16;
        }),
        line: {
          color: rows.map((row) => selectedActionKey === actionKey(row) || selectedPlayer && String(row.player ?? "") === selectedPlayer ? "#f59e0b" : themeColors.mode === "dark" ? "#ffffff" : "#0f172a"),
          width: rows.map((row) => selectedActionKey === actionKey(row) ? 3.2 : selectedPlayer && String(row.player ?? "") === selectedPlayer ? 2.6 : 1.2),
        },
      },
      hovertemplate: "%{text}<extra></extra>",
      showlegend: !isZoneMode || Boolean(selectedZone),
    };
  }).filter((trace) => trace.x.length);

  const playerTerritoryTrace = selectedPlayer && visibleActions.length >= 3 ? (() => {
    const hull = convexHull(visibleActions.map((row) => ({ x: num(row.x), y: num(row.y) })));
    return hull.length >= 3 ? [{
      x: [...hull.map((point) => point.x), hull[0].x],
      y: [...hull.map((point) => point.y), hull[0].y],
      name: "Player territory",
      type: "scatter",
      mode: "lines",
      fill: "toself",
      fillcolor: colorWithAlpha(teamColor, themeColors.mode === "dark" ? 0.14 : 0.11),
      line: { color: colorWithAlpha(teamColor, 0.48), width: 1.2, dash: "dot" },
      hoverinfo: "skip",
      showlegend: false,
    }] : [];
  })() : [];
  const sequenceArrowAnnotations = selectedAction ? selectedActionSequence
    .filter((event) => Number.isFinite(event.x) && Number.isFinite(event.y))
    .slice(0, 3)
    .map((event, index) => ({
      x: event.x,
      y: event.y,
      ax: num(selectedAction.x),
      ay: num(selectedAction.y),
      xref: "x",
      yref: "y",
      axref: "x",
      ayref: "y",
      text: `${index + 1}`,
      showarrow: true,
      arrowhead: 3,
      arrowsize: 1.2,
      arrowwidth: Math.max(1.3, 2.4 - index * 0.35),
      arrowcolor: "#f59e0b",
      bgcolor: themeColors.mode === "dark" ? "rgba(15,23,42,0.86)" : "rgba(255,255,255,0.86)",
      bordercolor: "#f59e0b",
      borderpad: 2,
      font: { color: themeColors.text, size: 10, family: CHART_FONT_FAMILY },
    })) : [];
  const counterpressArrowAnnotations = !isZoneMode && contextFilter === "counterpress"
    ? actions
      .filter((row) => row.counterpress_regain === true)
      .filter((row) => Number.isFinite(Number(row.loss_x)) && Number.isFinite(Number(row.loss_y)))
      .map((row) => ({
        x: num(row.x),
        y: num(row.y),
        ax: num(row.loss_x),
        ay: num(row.loss_y),
        xref: "x",
        yref: "y",
        axref: "x",
        ayref: "y",
        text: `${num(row.recovery_seconds).toFixed(1)}s`,
        showarrow: true,
        arrowhead: 3,
        arrowsize: 1.15,
        arrowwidth: 2,
        arrowcolor: "#f59e0b",
        bgcolor: themeColors.mode === "dark" ? "rgba(15,23,42,0.86)" : "rgba(255,255,255,0.88)",
        bordercolor: "#f59e0b",
        borderpad: 2,
        font: { color: themeColors.text, size: 10, family: CHART_FONT_FAMILY },
      }))
    : [];
  const plotData = isZoneMode ? [zoneHeatmapTrace, zoneClickTrace, ...traces] : [...playerTerritoryTrace, ...traces];

  return (
    <div className="defensive-actions-layout">
      <div className="defensive-visual-stack">
        <div className="plotly-chart-shell">
        <Plot
          data={plotData}
          layout={{
            autosize: true,
            height: compactAnalysis ? 300 : 620,
            margin: compactAnalysis ? { l: 8, r: 8, t: 6, b: 10 } : { l: 18, r: 18, t: 8, b: 18 },
            paper_bgcolor: "rgba(0,0,0,0)",
            plot_bgcolor: themeColors.surface,
            font: { color: themeColors.text, family: CHART_FONT_FAMILY },
            hoverlabel: {
              bgcolor: themeColors.mode === "dark" ? "#0f172a" : "#ffffff",
              bordercolor: themeColors.mode === "dark" ? "#334155" : "#cbd5e1",
              font: {
                color: themeColors.mode === "dark" ? "#f8fafc" : "#0f172a",
                family: CHART_FONT_FAMILY,
                size: 12,
              },
            },
            showlegend: !isZoneMode || Boolean(selectedZone),
            legend: { orientation: "h", x: 0, y: -0.06, font: { size: 11 } },
            xaxis: { range: [0, 105], visible: false, fixedrange: true, constrain: "domain" },
            yaxis: { range: [0, 68], visible: false, fixedrange: true, scaleanchor: "x", scaleratio: 1, constrain: "domain" },
            shapes: [...horizontalPitchShapes(themeColors.muted, { circleWidth: 1, zoneLines: isZoneMode }), ...defensiveLineCueShapes, ...(isZoneMode ? [...topZoneHighlightShapes, ...zoneHighlightShapes] : [])],
            annotations: isZoneMode ? zoneAnnotations : [...defensiveLineCueAnnotations, ...counterpressArrowAnnotations, ...sequenceArrowAnnotations],
          }}
          config={plotConfig}
          onClick={(event: { points?: Array<{ customdata?: unknown }> }) => {
            const point = event.points?.[0];
            const custom = point?.customdata as { kind?: string; key?: string } | undefined;
            if (isZoneMode) {
              if (custom?.kind !== "zone" || !custom.key) return;
              setSelectedZone((current) => current === custom.key ? "" : custom.key ?? "");
              return;
            }
            if (custom?.kind !== "action" || !custom.key) return;
            setSelectedActionKey((current) => current === custom.key ? "" : custom.key ?? "");
          }}
          className="plotly-chart"
        />
        </div>
        {!isZoneMode && <div className="defensive-profile-panel">
          <div>
            <span className="eyebrow">Defensive Profile</span>
            <p>{defensiveProfile.insight}</p>
          </div>
          <div className="defensive-profile-cards">
            {defensiveProfile.profiles.slice(0, 4).map((profile) => (
              <button
                key={profile.name}
                type="button"
                className={`${profile.score >= 55 ? "is-strong" : ""}${selectedProfile === profile.name ? " is-selected" : ""}`}
                onClick={() => setSelectedProfile((current) => current === profile.name ? "" : profile.name)}
              >
                <div>
                  <strong>{profile.name}</strong>
                  <span>{profile.score}</span>
                </div>
                <meter min={0} max={100} value={profile.score} />
                <small>{profile.detail}</small>
              </button>
            ))}
          </div>
          {selectedProfile && <button type="button" className="ghost-button" onClick={() => setSelectedProfile("")}>Clear profile highlight</button>}
        </div>}
      </div>
      {isZoneMode ? <aside className="defensive-player-panel">
        <div>
          <span className="eyebrow">Zone Focus</span>
          <h3>{selectedZone ? zoneLabel(selectedZone) : "Select a zone"}</h3>
        </div>
        {selectedZone ? <>
          <button type="button" className="ghost-button" onClick={() => setSelectedZone("")}>
            Clear zone
          </button>
          <div className="defensive-zone-summary">
            <span>Total actions</span>
            <strong>{zoneActions.length}</strong>
          </div>
          <div className="defensive-zone-breakdown">
            <span className="eyebrow">Action Distribution</span>
            {zoneActionDistribution.map(([type, count]) => (
              <div key={type}>
                <span>{actionStyles[type]?.label ?? type}</span>
                <strong>{count}</strong>
              </div>
            ))}
          </div>
          <div className="defensive-zone-breakdown">
            <span className="eyebrow">Players</span>
            {zonePlayerDistribution.map(([player, count]) => (
              <div key={player}>
                <span>{player}</span>
                <strong>{count}</strong>
              </div>
            ))}
          </div>
        </> : <>
          <div className="defensive-zone-controls">
            <label>
              <span>Action</span>
              <select value={highlightAction} onChange={(event) => setHighlightAction(event.target.value)}>
                <option value="">No highlight</option>
                {Object.entries(actionStyles).map(([value, style]) => (
                  <option key={value} value={value}>{style.label}</option>
                ))}
              </select>
            </label>
            <label>
              <span>Pitch area</span>
              <select value={highlightThird} onChange={(event) => setHighlightThird(event.target.value)}>
                {pitchThirds.map((third) => (
                  <option key={third.value} value={third.value}>{third.label}</option>
                ))}
              </select>
            </label>
          </div>
          <div className="defensive-zone-breakdown">
            <span className="eyebrow">Top Zones</span>
            {!highlightAction ? <p className="muted-copy">Choose an action to highlight its top three zones.</p> : topZoneKeys.length ? topZoneKeys.map((key, index) => {
              const count = actions.filter((row) => String(row.type ?? "") === highlightAction && zoneKey(row) === key).length;
              return (
                <button key={key} type="button" className="defensive-zone-pick" onClick={() => setSelectedZone(key)}>
                  <span>{index + 1}. {zoneLabel(key)}</span>
                  <strong>{count}</strong>
                </button>
              );
            }) : <p className="muted-copy">No zones found for this action and pitch area.</p>}
          </div>
          <p className="muted-copy">{highlightAction ? "The top three zones are outlined in amber. Select any zone to see the individual actions." : "You can still click any zone directly to inspect its actions."}</p>
        </>}
      </aside> : <aside className="defensive-player-panel">
        <div>
          <span className="eyebrow">Player Focus</span>
          <h3>{selectedPlayer || team}</h3>
        </div>
        <button type="button" className={!selectedPlayer ? "button" : "ghost-button"} onClick={() => setSelectedPlayer("")}>
          Team view
        </button>
        <label className="defensive-toggle-row">
          <input type="checkbox" checked={showLineCues} onChange={(event) => setShowLineCues(event.target.checked)} />
          <span>Show defensive line cues</span>
        </label>
        <div className="defensive-color-legend">
          <span><i style={{ background: "var(--accent)" }} />Retained</span>
          <span><i style={{ background: teamColor }} />Disrupted</span>
          <span><i style={{ background: "#ef4444" }} />Risk</span>
          <span><i style={{ background: "var(--text)" }} />Cleared</span>
        </div>
        {selectedAction && <div className="defensive-action-card">
          <div>
            <span className="eyebrow">Selected Action</span>
            <h4>{String(selectedAction.player ?? "Unknown")} · {String(selectedAction.type ?? "Action")}</h4>
            <p>{num(selectedAction.minute)}'{num(selectedAction.second) ? ` ${num(selectedAction.second)}s` : ""} · {actionConsequence(selectedAction)} · {String(selectedAction.zone ?? "")}</p>
            {Number.isFinite(Number(selectedAction.recovery_seconds)) && (
              <p>Recovered {num(selectedAction.recovery_seconds).toFixed(1)}s after possession was lost.</p>
            )}
          </div>
          <button type="button" className="ghost-button" onClick={() => setSelectedActionKey("")}>Clear action</button>
          <div className="defensive-sequence-list">
            <span className="eyebrow">Next Events</span>
            {selectedActionSequence.length ? selectedActionSequence.map((event, index) => (
              <div key={`${event.minute}-${event.second}-${event.type}-${index}`}>
                <strong>{index + 1}</strong>
                <span>{event.type || "Event"}{event.player ? ` by ${event.player}` : ""}</span>
                <small>{event.team}{event.minute ? ` · ${event.minute}'` : ""}</small>
              </div>
            )) : <p className="muted-copy">No meaningful follow-up event found.</p>}
          </div>
        </div>}
        {selectedPlayerStats && <div className="defensive-context-grid">
          <div><span>Actions</span><strong>{selectedPlayerStats.total}</strong></div>
          <div><span>Retained</span><strong>{selectedPlayerStats.retainedPct}%</strong></div>
          <div><span>Avg height</span><strong>{selectedPlayerStats.avgHeight}m</strong></div>
          <div><span>Recoveries</span><strong>{selectedPlayerStats.recoveries}</strong></div>
          <div><span>Tackles</span><strong>{selectedPlayerStats.tackles}</strong></div>
          <div><span>Interceptions</span><strong>{selectedPlayerStats.interceptions}</strong></div>
          <div><span>Clearances</span><strong>{selectedPlayerStats.clearances}</strong></div>
          <div><span>Blocked Passes</span><strong>{selectedPlayerStats.blockedPasses}</strong></div>
          <div><span>Aerials</span><strong>{selectedPlayerStats.aerials}</strong></div>
        </div>}
        {playerBaseline && <div className="defensive-baseline-card">
          <span className="eyebrow">Vs Team Baseline</span>
          <div><span>High actions</span><strong>{playerBaseline.highPct}%</strong><small>Team {playerBaseline.teamHighPct}%</small></div>
          <div><span>Retained after action</span><strong>{playerBaseline.retainedPct}%</strong><small>Team {playerBaseline.teamRetainedPct}%</small></div>
        </div>}
        <div className="defensive-player-list">
          {players.map(([player, count]) => (
            <button
              key={player}
              type="button"
              className={selectedPlayer === player ? "button" : "ghost-button"}
              onClick={() => setSelectedPlayer(player)}
            >
              <span>{player}</span>
              <strong>{count}</strong>
            </button>
          ))}
        </div>
      </aside>}
    </div>
  );
}
