"use client";

import { useSyncFiltersToUrl } from "../lib/analysisUrl";
import { PlayerAvatar, getCachedPlayerImage } from "./PlayerAvatar";
import { ActionOutcomeLegend } from "./ActionOutcomeLegend";
import { DownloadPngButton } from "./DownloadPngButton";
import { MobileAnalysisControls } from "./MobileAnalysisControls";
import { SeasonContextPanel } from "./season/SeasonContextPanel";
import type { SeasonBaselinePayload } from "./season/baselineTypes";

import { Plot } from "../lib/plotly";

import { useEffect, useMemo, useState } from "react";

import { getAnalysisView } from "../lib/api";
import { actionEndpointSymbol, actionOutcomeColor, actionStartSymbol, unsuccessfulActionColor } from "../lib/actionOutcome";
import { CHART_FONT_FAMILY, colorWithAlpha, num, readThemeColors } from "../lib/theme";
import { verticalPitchShapes } from "../lib/pitch";
import { useCompactAnalysis } from "../lib/useCompactAnalysis";


type Row = Record<string, string | number | boolean | null | undefined | Row[]>;
type PitchKind = "heatmap" | "in_possession" | "out_of_possession" | "touches" | "duels" | "shots";
type GameStateOption = { value?: string; label?: string; count?: number };

const PLAYER_COMPARISON_COLORS = [
  "#22c55e",
  "#38bdf8",
  "#f59e0b",
  "#a78bfa",
  "#f43f5e",
  "#14b8a6",
  "#e879f9",
  "#fb7185",
];

type Props = {
  matchId: string;
  source: string;
  league?: string;
  season?: string;
  jobId?: string;
  teams: string[];
  selectedTeam: string;
  payload: Record<string, unknown>;
  teamColors: Record<string, string>;
  initialPlayer?: string;
  seasonBaseline?: SeasonBaselinePayload | null;
};

const plotConfig = { responsive: true, displayModeBar: false };
const shotTypes = new Set(["Goal", "SavedShot", "MissedShots", "ShotOnPost"]);
const oopActionTypes = new Set(["Tackle", "Interception", "BallRecovery", "Clearance", "BlockedPass", "BlockedShot", "Save", "Challenge", "Foul", "Dispossessed"]);
const pitchOptions: Array<{ value: PitchKind; label: string }> = [
  { value: "heatmap", label: "Heatmap" },
  { value: "in_possession", label: "In possession" },
  { value: "out_of_possession", label: "Out of possession" },
  { value: "touches", label: "Touches" },
  { value: "duels", label: "Duels" },
  { value: "shots", label: "Shots + SCA" },
];
const passEdgeLegend = [
  ["Cross", "#38bdf8"],
  ["Through pass", "#a78bfa"],
  ["Long ball", "#14b8a6"],
  ["Key pass", "#f59e0b"],
  ["Assist", "#22c55e"],
  ["Ground pass", "#94a3b8"],
] as const;
const oopMarkerLegend = [
  ["Tackle", "star"],
  ["Interception", "cross-thin"],
  ["Recovery", "circle"],
  ["Clearance", "diamond"],
  ["Blocked pass", "square"],
  ["Blocked shot", "hexagon"],
  ["Possession lost", "triangle-down"],
] as const;
const shotMarkerLegend = [
  ["Goal", "star", "#facc15"],
  ["On target", "circle", "#60a5fa"],
  ["Blocked", "square", "#ef4444"],
  ["Woodwork", "diamond", "#22c55e"],
  ["Off target", "circle", "#94a3b8"],
  ["SCA-created shot", "circle", "#a78bfa"],
] as const;
const pitchAreaLabels = ["Own box", "Defensive third", "Middle third", "Final third", "Opp. box"] as const;
const gkPassLegend = [
  ["Short pass", "circle"],
  ["Long pass", "diamond"],
] as const;
const gkActionMarkerLegend = [
  ["Save", "star"],
  ["Claim", "diamond"],
  ["Punch", "hexagon"],
  ["Pickup", "circle"],
  ["Sweeper action", "triangle-down"],
] as const;
const gkActionSymbolByType: Record<string, string> = {
  Save: "star",
  KeeperSave: "star",
  Claim: "diamond",
  Punch: "hexagon",
  KeeperPickup: "circle",
  KeeperSweeper: "triangle-down",
  Smother: "hexagon",
};

function playerKey(row: Row) {
  return `${String(row.player ?? "")}|${String(row.team ?? "")}`;
}

function playerPositions(row: Row): string[] {
  const raw = row.positions as unknown;
  return Array.isArray(raw) ? raw.map((value) => String(value)) : [];
}

function positionsLabel(row: Row): string {
  const positions = playerPositions(row);
  if (positions.length > 1) return positions.join(" / ");
  if (positions.length === 1) return positions[0];
  return row.position ? String(row.position) : "";
}

function playerOptionLabel(row: Row): string {
  const label = positionsLabel(row);
  return label ? `${String(row.player ?? "")} (${label})` : String(row.player ?? "");
}

function rowsFromPayload(payload: Record<string, unknown>, key: string) {
  return (payload[key] as Row[] | undefined) ?? [];
}

function rowClock(row: Row) {
  const second = num(row.second);
  return `${num(row.minute)}'${second ? ` ${second}s` : ""}`;
}

function formatNumber(value: unknown, digits = 0) {
  const parsed = num(value);
  return digits > 0 ? parsed.toFixed(digits) : String(Math.round(parsed));
}

function pitchPointInFrame(row: Row, invert = false) {
  const rawX = Math.max(0, Math.min(105, num(row.x)));
  const rawY = Math.max(0, Math.min(68, num(row.y)));
  const x = invert ? 105 - rawX : rawX;
  const y = invert ? 68 - rawY : rawY;
  return {
    x: 68 - y,
    y: x,
  };
}

function pitchEndPointInFrame(row: Row, invert = false) {
  const rawX = Math.max(0, Math.min(105, num(row.end_x, num(row.x))));
  const rawY = Math.max(0, Math.min(68, num(row.end_y, num(row.y))));
  const x = invert ? 105 - rawX : rawX;
  const y = invert ? 68 - rawY : rawY;
  return {
    x: 68 - y,
    y: x,
  };
}

function pitchPoint(row: Row) {
  return pitchPointInFrame(row);
}

function pitchEndPoint(row: Row) {
  return pitchEndPointInFrame(row);
}

function goalMapX(goalMouthY: unknown) {
  const goalLeft = 30.8;
  const goalWidth = 6.4;
  const frameLeft = 4;
  const frameWidth = 60;
  return frameLeft + ((goalLeft + goalWidth - num(goalMouthY, 34)) / goalWidth) * frameWidth;
}

function shotOutcome(row: Row) {
  if (row.blocked === true) return "Blocked";
  const type = String(row.type ?? "");
  if (type === "Goal") return "Goal";
  if (type === "SavedShot") return "On target";
  if (type === "ShotOnPost") return "Woodwork";
  return "Off target";
}

function shotSymbol(row: Row) {
  if (row.blocked === true) return "square";
  const type = String(row.type ?? "");
  if (type === "Goal") return "star";
  if (type === "ShotOnPost") return "diamond";
  return "circle";
}

function shotOutcomeColor(outcome: string) {
  if (outcome === "Goal") return "#facc15";
  if (outcome === "On target") return "#60a5fa";
  if (outcome === "Blocked") return "#ef4444";
  if (outcome === "Woodwork") return "#22c55e";
  return "#94a3b8";
}

function shotRowKey(row: Row) {
  return `${String(row.minute)}-${String(row.second)}-${String(row.player)}-${String(row.type)}`;
}

function playerMinutes(row: Row) {
  return num(row.minutes ?? row.minutes_played);
}

function rowText(row: Row, key: string) {
  return String(row[key] ?? "").toLowerCase();
}

function rowTruthy(row: Row, key: string) {
  return row[key] === true || rowText(row, key) === "true" || rowText(row, key) === "1";
}

function qualifierText(row: Row) {
  return `${rowText(row, "qualifiers")} ${rowText(row, "satisfied_events")} ${rowText(row, "satisfiedEventsTypes")}`;
}

function movementDistance(row: Row) {
  const dx = num(row.end_x, num(row.x)) - num(row.x);
  const dy = num(row.end_y, num(row.y)) - num(row.y);
  return Math.sqrt(dx * dx + dy * dy);
}

function passSubtype(row: Row) {
  const qualifiers = qualifierText(row);
  if (rowTruthy(row, "pass_assist") || rowTruthy(row, "assist_cross") || rowTruthy(row, "assist_corner") || rowTruthy(row, "assist_through_ball") || rowTruthy(row, "assist_freekick") || rowTruthy(row, "assist_throw_in") || /intentionalgoalassist|goalassist/.test(qualifiers)) return "Assist";
  if (rowTruthy(row, "pass_key") || rowTruthy(row, "key_pass_cross") || rowTruthy(row, "key_pass_corner") || rowTruthy(row, "key_pass_through_ball") || rowTruthy(row, "key_pass_freekick") || rowTruthy(row, "key_pass_throw_in") || /keypass|shotassist|bigchancecreated/.test(qualifiers)) return "Key pass";
  if (rowTruthy(row, "pass_corner") || rowTruthy(row, "key_pass_corner") || rowTruthy(row, "assist_corner") || /corner|fromcorner|cornertaken/.test(qualifiers)) return "Corner";
  if (rowTruthy(row, "pass_freekick") || rowTruthy(row, "key_pass_freekick") || rowTruthy(row, "assist_freekick") || /freekick|free kick|free-kick|freekicktaken|directfreekick/.test(qualifiers)) return "Free kick";
  if (rowTruthy(row, "pass_throw_in") || rowTruthy(row, "throw_in") || rowTruthy(row, "key_pass_throw_in") || rowTruthy(row, "assist_throw_in") || /throwin|throw in|throw-in|throwintaken/.test(qualifiers)) return "Throw-in";
  if (rowTruthy(row, "pass_cross") || rowTruthy(row, "pass_cross_accurate") || rowTruthy(row, "pass_cross_inaccurate") || rowTruthy(row, "key_pass_cross") || rowTruthy(row, "assist_cross") || /cross/.test(qualifiers)) return "Cross";
  if (rowTruthy(row, "pass_through_ball") || rowTruthy(row, "pass_through_ball_accurate") || rowTruthy(row, "pass_through_ball_inaccurate") || rowTruthy(row, "key_pass_through_ball") || rowTruthy(row, "assist_through_ball") || /through/.test(qualifiers)) return "Through pass";
  if (rowTruthy(row, "pass_long_ball_accurate") || rowTruthy(row, "pass_long_ball_inaccurate") || /longball|long ball/.test(qualifiers) || movementDistance(row) >= 30) return "Long ball";
  return "Ground pass";
}

function passSubtypeEdgeColor(row: Row) {
  const subtype = passSubtype(row);
  if (subtype === "Cross") return "#38bdf8";
  if (subtype === "Through pass") return "#a78bfa";
  if (subtype === "Long ball") return "#14b8a6";
  if (subtype === "Key pass") return "#f59e0b";
  if (subtype === "Assist") return "#22c55e";
  if (["Corner", "Free kick", "Throw-in"].includes(subtype)) return "#facc15";
  return "#94a3b8";
}

function isSetPlayPass(row: Row) {
  const qualifiers = qualifierText(row);
  return (
    rowTruthy(row, "pass_corner") ||
    rowTruthy(row, "pass_freekick") ||
    rowTruthy(row, "pass_throw_in") ||
    rowTruthy(row, "throw_in") ||
    rowTruthy(row, "key_pass_corner") ||
    rowTruthy(row, "key_pass_freekick") ||
    rowTruthy(row, "key_pass_throw_in") ||
    rowTruthy(row, "assist_corner") ||
    rowTruthy(row, "assist_freekick") ||
    rowTruthy(row, "assist_throw_in") ||
    /corner|fromcorner|cornertaken|freekick|free kick|free-kick|freekicktaken|directfreekick|throwin|throw in|throw-in|throwintaken|setpiece|set piece/.test(qualifiers)
  );
}

function movementDirection(row: Row) {
  const dx = num(row.end_x, num(row.x)) - num(row.x);
  const dy = Math.abs(num(row.end_y, num(row.y)) - num(row.y));
  if (dx > 5 && dx >= dy * 0.7) return "Forward";
  if (dx < -5 && Math.abs(dx) >= dy * 0.7) return "Backward";
  return "Sideways";
}

function receivedPassDirection(row: Row) {
  const dx = num(row.x) - num(row.source_x, num(row.x));
  const dy = Math.abs(num(row.y) - num(row.source_y, num(row.y)));
  if (dx > 5 && dx >= dy * 0.7) return "Forward";
  if (dx < -5 && Math.abs(dx) >= dy * 0.7) return "Backward";
  return "Sideways";
}

function movementLength(row: Row) {
  const distance = movementDistance(row);
  if (distance >= 30) return "Long";
  if (distance >= 15) return "Medium";
  return "Short";
}

function passHeight(row: Row) {
  const value = `${rowText(row, "pass_height")} ${qualifierText(row)}`;
  if (rowTruthy(row, "pass_chipped") || /chipped|high|aerial|lob|headed|head/.test(value)) return "Chipped / aerial";
  return "Ground";
}

function pitchAreaLabel(row: Row) {
  const x = num(row.x);
  const y = num(row.y);
  if (x <= 16.5 && y >= 13.84 && y <= 54.16) return "Own box";
  if (x >= 88.5 && y >= 13.84 && y <= 54.16) return "Opp. box";
  if (x < 35) return "Defensive third";
  if (x < 70) return "Middle third";
  return "Final third";
}

function touchRowsFor(rows: Row[]): Row[] {
  return rows
    .filter((row) => row.is_ball_touch === true)
    .map((row) => ({ ...row, touch_kind: "Touch" }));
}

function isPossessionLostAction(row: Row) {
  const type = String(row.type ?? "");
  const qualifiers = qualifierText(row);
  return type === "Dispossessed" || (type === "BallTouch" && /turnover|dispossessed/.test(qualifiers));
}

function isBlockedShotAction(row: Row) {
  const type = String(row.type ?? "");
  return ["BlockedShot", "BlockedShots", "ShotBlocked", "Save"].includes(type);
}

function isOutOfPossessionAction(row: Row) {
  const type = String(row.type ?? "");
  return oopActionTypes.has(type) || isPossessionLostAction(row) || isBlockedShotAction(row);
}

type DefensiveArea = { x0: number; x1: number; y0: number; y1: number };

function percentile(values: number[], p: number) {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const index = (sorted.length - 1) * p;
  const lower = Math.floor(index);
  const upper = Math.ceil(index);
  if (lower === upper) return sorted[lower];
  return sorted[lower] + (sorted[upper] - sorted[lower]) * (index - lower);
}

function clampSpan(minValue: number, maxValue: number, pitchMin: number, pitchMax: number, minSpan: number, maxSpan: number) {
  const center = (minValue + maxValue) / 2;
  const span = Math.max(minSpan, Math.min(maxSpan, maxValue - minValue));
  return {
    min: Math.max(pitchMin, center - span / 2),
    max: Math.min(pitchMax, center + span / 2),
  };
}

function defensiveAreaForRows(rows: Row[]): DefensiveArea | null {
  const points = rows
    .filter(isOutOfPossessionAction)
    .map(pitchPoint)
    .filter((point) => point.x >= 0 && point.x <= 68 && point.y >= 0 && point.y <= 105);
  if (!points.length) return null;
  const xValues = points.map((point) => point.x);
  const yValues = points.map((point) => point.y);
  const xRange = clampSpan(percentile(xValues, 0.25) - 3, percentile(xValues, 0.75) + 3, 0, 68, 12, 30);
  const yRange = clampSpan(percentile(yValues, 0.25) - 4, percentile(yValues, 0.75) + 4, 0, 105, 14, 34);
  return {
    x0: xRange.min,
    x1: xRange.max,
    y0: yRange.min,
    y1: yRange.max,
  };
}

function defensiveAreaForPoints(rows: Row[]): DefensiveArea | null {
  const points = rows
    .map(pitchPoint)
    .filter((point) => point.x >= 0 && point.x <= 68 && point.y >= 0 && point.y <= 105);
  if (!points.length) return null;
  const xValues = points.map((point) => point.x);
  const yValues = points.map((point) => point.y);
  const xRange = clampSpan(percentile(xValues, 0.25) - 3, percentile(xValues, 0.75) + 3, 0, 68, 12, 30);
  const yRange = clampSpan(percentile(yValues, 0.25) - 4, percentile(yValues, 0.75) + 4, 0, 105, 14, 34);
  return {
    x0: xRange.min,
    x1: xRange.max,
    y0: yRange.min,
    y1: yRange.max,
  };
}

function pointInArea(point: { x: number; y: number }, area: DefensiveArea) {
  return point.x >= area.x0 && point.x <= area.x1 && point.y >= area.y0 && point.y <= area.y1;
}

function actionTouchesArea(row: Row, area: DefensiveArea, invert = false) {
  const start = pitchPointInFrame(row, invert);
  const end = pitchEndPointInFrame(row, invert);
  return pointInArea(start, area) || pointInArea(end, area);
}

function actionStartsInArea(row: Row, area: DefensiveArea, invert = false) {
  return pointInArea(pitchPointInFrame(row, invert), area);
}

function actionEndsInArea(row: Row, area: DefensiveArea, invert = false) {
  return pointInArea(pitchEndPointInFrame(row, invert), area);
}

function displayActionType(type: unknown) {
  const value = String(type ?? "Action");
  return value.replace(/([a-z])([A-Z])/g, "$1 $2");
}

function actionOutcome(row: Row) {
  const outcome = String(row.outcome ?? "").trim();
  if (outcome && outcome.toLowerCase() !== "nan") return outcome;
  if (row.is_successful === true) return "Successful";
  if (row.is_successful === false) return "Unsuccessful";
  return "";
}

function actionSubtype(row: Row, kind: PitchKind) {
  const type = String(row.type ?? "");
  if (kind === "in_possession") {
    if (type === "Pass") return passSubtype(row);
    if (type === "Carry") return `${movementDirection(row)} ${movementLength(row).toLowerCase()} carry`;
    if (type === "TakeOn") return "Dribble / take-on";
  }
  if (kind === "touches") return type === "PassReceived" ? "Receive" : String(row.touch_kind ?? "Touch");
  if (kind === "duels") return type === "Aerial" ? "Aerial duel" : "Ground duel";
  if (kind === "shots") return shotOutcome(row);
  return displayActionType(type);
}

function passRows(rows: Row[]) {
  return rows.filter((row) => String(row.type ?? "") === "Pass");
}

function completedPassCount(rows: Row[]) {
  return passRows(rows).filter((row) => row.is_successful === true).length;
}

function xPassTotal(rows: Row[]) {
  return passRows(rows).reduce((sum, row) => sum + num(row.xPass), 0);
}

function epvAddedTotal(rows: Row[]) {
  return rows
    .filter((row) => ["Pass", "Carry"].includes(String(row.type ?? "")))
    .reduce((sum, row) => sum + num(row.epv_added), 0);
}

function passAboveExpected(rows: Row[]) {
  return completedPassCount(rows) - xPassTotal(rows);
}

function passAboveExpectedPer100(rows: Row[]) {
  const attempts = passRows(rows).length;
  return attempts ? (passAboveExpected(rows) / attempts) * 100 : 0;
}

function avgPassDifficulty(rows: Row[]) {
  const passes = passRows(rows);
  if (!passes.length) return 0;
  return passes.reduce((sum, row) => sum + (1 - num(row.xPass)), 0) / passes.length;
}

function hoverActionText(row: Row, kind: PitchKind, label?: string) {
  const lines = [
    `<b>${String(row.player ?? "Player")}</b>`,
    `${rowClock(row)} · ${label ?? displayActionType(row.type)}`,
  ];
  const subtype = actionSubtype(row, kind);
  if (subtype && subtype !== displayActionType(row.type)) lines.push(`Subtype: ${subtype}`);
  const outcome = actionOutcome(row);
  if (outcome) lines.push(`Outcome: ${outcome}`);
  if (kind === "in_possession" && ["Pass", "Carry"].includes(String(row.type ?? ""))) {
    lines.push(`Direction: ${movementDirection(row)}`);
    lines.push(`Length: ${movementLength(row)}`);
    if (String(row.type ?? "") === "Pass") {
      lines.push(`Height: ${passHeight(row)}`);
      if (num(row.xPass)) {
        lines.push(`xPass: ${(num(row.xPass) * 100).toFixed(1)}%`);
        lines.push(`Difficulty: ${((1 - num(row.xPass)) * 100).toFixed(1)}%`);
      }
    }
    if (row.is_progressive === true && row.is_successful === true) lines.push("Progressive: Yes");
  }
  if (kind === "shots") {
    if (row.situation && String(row.situation) !== "nan") lines.push(`Situation: ${String(row.situation)}`);
    if (row.body_part && String(row.body_part) !== "nan") lines.push(`Body part: ${String(row.body_part)}`);
    lines.push(`xG: ${formatNumber(row.xg ?? row.xG, 2)}`);
    lines.push(`xGOT: ${formatNumber(row.xgot ?? row.xGOT, 2)}`);
  }
  if (num(row.xT)) lines.push(`xT: ${formatNumber(row.xT, 3)}`);
  if (num(row.xA)) lines.push(`xA: ${formatNumber(row.xA, 3)}`);
  if (num(row.epv_added)) lines.push(`EPV added: ${formatNumber(row.epv_added, 3)}`);
  if (row.game_state_label && String(row.game_state_label) !== "nan") lines.push(`Game state: ${String(row.game_state_label)}`);
  return lines.join("<br>");
}

function pitchRows(rows: Row[], kind: PitchKind) {
  if (kind === "heatmap") return rows;
  if (kind === "in_possession") return rows.filter((row) => ["Pass", "Carry", "TakeOn"].includes(String(row.type ?? "")));
  if (kind === "out_of_possession") return rows.filter(isOutOfPossessionAction);
  if (kind === "touches") return [...touchRowsFor(rows), ...rows.filter((row) => String(row.type ?? "") === "PassReceived")];
  if (kind === "duels") return rows.filter((row) => String(row.phase ?? "") === "duel");
  return rows.filter((row) => shotTypes.has(String(row.type ?? "")));
}

function statLabel(row: Row, kind: PitchKind) {
  const type = String(row.type ?? "");
  if (kind === "heatmap") return "Actions";
  if (kind === "in_possession") {
    if (row.is_progressive === true && row.is_successful === true && ["Pass", "Carry"].includes(type)) return "Progressive";
    if (type === "TakeOn") return "Dribbles";
    return type === "Pass" ? "Passes" : "Carries";
  }
  if (kind === "touches") return type === "PassReceived" ? "Receives" : "Touches";
  if (kind === "duels") return type === "Aerial" ? "Aerial duels" : "Ground duels";
  if (kind === "shots") {
    if (type === "Goal") return "Goals";
    if (type === "SavedShot") return "Saved";
    if (type === "ShotOnPost") return "Woodwork";
    return "Off target";
  }
  if (kind === "out_of_possession") {
    if (isPossessionLostAction(row)) return "Possession lost";
    if (isBlockedShotAction(row)) return "Blocked shot";
  }
  return type.replace(/([a-z])([A-Z])/g, "$1 $2");
}

function markerSymbol(row: Row, kind: PitchKind) {
  const type = String(row.type ?? "");
  if (kind === "touches") return type === "PassReceived" ? "circle-open" : "circle";
  if (kind === "duels") return type === "Aerial" ? "x" : "diamond";
  if (kind === "shots") return type === "Goal" ? "star" : type === "ShotOnPost" ? "cross" : "diamond";
  const map: Record<string, string> = {
    BallRecovery: "circle",
    Interception: "cross-thin",
    Tackle: "star",
    Clearance: "diamond",
    BlockedPass: "square",
    BlockedShot: "hexagon",
    Save: "hexagon",
    Dispossessed: "triangle-down",
    Challenge: "triangle-up",
    Aerial: "x",
  };
  if (isPossessionLostAction(row)) return "triangle-down";
  if (isBlockedShotAction(row)) return "hexagon";
  return map[type] ?? "circle";
}

function scaSymbol(type: string) {
  const normalized = type.toLowerCase();
  if (normalized === "pass") return "triangle-up";
  if (normalized === "carry") return "square";
  if (normalized === "takeon") return "diamond";
  if (["tackle", "interception", "ballrecovery"].includes(normalized)) return "x";
  return "circle-open";
}

function statMatches(row: Row, kind: PitchKind, label: string) {
  const type = String(row.type ?? "");
  if (kind === "in_possession") {
    if (label === "Progressive actions") return row.is_progressive === true && row.is_successful === true && ["Pass", "Carry"].includes(type);
    if (label === "Passes") return type === "Pass";
    if (label === "Carries") return type === "Carry";
    if (label === "Dribbles") return type === "TakeOn";
  }
  if (kind === "touches") {
    if (label === "Touches") return type !== "PassReceived";
    if (label === "Receives") return type === "PassReceived";
  }
  if (kind === "duels") {
    if (label === "Ground won / total") return type !== "Aerial";
    if (label === "Aerial won / total") return type === "Aerial";
  }
  return statLabel(row, kind) === label;
}

export function PlayerAnalysisSection({
  matchId,
  source,
  league,
  season,
  jobId,
  teams,
  selectedTeam,
  payload,
  teamColors,
  initialPlayer,
  seasonBaseline,
}: Props) {
  const initialTeam = String(payload.team ?? selectedTeam);
  const [currentTeam, setCurrentTeam] = useState(initialTeam);
  const [payloadsByTeam, setPayloadsByTeam] = useState<Record<string, Record<string, unknown>>>({ [initialTeam]: payload });
  const [selectedPlayers, setSelectedPlayers] = useState<string[]>(() => {
    const availablePlayers = rowsFromPayload(payload, "players");
    const initial = initialPlayer ? availablePlayers.find((row) => String(row.player ?? "") === initialPlayer) : undefined;
    const first = initial ?? availablePlayers[0];
    return first ? [playerKey(first)] : [];
  });
  const [isLoading, setIsLoading] = useState(false);
  const [compareTeams, setCompareTeams] = useState(false);
  const [allowMultiplePlayers, setAllowMultiplePlayers] = useState(false);
  const [playerSlotCount, setPlayerSlotCount] = useState(2);
  const [pitchKinds, setPitchKinds] = useState<PitchKind[]>(["heatmap", "in_possession", "out_of_possession"]);
  const [activeStats, setActiveStats] = useState<Array<string | null>>([null, null, null]);
  const [selectedGameState, setSelectedGameState] = useState(String(payload.score_state ?? "all"));

  useSyncFiltersToUrl({
    team: currentTeam,
    player: (selectedPlayers[0] ?? "").split("|")[0],
    gameState: selectedGameState,
  });

  const [showStatsTable, setShowStatsTable] = useState(false);
  const [excludeSetPlayPasses, setExcludeSetPlayPasses] = useState(false);
  const [highlightProgressiveActions, setHighlightProgressiveActions] = useState(false);
  const [hideUnsuccessfulActions, setHideUnsuccessfulActions] = useState(false);
  const [activePassSubtype, setActivePassSubtype] = useState<string | null>(null);
  const [showOpponentActionsInDefensiveArea, setShowOpponentActionsInDefensiveArea] = useState(false);
  const [showProgressiveReceives, setShowProgressiveReceives] = useState(false);
  const [positionFilter, setPositionFilter] = useState<string | null>(null);
  const [mobilePitchIndex, setMobilePitchIndex] = useState(0);
  const compactAnalysis = useCompactAnalysis();

  const visibleTeams = compareTeams ? teams : [currentTeam];
  const players = useMemo(
    () => visibleTeams.flatMap((team) => rowsFromPayload(payloadsByTeam[team] ?? {}, "players")),
    [visibleTeams, payloadsByTeam],
  );
  const actions = useMemo(
    () => visibleTeams.flatMap((team) => rowsFromPayload(payloadsByTeam[team] ?? {}, "actions")),
    [visibleTeams, payloadsByTeam],
  );
  const loadedActions = useMemo(
    () => Object.values(payloadsByTeam).flatMap((teamPayload) => rowsFromPayload(teamPayload, "actions")),
    [payloadsByTeam],
  );
  const shotRows = useMemo(
    () => visibleTeams.flatMap((team) => rowsFromPayload(payloadsByTeam[team] ?? {}, "shot_rows")),
    [visibleTeams, payloadsByTeam],
  );
  const shotSummaries = useMemo(
    () => visibleTeams.flatMap((team) => rowsFromPayload(payloadsByTeam[team] ?? {}, "shot_player_summary")),
    [visibleTeams, payloadsByTeam],
  );
  const selectedSet = useMemo(() => new Set(selectedPlayers), [selectedPlayers]);
  const selectedRows = players.filter((row) => selectedSet.has(playerKey(row)));
  const selectedActions = actions.filter(
    (row) => selectedSet.has(playerKey(row)) && (!positionFilter || String(row.position ?? "") === positionFilter),
  );
  const activeTeamColor = teamColors[currentTeam] ?? "#22c55e";
  const selectedTitle = selectedRows.length
    ? selectedRows.map((row) => playerOptionLabel(row)).join(", ")
    : "Select a player";
  const primaryPositions = !allowMultiplePlayers && selectedRows[0] ? playerPositions(selectedRows[0]) : [];
  const [theme, setTheme] = useState(readThemeColors);
  const unsuccessfulColor = unsuccessfulActionColor(theme.mode);

  useEffect(() => {
    const updateColors = () => setTheme(readThemeColors());
    updateColors();
    const observer = new MutationObserver(updateColors);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "data-theme"] });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    setPositionFilter(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedPlayers.join(",")]);
  const gameStateOptions = ((payloadsByTeam[currentTeam]?.game_state_options as GameStateOption[] | undefined) ?? [])
    .filter((option) => String(option.value ?? "").trim());

  const buildBody = (team: string, gameState = selectedGameState) => {
    const filters: Record<string, string | undefined> = { team, gameState, timeRange: "all" };
    if (source !== "r2") filters.job_id = jobId;
    return source !== "r2"
      ? { match_id: matchId, source, filters }
      : { match_id: matchId, source: "r2", league, season, filters };
  };

  const fetchTeamPayload = async (team: string, gameState = selectedGameState, force = false) => {
    if (!force && gameState === selectedGameState && payloadsByTeam[team]) return payloadsByTeam[team];
    const response = await getAnalysisView("player-analysis", buildBody(team, gameState));
    const nextPayload = response.payload ?? {};
    setPayloadsByTeam((current) => ({ ...current, [String(nextPayload.team ?? team)]: nextPayload }));
    return nextPayload;
  };

  const isPrimaryGoalkeeper = !allowMultiplePlayers && String(selectedRows[0]?.position_group ?? "") === "GK";
  const [goalkeeperPayload, setGoalkeeperPayload] = useState<Record<string, unknown> | null>(null);
  const [showGkOpponentActions, setShowGkOpponentActions] = useState(false);

  useEffect(() => {
    if (!isPrimaryGoalkeeper) {
      setGoalkeeperPayload(null);
      return;
    }
    let cancelled = false;
    setIsLoading(true);
    getAnalysisView("goalkeeper", buildBody(currentTeam))
      .then((response) => {
        if (!cancelled) setGoalkeeperPayload(response.payload ?? {});
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isPrimaryGoalkeeper, currentTeam, selectedGameState]);

  const loadTeam = async (team: string) => {
    if (team === currentTeam && !compareTeams) return;
    setIsLoading(true);
    try {
      const nextPayload = await fetchTeamPayload(team, selectedGameState, true);
      const nextPlayers = rowsFromPayload(nextPayload, "players");
      setCurrentTeam(String(nextPayload.team ?? team));
      setSelectedPlayers(nextPlayers[0] ? [playerKey(nextPlayers[0])] : []);
      setCompareTeams(false);
    } finally {
      setIsLoading(false);
    }
  };

  const toggleCompareTeams = async () => {
    const nextCompare = !compareTeams;
    setCompareTeams(nextCompare);
    if (!nextCompare) {
      const currentPlayers = rowsFromPayload(payloadsByTeam[currentTeam] ?? {}, "players");
      setSelectedPlayers((current) => {
        const sameTeam = current.filter((key) => key.endsWith(`|${currentTeam}`));
        return sameTeam.length ? sameTeam : currentPlayers[0] ? [playerKey(currentPlayers[0])] : [];
      });
      return;
    }
    setIsLoading(true);
    try {
      await Promise.all(teams.map((team) => fetchTeamPayload(team, selectedGameState, true)));
    } finally {
      setIsLoading(false);
    }
  };

  const loadGameState = async (gameState: string) => {
    setSelectedGameState(gameState);
    setIsLoading(true);
    try {
      await Promise.all(visibleTeams.map((team) => fetchTeamPayload(team, gameState, true)));
    } finally {
      setIsLoading(false);
    }
  };

  const togglePlayer = (row: Row) => {
    const key = playerKey(row);
    setSelectedPlayers((current) => {
      if (current.includes(key)) return current.length === 1 ? current : current.filter((item) => item !== key);
      return [...current, key];
    });
  };

  const setSinglePlayer = (key: string) => {
    if (!key) return;
    setSelectedPlayers([key]);
  };

  const selectPlayerSlot = (slotIndex: number, key: string) => {
    if (!key) return;
    setSelectedPlayers((current) => {
      const next = [...current];
      next[slotIndex] = key;
      return next.slice(0, playerSlotCount);
    });
  };

  const updatePlayerSlotCount = (count: number) => {
    const nextCount = Math.max(1, Math.min(8, Math.round(count || 1)));
    setPlayerSlotCount(nextCount);
    setSelectedPlayers((current) => {
      const next = current.slice(0, nextCount);
      const used = new Set(next);
      for (const row of players) {
        if (next.length >= nextCount) break;
        const key = playerKey(row);
        if (!used.has(key)) {
          next.push(key);
          used.add(key);
        }
      }
      return next;
    });
  };

  const toggleMultiplePlayers = () => {
    const next = !allowMultiplePlayers;
    setAllowMultiplePlayers(next);
    if (!next) {
      setSelectedPlayers((players) => players.slice(0, 1));
    } else {
      updatePlayerSlotCount(Math.max(2, selectedPlayers.length));
    }
  };

  const pitchLayout = (height = 500) => ({
    autosize: true,
    height,
    margin: { l: 8, r: 8, t: 8, b: 8 },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: theme.surface,
    font: { family: CHART_FONT_FAMILY, color: theme.text, size: compactAnalysis ? 10 : 12 },
    shapes: verticalPitchShapes(theme.pitchLine),
    xaxis: { range: [0, 68], visible: false, fixedrange: true, constrain: "domain" },
    yaxis: { range: [0, 105], visible: false, fixedrange: true, scaleanchor: "x", scaleratio: 1, constrain: "domain" },
    hoverlabel: { bgcolor: theme.hoverBg, bordercolor: colorWithAlpha(activeTeamColor, 0.6), font: { color: theme.hoverText } },
    showlegend: false,
  });

  const shotHalfPitchLayout = (height = 330) => ({
    ...pitchLayout(height),
    shapes: [
      { type: "rect", x0: 0, y0: 52.5, x1: 68, y1: 105, line: { color: theme.pitchLine, width: 2 } },
      { type: "line", x0: 0, y0: 52.5, x1: 68, y1: 52.5, line: { color: theme.pitchLine, width: 1.4 } },
      { type: "circle", x0: 24.85, y0: 43.35, x1: 43.15, y1: 61.65, line: { color: theme.pitchLine, width: 1 } },
      { type: "rect", x0: 13.84, y0: 88.5, x1: 54.16, y1: 105, line: { color: theme.pitchLine, width: 1.6 } },
      { type: "rect", x0: 24.84, y0: 99.5, x1: 43.16, y1: 105, line: { color: theme.pitchLine, width: 1.6 } },
      { type: "line", x0: 30.34, y0: 105, x1: 30.34, y1: 105.8, line: { color: theme.text, width: 3 } },
      { type: "line", x0: 37.66, y0: 105, x1: 37.66, y1: 105.8, line: { color: theme.text, width: 3 } },
      { type: "line", x0: 30.34, y0: 105.8, x1: 37.66, y1: 105.8, line: { color: theme.text, width: 3 } },
    ],
    yaxis: { range: [52.5, 105.8], visible: false, fixedrange: true, scaleanchor: "x", scaleratio: 1, constrain: "domain" },
  });

  const goalkeeperDefensiveThirdLayout = (height = 500) => ({
    ...pitchLayout(height),
    xaxis: { range: [7, 61], visible: false, fixedrange: true, constrain: "domain" },
    yaxis: { range: [0, 30], visible: false, fixedrange: true, scaleanchor: "x", scaleratio: 1, constrain: "domain" },
  });

  const goalLayout = (height = 260) => {
    const goalFront = { left: 4, right: 64, bottom: 0, top: 31 };
    const goalBack = { left: 8.5, right: 59.5, bottom: 4, top: 28.5 };
    const netLine = colorWithAlpha(theme.muted, 0.36);
    const backNetLine = colorWithAlpha(theme.muted, 0.22);
    const netPlaneLine = colorWithAlpha(theme.muted, 0.14);
    const netPlaneFill = colorWithAlpha(theme.muted, 0.08);
    const shapes = [
      { type: "line", x0: 0, y0: 0, x1: 68, y1: 0, line: { color: theme.pitchLine, width: 1.5 } },
      {
        type: "path",
        path: `M ${goalFront.left} ${goalFront.bottom} L ${goalBack.left} ${goalBack.bottom} L ${goalBack.right} ${goalBack.bottom} L ${goalFront.right} ${goalFront.bottom} Z`,
        line: { color: netPlaneLine, width: 1 },
        fillcolor: netPlaneFill,
      },
      {
        type: "path",
        path: `M ${goalFront.left} ${goalFront.top} L ${goalBack.left} ${goalBack.top} L ${goalBack.right} ${goalBack.top} L ${goalFront.right} ${goalFront.top} Z`,
        line: { color: netPlaneLine, width: 1 },
        fillcolor: colorWithAlpha(theme.muted, 0.05),
      },
      { type: "rect", x0: goalBack.left, y0: goalBack.bottom, x1: goalBack.right, y1: goalBack.top, line: { color: backNetLine, width: 1.5 } },
      ...Array.from({ length: 7 }).map((_, index) => ({
        type: "line",
        x0: goalBack.left + index * ((goalBack.right - goalBack.left) / 6),
        y0: goalBack.bottom,
        x1: goalBack.left + index * ((goalBack.right - goalBack.left) / 6),
        y1: goalBack.top,
        line: { color: backNetLine, width: 1 },
      })),
      ...Array.from({ length: 7 }).map((_, index) => ({
        type: "line",
        x0: goalBack.left,
        y0: goalBack.bottom + index * ((goalBack.top - goalBack.bottom) / 6),
        x1: goalBack.right,
        y1: goalBack.bottom + index * ((goalBack.top - goalBack.bottom) / 6),
        line: { color: backNetLine, width: 1 },
      })),
      { type: "line", x0: goalFront.left, y0: goalFront.bottom, x1: goalBack.left, y1: goalBack.bottom, line: { color: netLine, width: 1.5 } },
      { type: "line", x0: goalFront.right, y0: goalFront.bottom, x1: goalBack.right, y1: goalBack.bottom, line: { color: netLine, width: 1.5 } },
      { type: "line", x0: goalFront.left, y0: goalFront.top, x1: goalBack.left, y1: goalBack.top, line: { color: netLine, width: 1.5 } },
      { type: "line", x0: goalFront.right, y0: goalFront.top, x1: goalBack.right, y1: goalBack.top, line: { color: netLine, width: 1.5 } },
      { type: "line", x0: goalFront.left, y0: goalFront.bottom, x1: goalFront.left, y1: goalFront.top, line: { color: theme.text, width: 4 } },
      { type: "line", x0: goalFront.right, y0: goalFront.bottom, x1: goalFront.right, y1: goalFront.top, line: { color: theme.text, width: 4 } },
      { type: "line", x0: goalFront.left, y0: goalFront.top, x1: goalFront.right, y1: goalFront.top, line: { color: theme.text, width: 4 } },
      { type: "line", x0: goalFront.left, y0: goalFront.bottom, x1: goalFront.right, y1: goalFront.bottom, line: { color: theme.pitchLine, width: 1.5 } },
    ];
    return {
      autosize: true,
      height,
      margin: { l: 8, r: 8, t: 8, b: 8 },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: theme.surface,
      font: { family: CHART_FONT_FAMILY, color: theme.text, size: compactAnalysis ? 10 : 12 },
      xaxis: { range: [0, 68], visible: false, fixedrange: true, constrain: "domain" },
      yaxis: { range: [-2, 34], visible: false, fixedrange: true, constrain: "domain" },
      hoverlabel: { bgcolor: theme.hoverBg, bordercolor: colorWithAlpha(activeTeamColor, 0.6), font: { color: theme.hoverText } },
      shapes,
      showlegend: false,
    };
  };

  const heatmapTraceFor = (rows: Row[]) => {
    const points = rows
      .map((row) => pitchPoint(row))
      .filter((point) => point.x >= 0 && point.x <= 68 && point.y >= 0 && point.y <= 105);
    return [{
      x: points.map((point) => point.x),
      y: points.map((point) => point.y),
      type: "histogram2dcontour",
      colorscale: [
        [0, "rgba(34,197,94,0)"],
        [0.16, "rgba(34,197,94,0.12)"],
        [0.38, "rgba(34,197,94,0.52)"],
        [0.62, "rgba(250,204,21,0.72)"],
        [0.82, "rgba(249,115,22,0.78)"],
        [1, "rgba(239,68,68,0.9)"],
      ],
      contours: { coloring: "heatmap", showlines: false, start: 1 },
        line: { width: 0, color: "rgba(0,0,0,0)" },
      nbinsx: 20,
      nbinsy: 34,
      ncontours: 46,
      opacity: 0.94,
      showscale: false,
      hoverinfo: "skip",
    }];
  };

  const defensiveAreaTrace = (area: DefensiveArea | null): Record<string, unknown>[] => {
    if (!area) return [];
    return [{
      x: [area.x0, area.x1, area.x1, area.x0, area.x0],
      y: [area.y0, area.y0, area.y1, area.y1, area.y0],
      type: "scatter",
      mode: "lines",
      fill: "toself",
      fillcolor: "rgba(34,197,94,0.16)",
      line: { color: "rgba(34,197,94,0.45)", width: 1.5 },
      hovertemplate: "<b>Defended area</b><br>Area where this player defended most<extra></extra>",
      showlegend: false,
    }];
  };

  const opponentAreaActionTraces = (rows: Row[], invert = false): Record<string, unknown>[] => rows.flatMap((row): Record<string, unknown>[] => {
    const type = String(row.type ?? "");
    const start = pitchPointInFrame(row, invert);
    const end = pitchEndPointInFrame(row, invert);
    const hoverText = hoverActionText(row, "in_possession", `Opponent ${displayActionType(type)}`);
    const isMovement = ["Pass", "Carry"].includes(type);
    if (!isMovement) {
      return [{
        x: [start.x],
        y: [start.y],
        text: hoverText,
        type: "scatter",
        mode: "markers",
        marker: { size: 11, symbol: "diamond", color: "#facc15", line: { color: "rgba(15,23,42,0.85)", width: 1.4 } },
        hovertemplate: "%{text}<extra></extra>",
        showlegend: false,
      }];
    }
    const angle = Math.atan2(end.x - start.x, end.y - start.y) * (180 / Math.PI);
    return [{
      x: [start.x, end.x],
      y: [start.y, end.y],
      text: [hoverText, hoverText],
      type: "scatter",
      mode: "lines+markers",
      line: { color: "rgba(250,204,21,0.72)", width: 2.4, dash: type === "Carry" ? "dash" : "solid" },
      marker: {
        size: [4, 11],
        symbol: ["circle", "triangle-up"],
        angle: [0, angle],
        color: ["rgba(250,204,21,0.58)", "rgba(250,204,21,0.86)"],
        line: { color: "rgba(15,23,42,0.85)", width: 1.1 },
      },
      hovertemplate: "%{text}<extra></extra>",
      showlegend: false,
    }];
  });

  const movementTraces = (
    rows: Row[],
    kind: PitchKind,
    activeStat?: string | null,
    emphasizeProgressive = false,
    emphasizedPassSubtype?: string | null,
    defensiveArea?: DefensiveArea | null,
    opponentAreaActions: Row[] = [],
    contextRows: Row[] = rows,
  ) => {
    const traces: Record<string, unknown>[] = [];
    if (kind === "in_possession") {
      rows.filter((row) => ["Pass", "Carry"].includes(String(row.type ?? ""))).forEach((row) => {
        const start = pitchPoint(row);
        const end = pitchEndPoint(row);
        const teamColor = teamColors[String(row.team ?? "")] ?? activeTeamColor;
        const successful = row.is_successful !== false;
        const progressive = row.is_progressive === true && successful;
        const highlightProgressive = (activeStat === "Progressive actions" || emphasizeProgressive) && progressive;
        const dimForProgressiveMode = emphasizeProgressive && !progressive;
        const isCarry = String(row.type) === "Carry";
        const baseColor = isCarry ? "#38bdf8" : teamColor;
        const edgeColor = isCarry ? "#38bdf8" : passSubtypeEdgeColor(row);
        const dimForPassSubtype = Boolean(emphasizedPassSubtype) && String(row.type ?? "") === "Pass" && passSubtype(row) !== emphasizedPassSubtype;
        const shouldDim = dimForProgressiveMode || dimForPassSubtype;
        const actionAlpha = shouldDim ? 0.14 : 0.62;
        const markerAlpha = shouldDim ? 0.2 : 0.9;
        const hoverText = hoverActionText(row, kind);
        const carryAngle = Math.atan2(end.x - start.x, end.y - start.y) * (180 / Math.PI);
        traces.push({
          x: [start.x, end.x],
          y: [start.y, end.y],
          type: "scatter",
          mode: "lines+markers",
          line: {
            color: actionOutcomeColor(
              teamColor,
              successful,
              actionAlpha,
              shouldDim ? 0.13 : 0.34,
              unsuccessfulColor,
            ),
            width: isCarry ? 2.7 : 1.95,
            dash: isCarry ? "dash" : "solid",
          },
          marker: {
            size: isCarry ? [5, highlightProgressive ? 15 : 11] : [4, highlightProgressive ? 13 : 8],
            symbol: [
              actionStartSymbol(successful),
              actionEndpointSymbol(successful, isCarry ? "triangle-up" : "circle"),
            ],
            ...(isCarry ? { angle: [0, carryAngle] } : {}),
            color: [
              actionOutcomeColor(baseColor, successful, markerAlpha, shouldDim ? 0.16 : 0.58, unsuccessfulColor),
              actionOutcomeColor(baseColor, successful, markerAlpha, shouldDim ? 0.16 : 0.58, unsuccessfulColor),
            ],
            line: { color: highlightProgressive ? "#facc15" : edgeColor, width: highlightProgressive ? 3 : 1.8 },
          },
          opacity: shouldDim ? 0.5 : 1,
          text: [hoverText, hoverText],
          hovertemplate: "%{text}<extra></extra>",
          showlegend: false,
        });
      });
      rows.filter((row) => String(row.type ?? "") === "TakeOn").forEach((row) => {
        const trace = markerTrace([row], kind)[0] as Record<string, unknown>;
        if (emphasizeProgressive || emphasizedPassSubtype) trace.opacity = 0.24;
        traces.push(trace);
      });
      return traces;
    }
    if (kind === "out_of_possession") {
      return [
        ...defensiveAreaTrace(defensiveArea ?? null),
        ...opponentAreaActionTraces(opponentAreaActions, true),
        ...markerTrace(rows, kind, opponentAreaActions.length ? 0.28 : undefined),
      ];
    }
    if (kind === "touches") return touchTraces(rows, activeStat, contextRows);
    return markerTrace(rows, kind);
  };

  const touchTraces = (rows: Row[], activeStat?: string | null, contextRows: Row[] = rows) => {
    const touchRows = rows.filter((row) => String(row.type ?? "") !== "PassReceived");
    const receiveRows = rows.filter((row) => String(row.type ?? "") === "PassReceived");
    const traces: Record<string, unknown>[] = [];
    if (activeStat === "Receives") {
      const incomingPasses = receiveRows.map((receive) => {
        if (receive.source_x !== undefined && receive.source_y !== undefined) {
          return {
            ...receive,
            type: "Pass",
            player: receive.passer ?? receive.player,
            x: receive.source_x,
            y: receive.source_y,
            end_x: receive.x,
            end_y: receive.y,
          };
        }
        const sourceId = String(receive.id ?? "").replace(":received", "");
        return contextRows.find((row) => String(row.id ?? "") === sourceId && String(row.type ?? "") === "Pass");
      }).filter((row): row is Row => Boolean(row));
      incomingPasses.forEach((row) => {
        const start = pitchPoint(row);
        const end = pitchEndPoint(row);
        const hoverText = hoverActionText(row, "in_possession", "Received pass");
        traces.push({
          x: [start.x, end.x],
          y: [start.y, end.y],
          text: [hoverText, hoverText],
          type: "scatter",
          mode: "lines",
          line: { color: row.is_progressive === true && row.is_successful === true ? colorWithAlpha(activeTeamColor, 0.48) : colorWithAlpha(activeTeamColor, 0.2), width: row.is_progressive === true && row.is_successful === true ? 2.6 : 1.8, dash: row.is_progressive === true && row.is_successful === true ? "solid" : "dot" },
          hovertemplate: "%{text}<extra></extra>",
          showlegend: false,
        });
      });
    }
    traces.push(markerTrace(touchRows, "touches", activeStat === "Receives" ? 0.28 : undefined)[0]);
    traces.push(markerTrace(receiveRows, "touches", activeStat === "Touches" ? 0.28 : undefined)[0]);
    return traces;
  };

  const markerTrace = (rows: Row[], kind: PitchKind, opacity?: number) => {
    const points = rows
      .map((row) => ({ row, ...pitchPoint(row) }))
      .filter((point) => point.x >= 0 && point.x <= 68 && point.y >= 0 && point.y <= 105);
    return [{
      x: points.map((point) => point.x),
      y: points.map((point) => point.y),
      text: points.map(({ row }) => hoverActionText(row, kind)),
      type: "scatter",
      mode: "markers",
      marker: {
        size: kind === "duels" ? 16 : kind === "out_of_possession" ? 14 : kind === "shots" ? 13 : 10,
        color: points.map(({ row }) => {
          const teamColor = teamColors[String(row.team ?? "")] ?? activeTeamColor;
          if (kind === "shots") return String(row.type ?? "") === "Goal" ? "#facc15" : "#ef4444";
          if (kind === "touches") {
            if (String(row.type ?? "") === "PassReceived") return row.is_progressive === true && row.is_successful === true ? "#facc15" : "#38bdf8";
            return actionOutcomeColor(teamColor, row.is_successful !== false, 0.9, 0.58, unsuccessfulColor);
          }
          return actionOutcomeColor(teamColor, row.is_successful !== false, 0.9, 0.52, unsuccessfulColor);
        }),
        symbol: points.map(({ row }) => {
          const symbol = markerSymbol(row, kind);
          return row.is_successful === false && ["in_possession", "touches"].includes(kind)
            ? actionEndpointSymbol(false, symbol)
            : symbol;
        }),
        line: { color: "rgba(255,255,255,0.58)", width: 1.2 },
        opacity: opacity ?? 0.88,
      },
      hovertemplate: "%{text}<extra></extra>",
      showlegend: false,
    }];
  };

  const createdShotKeysForPlayers = (panelPlayers: Row[]) => {
    const playerNames = new Set(panelPlayers.map((row) => String(row.player ?? "")));
    const playerKeys = new Set(panelPlayers.map(playerKey));
    const createdKeys = new Set<string>();
    shotRows.forEach((shot) => {
      if (playerKeys.has(playerKey(shot))) return;
      const events = Array.isArray(shot.leadup_events) ? shot.leadup_events : [];
      if (events.some((event) => playerNames.has(String(event.player ?? "")))) {
        createdKeys.add(shotRowKey(shot));
      }
    });
    return createdKeys;
  };

  const shotTrace = (rows: Row[], createdKeys?: Set<string>, dimNonSca = false) => {
    const points = rows.map((row) => ({ row, ...pitchPoint(row) }));
    return [{
      x: points.map((point) => point.x),
      y: points.map((point) => point.y),
      text: points.map(({ row }) => hoverActionText(row, "shots", "Shot")),
      type: "scatter",
      mode: "markers",
      marker: {
        symbol: rows.map(shotSymbol),
        size: rows.map((row) => Math.max(12, Math.min(30, 12 + num(row.xg ?? row.xG) * 42))),
        color: rows.map((row) => ["Goal", "On target"].includes(shotOutcome(row)) ? activeTeamColor : "rgba(0,0,0,0)"),
        line: {
          color: rows.map((row) => createdKeys?.has(shotRowKey(row)) ? "#a78bfa" : shotOutcomeColor(shotOutcome(row))),
          width: rows.map((row) => createdKeys?.has(shotRowKey(row)) ? 3.2 : 2.4),
        },
        opacity: rows.map((row) => dimNonSca && !createdKeys?.has(shotRowKey(row)) ? 0.22 : 0.92),
      },
      hovertemplate: "%{text}<extra></extra>",
      showlegend: false,
    }];
  };

  const goalTrace = (rows: Row[], createdKeys?: Set<string>, dimNonSca = false) => {
    const onGoalRows = rows.filter((row) => ["Goal", "On target", "Woodwork"].includes(shotOutcome(row)));
    return [{
      x: onGoalRows.map((row) => goalMapX(row.goal_mouth_y)),
      y: onGoalRows.map((row) => num(row.goal_mouth_z)),
      text: onGoalRows.map((row) => hoverActionText(row, "shots", "Shot on goal")),
      type: "scatter",
      mode: "markers",
      marker: {
        symbol: onGoalRows.map(shotSymbol),
        size: onGoalRows.map((row) => Math.max(11, Math.min(26, 11 + num(row.xg ?? row.xG) * 38))),
        color: onGoalRows.map((row) => shotOutcome(row) === "Goal" ? activeTeamColor : "rgba(0,0,0,0)"),
        line: {
          color: onGoalRows.map((row) => createdKeys?.has(shotRowKey(row)) ? "#a78bfa" : shotOutcomeColor(shotOutcome(row))),
          width: onGoalRows.map((row) => createdKeys?.has(shotRowKey(row)) ? 3.1 : 2.3),
        },
        opacity: onGoalRows.map((row) => dimNonSca && !createdKeys?.has(shotRowKey(row)) ? 0.22 : 0.92),
      },
      hovertemplate: "%{text}<extra></extra>",
      showlegend: false,
    }];
  };

  const scaTraces = (rows: Row[], panelPlayers: Row[], showFullChain: boolean) => rows.flatMap((shot) => {
    const events = Array.isArray(shot.leadup_events) ? shot.leadup_events : [];
    const selectedPlayerNames = new Set(panelPlayers.map((row) => String(row.player ?? "")));
    const visibleEvents = showFullChain ? events : events.filter((event) => selectedPlayerNames.has(String(event.player ?? "")));
    return visibleEvents.map((event) => {
      const start = pitchPoint(event);
      const end = pitchEndPoint(event);
      const type = String(event.type ?? "SCA");
      const isPassOrCarry = ["Pass", "Carry"].includes(type);
      const scaKind: PitchKind = ["Pass", "Carry", "TakeOn"].includes(type) ? "in_possession" : "out_of_possession";
      const scaHoverText = hoverActionText(event, scaKind, `SCA ${displayActionType(type)}`);
      const color = type === "Pass" ? "#f59e0b" : type === "Carry" ? "#38bdf8" : type === "TakeOn" ? "#a78bfa" : "#22c55e";
      const isSelectedPlayerEvent = selectedPlayerNames.has(String(event.player ?? ""));
      const opacity = showFullChain ? (isSelectedPlayerEvent ? 0.95 : 0.12) : 0.34;
      return {
        x: showFullChain && isPassOrCarry ? [start.x, end.x] : [start.x],
        y: showFullChain && isPassOrCarry ? [start.y, end.y] : [start.y],
        text: showFullChain && isPassOrCarry ? [scaHoverText, scaHoverText] : scaHoverText,
        type: "scatter",
        mode: showFullChain && isPassOrCarry ? "lines+markers" : "markers",
        line: { color, width: isSelectedPlayerEvent ? 3 : 1.4, dash: type === "Carry" ? "dash" : "dot" },
        marker: {
          size: showFullChain && isPassOrCarry ? [7, 11] : 10,
          symbol: showFullChain && isPassOrCarry ? ["circle", scaSymbol(type)] : scaSymbol(type),
          color,
          line: { color: theme.text, width: isSelectedPlayerEvent ? 1.2 : 0.8 },
          opacity,
        },
        opacity,
        hovertemplate: "%{text}<extra></extra>",
        showlegend: false,
      };
    });
  });

  const shotTakerRowsForPlayers = (panelPlayers: Row[]) => {
    const keys = new Set(panelPlayers.map(playerKey));
    return shotRows.filter((row) => keys.has(playerKey(row)));
  };

  const shotsForPlayers = (panelPlayers: Row[]) => {
    const shooterRows = shotTakerRowsForPlayers(panelPlayers);
    const playerNames = new Set(panelPlayers.map((row) => String(row.player ?? "")));
    const createdRows = shotRows.filter((shot) => {
      if (shooterRows.some((row) => shotRowKey(row) === shotRowKey(shot))) return false;
      const events = Array.isArray(shot.leadup_events) ? shot.leadup_events : [];
      return events.some((event) => playerNames.has(String(event.player ?? "")));
    });
    const byId = new Map<string, Row>();
    [...shooterRows, ...createdRows].forEach((row) => byId.set(shotRowKey(row), row));
    return Array.from(byId.values());
  };

  const shotSummaryForPlayers = (panelPlayers: Row[]) => {
    const keys = new Set(panelPlayers.map((row) => `${String(row.player ?? "")}|${String(row.team ?? "")}`));
    return shotSummaries.filter((row) => keys.has(`${String(row.playerName ?? "")}|${String(row.Team ?? "")}`));
  };

  const statCounts = (rows: Row[], kind: PitchKind) => {
    const counts = new Map<string, number>();
    rows.forEach((row) => counts.set(statLabel(row, kind), (counts.get(statLabel(row, kind)) ?? 0) + 1));
    return Array.from(counts.entries()).sort((a, b) => b[1] - a[1]);
  };

  const pitchStats = (rows: Row[], kind: PitchKind, panelPlayers: Row[]) => {
    if (kind === "in_possession") {
      const passes = passRows(rows);
      const accuratePasses = completedPassCount(rows);
      return [
        ["Passes", `${accuratePasses}/${passes.length}`],
        ["Carries", rows.filter((row) => String(row.type ?? "") === "Carry").length],
        ["Dribbles", rows.filter((row) => String(row.type ?? "") === "TakeOn").length],
      ] as Array<[string, string | number]>;
    }
    if (kind === "touches") {
      return [
        ["Touches", rows.filter((row) => String(row.type ?? "") !== "PassReceived").length],
        ["Receives", rows.filter((row) => String(row.type ?? "") === "PassReceived").length],
      ] as Array<[string, string | number]>;
    }
    if (kind === "duels") {
      const ground = rows.filter((row) => String(row.type ?? "") !== "Aerial");
      const aerial = rows.filter((row) => String(row.type ?? "") === "Aerial");
      return [
        ["Ground won / total", `${ground.filter((row) => row.is_successful === true).length}/${ground.length}`],
        ["Aerial won / total", `${aerial.filter((row) => row.is_successful === true).length}/${aerial.length}`],
      ] as Array<[string, string | number]>;
    }
    if (kind === "shots") return shotMetricCounts(rows, panelPlayers);
    return statCounts(rows, kind);
  };

  const shotMetricCounts = (_rows: Row[], panelPlayers: Row[]) => {
    const playerShots = shotTakerRowsForPlayers(panelPlayers);
    const summaries = shotSummaryForPlayers(panelPlayers);
    const sca = summaries.reduce((sum, row) => sum + num(row["SCA Count"]), 0);
    const xa = summaries.reduce((sum, row) => sum + num(row.xA), 0);
    return [
      ["Shots", playerShots.length],
      ["Goals", playerShots.filter((row) => String(row.type ?? "") === "Goal").length],
      ["xG", playerShots.reduce((sum, row) => sum + num(row.xg ?? row.xG), 0).toFixed(2)],
      ["xGOT", playerShots.reduce((sum, row) => sum + num(row.xgot ?? row.xGOT), 0).toFixed(2)],
      ["SCA", sca],
      ["xA", xa.toFixed(2)],
    ] as Array<[string, string | number]>;
  };

  const distributionRows = (rows: Row[], getter: (row: Row) => string) => {
    const counts = new Map<string, number>();
    rows.forEach((row) => counts.set(getter(row), (counts.get(getter(row)) ?? 0) + 1));
    return Array.from(counts.entries()).sort((a, b) => b[1] - a[1]);
  };

  const renderPossessionBreakdown = (rows: Row[], activeStat: string | null) => {
    if (!["Passes", "Carries"].includes(String(activeStat))) return null;
    const selectedRows = activeStat === "Passes"
      ? rows.filter((row) => String(row.type ?? "") === "Pass")
      : rows.filter((row) => String(row.type ?? "") === "Carry");
    const passExpectedRows = activeStat === "Passes"
      ? [
          ["xPass", xPassTotal(selectedRows).toFixed(2)],
          ["Pass +/- Expected", `${passAboveExpected(selectedRows) >= 0 ? "+" : ""}${passAboveExpected(selectedRows).toFixed(2)}`],
          ["+/- Expected / 100", `${passAboveExpectedPer100(selectedRows) >= 0 ? "+" : ""}${passAboveExpectedPer100(selectedRows).toFixed(1)}`],
          ["Avg difficulty", `${(avgPassDifficulty(selectedRows) * 100).toFixed(1)}%`],
        ] as Array<[string, string]>
      : [];
    const epvRows = [
      ["EPV Added", `${epvAddedTotal(selectedRows) >= 0 ? "+" : ""}${epvAddedTotal(selectedRows).toFixed(3)}`],
      ["Positive EPV", selectedRows.reduce((sum, row) => sum + Math.max(0, num(row.epv_added)), 0).toFixed(3)],
      ["Negative EPV", selectedRows.reduce((sum, row) => sum + Math.min(0, num(row.epv_added)), 0).toFixed(3)],
    ] as Array<[string, string]>;
    const groups = activeStat === "Passes"
      ? [
          ["Expected Pass", passExpectedRows],
          ["EPV", epvRows],
          ["Direction", distributionRows(selectedRows, movementDirection)],
          ["Pass Type", distributionRows(selectedRows, passSubtype)],
          ["Length", distributionRows(selectedRows, movementLength)],
          ["Height", distributionRows(selectedRows, passHeight)],
        ]
      : [
          ["EPV", epvRows],
          ["Direction", distributionRows(selectedRows, movementDirection)],
          ["Length", distributionRows(selectedRows, movementLength)],
        ];
    return (
      <div className="player-analysis-breakdown">
        {groups.map(([title, values]) => (
          <div key={String(title)}>
            <strong>{String(title)}</strong>
            {(values as Array<[string, number]>).map(([label, count]) => (
              <span key={label}><em>{label}</em><b>{count}</b></span>
            ))}
          </div>
        ))}
      </div>
    );
  };

  const renderTouchBreakdown = (rows: Row[], activeStat: string | null) => {
    if (!["Touches", "Receives"].includes(String(activeStat))) return null;
    const selectedRows = activeStat === "Touches"
      ? rows.filter((row) => String(row.type ?? "") !== "PassReceived")
      : rows.filter((row) => String(row.type ?? "") === "PassReceived");
    const areaCounts = distributionRows(selectedRows, pitchAreaLabel);
    const orderedAreas = pitchAreaLabels
      .map((label) => [label, areaCounts.find(([area]) => area === label)?.[1] ?? 0] as [string, number])
      .filter(([, count]) => count > 0);
    const outcomeCounts = distributionRows(selectedRows, actionOutcome);
    const receiveDirectionCounts = distributionRows(selectedRows, receivedPassDirection);
    return (
      <div className="player-analysis-breakdown player-analysis-touch-breakdown">
        <div>
          <strong>Pitch Area</strong>
          {orderedAreas.map(([label, count]) => (
            <span key={label}><em>{label}</em><b>{count}</b></span>
          ))}
        </div>
        {activeStat === "Touches" && (
          <div>
            <strong>Outcome</strong>
            {outcomeCounts.map(([label, count]) => (
              <span key={label || "Unknown"}><em>{label || "Unknown"}</em><b>{count}</b></span>
            ))}
          </div>
        )}
        {activeStat === "Receives" && (
          <div>
            <strong>Pass Direction</strong>
            {receiveDirectionCounts.map(([label, count]) => (
              <span key={label}><em>{label}</em><b>{count}</b></span>
            ))}
          </div>
        )}
      </div>
    );
  };

  const renderScaBreakdown = (rows: Row[], panelPlayers: Row[], activeStat: string | null) => {
    if (activeStat !== "SCA") return null;
    const selectedPlayerNames = new Set(panelPlayers.map((row) => String(row.player ?? "")));
    const actions = rows.flatMap((shot) => {
      const events = Array.isArray(shot.leadup_events) ? shot.leadup_events : [];
      return events
        .filter((event) => selectedPlayerNames.has(String(event.player ?? "")))
        .map((event) => ({ event, shot }));
    });
    if (!actions.length) return null;
    return (
      <div className="player-analysis-sca-breakdown">
        <strong>SCA actions</strong>
        <div>
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Action</th>
                <th>Outcome</th>
                <th>Shot</th>
              </tr>
            </thead>
            <tbody>
              {actions.map(({ event, shot }, actionIndex) => (
                <tr key={`${shotRowKey(shot)}-${String(event.id ?? actionIndex)}`}>
                  <td>{rowClock(event)}</td>
                  <td>{displayActionType(String(event.type ?? "SCA"))} by {String(event.player ?? "")}</td>
                  <td>{actionOutcome(event)}</td>
                  <td>{shotOutcome(shot)} by {String(shot.player ?? "")} · xG {formatNumber(shot.xg ?? shot.xG, 2)} · xGOT {formatNumber(shot.xgot ?? shot.xGOT, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  const renderOopAreaSummary = (area: DefensiveArea | null, opponentAreaActions: Row[]) => {
    if (!showOpponentActionsInDefensiveArea || !area) return null;
    const xtFrom = opponentAreaActions
      .filter((row) => actionStartsInArea(row, area, true))
      .reduce((sum, row) => sum + Math.max(0, num(row.xT)), 0);
    const xtInto = opponentAreaActions
      .filter((row) => !actionStartsInArea(row, area, true) && actionEndsInArea(row, area, true))
      .reduce((sum, row) => sum + Math.max(0, num(row.xT)), 0);
    return (
      <div className="player-analysis-oop-summary">
        <span><em>xT allowed from area</em><strong>{xtFrom.toFixed(2)}</strong></span>
        <span><em>xT allowed into area</em><strong>{xtInto.toFixed(2)}</strong></span>
        <span><em>Opp. progressive actions</em><strong>{opponentAreaActions.length}</strong></span>
      </div>
    );
  };

  const renderPitchCard = (index: number, sourceRows: Row[], panelPlayers: Row[]) => {
    const kind = pitchKinds[index];
    const activeStat = activeStats[index];
    const showSca = kind === "shots" && activeStat === "SCA";
    const shotPitchRows = showSca ? shotsForPlayers(panelPlayers) : shotTakerRowsForPlayers(panelPlayers);
    const baseRows = kind === "shots" ? shotPitchRows : pitchRows(sourceRows, kind);
    const rawRows = kind === "in_possession"
      ? baseRows
        .filter((row) => !excludeSetPlayPasses || String(row.type ?? "") !== "Pass" || !isSetPlayPass(row))
        .filter((row) => !hideUnsuccessfulActions || row.is_successful === true)
      : baseRows;
    const rows = activeStat && kind !== "shots"
      ? rawRows
        .filter((row) => statMatches(row, kind, activeStat))
        .filter((row) => !(kind === "touches" && activeStat === "Receives" && showProgressiveReceives) || (row.is_progressive === true && row.is_successful === true))
      : rawRows;
    const stats = kind === "heatmap" ? [] : pitchStats(rawRows, kind, panelPlayers);
    const createdShotKeys = kind === "shots" && showSca ? createdShotKeysForPlayers(panelPlayers) : undefined;
    const panelTeams = new Set(panelPlayers.map((row) => String(row.team ?? "")));
    const defensiveArea = kind === "out_of_possession" ? defensiveAreaForRows(rawRows) : null;
    const opponentAreaActions = kind === "out_of_possession" && showOpponentActionsInDefensiveArea && defensiveArea
      ? loadedActions.filter((row) => {
          const type = String(row.type ?? "");
          return (
            !panelTeams.has(String(row.team ?? "")) &&
            ["Pass", "Carry", "TakeOn"].includes(type) &&
            row.is_successful === true &&
            row.is_progressive === true &&
            actionTouchesArea(row, defensiveArea, true)
          );
        })
      : [];
    const setKind = (value: PitchKind) => {
      setPitchKinds((current) => current.map((item, itemIndex) => itemIndex === index ? value : item));
      setActiveStats((current) => current.map((item, itemIndex) => itemIndex === index ? null : item));
    };
    const toggleOpponentAreaActions = async (checked: boolean) => {
      setShowOpponentActionsInDefensiveArea(checked);
      if (!checked) return;
      setIsLoading(true);
      try {
        await Promise.all(teams.filter((team) => !payloadsByTeam[team]).map((team) => fetchTeamPayload(team, selectedGameState, true)));
      } finally {
        setIsLoading(false);
      }
    };
    const minutes = panelPlayers.reduce((sum, row) => sum + playerMinutes(row), 0);
    const selectableStat = (label: string) => {
      if (kind === "in_possession") return ["Passes", "Carries", "Dribbles"].includes(label);
      if (kind === "shots") return label === "SCA";
      return true;
    };
    const controls = kind === "in_possession" ? (
      <div className="player-analysis-pitch-options">
        <label className="player-analysis-checkbox">
          <input
            type="checkbox"
            checked={excludeSetPlayPasses}
            onChange={(event) => {
              setExcludeSetPlayPasses(event.target.checked);
              setActivePassSubtype(null);
              setActiveStats((current) => current.map((item, itemIndex) => itemIndex === index && item === "Passes" ? null : item));
            }}
          />
          <span>Exclude set plays</span>
        </label>
        <label className="player-analysis-checkbox">
          <input
            type="checkbox"
            checked={highlightProgressiveActions}
            onChange={(event) => setHighlightProgressiveActions(event.target.checked)}
          />
          <span>Progressive actions</span>
        </label>
        <label className="player-analysis-checkbox">
          <input
            type="checkbox"
            checked={hideUnsuccessfulActions}
            onChange={(event) => setHideUnsuccessfulActions(event.target.checked)}
          />
          <span>Hide unsuccessful</span>
        </label>
      </div>
    ) : kind === "out_of_possession" ? (
      <div className="player-analysis-pitch-options">
        <label className="player-analysis-checkbox">
          <input
            type="checkbox"
            checked={showOpponentActionsInDefensiveArea}
            onChange={(event) => {
              void toggleOpponentAreaActions(event.target.checked);
            }}
          />
          <span>Opp. actions in area</span>
        </label>
      </div>
    ) : kind === "touches" ? (
      <div className="player-analysis-pitch-options">
        <label className="player-analysis-checkbox">
          <input
            type="checkbox"
            checked={showProgressiveReceives}
            onChange={(event) => setShowProgressiveReceives(event.target.checked)}
          />
          <span>Progressive receives</span>
        </label>
      </div>
    ) : null;
    const pitchHeight = compactAnalysis ? 280 : 500;
    const plotContent = kind === "heatmap" ? (
      <Plot data={heatmapTraceFor(rows)} layout={pitchLayout(pitchHeight)} config={plotConfig} className="plotly-chart" style={{ width: "100%", height: "100%" }} />
    ) : kind === "shots" ? (
      <div className="player-analysis-shot-split">
        <Plot data={goalTrace(rows, createdShotKeys, showSca)} layout={goalLayout(compactAnalysis ? 105 : 160)} config={plotConfig} className="plotly-chart" style={{ width: "100%", height: "100%" }} />
        <Plot data={[...scaTraces(rows, panelPlayers, showSca), ...shotTrace(rows, createdShotKeys, showSca)]} layout={shotHalfPitchLayout(compactAnalysis ? 225 : 356)} config={plotConfig} className="plotly-chart" style={{ width: "100%", height: "100%" }} />
      </div>
    ) : (
      <Plot data={movementTraces(rows, kind, activeStat, kind === "in_possession" && highlightProgressiveActions, kind === "in_possession" && activeStat === "Passes" ? activePassSubtype : null, defensiveArea, opponentAreaActions, rawRows)} layout={pitchLayout(pitchHeight)} config={plotConfig} className="plotly-chart" style={{ width: "100%", height: "100%" }} />
    );
    return (
      <div key={index} className={`plotly-chart-shell player-analysis-action-pitch${kind === "shots" ? " is-shots" : ""}${mobilePitchIndex === index ? " is-mobile-active" : ""}`}>
        <div className="player-analysis-pitch-head">
          <select className="select" value={kind} onChange={(event) => setKind(event.target.value as PitchKind)}>
            {pitchOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </div>
        <div className="player-analysis-pitch-control-row">{controls}</div>
        <div className="player-analysis-pitch-viewport">{plotContent}</div>
        <div className="player-analysis-stat-buttons">
          {kind === "heatmap" && (
            <span className="player-analysis-static-stat">
              <span>Minutes</span>
              <strong>{minutes || "-"}</strong>
            </span>
          )}
          {stats.map(([label, count]) => (
            selectableStat(String(label)) ? (
              <button
                key={label}
                type="button"
                className={activeStat === label ? "is-active" : ""}
                onClick={() => {
                  if (kind === "in_possession" && label !== "Passes") setActivePassSubtype(null);
                  if (kind === "in_possession" && label === "Passes" && activeStat === label) setActivePassSubtype(null);
                  setActiveStats((current) => current.map((item, itemIndex) => itemIndex === index ? item === label ? null : label : item));
                }}
              >
                <span>{label}</span>
                <strong>{count}</strong>
              </button>
            ) : (
              <span key={label} className="player-analysis-static-stat">
                <span>{label}</span>
                <strong>{count}</strong>
              </span>
            )
          ))}
        </div>
        <div className="player-analysis-detail-slot">
          {kind === "in_possession" && (
            <ActionOutcomeLegend color={activeTeamColor} unsuccessfulColor={unsuccessfulColor} />
          )}
          {kind === "shots" && (
            <div className="player-analysis-shot-legend" aria-label="Shot marker legend">
              {shotMarkerLegend.map(([label, symbol, color]) => (
                <span key={label}>
                  <i className={`is-${symbol}`} style={{ borderColor: color, color }} />
                  {label}
                </span>
              ))}
            </div>
          )}
          {kind === "out_of_possession" && renderOopAreaSummary(defensiveArea, opponentAreaActions)}
          {kind === "in_possession" && activeStat === "Passes" && (
            <div className="player-analysis-pass-legend" aria-label="Pass marker edge legend">
              {passEdgeLegend.map(([label, color]) => (
                <button
                  key={label}
                  type="button"
                  className={activePassSubtype === label ? "is-active" : ""}
                  onClick={() => setActivePassSubtype((current) => current === label ? null : label)}
                >
                  <i style={{ borderColor: color }} />
                  {label}
                </button>
              ))}
            </div>
          )}
          {kind === "out_of_possession" && (
            <div className="player-analysis-oop-legend-panel">
              <div className="player-analysis-oop-legend" aria-label="Out of possession marker legend">
                <span><i className="is-area" />Defended area</span>
                {showOpponentActionsInDefensiveArea && <span><i className="is-opponent" />Opponent action in area</span>}
                {oopMarkerLegend.map(([label, symbol]) => (
                  <span key={label}>
                    <i className={`is-marker is-${symbol}`} />
                    {label}
                  </span>
                ))}
              </div>
            </div>
          )}
          {kind === "touches" && activeStat === "Receives" && (
            <div className="player-analysis-touch-legend" aria-label="Receives marker legend">
              <span><i className="is-progressive" style={{ borderColor: activeTeamColor }} />Progressive receive</span>
              <span><i className="is-other" style={{ borderColor: colorWithAlpha(activeTeamColor, 0.45) }} />Other receive</span>
            </div>
          )}
          {kind === "shots" && renderScaBreakdown(rows, panelPlayers, activeStat)}
          {kind === "in_possession" && renderPossessionBreakdown(rawRows, activeStat)}
          {kind === "touches" && renderTouchBreakdown(rawRows, activeStat)}
        </div>
      </div>
    );
  };

  const playerStatSections = (panelPlayers: Row[], panelRows: Row[]) => {
    const panelShots = shotTakerRowsForPlayers(panelPlayers);
    const summaries = shotSummaryForPlayers(panelPlayers);
    const playerBase = panelPlayers[0] ?? {};
    const possessionRows = pitchRows(panelRows, "in_possession");
    const possessionPasses = passRows(possessionRows);
    const possessionCompleted = completedPassCount(possessionRows);
    const possessionXPass = xPassTotal(possessionRows);
    const possessionPassAE = possessionCompleted - possessionXPass;
    const possessionEPV = epvAddedTotal(possessionRows);
    const oopRows = pitchRows(panelRows, "out_of_possession");
    const duelRows = pitchRows(panelRows, "duels");
    const touchRows = pitchRows(panelRows, "touches");
    const providerTouches = panelPlayers.reduce((sum, row) => sum + num(row.touches), 0);
    return [
      {
        title: "Availability",
        rows: [["Minutes", playerMinutes(playerBase)], ["Actions", panelRows.length], ["Touches", providerTouches || touchRows.filter((row) => String(row.type) !== "PassReceived").length]],
      },
      {
        title: "In Possession",
        rows: [
          ["Passes", `${possessionCompleted}/${possessionPasses.length}`],
          ["xPass", possessionXPass.toFixed(2)],
          ["Pass +/- Expected", `${possessionPassAE >= 0 ? "+" : ""}${possessionPassAE.toFixed(2)}`],
          ["Pass +/- Exp / 100", `${passAboveExpectedPer100(possessionRows) >= 0 ? "+" : ""}${passAboveExpectedPer100(possessionRows).toFixed(1)}`],
          ["Avg pass difficulty", `${(avgPassDifficulty(possessionRows) * 100).toFixed(1)}%`],
          ["EPV Added", `${possessionEPV >= 0 ? "+" : ""}${possessionEPV.toFixed(3)}`],
          ["Carries", possessionRows.filter((row) => String(row.type) === "Carry").length],
          ["Dribbles", possessionRows.filter((row) => String(row.type) === "TakeOn").length],
          ["Progressive", possessionRows.filter((row) => row.is_progressive === true && row.is_successful === true && ["Pass", "Carry"].includes(String(row.type))).length],
        ],
      },
      {
        title: "Out Of Possession",
        rows: [["Actions", oopRows.length], ["Tackles", oopRows.filter((row) => String(row.type) === "Tackle").length], ["Interceptions", oopRows.filter((row) => String(row.type) === "Interception").length], ["Recoveries", oopRows.filter((row) => String(row.type) === "BallRecovery").length]],
      },
      {
        title: "Duels",
        rows: [["Duels", duelRows.length], ["Won", duelRows.filter((row) => row.is_successful === true).length], ["Aerial", duelRows.filter((row) => String(row.type) === "Aerial").length], ["Ground", duelRows.filter((row) => String(row.type) !== "Aerial").length]],
      },
      {
        title: "Shots + SCA",
        rows: [["Shots", panelShots.length], ["Goals", panelShots.filter((row) => String(row.type) === "Goal").length], ["xG", panelShots.reduce((sum, row) => sum + num(row.xg ?? row.xG), 0).toFixed(2)], ["xGOT", panelShots.reduce((sum, row) => sum + num(row.xgot ?? row.xGOT), 0).toFixed(2)], ["SCA", summaries.reduce((sum, row) => sum + num(row["SCA Count"]), 0)], ["xA", summaries.reduce((sum, row) => sum + num(row.xA), 0).toFixed(2)]],
      },
    ];
  };

  const renderStatsTable = (panelPlayers: Row[], panelRows: Row[]) => (
    <div className="player-analysis-stats-table">
      {playerStatSections(panelPlayers, panelRows).map((section) => (
        <div key={section.title}>
          <strong>{section.title}</strong>
          <table>
            <tbody>
              {section.rows.map(([label, value]) => (
                <tr key={String(label)}>
                  <th>{label}</th>
                  <td>{value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );

  const renderPlayerPanel = (panelRows: Row[], panelPlayers: Row[], title?: string, team?: string, panelKey = "combined") => (
    <div key={panelKey} className="player-analysis-player-panel">
      {title && (
        <div className="player-analysis-player-panel-title">
          <PlayerAvatar name={title} team={team} size={48} />
          <div>
            <strong>{title}</strong>
            {team && <span>{team}</span>}
          </div>
        </div>
      )}
      <div className="player-analysis-mobile-pitch-tabs" role="tablist" aria-label="Player visual">
        {[0, 1, 2].map((index) => {
          const option = pitchOptions.find((item) => item.value === pitchKinds[index]);
          return (
            <button
              key={index}
              type="button"
              role="tab"
              aria-selected={mobilePitchIndex === index}
              className={mobilePitchIndex === index ? "is-active" : ""}
              onClick={() => setMobilePitchIndex(index)}
            >
              {option?.label ?? `Visual ${index + 1}`}
            </button>
          );
        })}
      </div>
      <div className="player-analysis-action-grid">
        {[0, 1, 2].map((index) => renderPitchCard(index, panelRows, panelPlayers))}
      </div>
      {showStatsTable && renderStatsTable(panelPlayers, panelRows)}
    </div>
  );

  const gkPassTraces = (passMap: Row[]) => {
    const groups: Record<string, Row[]> = { "short-ok": [], "short-bad": [], "long-ok": [], "long-bad": [] };
    passMap.forEach((row) => {
      const key = `${row.long === true ? "long" : "short"}-${row.successful === true ? "ok" : "bad"}`;
      groups[key].push(row);
    });
    const lineTraces = Object.entries(groups)
      .filter(([, rows]) => rows.length)
      .map(([key, rows]) => {
        const xs: Array<number | null> = [];
        const ys: Array<number | null> = [];
        rows.forEach((row) => {
          const start = pitchPoint(row);
          const end = pitchEndPoint(row);
          xs.push(start.x, end.x, null);
          ys.push(start.y, end.y, null);
        });
        const successful = key.endsWith("ok");
        return {
          x: xs,
          y: ys,
          type: "scatter",
          mode: "lines",
          line: { color: successful ? activeTeamColor : unsuccessfulColor, width: key.startsWith("long") ? 2.2 : 1.5, dash: key.startsWith("long") ? "dot" : "solid" },
          opacity: 0.75,
          hoverinfo: "skip",
          showlegend: false,
        };
      });
    const markerTrace = {
      x: passMap.map((row) => pitchEndPoint(row).x),
      y: passMap.map((row) => pitchEndPoint(row).y),
      text: passMap.map((row) => `${row.successful ? "Completed" : "Incomplete"} ${row.long ? "long" : "short"} pass`),
      type: "scatter",
      mode: "markers",
      marker: {
        symbol: passMap.map((row) => row.long ? "diamond" : "circle"),
        size: 8,
        color: passMap.map((row) => row.successful ? activeTeamColor : "rgba(0,0,0,0)"),
        line: { color: passMap.map((row) => row.successful ? activeTeamColor : unsuccessfulColor), width: 1.6 },
      },
      hovertemplate: "%{text}<extra></extra>",
      showlegend: false,
    };
    return [...lineTraces, markerTrace];
  };

  const gkActionTraces = (rows: Row[]) => {
    const points = rows.map((row) => ({ row, ...pitchPoint(row) }));
    return [{
      x: points.map((point) => point.x),
      y: points.map((point) => point.y),
      text: points.map(({ row }) => `${rowClock(row)} · ${String(row.label ?? row.type ?? "")} · ${row.is_successful ? "Successful" : "Unsuccessful"}`),
      type: "scatter",
      mode: "markers",
      marker: {
        symbol: rows.map((row) => gkActionSymbolByType[String(row.type ?? "")] ?? "circle"),
        size: 13,
        color: rows.map((row) => row.is_successful ? activeTeamColor : "rgba(0,0,0,0)"),
        line: { color: rows.map((row) => row.is_successful ? activeTeamColor : unsuccessfulColor), width: 2 },
      },
      hovertemplate: "%{text}<extra></extra>",
      showlegend: false,
    }];
  };

  const renderGoalkeeperPanel = () => {
    const gkRow = selectedRows[0];
    const keeperName = String(gkRow?.player ?? "");
    const keeperTeam = String(gkRow?.team ?? currentTeam);
    if (!goalkeeperPayload || goalkeeperPayload.available !== true) {
      return (
        <div className="player-analysis-player-panel">
          <p className="chart-footnote">Loading goalkeeper data…</p>
        </div>
      );
    }
    const distribution = (goalkeeperPayload.distribution as Record<string, unknown>) ?? {};
    const sweeping = (goalkeeperPayload.sweeping as Record<string, unknown>) ?? {};
    const shotStopping = (goalkeeperPayload.shot_stopping as Record<string, unknown>) ?? {};
    const passMap = rowsFromPayload(goalkeeperPayload, "pass_map");
    const gkActions = rowsFromPayload(goalkeeperPayload, "gk_actions");
    const shotsFaced = rowsFromPayload(goalkeeperPayload, "shots_faced_rows");
    const gkArea = defensiveAreaForPoints(gkActions);
    const opponentTeam = teams.find((team) => team !== keeperTeam);
    const gkOpponentActions = showGkOpponentActions && gkArea
      ? loadedActions.filter((row) => {
          const type = String(row.type ?? "");
          return (
            String(row.team ?? "") === opponentTeam &&
            ["Pass", "Carry", "TakeOn"].includes(type) &&
            row.is_successful === true &&
            row.is_progressive === true &&
            actionTouchesArea(row, gkArea, true)
          );
        })
      : [];

    return (
      <div className="player-analysis-player-panel is-goalkeeper">
        <div className="player-analysis-player-panel-title">
          <PlayerAvatar name={keeperName} team={keeperTeam} size={48} />
          <div>
            <strong>{keeperName}</strong>
            <span>{keeperTeam} · Goalkeeper</span>
          </div>
        </div>
        <div className="player-analysis-action-grid">
          <div className="plotly-chart-shell player-analysis-action-pitch">
            <div className="player-analysis-pitch-head"><span>In possession</span></div>
            <div className="player-analysis-pitch-control-row" />
            <div className="player-analysis-pitch-viewport">
              <Plot data={gkPassTraces(passMap)} layout={pitchLayout(500)} config={plotConfig} className="plotly-chart" style={{ width: "100%", height: "100%" }} />
            </div>
            <div className="player-analysis-stat-buttons">
              <span className="player-analysis-static-stat"><span>Passes</span><strong>{formatNumber(distribution.completed)}/{formatNumber(distribution.passes)}</strong></span>
              <span className="player-analysis-static-stat"><span>Completion %</span><strong>{formatNumber(distribution.completion_pct, 1)}</strong></span>
              <span className="player-analysis-static-stat"><span>Long %</span><strong>{formatNumber(distribution.long_pct, 1)}</strong></span>
              <span className="player-analysis-static-stat"><span>Avg length</span><strong>{formatNumber(distribution.avg_length, 1)}</strong></span>
            </div>
            <div className="player-analysis-detail-slot">
              <ActionOutcomeLegend color={activeTeamColor} unsuccessfulColor={unsuccessfulColor} />
              <div className="player-analysis-oop-legend-panel">
                <div className="player-analysis-oop-legend" aria-label="Pass length legend">
                  {gkPassLegend.map(([label, symbol]) => (
                    <span key={label}><i className={`is-marker is-${symbol}`} />{label}</span>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div className="plotly-chart-shell player-analysis-action-pitch">
            <div className="player-analysis-pitch-head"><span>Out of possession</span></div>
            <div className="player-analysis-pitch-control-row">
              <div className="player-analysis-pitch-options">
                <label className="player-analysis-checkbox">
                  <input
                    type="checkbox"
                    checked={showGkOpponentActions}
                    onChange={async (event) => {
                      const checked = event.target.checked;
                      setShowGkOpponentActions(checked);
                      if (checked && opponentTeam && !payloadsByTeam[opponentTeam]) {
                        setIsLoading(true);
                        try {
                          await fetchTeamPayload(opponentTeam, selectedGameState, true);
                        } finally {
                          setIsLoading(false);
                        }
                      }
                    }}
                  />
                  <span>Opp. actions in area</span>
                </label>
              </div>
            </div>
            <div className="player-analysis-pitch-viewport">
              <Plot
                data={[
                  ...defensiveAreaTrace(gkArea),
                  ...opponentAreaActionTraces(gkOpponentActions, true),
                  ...gkActionTraces(gkActions),
                ]}
                layout={goalkeeperDefensiveThirdLayout(500)}
                config={plotConfig}
                className="plotly-chart"
                style={{ width: "100%", height: "100%" }}
              />
            </div>
            <div className="player-analysis-stat-buttons">
              <span className="player-analysis-static-stat"><span>Claims</span><strong>{formatNumber(sweeping.claims)}</strong></span>
              <span className="player-analysis-static-stat"><span>Pickups</span><strong>{formatNumber(sweeping.pickups)}</strong></span>
              <span className="player-analysis-static-stat"><span>Sweeper actions</span><strong>{formatNumber(sweeping.actions_outside_box)}</strong></span>
            </div>
            <div className="player-analysis-detail-slot">
              <div className="player-analysis-oop-legend-panel">
                <div className="player-analysis-oop-legend" aria-label="Goalkeeper action marker legend">
                  {showGkOpponentActions && <span><i className="is-opponent" />Opponent action in area</span>}
                  {gkActionMarkerLegend.map(([label, symbol]) => (
                    <span key={label}><i className={`is-marker is-${symbol}`} />{label}</span>
                  ))}
                </div>
              </div>
              {showGkOpponentActions && gkArea && (
                <div className="player-analysis-oop-summary">
                  <span><em>Opp. progressive actions</em><strong>{gkOpponentActions.length}</strong></span>
                </div>
              )}
            </div>
          </div>

          <div className="plotly-chart-shell player-analysis-action-pitch is-shots">
            <div className="player-analysis-pitch-head"><span>Shots faced</span></div>
            <div className="player-analysis-pitch-control-row" />
            <div className="player-analysis-pitch-viewport">
              <div className="player-analysis-shot-split">
                <Plot data={goalTrace(shotsFaced)} layout={goalLayout(160)} config={plotConfig} className="plotly-chart" style={{ width: "100%", height: "100%" }} />
                <Plot data={shotTrace(shotsFaced)} layout={shotHalfPitchLayout(356)} config={plotConfig} className="plotly-chart" style={{ width: "100%", height: "100%" }} />
              </div>
            </div>
            <div className="player-analysis-stat-buttons">
              <span className="player-analysis-static-stat"><span>Shots faced</span><strong>{formatNumber(shotStopping.sot_faced)}</strong></span>
              <span className="player-analysis-static-stat"><span>Goals conceded</span><strong>{formatNumber(shotStopping.goals_conceded)}</strong></span>
              <span className="player-analysis-static-stat"><span>Saves</span><strong>{formatNumber(shotStopping.saves)}</strong></span>
              <span className="player-analysis-static-stat"><span>Save %</span><strong>{formatNumber(shotStopping.save_pct, 1)}</strong></span>
              <span className="player-analysis-static-stat"><span>xG faced</span><strong>{formatNumber(shotStopping.xg_on_target_faced, 2)}</strong></span>
              <span className="player-analysis-static-stat"><span>xGOT faced</span><strong>{formatNumber(shotStopping.xgot_faced, 2)}</strong></span>
              <span className="player-analysis-static-stat"><span>Goals prevented</span><strong>{formatNumber(shotStopping.goals_prevented, 2)}</strong></span>
            </div>
            <div className="player-analysis-detail-slot">
              <div className="player-analysis-shot-legend" aria-label="Shot marker legend">
                {shotMarkerLegend.map(([label, symbol, color]) => (
                  <span key={label}>
                    <i className={`is-${symbol}`} style={{ borderColor: color, color }} />
                    {label}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  };

  return (
    <>
    <section className={`card stack player-analysis-section${isLoading ? " is-loading-soft" : ""}`}>
      {isLoading && <div className="analysis-loading-bar" aria-label="Loading player analysis" />}
      <div className="player-analysis-header">
        <div>
          <span className="eyebrow">Player Analysis</span>
          <div className="player-analysis-title-row">
            {!allowMultiplePlayers && selectedPlayers.slice(0, 1).map((key) => (
              <PlayerAvatar key={key} name={key.split("|")[0]} team={key.split("|")[1]} size={40} />
            ))}
            <h2>{selectedTitle}</h2>
          </div>
        </div>
        <div className="player-analysis-team-switch">
          {teams.map((team) => (
            <button key={team} type="button" className={team === currentTeam && !compareTeams ? "button" : "ghost-button"} onClick={() => loadTeam(team)}>
              {team}
            </button>
          ))}
          <DownloadPngButton
            filename={`${selectedTitle}-player-analysis`}
            title={selectedTitle}
            filters={() => {
              const labels = [...new Set(selectedRows.map((row) => String(row.team ?? "")).filter(Boolean))];
              if (selectedGameState !== "all") {
                const option = gameStateOptions.find((item) => String(item.value ?? "") === selectedGameState);
                labels.push(String(option?.label ?? selectedGameState));
              }
              return labels;
            }}
            chartLabels={() =>
              [...document.querySelectorAll<HTMLElement>(".player-analysis-action-pitch")].map((panel) => {
                const select = panel.querySelector<HTMLSelectElement>(".player-analysis-pitch-head select");
                const heading = panel.querySelector<HTMLElement>(".player-analysis-pitch-head span");
                const kindLabel = select?.selectedOptions?.[0]?.textContent?.trim() ?? heading?.textContent?.trim() ?? "";
                const active = panel.querySelector<HTMLElement>(".player-analysis-stat-buttons button.is-active span");
                const base = active?.textContent ? `${kindLabel} · ${active.textContent.trim()}` : kindLabel;
                const owner = panel.closest(".player-analysis-player-panel")?.querySelector(".player-analysis-player-panel-title strong")?.textContent?.trim();
                const isGoalkeeperPanel = Boolean(panel.closest(".player-analysis-player-panel.is-goalkeeper"));
                return owner && !allowMultiplePlayers && !isGoalkeeperPanel ? `${owner} — ${base}` : base;
              })}
            chartSubtitles={() =>
              [...document.querySelectorAll<HTMLElement>(".player-analysis-action-pitch")].map((panel) => {
                const options = [...panel.querySelectorAll<HTMLElement>(".player-analysis-checkbox")]
                  .filter((label) => label.querySelector<HTMLInputElement>("input")?.checked)
                  .map((label) => label.textContent?.trim() ?? "")
                  .filter(Boolean);
                const passSubtype = panel.querySelector<HTMLElement>(".player-analysis-pass-legend button.is-active")?.textContent?.trim();
                if (passSubtype) options.push(`Pass type: ${passSubtype}`);
                return options.join(" · ");
              })}
            chartPanels={() =>
              [...document.querySelectorAll<HTMLElement>(".player-analysis-action-pitch")].map((panel) => {
                const groups: Array<{ title?: string; stats: Array<{ label: string; value: string; active?: boolean }> }> = [];
                const counters = [...panel.querySelectorAll<HTMLElement>(".player-analysis-stat-buttons button, .player-analysis-stat-buttons .player-analysis-static-stat")]
                  .map((button) => ({
                    label: button.querySelector("span")?.textContent?.trim() ?? "",
                    value: button.querySelector("strong")?.textContent?.trim() ?? "",
                    active: button.classList.contains("is-active"),
                  }))
                  .filter((stat) => stat.label && stat.value);
                if (counters.length) groups.push({ stats: counters });
                // Detail breakdown panel (e.g. pass direction/type/length/height when "Passes" is selected).
                [...panel.querySelectorAll<HTMLElement>(".player-analysis-breakdown > div")].forEach((group) => {
                  const title = group.querySelector("strong")?.textContent?.trim() ?? "";
                  const stats = [...group.querySelectorAll("span")]
                    .map((item) => ({
                      label: item.querySelector("em")?.textContent?.trim() ?? "",
                      value: item.querySelector("b")?.textContent?.trim() ?? "",
                    }))
                    .filter((stat) => stat.label);
                  if (title && stats.length) groups.push({ title, stats });
                });
                // SCA actions table (concise: one row per action).
                const scaRows = [...panel.querySelectorAll<HTMLElement>(".player-analysis-sca-breakdown table tbody tr")];
                scaRows.slice(0, 5).forEach((row) => {
                  const cells = [...row.querySelectorAll("td")].map((cell) => cell.textContent?.trim() ?? "");
                  if (cells.length < 4) return;
                  const [time, action, outcome, shot] = cells;
                  const [shotPart, ...metricParts] = shot.split("·").map((part) => part.trim());
                  groups.push({
                    title: time,
                    stats: [
                      { label: action, value: outcome },
                      { label: shotPart ?? "", value: metricParts.join(" · ") },
                    ].filter((stat) => stat.label),
                  });
                });
                if (scaRows.length > 5) {
                  groups.push({ title: "…", stats: [{ label: `+${scaRows.length - 5} more SCA actions`, value: "" }] });
                }
                const legend = [...panel.querySelectorAll<HTMLElement>(
                  ".player-analysis-shot-legend > span, .player-analysis-pass-legend > button, .player-analysis-oop-legend > span, .player-analysis-touch-legend > span"
                )]
                  .map((item) => {
                    const swatch = item.querySelector<HTMLElement>("i");
                    const label = item.textContent?.trim() ?? "";
                    if (!swatch || !label) return null;
                    const computed = window.getComputedStyle(swatch);
                    const pick = (value: string) => value && value !== "rgba(0, 0, 0, 0)" && value !== "transparent" ? value : "";
                    const color = pick(computed.borderTopColor) || pick(computed.backgroundColor) || pick(computed.color) || "#9fb0c3";
                    const shape: "line" | "circle" | "square" | "ring" = item.closest(".player-analysis-pass-legend")
                      ? "ring"
                      : item.closest(".player-analysis-touch-legend")
                        ? "line"
                        : swatch.className.includes("is-area")
                          ? "square"
                          : "circle";
                    return { label, color, shape };
                  })
                  .filter((item): item is { label: string; color: string; shape: "line" | "circle" | "square" | "ring" } => Boolean(item));
                return { groups, legend };
              })}
            statLines={() => {
              const lines: string[] = [];
              document.querySelectorAll<HTMLElement>(".player-analysis-player-panel").forEach((panel) => {
                const owner = panel.querySelector(".player-analysis-player-panel-title strong")?.textContent?.trim();
                const table = panel.querySelector<HTMLElement>(".player-analysis-stats-table");
                if (!table) return;
                [...table.querySelectorAll("tr")].forEach((row) => {
                  const cells = [...row.querySelectorAll("th, td")].map((cell) => cell.textContent?.trim() ?? "").filter(Boolean);
                  if (cells.length >= 2) lines.push([owner, ...cells].filter(Boolean).join("  ·  "));
                });
              });
              return lines;
            }}
            titleImages={() =>
              (allowMultiplePlayers ? [] : selectedPlayers)
                .slice(0, 1)
                .map((key) => getCachedPlayerImage(key.split("|")[0], key.split("|")[1]))
                .filter((url): url is string => Boolean(url))}
            chartRowProfiles={() =>
              allowMultiplePlayers
                ? selectedRows.map((row) => {
                    const player = String(row.player ?? "");
                    const team = String(row.team ?? "");
                    return {
                      name: player,
                      sub: team,
                      image: getCachedPlayerImage(player, team),
                      color: teamColors[team] ?? activeTeamColor,
                    };
                  })
                : []}
            scopeSelector=".player-analysis-section"
            chartGroupSelector=".player-analysis-action-pitch"
            chartsPerRow={3}
            maxCharts={Math.max(3, selectedRows.length * 3)}
            expandCanvasForRows={allowMultiplePlayers}
          />
        </div>
      </div>

      <MobileAnalysisControls label="Player & filters" summary={`${selectedPlayers.length} player${selectedPlayers.length === 1 ? "" : "s"} selected`}>
      <div className="player-analysis-selector-card">
        <label>
          <span>Game state</span>
          <select className="select" value={selectedGameState} onChange={(event) => loadGameState(event.target.value)}>
            {(gameStateOptions.length ? gameStateOptions : [{ value: "all", label: "All" }]).map((option) => (
              <option key={String(option.value ?? "all")} value={String(option.value ?? "all")}>
                {String(option.label ?? option.value ?? "All")}
              </option>
            ))}
          </select>
        </label>
        {allowMultiplePlayers ? (
          <div className="player-analysis-player-slots">
            <label className="player-analysis-player-count">
              <span>Players</span>
              <input className="input" type="number" min={1} max={8} value={playerSlotCount} onChange={(event) => updatePlayerSlotCount(Number(event.target.value))} />
            </label>
            {Array.from({ length: playerSlotCount }).map((_, index) => (
              <label key={index} className="player-analysis-player-slot">
                <span>{`Player ${index + 1}`}</span>
                <select className="select" value={selectedPlayers[index] ?? ""} onChange={(event) => selectPlayerSlot(index, event.target.value)}>
                  {visibleTeams.map((team) => (
                    <optgroup key={team} label={team}>
                      {players.filter((row) => String(row.team ?? "") === team).map((row) => (
                        <option key={playerKey(row)} value={playerKey(row)}>
                          {playerOptionLabel(row)}
                        </option>
                      ))}
                    </optgroup>
                  ))}
                </select>
              </label>
            ))}
          </div>
        ) : (
          <div className="player-analysis-player-filter-row">
            <label className="player-analysis-player-filter">
              <span>Player</span>
              <select className="select" value={selectedPlayers[0] ?? ""} onChange={(event) => setSinglePlayer(event.target.value)}>
                {visibleTeams.map((team) => (
                  <optgroup key={team} label={team}>
                    {players.filter((row) => String(row.team ?? "") === team).map((row) => (
                      <option key={playerKey(row)} value={playerKey(row)}>
                        {playerOptionLabel(row)}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
            </label>
            {primaryPositions.length > 1 && (
              <label className="player-analysis-position-filter">
                <span>Position</span>
                <select className="select" value={positionFilter ?? ""} onChange={(event) => setPositionFilter(event.target.value || null)}>
                  <option value="">All positions</option>
                  {primaryPositions.map((position) => (
                    <option key={position} value={position}>{position}</option>
                  ))}
                </select>
              </label>
            )}
          </div>
        )}
        <div className="player-analysis-selector-actions">
          <button type="button" className={allowMultiplePlayers ? "button" : "ghost-button"} onClick={toggleMultiplePlayers}>
            Multiple players
          </button>
          <button type="button" className={compareTeams ? "button" : "ghost-button"} onClick={toggleCompareTeams}>
            Compare teams
          </button>
          <strong>{selectedPlayers.length} selected</strong>
          <button type="button" className={showStatsTable ? "button" : "ghost-button"} onClick={() => setShowStatsTable((current) => !current)}>
            Stats table
          </button>
        </div>
        {allowMultiplePlayers && (
          <div className="player-analysis-selected-pills">
            {selectedRows.map((row) => (
              <button key={playerKey(row)} type="button" onClick={() => togglePlayer(row)}>
                {playerOptionLabel(row)}
              </button>
            ))}
          </div>
        )}
      </div>
      </MobileAnalysisControls>

      <div className="player-analysis-main">
        {isPrimaryGoalkeeper
          ? renderGoalkeeperPanel()
          : allowMultiplePlayers
            ? selectedRows.map((row) => renderPlayerPanel(
                selectedActions.filter((action) => playerKey(action) === playerKey(row)),
                [row],
                String(row.player ?? ""),
                String(row.team ?? ""),
                playerKey(row),
              ))
            : renderPlayerPanel(selectedActions, selectedRows)}
      </div>
    </section>
    {(() => {
      if (!seasonBaseline?.available) return null;
      const contextPlayers = selectedRows.flatMap((row, index) => {
        const player = String(row.player ?? "");
        const baseline = seasonBaseline.players?.[player];
        if (!player || !baseline) return [];
        return [{
          player,
          baseline,
          color: PLAYER_COMPARISON_COLORS[index % PLAYER_COMPARISON_COLORS.length],
        }];
      });
      if (!contextPlayers.length) return null;
      const allGroups = seasonBaseline.meta?.metricGroups ?? [];
      const onlyGoalkeepers = contextPlayers.every(({ baseline }) => baseline.positionGroup === "GK");
      const groups = onlyGoalkeepers
        ? allGroups.filter((group) => group.id === "goalkeeping")
        : allGroups.filter((group) => group.id !== "goalkeeping");
      if (!groups.length) return null;
      return (
        <SeasonContextPanel
          players={contextPlayers}
          groups={groups}
        />
      );
    })()}
    </>
  );
}
