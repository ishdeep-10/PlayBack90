"use client";

import { Plot } from "../lib/plotly";

import { type MouseEvent, useEffect, useMemo, useRef, useState } from "react";
import { actionEndpointSymbol, actionOutcomeColor, actionStartSymbol, unsuccessfulActionColor } from "../lib/actionOutcome";
import { CHART_FONT_FAMILY, colorWithAlpha, num, readThemeColors } from "../lib/theme";
import { horizontalPitchShapes } from "../lib/pitch";
import { circularImageDataUrl } from "../lib/images";
import { ActionOutcomeLegend } from "./ActionOutcomeLegend";
import { getCachedPlayerImage, prefetchPlayerImages, subscribePlayerImages } from "./PlayerAvatar";


type NodeRow = {
  player_id?: number;
  player?: string;
  label?: string;
  x?: number;
  y?: number;
  play_x?: number;
  play_y?: number;
  receive_x?: number;
  receive_y?: number;
  count?: number;
  passes_made?: number;
  passes_received?: number;
  progressive_passes_made?: number;
  progressive_passes_received?: number;
  carries?: number;
  progressive_carries?: number;
  take_ons?: number;
  progressive_intensity?: number;
  avg_pass_distance?: number;
  size?: number;
  introduced_in_window?: boolean;
  part_window_player?: boolean;
};

type EdgeRow = {
  source_id?: number;
  target_id?: number;
  x0?: number;
  y0?: number;
  x1?: number;
  y1?: number;
  connection_source_x?: number;
  connection_source_y?: number;
  connection_target_x?: number;
  connection_target_y?: number;
  pass_count?: number;
  total_xt?: number;
  avg_xt?: number;
  xt_intensity?: number;
  progressive_count?: number;
  progressive_intensity?: number;
  width?: number;
};

type HeatRow = {
  x?: number;
  y?: number;
  count?: number;
  xT?: number;
};

type ActionRow = Record<string, string | number | boolean | null | undefined>;
type PlotTrace = Record<string, unknown>;

type PossessionProfile = {
  name: string;
  score: number;
  detail: string;
  description: string;
  selected: string;
};

type PossessionProfileResult = {
  profiles: PossessionProfile[];
  insight: string;
};

type Props = {
  payload: Record<string, unknown>;
  opponentPayload?: Record<string, unknown>;
  actionsPayload?: Record<string, unknown>;
  teamColor: string;
  selectedPlayerId: string | null;
  onSelectedPlayerChange: (id: string | null) => void;
  showPlayerActions: boolean;
  overlayActionTypes: string[];
  overlayShowUnsuccessful: boolean;
  highlightThird?: string;
};

type LocationMode = "both" | "played" | "received";

function shortenedLine(x0: number, y0: number, x1: number, y1: number, gap = 3.2) {
  const dx = x1 - x0;
  const dy = y1 - y0;
  const length = Math.hypot(dx, dy);
  if (!Number.isFinite(length) || length <= gap * 2) {
    return { x0, y0, x1, y1 };
  }
  const offsetX = (dx / length) * gap;
  const offsetY = (dy / length) * gap;
  return {
    x0: x0 + offsetX,
    y0: y0 + offsetY,
    x1: x1 - offsetX,
    y1: y1 - offsetY,
  };
}

function introducedNodeColor(mode: string) {
  return mode === "dark" ? "#38bdf8" : "#0369a1";
}

function edgeKey(edge: EdgeRow) {
  return `${edge.source_id ?? ""}-${edge.target_id ?? ""}-${edge.pass_count ?? 0}-${edge.total_xt ?? 0}`;
}

function clampScore(value: number) {
  return Math.max(0, Math.min(100, Math.round(value)));
}

function targetScore(value: number, target: number, maxScore = 88) {
  if (target <= 0) return 0;
  return Math.min(maxScore, (Math.max(0, value) / target) * maxScore);
}

function edgeDistance(edge: EdgeRow) {
  return Math.hypot(num(edge.x1) - num(edge.x0), num(edge.y1) - num(edge.y0));
}

function isWideY(y: number) {
  return y <= 18 || y >= 50;
}

function isAttackingHalfSpace(x: number, y: number) {
  return x >= 52.5 && ((y >= 18 && y <= 30) || (y >= 38 && y <= 50));
}

function edgeXGain(edge: EdgeRow) {
  return Math.max(num(edge.x1), num(edge.connection_target_x)) - Math.min(num(edge.x0), num(edge.connection_source_x));
}

function edgeMatchesProfile(edge: EdgeRow, profileName: string) {
  const progressive = num(edge.progressive_count) > 0;
  const xGain = edgeXGain(edge);
  const targetFinalThird = num(edge.x1) >= 70 || num(edge.connection_target_x) >= 70;
  const wideChannel = isWideY(num(edge.y1)) || isWideY(num(edge.connection_target_y));
  const halfSpaceInvolvement = isAttackingHalfSpace(num(edge.x0), num(edge.y0))
    || isAttackingHalfSpace(num(edge.x1), num(edge.y1))
    || isAttackingHalfSpace(num(edge.connection_source_x), num(edge.connection_source_y))
    || isAttackingHalfSpace(num(edge.connection_target_x), num(edge.connection_target_y));
  const highXt = num(edge.total_xt) >= 0.03 || num(edge.avg_xt) >= 0.01;
  if (["Progressive Passing", "Progressor"].includes(profileName)) return progressive;
  if (["Build-up Control", "Connector"].includes(profileName)) return num(edge.pass_count) >= 3;
  if (["Wide Progression", "Wide Outlet"].includes(profileName)) return wideChannel && (num(edge.progressive_count) >= 1 || xGain >= 10) && num(edge.pass_count) >= 2;
  if (["Central Access"].includes(profileName)) return halfSpaceInvolvement;
  if (["Final Third Threat", "Final Third Creator"].includes(profileName)) return targetFinalThird && highXt;
  if (["Directness"].includes(profileName)) return edgeDistance(edge) >= 34 || (num(edge.progressive_count) >= 2 && xGain >= 15);
  if (["Outlet Receiver"].includes(profileName)) return progressive || targetFinalThird;
  if (["Build-up Anchor"].includes(profileName)) return num(edge.x0) <= 45 && num(edge.pass_count) >= 2;
  if (["Advanced Link Player"].includes(profileName)) return num(edge.x1) >= 62 && (highXt || progressive);
  return false;
}

function actionColor(row: ActionRow, teamColor: string, mode: string) {
  const type = String(row.type ?? "");
  if (type === "Carry") return teamColor;
  if (type === "TakeOn") return mode === "dark" ? "#38bdf8" : "#2563eb";
  return mode === "dark" ? "#e2e8f0" : "#334155";
}

function isPlayerAction(row: ActionRow, selectedPlayer?: { player?: string; player_id?: number }) {
  if (!selectedPlayer) return false;
  const playerName = String(selectedPlayer.player ?? "");
  const playerId = String(selectedPlayer.player_id ?? "");
  return String(row.player ?? "") === playerName || (playerId && String(row.player_id ?? "") === playerId);
}

function profileEdgeWeight(edge: EdgeRow, profileName: string) {
  if (["Progressive Passing", "Progressor"].includes(profileName)) return num(edge.progressive_count);
  if (["Build-up Control", "Connector"].includes(profileName)) return num(edge.pass_count);
  if (["Wide Progression", "Wide Outlet"].includes(profileName)) return num(edge.progressive_count) * 2 + Math.max(0, edgeXGain(edge) / 10) + num(edge.pass_count) * 0.35;
  if (profileName === "Central Access") return num(edge.pass_count) + Math.max(0, num(edge.total_xt) * 20);
  if (["Final Third Threat", "Final Third Creator"].includes(profileName)) return num(edge.pass_count) + Math.max(0, num(edge.total_xt) * 35);
  if (profileName === "Directness") return Math.max(1, edgeDistance(edge) / 18) + num(edge.progressive_count) * 1.5;
  if (profileName === "Outlet Receiver") return num(edge.pass_count) + num(edge.progressive_count) * 2;
  if (profileName === "Build-up Anchor") return num(edge.pass_count);
  if (profileName === "Advanced Link Player") return num(edge.pass_count) + Math.max(0, num(edge.total_xt) * 30);
  return 1;
}

const PROFILE_COPY: Record<string, { description: string; selected: string }> = {
  "Build-up Control": {
    description: "Stable circulation through repeated passing links.",
    selected: "Highlights the main repeat links that keep possession moving.",
  },
  "Progressive Passing": {
    description: "Forward value through progressive passes and carries.",
    selected: "Highlights the links and players driving possession closer to goal.",
  },
  "Wide Progression": {
    description: "Advancement through wide channels.",
    selected: "Highlights the key wide-side progression routes and contributors.",
  },
  "Central Access": {
    description: "Access into attacking half spaces.",
    selected: "Highlights passes played or received in attacking half-space lanes.",
  },
  "Final Third Threat": {
    description: "Connections that reach or create value near the final third.",
    selected: "Highlights final-third links with meaningful xT.",
  },
  "Directness": {
    description: "Longer, more vertical routes through the pitch.",
    selected: "Highlights the strongest direct or vertical links only.",
  },
  Progressor: {
    description: "Player moves the ball forward through passes and carries.",
    selected: "Highlights this player's progressive connections.",
  },
  Connector: {
    description: "Player is central to circulation and repeat links.",
    selected: "Highlights this player's strongest possession links.",
  },
  "Final Third Creator": {
    description: "Player connects possession into dangerous final-third zones.",
    selected: "Highlights this player's final-third/xT links.",
  },
  "Outlet Receiver": {
    description: "Player receives as a release option, especially progressive passes.",
    selected: "Highlights receiving links that find this player in useful areas.",
  },
  "Build-up Anchor": {
    description: "Deep player anchoring early possession.",
    selected: "Highlights deeper build-up links involving this player.",
  },
  "Advanced Link Player": {
    description: "Advanced connector between midfield and attack.",
    selected: "Highlights advanced links and value-adding connections.",
  },
  "Wide Outlet": {
    description: "Wide player used as an outlet or progression lane.",
    selected: "Highlights wide progression involving this player.",
  },
};

function buildPossessionProfiles(nodes: NodeRow[], edges: EdgeRow[], selectedPlayerId: string | null, opponentNodes: NodeRow[] = [], opponentEdges: EdgeRow[] = []): PossessionProfileResult {
  const scopedEdges = selectedPlayerId
    ? edges.filter((edge) => String(edge.source_id ?? "") === selectedPlayerId || String(edge.target_id ?? "") === selectedPlayerId)
    : edges;
  const totalPasses = Math.max(1, scopedEdges.reduce((sum, edge) => sum + num(edge.pass_count), 0));
  const totalEdges = Math.max(1, scopedEdges.length);
  const progressive = scopedEdges.reduce((sum, edge) => sum + num(edge.progressive_count), 0);
  const totalXt = scopedEdges.reduce((sum, edge) => sum + num(edge.total_xt), 0);
  const finalThirdEdges = scopedEdges.filter((edge) => num(edge.x1) >= 70 || num(edge.connection_target_x) >= 70).length;
  const centralEdges = scopedEdges.filter((edge) => edgeMatchesProfile(edge, "Central Access")).length;
  const centralPasses = scopedEdges.filter((edge) => edgeMatchesProfile(edge, "Central Access")).reduce((sum, edge) => sum + num(edge.pass_count), 0);
  const wideEdges = scopedEdges.filter((edge) => edgeMatchesProfile(edge, "Wide Progression")).length;
  const directEdges = scopedEdges.filter((edge) => edgeMatchesProfile(edge, "Directness")).length;
  const totalProgressiveCarries = nodes.reduce((sum, node) => sum + num(node.progressive_carries), 0);
  const totalTakeOns = nodes.reduce((sum, node) => sum + num(node.take_ons), 0);
  const progressionActions = progressive + totalProgressiveCarries;
  const selectedNode = selectedPlayerId ? nodes.find((node) => String(node.player_id ?? node.player ?? "") === selectedPlayerId) : null;

  const teamProfiles: PossessionProfile[] = [
    {
      name: "Build-up Control",
      score: clampScore(
        targetScore(totalPasses, Math.max(1, nodes.length * 8), 42)
        + targetScore(totalEdges, Math.max(1, nodes.length * 2.4), 28)
        + Math.min(14, Math.max(0, totalXt) * 42),
      ),
      detail: `${totalPasses} successful passes across ${totalEdges} links`,
      description: PROFILE_COPY["Build-up Control"].description,
      selected: PROFILE_COPY["Build-up Control"].selected,
    },
    {
      name: "Progressive Passing",
      score: clampScore(
        targetScore(progressionActions, Math.max(1, nodes.length * 3.4), 58)
        + Math.min(16, Math.max(0, totalXt) * 42)
        + targetScore(wideEdges + directEdges, Math.max(1, nodes.length * 1.4), 12),
      ),
      detail: `${progressive} progressive passes, ${totalProgressiveCarries} progressive carries`,
      description: PROFILE_COPY["Progressive Passing"].description,
      selected: PROFILE_COPY["Progressive Passing"].selected,
    },
    {
      name: "Wide Progression",
      score: clampScore(
        targetScore(wideEdges, Math.max(1, nodes.length * 1.35), 58)
        + targetScore(progressionActions, Math.max(1, nodes.length * 4.5), 16)
        + targetScore(totalTakeOns, Math.max(1, nodes.length * 1.6), 10),
      ),
      detail: `${wideEdges} advancing wide links`,
      description: PROFILE_COPY["Wide Progression"].description,
      selected: PROFILE_COPY["Wide Progression"].selected,
    },
    {
      name: "Central Access",
      score: clampScore(
        targetScore(centralPasses, Math.max(1, nodes.length * 7), 58)
        + targetScore(centralEdges, Math.max(1, nodes.length * 1.8), 22)
        + Math.min(10, Math.max(0, totalXt) * 28),
      ),
      detail: `${centralPasses} half-space passes across ${centralEdges} links`,
      description: PROFILE_COPY["Central Access"].description,
      selected: PROFILE_COPY["Central Access"].selected,
    },
    {
      name: "Final Third Threat",
      score: clampScore(
        targetScore(finalThirdEdges, Math.max(1, nodes.length * 1.25), 56)
        + Math.min(24, Math.max(0, totalXt) * 58),
      ),
      detail: `${finalThirdEdges} final-third links, ${totalXt.toFixed(3)} total xT`,
      description: PROFILE_COPY["Final Third Threat"].description,
      selected: PROFILE_COPY["Final Third Threat"].selected,
    },
    {
      name: "Directness",
      score: clampScore(
        targetScore(directEdges, Math.max(1, nodes.length * 1.45), 68)
        + targetScore(progressionActions, Math.max(1, nodes.length * 5.5), 14),
      ),
      detail: `${directEdges} direct/progressive links`,
      description: PROFILE_COPY.Directness.description,
      selected: PROFILE_COPY.Directness.selected,
    },
  ].sort((a, b) => b.score - a.score);
  const opponentProfiles: PossessionProfile[] = !selectedPlayerId && opponentNodes.length && opponentEdges.length
    ? buildPossessionProfiles(opponentNodes, opponentEdges, null).profiles
    : [];
  const matchupTeamProfiles: PossessionProfile[] = opponentProfiles.length
    ? teamProfiles.map((profile) => {
      const opponentProfile = opponentProfiles.find((row) => row.name === profile.name);
      if (!opponentProfile) return profile;
      const rawScore = profile.score;
      const opponentScore = opponentProfile.score;
      const delta = rawScore - opponentScore;
      const deltaLabel = delta === 0 ? "level" : `${delta > 0 ? "+" : ""}${delta} vs opponent`;
      return {
        ...profile,
        score: clampScore(50 + delta * 0.65),
        detail: `${profile.detail} · internal ${rawScore}/100 · opponent ${opponentScore}/100`,
        description: `${profile.description} Matchup score: 50 is level; above 50 means stronger than opponent in this filter.`,
        selected: `${profile.selected} ${deltaLabel}.`,
      };
    }).sort((a, b) => b.score - a.score)
    : teamProfiles;

  const outgoingEdges = selectedPlayerId ? scopedEdges.filter((edge) => String(edge.source_id ?? "") === selectedPlayerId) : scopedEdges;
  const incomingEdges = selectedPlayerId ? scopedEdges.filter((edge) => String(edge.target_id ?? "") === selectedPlayerId) : scopedEdges;
  const outgoingProg = outgoingEdges.reduce((sum, edge) => sum + num(edge.progressive_count), 0);
  const incomingProg = incomingEdges.reduce((sum, edge) => sum + num(edge.progressive_count), 0);
  const outgoingXt = outgoingEdges.reduce((sum, edge) => sum + num(edge.total_xt), 0);
  const finalThirdOut = outgoingEdges.filter((edge) => num(edge.x1) >= 70).length;
  const buildUpLinks = scopedEdges.filter((edge) => num(edge.x0) <= 45).length;
  const advancedLinks = scopedEdges.filter((edge) => num(edge.x1) >= 62).length;
  const wideLinks = scopedEdges.filter((edge) => edgeMatchesProfile(edge, "Wide Outlet")).length;
  const progressiveCarries = num(selectedNode?.progressive_carries);
  const takeOns = num(selectedNode?.take_ons);
  const receivedPasses = num(selectedNode?.passes_received);
  const madePasses = num(selectedNode?.passes_made);
  const maxInvolvement = Math.max(1, ...nodes.map((node) => num(node.passes_made) + num(node.passes_received)));
  const maxReceived = Math.max(1, ...nodes.map((node) => num(node.passes_received)));
  const maxProgressiveReceived = Math.max(1, ...nodes.map((node) => num(node.progressive_passes_received)));
  const playerIds = nodes.map((node) => String(node.player_id ?? node.player ?? ""));
  const maxPlayerMetric = (calculator: (id: string) => number) => Math.max(1, ...playerIds.map(calculator));
  const maxOutgoingXt = maxPlayerMetric((id) => edges.filter((edge) => String(edge.source_id ?? "") === id).reduce((sum, edge) => sum + num(edge.total_xt), 0));
  const maxProgressionActions = Math.max(1, ...nodes.map((node) => num(node.progressive_passes_made) + num(node.progressive_carries)));
  const maxTakeOns = Math.max(1, ...nodes.map((node) => num(node.take_ons)));
  const maxScopedLinks = maxPlayerMetric((id) => edges.filter((edge) => String(edge.source_id ?? "") === id || String(edge.target_id ?? "") === id).length);
  const maxFinalThirdOut = maxPlayerMetric((id) => edges.filter((edge) => String(edge.source_id ?? "") === id && num(edge.x1) >= 70).length);
  const maxBuildUpLinks = maxPlayerMetric((id) => edges.filter((edge) => (String(edge.source_id ?? "") === id || String(edge.target_id ?? "") === id) && num(edge.x0) <= 45).length);
  const maxAdvancedLinks = maxPlayerMetric((id) => edges.filter((edge) => (String(edge.source_id ?? "") === id || String(edge.target_id ?? "") === id) && num(edge.x1) >= 62).length);
  const maxWideLinks = maxPlayerMetric((id) => edges.filter((edge) => (String(edge.source_id ?? "") === id || String(edge.target_id ?? "") === id) && edgeMatchesProfile(edge, "Wide Outlet")).length);
  const selectedInvolvement = madePasses + receivedPasses;
  const selectedX = num(selectedNode?.x);
  const selectedY = num(selectedNode?.y);
  const isWidePlayer = selectedY <= 20 || selectedY >= 48;

  const basePlayerProfiles = [
    {
      name: "Progressor",
      score: clampScore(
        ((outgoingProg + progressiveCarries) / maxProgressionActions) * 46
        + (Math.max(0, outgoingXt) / Math.max(0.001, maxOutgoingXt)) * 26
        + (takeOns / maxTakeOns) * 8,
      ),
      detail: `${outgoingProg} progressive passes, ${progressiveCarries} progressive carries`,
      description: PROFILE_COPY.Progressor.description,
      selected: PROFILE_COPY.Progressor.selected,
    },
    {
      name: "Connector",
      score: clampScore(
        (selectedInvolvement / maxInvolvement) * 46
        + (scopedEdges.length / maxScopedLinks) * 28
        + targetScore(selectedInvolvement, 30, 10),
      ),
      detail: `${madePasses} made, ${receivedPasses} received vs team max ${maxInvolvement}`,
      description: PROFILE_COPY.Connector.description,
      selected: PROFILE_COPY.Connector.selected,
    },
    {
      name: "Final Third Creator",
      score: clampScore(
        (finalThirdOut / maxFinalThirdOut) * 42
        + (Math.max(0, outgoingXt) / Math.max(0.001, maxOutgoingXt)) * 28
        + (takeOns / maxTakeOns) * 8,
      ),
      detail: `${finalThirdOut} final-third links, ${outgoingXt.toFixed(3)} xT, ${takeOns} take-ons`,
      description: PROFILE_COPY["Final Third Creator"].description,
      selected: PROFILE_COPY["Final Third Creator"].selected,
    },
    {
      name: "Outlet Receiver",
      score: clampScore(
        (num(selectedNode?.progressive_passes_received) / maxProgressiveReceived) * 42
        + (receivedPasses / maxReceived) * 34
        + targetScore(receivedPasses, 18, 8),
      ),
      detail: `${num(selectedNode?.progressive_passes_received)} progressive received, ${receivedPasses} total received`,
      description: PROFILE_COPY["Outlet Receiver"].description,
      selected: PROFILE_COPY["Outlet Receiver"].selected,
    },
  ];

  const rolePlayerProfiles = [
    selectedX <= 45 ? {
      name: "Build-up Anchor",
      score: clampScore(
        (madePasses / Math.max(1, maxInvolvement)) * 34
        + (buildUpLinks / maxBuildUpLinks) * 44
        + targetScore(buildUpLinks, 8, 8),
      ),
      detail: `${buildUpLinks} deeper build-up links`,
      description: PROFILE_COPY["Build-up Anchor"].description,
      selected: PROFILE_COPY["Build-up Anchor"].selected,
    } : null,
    selectedX >= 60 ? {
      name: "Advanced Link Player",
      score: clampScore(
        (advancedLinks / maxAdvancedLinks) * 40
        + (Math.max(0, outgoingXt) / Math.max(0.001, maxOutgoingXt)) * 26
        + (takeOns / maxTakeOns) * 10,
      ),
      detail: `${advancedLinks} advanced links, ${takeOns} take-ons`,
      description: PROFILE_COPY["Advanced Link Player"].description,
      selected: PROFILE_COPY["Advanced Link Player"].selected,
    } : null,
    isWidePlayer ? {
      name: "Wide Outlet",
      score: clampScore(
        (wideLinks / maxWideLinks) * 42
        + (incomingProg / Math.max(1, maxProgressiveReceived)) * 22
        + ((progressiveCarries + takeOns) / Math.max(1, maxProgressionActions + maxTakeOns)) * 12,
      ),
      detail: `${wideLinks} wide progression links, ${progressiveCarries} progressive carries`,
      description: PROFILE_COPY["Wide Outlet"].description,
      selected: PROFILE_COPY["Wide Outlet"].selected,
    } : null,
  ].filter((profile): profile is PossessionProfile => Boolean(profile));

  const playerProfiles = [...basePlayerProfiles, ...rolePlayerProfiles].sort((a, b) => b.score - a.score);

  const profiles: PossessionProfile[] = selectedPlayerId ? playerProfiles : matchupTeamProfiles;
  const top = profiles[0];
  return {
    profiles,
    insight: selectedPlayerId
      ? `Selected player profiles strongest as ${top.name.toLowerCase()} (${top.score}/100).`
      : `Team possession profile strongest as ${top.name.toLowerCase()} (${top.score}/100).`,
  };
}

export function PassNetworkPlotly({
  payload,
  opponentPayload,
  actionsPayload,
  teamColor,
  selectedPlayerId,
  onSelectedPlayerChange,
  showPlayerActions,
  overlayActionTypes,
  overlayShowUnsuccessful,
  highlightThird,
}: Props) {
  const [themeColors, setThemeColors] = useState(readThemeColors);
  const unsuccessfulColor = unsuccessfulActionColor(themeColors.mode);
  const [locationModes, setLocationModes] = useState<Record<string, LocationMode>>({});
  const [showProgressive, setShowProgressive] = useState(false);
  const [selectedProfile, setSelectedProfile] = useState("");
  const [nodeHeadshots, setNodeHeadshots] = useState<Record<string, string>>({});
  const [comboMode, setComboMode] = useState<"off" | "pairs" | "triangles">("off");
  const composedHeadshots = useRef(new Set<string>());
  const nodes = (payload.nodes as NodeRow[] | undefined) ?? [];
  const edges = (payload.edges as EdgeRow[] | undefined) ?? [];
  const actions = (actionsPayload?.actions as ActionRow[] | undefined) ?? [];
  const opponentNodes = (opponentPayload?.nodes as NodeRow[] | undefined) ?? [];
  const opponentEdges = (opponentPayload?.edges as EdgeRow[] | undefined) ?? [];
  const heatmap = (payload.heatmap as HeatRow[] | undefined) ?? [];
  const heatPoints = (payload.heat_points as HeatRow[] | undefined) ?? heatmap;
  const mergedWindowNote = String(payload.merged_window_note ?? "");

  useEffect(() => {
    const updateColors = () => setThemeColors(readThemeColors());
    updateColors();
    const observer = new MutationObserver(updateColors);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "data-theme"] });
    return () => observer.disconnect();
  }, []);

  const teamName = String(payload.team ?? "");
  useEffect(() => {
    let cancelled = false;
    const names = nodes.map((row) => String(row.player ?? "")).filter(Boolean);
    if (!names.length) return undefined;
    prefetchPlayerImages(names, teamName);
    const compose = async () => {
      for (const name of names) {
        const key = `${name}|${teamName}|${teamColor}`;
        if (composedHeadshots.current.has(key)) continue;
        const url = getCachedPlayerImage(name, teamName);
        if (!url) continue;
        composedHeadshots.current.add(key);
        const circular = await circularImageDataUrl(url, teamColor);
        if (circular && !cancelled) setNodeHeadshots((prev) => ({ ...prev, [key]: circular }));
      }
    };
    void compose();
    const unsubscribe = subscribePlayerImages(() => {
      void compose();
    });
    return () => {
      cancelled = true;
      unsubscribe();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, teamName, teamColor]);

  const basePositionedNodes = useMemo(() => nodes.map((row) => {
    const id = String(row.player_id ?? row.player ?? "");
    const mode = locationModes[id] ?? "both";
    const x = mode === "played" ? num(row.play_x, num(row.x)) : mode === "received" ? num(row.receive_x, num(row.x)) : num(row.x);
    const y = mode === "played" ? num(row.play_y, num(row.y)) : mode === "received" ? num(row.receive_y, num(row.y)) : num(row.y);
    return { ...row, id, display_x: x, display_y: y, mode };
  }), [locationModes, nodes]);

  const selectedConnectionPositions = useMemo(() => {
    const positions = new Map<string, { x: number; y: number; weight: number }>();
    if (!selectedPlayerId) return positions;

    const addPosition = (id: string, x: number, y: number, weight: number) => {
      const current = positions.get(id) ?? { x: 0, y: 0, weight: 0 };
      positions.set(id, {
        x: current.x + x * weight,
        y: current.y + y * weight,
        weight: current.weight + weight,
      });
    };

    edges.forEach((edge) => {
      const sourceId = String(edge.source_id ?? "");
      const targetId = String(edge.target_id ?? "");
      const weight = Math.max(1, num(edge.pass_count, 1));
      if (sourceId === selectedPlayerId) {
        addPosition(sourceId, num(edge.connection_source_x, num(edge.x0)), num(edge.connection_source_y, num(edge.y0)), weight);
        addPosition(targetId, num(edge.connection_target_x, num(edge.x1)), num(edge.connection_target_y, num(edge.y1)), weight);
      } else if (targetId === selectedPlayerId) {
        addPosition(sourceId, num(edge.connection_source_x, num(edge.x0)), num(edge.connection_source_y, num(edge.y0)), weight);
        addPosition(targetId, num(edge.connection_target_x, num(edge.x1)), num(edge.connection_target_y, num(edge.y1)), weight);
      }
    });

    positions.forEach((position, id) => {
      if (position.weight <= 0) return;
      positions.set(id, { x: position.x / position.weight, y: position.y / position.weight, weight: position.weight });
    });
    return positions;
  }, [edges, selectedPlayerId]);

  const positionedNodes = useMemo(() => basePositionedNodes.map((row) => {
    const selectedPosition = selectedConnectionPositions.get(row.id);
    if (!selectedPosition) return row;
    return {
      ...row,
      display_x: selectedPosition.x,
      display_y: selectedPosition.y,
      mode: "selected links" as LocationMode | "selected links",
    };
  }), [basePositionedNodes, selectedConnectionPositions]);

  const nodeById = useMemo(() => {
    const lookup = new Map<string, typeof positionedNodes[number]>();
    positionedNodes.forEach((node) => lookup.set(String(node.player_id ?? node.player ?? ""), node));
    return lookup;
  }, [positionedNodes]);

  useEffect(() => {
    if (selectedPlayerId && !nodeById.has(selectedPlayerId)) {
      onSelectedPlayerChange(null);
    }
  }, [nodeById, onSelectedPlayerChange, selectedPlayerId]);

  const selectedNetwork = useMemo(() => {
    if (!selectedPlayerId) {
      return {
        connectedIds: new Set<string>(),
        selectedEdges: [] as EdgeRow[],
        outgoingPasses: 0,
        incomingPasses: 0,
        outgoingXt: 0,
        incomingXt: 0,
        connections: [] as Array<{ id: string; player: string; passes: number; xt: number; direction: string }>,
      };
    }

    const connectedIds = new Set<string>();
    const selectedEdges = edges.filter((edge) => {
      const sourceId = String(edge.source_id ?? "");
      const targetId = String(edge.target_id ?? "");
      const isSelectedEdge = sourceId === selectedPlayerId || targetId === selectedPlayerId;
      if (isSelectedEdge) {
        connectedIds.add(sourceId === selectedPlayerId ? targetId : sourceId);
      }
      return isSelectedEdge;
    });

    const outgoingPasses = selectedEdges
      .filter((edge) => String(edge.source_id ?? "") === selectedPlayerId)
      .reduce((sum, edge) => sum + num(edge.pass_count), 0);
    const incomingPasses = selectedEdges
      .filter((edge) => String(edge.target_id ?? "") === selectedPlayerId)
      .reduce((sum, edge) => sum + num(edge.pass_count), 0);
    const outgoingXt = selectedEdges
      .filter((edge) => String(edge.source_id ?? "") === selectedPlayerId)
      .reduce((sum, edge) => sum + num(edge.total_xt), 0);
    const incomingXt = selectedEdges
      .filter((edge) => String(edge.target_id ?? "") === selectedPlayerId)
      .reduce((sum, edge) => sum + num(edge.total_xt), 0);

    const connectionMap = new Map<string, { id: string; player: string; passes: number; xt: number; made: number; received: number }>();
    selectedEdges.forEach((edge) => {
      const sourceId = String(edge.source_id ?? "");
      const targetId = String(edge.target_id ?? "");
      const otherId = sourceId === selectedPlayerId ? targetId : sourceId;
      const existing = connectionMap.get(otherId) ?? {
        id: otherId,
        player: nodeById.get(otherId)?.player ?? "Player",
        passes: 0,
        xt: 0,
        made: 0,
        received: 0,
      };
      const passCount = num(edge.pass_count);
      existing.passes += passCount;
      existing.xt += num(edge.total_xt);
      if (sourceId === selectedPlayerId) existing.made += passCount;
      if (targetId === selectedPlayerId) existing.received += passCount;
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

    return { connectedIds, selectedEdges, outgoingPasses, incomingPasses, outgoingXt, incomingXt, connections };
  }, [edges, nodeById, selectedPlayerId]);

  const selectedPlayer = selectedPlayerId ? nodeById.get(selectedPlayerId) : null;
  const selectedPlayerActions = useMemo(() => actions.filter((row) => {
    if (!selectedPlayer || !isPlayerAction(row, selectedPlayer)) return false;
    if (!overlayShowUnsuccessful && row.is_successful === false) return false;
    if (overlayActionTypes.length && !overlayActionTypes.includes(String(row.type ?? ""))) return false;
    return true;
  }), [actions, overlayActionTypes, overlayShowUnsuccessful, selectedPlayer]);
  const possessionProfile = useMemo(
    () => buildPossessionProfiles(nodes, edges, selectedPlayerId, opponentNodes, opponentEdges),
    [edges, nodes, opponentEdges, opponentNodes, selectedPlayerId],
  );
  const profileEdgeKeys = useMemo(() => {
    if (!selectedProfile) return new Set<string>();
    const scopedEdges = selectedPlayerId
      ? edges.filter((edge) => String(edge.source_id ?? "") === selectedPlayerId || String(edge.target_id ?? "") === selectedPlayerId)
      : edges;
    return new Set(scopedEdges.filter((edge) => edgeMatchesProfile(edge, selectedProfile)).map(edgeKey));
  }, [edges, selectedPlayerId, selectedProfile]);
  const profileNodeIds = useMemo(() => {
    const ids = new Set<string>();
    if (!selectedProfile) return ids;
    const contributions = new Map<string, number>();
    const scopedEdges = selectedPlayerId
      ? edges.filter((edge) => String(edge.source_id ?? "") === selectedPlayerId || String(edge.target_id ?? "") === selectedPlayerId)
      : edges;
    scopedEdges.forEach((edge) => {
      if (!profileEdgeKeys.has(edgeKey(edge))) return;
      const sourceId = String(edge.source_id ?? "");
      const targetId = String(edge.target_id ?? "");
      const weight = profileEdgeWeight(edge, selectedProfile);
      const sourceWeight = ["Outlet Receiver"].includes(selectedProfile) ? weight * 0.25 : weight;
      const targetWeight = ["Progressive Passing", "Progressor", "Directness"].includes(selectedProfile) ? weight * 0.35 : weight;
      contributions.set(sourceId, (contributions.get(sourceId) ?? 0) + sourceWeight);
      contributions.set(targetId, (contributions.get(targetId) ?? 0) + targetWeight);
    });
    const maxContribution = Math.max(0, ...Array.from(contributions.values()));
    const threshold = Math.max(1.5, maxContribution * 0.35);
    Array.from(contributions.entries())
      .sort((first, second) => second[1] - first[1])
      .slice(0, selectedPlayerId ? 6 : 7)
      .forEach(([id, value]) => {
        if (value >= threshold || id === selectedPlayerId) ids.add(id);
      });
    return ids;
  }, [edges, profileEdgeKeys, selectedPlayerId, selectedProfile]);
  // Opt-in combination overlay: strongest mutual pass pairs / passing triangles
  // derived from the currently displayed network edges.
  const comboHighlight = useMemo(() => {
    if (comboMode === "off") return null;
    const pairKeyOf = (a: string, b: string) => [a, b].sort().join("|");
    const pairMap = new Map<string, { a: string; b: string; passes: number; xt: number }>();
    edges.forEach((edge) => {
      const a = String(edge.source_id ?? "");
      const b = String(edge.target_id ?? "");
      if (!a || !b || a === b) return;
      const key = pairKeyOf(a, b);
      const current = pairMap.get(key) ?? { a, b, passes: 0, xt: 0 };
      current.passes += num(edge.pass_count);
      current.xt += num(edge.total_xt);
      pairMap.set(key, current);
    });
    if (comboMode === "pairs") {
      const pairs = [...pairMap.values()].sort((x, z) => z.passes - x.passes).slice(0, 5);
      return {
        pairs,
        triangles: [] as Array<{ ids: [string, string, string]; passes: number }>,
        nodeIds: new Set(pairs.flatMap((pair) => [pair.a, pair.b])),
        pairKeys: new Set(pairs.map((pair) => pairKeyOf(pair.a, pair.b))),
      };
    }
    const findTriangles = (minPasses: number) => {
      const ids = nodes.map((row) => String(row.player_id ?? row.player ?? "")).filter(Boolean);
      const found: Array<{ ids: [string, string, string]; passes: number }> = [];
      for (let i = 0; i < ids.length; i += 1) {
        for (let j = i + 1; j < ids.length; j += 1) {
          const ab = pairMap.get(pairKeyOf(ids[i], ids[j]));
          if (!ab || ab.passes < minPasses) continue;
          for (let k = j + 1; k < ids.length; k += 1) {
            const bc = pairMap.get(pairKeyOf(ids[j], ids[k]));
            const ca = pairMap.get(pairKeyOf(ids[k], ids[i]));
            if (!bc || !ca || bc.passes < minPasses || ca.passes < minPasses) continue;
            found.push({ ids: [ids[i], ids[j], ids[k]], passes: ab.passes + bc.passes + ca.passes });
          }
        }
      }
      return found.sort((x, z) => z.passes - x.passes).slice(0, 3);
    };
    const triangles = (() => {
      const strict = findTriangles(3);
      return strict.length ? strict : findTriangles(1);
    })();
    const trianglePairKeys = new Set<string>();
    triangles.forEach((triangle) => {
      const [a, b, c] = triangle.ids;
      trianglePairKeys.add(pairKeyOf(a, b));
      trianglePairKeys.add(pairKeyOf(b, c));
      trianglePairKeys.add(pairKeyOf(c, a));
    });
    return {
      pairs: [] as Array<{ a: string; b: string; passes: number; xt: number }>,
      triangles,
      nodeIds: new Set(triangles.flatMap((triangle) => triangle.ids)),
      pairKeys: trianglePairKeys,
    };
  }, [comboMode, edges, nodes]);

  const traces = useMemo(() => {
    const actionModeActive = Boolean(showPlayerActions && selectedPlayer);
    const heatTrace = {
      x: heatPoints.map((row) => num(row.x)),
      y: heatPoints.map((row) => num(row.y)),
      z: heatPoints.map((row) => Math.max(0.01, num(row.xT, num(row.count, 1)))),
      type: "histogram2dcontour",
      histfunc: "sum",
      ncontours: 18,
      colorscale: [
        [0, "rgba(0,0,0,0)"],
        [0.28, colorWithAlpha(teamColor, themeColors.mode === "dark" ? 0.08 : 0.06)],
        [0.58, colorWithAlpha(teamColor, themeColors.mode === "dark" ? 0.34 : 0.26)],
        [0.82, colorWithAlpha(teamColor, themeColors.mode === "dark" ? 0.68 : 0.54)],
        [1, colorWithAlpha(teamColor, themeColors.mode === "dark" ? 0.94 : 0.8)],
      ],
      contours: { coloring: "heatmap", showlines: true },
      line: { width: 0.7, color: colorWithAlpha(teamColor, themeColors.mode === "dark" ? 0.42 : 0.3) },
      showscale: false,
      opacity: 0.94,
      hoverinfo: "skip",
      showlegend: false,
    };

    const edgeLineTraces = edges.map((edge) => {
      const source = nodeById.get(String(edge.source_id ?? ""));
      const target = nodeById.get(String(edge.target_id ?? ""));
      const x0 = source ? source.display_x : num(edge.x0);
      const y0 = source ? source.display_y : num(edge.y0);
      const x1 = target ? target.display_x : num(edge.x1);
      const y1 = target ? target.display_y : num(edge.y1);
      const line = shortenedLine(x0, y0, x1, y1);
      const intensity = Math.max(0, Math.min(1, num(edge.xt_intensity)));
      const isSelectedEdge = selectedPlayerId
        ? String(edge.source_id ?? "") === selectedPlayerId || String(edge.target_id ?? "") === selectedPlayerId
        : true;
      const isProfileEdge = !selectedProfile || profileEdgeKeys.has(edgeKey(edge));
      const isComboEdge = !comboHighlight
        || comboHighlight.pairKeys.has([String(edge.source_id ?? ""), String(edge.target_id ?? "")].sort().join("|"));
      const baseAlpha = 0.18 + intensity * 0.62;
      const linkAlpha = comboHighlight && !isComboEdge
        ? 0.03
        : selectedProfile && !isProfileEdge ? 0.035 : selectedPlayerId && !isSelectedEdge ? 0.025 : baseAlpha;
      const linkColor = themeColors.mode === "dark"
        ? `rgba(255,255,255,${linkAlpha})`
        : `rgba(0,0,0,${linkAlpha})`;
      return {
        x: [line.x0, line.x1],
        y: [line.y0, line.y1],
        mode: "lines",
        type: "scatter",
        line: {
          color: linkColor,
          width: Math.min(5.2, Math.max(0.6, num(edge.width) * (selectedProfile && isProfileEdge ? 1 : selectedPlayerId && isSelectedEdge ? 0.82 : 0.62))),
          shape: "spline",
        },
        hoverinfo: "skip",
        showlegend: false,
      };
    });

    const progressiveEdgeTraces = showProgressive ? edges
      .filter((edge) => {
        if (num(edge.progressive_count) <= 0) return false;
        if (!selectedPlayerId) return true;
        return String(edge.source_id ?? "") === selectedPlayerId || String(edge.target_id ?? "") === selectedPlayerId;
      })
      .flatMap((edge) => {
        const source = nodeById.get(String(edge.source_id ?? ""));
        const target = nodeById.get(String(edge.target_id ?? ""));
        const x0 = source ? source.display_x : num(edge.x0);
        const y0 = source ? source.display_y : num(edge.y0);
        const x1 = target ? target.display_x : num(edge.x1);
        const y1 = target ? target.display_y : num(edge.y1);
        const line = shortenedLine(x0, y0, x1, y1);
        const intensity = Math.max(0.12, Math.min(1, num(edge.progressive_intensity)));
        return [
          {
            x: [line.x0, line.x1],
            y: [line.y0, line.y1],
            mode: "lines",
            type: "scatter",
            line: { color: colorWithAlpha(teamColor, 0.18 + intensity * 0.28), width: 9 + intensity * 10, shape: "spline" },
            opacity: 1,
            hoverinfo: "skip",
            showlegend: false,
          },
          {
            x: [line.x0, line.x1],
            y: [line.y0, line.y1],
            mode: "lines",
            type: "scatter",
            line: { color: colorWithAlpha(teamColor, 0.62 + intensity * 0.34), width: 1.8 + intensity * 3.8, shape: "spline" },
            customdata: [`${num(edge.progressive_count)} progressive passes<br>${num(edge.pass_count)} successful passes`],
            hovertemplate: "%{customdata}<extra></extra>",
            showlegend: false,
          },
        ];
      }) : [];

    const edgeHoverTrace = {
      x: edges.map((edge) => {
        const source = nodeById.get(String(edge.source_id ?? ""));
        const target = nodeById.get(String(edge.target_id ?? ""));
        return ((source ? source.display_x : num(edge.x0)) + (target ? target.display_x : num(edge.x1))) / 2;
      }),
      y: edges.map((edge) => {
        const source = nodeById.get(String(edge.source_id ?? ""));
        const target = nodeById.get(String(edge.target_id ?? ""));
        return ((source ? source.display_y : num(edge.y0)) + (target ? target.display_y : num(edge.y1))) / 2;
      }),
      customdata: edges.map((edge) => `${num(edge.pass_count)} successful passes<br>Total xT ${num(edge.total_xt).toFixed(3)}<br>xT/pass ${num(edge.avg_xt).toFixed(3)}`),
      mode: "markers",
      type: "scatter",
      marker: { size: 18, color: "rgba(0,0,0,0)" },
      hovertemplate: "%{customdata}<extra></extra>",
      showlegend: false,
    };

    const comboOverlayTraces: PlotTrace[] = [];
    if (comboHighlight && !actionModeActive) {
      const maxPairPasses = Math.max(1, ...comboHighlight.pairs.map((pair) => pair.passes));
      comboHighlight.pairs.forEach((pair, rank) => {
        const nodeA = nodeById.get(pair.a);
        const nodeB = nodeById.get(pair.b);
        if (!nodeA || !nodeB) return;
        const width = 3.5 + (pair.passes / maxPairPasses) * 5;
        const hover = `#${rank + 1} pair · ${nodeA.player} ⇄ ${nodeB.player}<br>${pair.passes} passes · xT ${pair.xt.toFixed(3)}`;
        comboOverlayTraces.push({
          x: [nodeA.display_x, nodeB.display_x],
          y: [nodeA.display_y, nodeB.display_y],
          mode: "lines",
          type: "scatter",
          line: { color: colorWithAlpha(teamColor, 0.28), width: width + 7, shape: "spline" },
          hoverinfo: "skip",
          showlegend: false,
        });
        comboOverlayTraces.push({
          x: [nodeA.display_x, nodeB.display_x],
          y: [nodeA.display_y, nodeB.display_y],
          customdata: [hover, hover],
          mode: "lines",
          type: "scatter",
          line: { color: colorWithAlpha(teamColor, 0.9), width, shape: "spline" },
          hovertemplate: "%{customdata}<extra></extra>",
          showlegend: false,
        });
        comboOverlayTraces.push({
          x: [(nodeA.display_x + nodeB.display_x) / 2],
          y: [(nodeA.display_y + nodeB.display_y) / 2],
          mode: "text",
          type: "scatter",
          text: [`#${rank + 1} · ${pair.passes}`],
          textposition: "top center",
          textfont: { color: themeColors.text, size: 12, family: CHART_FONT_FAMILY },
          hoverinfo: "skip",
          showlegend: false,
        });
      });
      comboHighlight.triangles.forEach((triangle, rank) => {
        const points = triangle.ids
          .map((id) => nodeById.get(id))
          .filter((node): node is NonNullable<typeof node> => Boolean(node));
        if (points.length < 3) return;
        const hover = `#${rank + 1} triangle · ${points.map((point) => point.player).join(" · ")}<br>${triangle.passes} passes combined`;
        comboOverlayTraces.push({
          x: [...points.map((point) => point.display_x), points[0].display_x],
          y: [...points.map((point) => point.display_y), points[0].display_y],
          customdata: Array(points.length + 1).fill(hover),
          mode: "lines",
          type: "scatter",
          fill: "toself",
          fillcolor: colorWithAlpha(teamColor, 0.18 - rank * 0.05),
          line: { color: colorWithAlpha(teamColor, 0.85), width: rank === 0 ? 3 : 2 },
          hovertemplate: "%{customdata}<extra></extra>",
          showlegend: false,
        });
        comboOverlayTraces.push({
          x: [points.reduce((sum, point) => sum + point.display_x, 0) / points.length],
          y: [points.reduce((sum, point) => sum + point.display_y, 0) / points.length],
          mode: "text",
          type: "scatter",
          text: [`#${rank + 1} · ${triangle.passes}`],
          textfont: { color: themeColors.text, size: 12, family: CHART_FONT_FAMILY },
          hoverinfo: "skip",
          showlegend: false,
        });
      });
    }

    const progressiveNodeGlowTrace = showProgressive ? {
      x: positionedNodes.map((row) => row.display_x),
      y: positionedNodes.map((row) => row.display_y),
      mode: "markers",
      type: "scatter",
      marker: {
        size: positionedNodes.map((row) => num(row.progressive_passes_made) > 0 ? num(row.size, 22) + 16 + num(row.progressive_intensity) * 18 : 0),
        color: positionedNodes.map((row) => {
          const intensity = Math.max(0, Math.min(1, num(row.progressive_intensity)));
          return colorWithAlpha(teamColor, 0.1 + intensity * (themeColors.mode === "dark" ? 0.28 : 0.22));
        }),
        line: { color: "rgba(0,0,0,0)", width: 0 },
      },
      hoverinfo: "skip",
      showlegend: false,
    } : null;

    const actionOverlayTraces: PlotTrace[] = actionModeActive ? selectedPlayerActions.flatMap((row): PlotTrace[] => {
      const id = String(row.id ?? "");
      const type = String(row.type ?? "Action");
      const color = actionColor(row, teamColor, themeColors.mode);
      const successful = row.is_successful !== false;
      const retainedText = row.next_team_retained === false ? "Not retained" : "Retained";
      const text = `${row.player}<br>${row.type} ${num(row.minute)}'<br>xT ${num(row.xT).toFixed(3)} | xA ${num(row.xA).toFixed(3)}<br>${row.is_successful === false ? "Unsuccessful" : "Successful"} · ${row.is_progressive ? "Progressive" : "Non-progressive"}<br>${retainedText}`;
      if (type === "TakeOn") {
        return [{
          x: [num(row.x)],
          y: [num(row.y)],
          customdata: [id],
          text: [text],
          type: "scatter",
          mode: "markers",
          marker: {
            size: 10,
            color: actionOutcomeColor(color, successful, 0.88, 0.62, unsuccessfulColor),
            symbol: actionEndpointSymbol(successful, "diamond"),
            line: { color: "#ffffff", width: 1.5 },
          },
          hovertemplate: "%{text}<extra></extra>",
          showlegend: false,
        }];
      }
      const endX = num(row.end_x, num(row.x));
      const endY = num(row.end_y, num(row.y));
      const glowTrace = successful && row.is_progressive === true && showProgressive ? [{
        x: [num(row.x), endX],
        y: [num(row.y), endY],
        type: "scatter",
        mode: "lines",
        line: { color: colorWithAlpha(teamColor, 0.34), width: 11, dash: type === "Carry" ? "dash" : "solid" },
        hoverinfo: "skip",
        showlegend: false,
      }] : [];
      return [
        ...glowTrace,
        {
          x: [num(row.x), endX],
          y: [num(row.y), endY],
          customdata: [id, id],
          text: [text, text],
          type: "scatter",
          mode: "lines",
          line: {
            color: actionOutcomeColor(color, successful, 0.86, 0.52, unsuccessfulColor),
            width: type === "Carry" ? 2.8 : 2.4,
            dash: type === "Carry" ? "dash" : "solid",
          },
          hovertemplate: "%{text}<extra></extra>",
          showlegend: false,
        },
        {
          x: [num(row.x), endX],
          y: [num(row.y), endY],
          customdata: [id, id],
          text: [text, text],
          type: "scatter",
          mode: "markers",
          marker: {
            size: [7, 8],
            color: [
              actionOutcomeColor(color, successful, 0.55, 0.44, unsuccessfulColor),
              actionOutcomeColor(color, successful, 0.9, 0.68, unsuccessfulColor),
            ],
            symbol: [
              actionStartSymbol(successful),
              actionEndpointSymbol(successful, type === "Carry" ? "square" : "triangle-right"),
            ],
            line: { color: themeColors.mode === "dark" ? "#0f172a" : "#ffffff", width: 1.2 },
          },
          hovertemplate: "%{text}<extra></extra>",
          showlegend: false,
        },
      ];
    }) : [];

    const emptyActionTrace: PlotTrace | null = actionModeActive && selectedPlayerActions.length === 0 ? {
      x: [52.5],
      y: [34],
      type: "scatter",
      mode: "text",
      text: ["No matching actions for this selection"],
      textfont: { color: themeColors.muted, size: 15, family: CHART_FONT_FAMILY },
      hoverinfo: "skip",
      showlegend: false,
    } : null;

    const nodeTrace = {
      x: positionedNodes.map((row) => row.display_x),
      y: positionedNodes.map((row) => row.display_y),
      mode: "markers+text",
      type: "scatter",
      text: positionedNodes.map((row) => (nodeHeadshots[`${String(row.player ?? "")}|${teamName}|${teamColor}`] ? "" : row.label ?? "")),
      textposition: "middle center",
      textfont: {
        color: positionedNodes.map((row) => {
          if (comboHighlight) return comboHighlight.nodeIds.has(row.id) ? themeColors.text : themeColors.mode === "dark" ? "rgba(148,163,184,0.28)" : "rgba(71,85,105,0.32)";
          if (selectedProfile) return profileNodeIds.has(row.id) ? themeColors.text : themeColors.mode === "dark" ? "rgba(148,163,184,0.28)" : "rgba(71,85,105,0.32)";
          if (!selectedPlayerId) return themeColors.text;
          if (row.id === selectedPlayerId) return themeColors.text;
          if (selectedNetwork.connectedIds.has(row.id)) return themeColors.text;
          return themeColors.mode === "dark" ? "rgba(148,163,184,0.38)" : "rgba(71,85,105,0.42)";
        }),
        size: 12,
        family: CHART_FONT_FAMILY,
      },
      marker: {
        symbol: positionedNodes.map((row) => row.part_window_player ? "square" : "circle"),
        size: positionedNodes.map((row) => {
          if (comboHighlight) return comboHighlight.nodeIds.has(row.id) ? num(row.size, 22) + 5 : Math.max(16, num(row.size, 22) - 5);
          if (selectedProfile && profileNodeIds.has(row.id)) return num(row.size, 22) + 5;
          const baseSize = num(row.size, 22);
          if (!selectedPlayerId) return baseSize;
          if (row.id === selectedPlayerId) return baseSize + 9;
          if (selectedNetwork.connectedIds.has(row.id)) return baseSize + 3;
          return Math.max(16, baseSize - 5);
        }),
        color: positionedNodes.map((row) => {
          if (comboHighlight) return comboHighlight.nodeIds.has(row.id) ? colorWithAlpha(teamColor, themeColors.mode === "dark" ? 0.72 : 0.58) : themeColors.mode === "dark" ? "rgba(15,23,42,0.18)" : "rgba(255,255,255,0.28)";
          if (selectedProfile) return profileNodeIds.has(row.id) ? colorWithAlpha(teamColor, themeColors.mode === "dark" ? 0.72 : 0.58) : themeColors.mode === "dark" ? "rgba(15,23,42,0.18)" : "rgba(255,255,255,0.28)";
          if (!selectedPlayerId) return themeColors.mode === "dark" ? "rgba(2,6,23,0.9)" : "rgba(255,255,255,0.94)";
          if (row.id === selectedPlayerId) return colorWithAlpha(teamColor, themeColors.mode === "dark" ? 0.88 : 0.78);
          if (selectedNetwork.connectedIds.has(row.id)) return themeColors.mode === "dark" ? "rgba(15,23,42,0.96)" : "rgba(255,255,255,0.98)";
          return themeColors.mode === "dark" ? "rgba(15,23,42,0.26)" : "rgba(255,255,255,0.35)";
        }),
        line: {
          color: positionedNodes.map((row) => {
            if (comboHighlight && comboHighlight.nodeIds.has(row.id)) return "#facc15";
            if (selectedProfile && profileNodeIds.has(row.id)) return "#facc15";
            if (row.id === selectedPlayerId) return "#facc15";
            if (showProgressive && num(row.progressive_passes_made) > 0) return teamColor;
            if (row.introduced_in_window) return introducedNodeColor(themeColors.mode);
            if (!selectedPlayerId) return teamColor;
            if (selectedNetwork.connectedIds.has(row.id)) return teamColor;
            return themeColors.mode === "dark" ? "rgba(148,163,184,0.24)" : "rgba(71,85,105,0.24)";
          }),
          width: positionedNodes.map((row) => {
            if (comboHighlight && comboHighlight.nodeIds.has(row.id)) return 4;
            if (selectedProfile && profileNodeIds.has(row.id)) return 4;
            if (row.id === selectedPlayerId) return 4;
            if (showProgressive && num(row.progressive_passes_made) > 0) return 4;
            if (row.introduced_in_window) return 3.6;
            if (selectedNetwork.connectedIds.has(row.id)) return 3;
            return 1.5;
          }),
        },
      },
      customdata: positionedNodes.map((row) => row.id),
      hovertext: positionedNodes.map((row) => `${row.player}<br>Successful passes made: ${num(row.passes_made)}<br>Passes received: ${num(row.passes_received)}<br>Progressive passes made: ${num(row.progressive_passes_made)}<br>Progressive passes received: ${num(row.progressive_passes_received)}<br>Location: ${row.mode}${row.introduced_in_window ? "<br>Introduced in this window" : ""}${row.part_window_player ? "<br>Part-window player in merged sub-window" : ""}<br>Click to ${selectedPlayerId === row.id ? "clear" : "focus"}`),
      hovertemplate: "%{hovertext}<extra></extra>",
      showlegend: false,
    };

    const nodeClickTrace = {
      x: positionedNodes.map((row) => row.display_x),
      y: positionedNodes.map((row) => row.display_y),
      mode: "markers",
      type: "scatter",
      customdata: positionedNodes.map((row) => row.id),
      hovertext: positionedNodes.map((row) => `${row.player}<br>Successful passes made: ${num(row.passes_made)}<br>Passes received: ${num(row.passes_received)}<br>Progressive passes made: ${num(row.progressive_passes_made)}<br>Progressive passes received: ${num(row.progressive_passes_received)}<br>Location: ${row.mode}${row.introduced_in_window ? "<br>Introduced in this window" : ""}${row.part_window_player ? "<br>Part-window player in merged sub-window" : ""}<br>Click to ${selectedPlayerId === row.id ? "clear" : "focus"}`),
      hovertemplate: "%{hovertext}<extra></extra>",
      marker: {
        symbol: positionedNodes.map((row) => row.part_window_player ? "square" : "circle"),
        size: positionedNodes.map((row) => num(row.size, 22) + 18),
        color: "rgba(0,0,0,0.01)",
        line: { color: "rgba(0,0,0,0)", width: 0 },
      },
      showlegend: false,
    };

    if (actionModeActive) {
      return [
        ...actionOverlayTraces,
        ...(emptyActionTrace ? [emptyActionTrace] : []),
      ];
    }

    return [
      heatTrace,
      ...edgeLineTraces,
      ...progressiveEdgeTraces,
      edgeHoverTrace,
      ...(progressiveNodeGlowTrace ? [progressiveNodeGlowTrace] : []),
      ...comboOverlayTraces,
      ...actionOverlayTraces,
      nodeTrace,
      nodeClickTrace,
    ];
  }, [comboHighlight, edges, heatPoints, nodeById, nodeHeadshots, positionedNodes, profileEdgeKeys, profileNodeIds, selectedNetwork.connectedIds, selectedPlayer, selectedPlayerActions, selectedPlayerId, selectedProfile, showPlayerActions, showProgressive, teamColor, teamName, themeColors]);

  // Circular headshots rendered on top of the node markers (marker ring stays
  // visible around the image for selection/progressive states).
  const nodeImages = useMemo(() => {
    if (showPlayerActions && selectedPlayer) return [];
    const pxToUnits = 68 / 654; // layout height 680 minus vertical margins
    return positionedNodes.flatMap((row) => {
      const source = nodeHeadshots[`${String(row.player ?? "")}|${teamName}|${teamColor}`];
      if (!source) return [];
      let sizePx = num(row.size, 22);
      if (selectedProfile && profileNodeIds.has(row.id)) sizePx += 5;
      else if (selectedPlayerId && row.id === selectedPlayerId) sizePx += 9;
      else if (selectedPlayerId && selectedNetwork.connectedIds.has(row.id)) sizePx += 3;
      else if (selectedPlayerId || selectedProfile) sizePx = Math.max(16, sizePx - 5);
      const size = (sizePx - 2) * pxToUnits;
      const opacity = comboHighlight
        ? (comboHighlight.nodeIds.has(row.id) ? 1 : 0.15)
        : selectedProfile
        ? (profileNodeIds.has(row.id) ? 1 : 0.15)
        : !selectedPlayerId
          ? 1
          : row.id === selectedPlayerId
            ? 1
            : selectedNetwork.connectedIds.has(row.id)
              ? 0.95
              : 0.18;
      return [{
        source,
        xref: "x",
        yref: "y",
        x: row.display_x,
        y: row.display_y,
        sizex: size,
        sizey: size,
        xanchor: "center",
        yanchor: "middle",
        opacity,
        layer: "above",
      }];
    });
  }, [comboHighlight, nodeHeadshots, positionedNodes, profileNodeIds, selectedNetwork.connectedIds, selectedPlayer, selectedPlayerId, selectedProfile, showPlayerActions, teamColor, teamName]);

  const setPlayerMode = (id: string, mode: LocationMode) => {
    setLocationModes((current) => ({ ...current, [id]: mode }));
  };

  const handleNetworkClick = (event: MouseEvent<HTMLDivElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const margin = { left: 16, right: 16, top: 10, bottom: 16 };
    const availableWidth = rect.width - margin.left - margin.right;
    const availableHeight = rect.height - margin.top - margin.bottom;
    const pitchRatio = 105 / 68;
    const availableRatio = availableWidth / availableHeight;
    const plotWidth = availableRatio > pitchRatio ? availableHeight * pitchRatio : availableWidth;
    const plotHeight = availableRatio > pitchRatio ? availableHeight : availableWidth / pitchRatio;
    const plotLeft = margin.left + (availableWidth - plotWidth) / 2;
    const plotTop = margin.top + (availableHeight - plotHeight) / 2;
    const relativeX = event.clientX - rect.left - plotLeft;
    const relativeY = event.clientY - rect.top - plotTop;

    if (relativeX < 0 || relativeY < 0 || relativeX > plotWidth || relativeY > plotHeight) return;

    const pitchX = (relativeX / plotWidth) * 105;
    const pitchY = 68 - (relativeY / plotHeight) * 68;
    if (showPlayerActions && selectedPlayerId) return;
    const nearestNode = positionedNodes.reduce<{ id: string; distance: number } | null>((nearest, node) => {
      const distance = Math.hypot(pitchX - node.display_x, pitchY - node.display_y);
      return !nearest || distance < nearest.distance ? { id: node.id, distance } : nearest;
    }, null);

    if (!nearestNode || nearestNode.distance > 6.5) return;
    onSelectedPlayerChange(selectedPlayerId === nearestNode.id ? null : nearestNode.id);
  };

  const actionOverlayAnnotations = useMemo(() => (
    showPlayerActions && selectedPlayer
      ? selectedPlayerActions
        .filter((row) => ["Pass", "Carry"].includes(String(row.type ?? "")))
        .map((row) => {
          const color = actionColor(row, teamColor, themeColors.mode);
          const type = String(row.type ?? "");
          return {
            x: num(row.end_x, num(row.x)),
            y: num(row.end_y, num(row.y)),
            ax: num(row.x),
            ay: num(row.y),
            xref: "x",
            yref: "y",
            axref: "x",
            ayref: "y",
            text: "",
            showarrow: true,
            arrowhead: 3,
            arrowsize: type === "Carry" ? 0.85 : 1,
            arrowwidth: type === "Carry" ? 2.6 : 2.4,
            arrowcolor: actionOutcomeColor(
              color,
              row.is_successful !== false,
              0.9,
              0.56,
              unsuccessfulColor,
            ),
          };
        })
      : []
  ), [selectedPlayer, selectedPlayerActions, showPlayerActions, teamColor, themeColors.mode]);

  return (
    <div className="pass-network-shell">
      <div className="pass-network-tools">
        <button
          type="button"
          className={showProgressive ? "is-active" : ""}
          aria-pressed={showProgressive}
          onClick={() => setShowProgressive((current) => !current)}
        >
          Progressive actions
        </button>
        <button
          type="button"
          className={comboMode === "pairs" ? "is-active" : ""}
          aria-pressed={comboMode === "pairs"}
          onClick={() => setComboMode((current) => (current === "pairs" ? "off" : "pairs"))}
        >
          Top pass pairs
        </button>
        <button
          type="button"
          className={comboMode === "triangles" ? "is-active" : ""}
          aria-pressed={comboMode === "triangles"}
          onClick={() => setComboMode((current) => (current === "triangles" ? "off" : "triangles"))}
        >
          Passing triangles
        </button>
      </div>
      {comboMode !== "off" && (
        <p className="pass-network-note">
          {comboMode === "pairs"
            ? "Highlighting the 5 strongest pass pairs (both directions combined) in the current window — line width scales with volume."
            : "Highlighting the 3 strongest passing triangles (trios connected on all three sides) by combined pass volume in the current window."}
        </p>
      )}
      {mergedWindowNote && <p className="pass-network-note">{mergedWindowNote}</p>}
      {showPlayerActions && selectedPlayer && (
        <ActionOutcomeLegend color={teamColor} unsuccessfulColor={unsuccessfulColor} />
      )}
      <div className="pass-network-stage">
        <div className="pass-network-click-layer" onClick={handleNetworkClick}>
          <Plot
            data={traces}
            layout={{
              autosize: true,
              height: 680,
              margin: { l: 16, r: 16, t: 10, b: 16 },
              paper_bgcolor: "rgba(0,0,0,0)",
              plot_bgcolor: themeColors.surface,
              font: { color: themeColors.text, family: CHART_FONT_FAMILY },
              showlegend: false,
              clickmode: "event",
              xaxis: { range: [0, 105], visible: false, fixedrange: true, constrain: "domain" },
              yaxis: { range: [0, 68], visible: false, fixedrange: true, scaleanchor: "x", scaleratio: 1, constrain: "domain" },
              shapes: [
                ...horizontalPitchShapes(themeColors.muted),
                ...(highlightThird && highlightThird !== "all"
                  ? [{
                      type: "rect",
                      x0: highlightThird === "defensive" ? 0 : highlightThird === "middle" ? 35 : 70,
                      x1: highlightThird === "defensive" ? 35 : highlightThird === "middle" ? 70 : 105,
                      y0: 0,
                      y1: 68,
                      fillcolor: "rgba(74,222,128,0.10)",
                      line: { color: "rgba(74,222,128,0.45)", width: 1, dash: "dot" },
                      layer: "below",
                    }]
                  : []),
              ],
              images: nodeImages,
              annotations: actionOverlayAnnotations,
              hoverlabel: {
                bgcolor: themeColors.mode === "dark" ? "#0f2236" : "#ffffff",
                bordercolor: themeColors.mode === "dark" ? "rgba(255,255,255,0.18)" : "rgba(15,23,42,0.16)",
                font: { color: themeColors.text, family: CHART_FONT_FAMILY, size: 12 },
              },
            }}
            config={{ responsive: true, displayModeBar: false }}
            className="plotly-chart pass-network-chart"
          />
        </div>
        <aside className="pass-network-player-panel">
          {selectedPlayer ? (
            <>
              <div className="pass-network-player-panel-header">
                <div>
                  <span className="eyebrow">Selected Player</span>
                  <strong>Connection distribution</strong>
                </div>
                <button type="button" onClick={() => onSelectedPlayerChange(null)}>
                  Clear
                </button>
              </div>
              <div className="pass-network-player-distribution">
                <div className="pass-network-distribution-summary">
                  <strong style={{ color: teamColor }}>{selectedPlayer.player}</strong>
                  <span>{selectedNetwork.outgoingPasses} made / {selectedNetwork.incomingPasses} received</span>
                </div>
                <div className="pass-network-connection-list">
                  {selectedNetwork.connections.length ? selectedNetwork.connections.slice(0, 10).map((connection) => (
                    <div key={connection.id}>
                      <strong>{connection.player}</strong>
                      <span>{connection.direction}</span>
                      <span>{connection.passes} passes · xT {connection.xt.toFixed(3)}</span>
                    </div>
                  )) : (
                    <div>
                      <strong>No passing links</strong>
                      <span>This player has no successful pass connections in the current window.</span>
                    </div>
                  )}
                </div>
              </div>
            </>
          ) : (
            <>
              <div className="pass-network-player-panel-header">
                <div>
                  <span className="eyebrow">Node Location</span>
                  <strong>Player positions</strong>
                </div>
                <button type="button" onClick={() => setLocationModes({})}>
                  Set to default
                </button>
              </div>
              <div className="pass-network-player-list">
                {positionedNodes.map((node) => (
                  <div key={node.id} className="pass-network-player-control">
                    <span>{node.player}</span>
                    <div>
                      {(["played", "received", "both"] as LocationMode[]).map((mode) => (
                        <button
                          key={mode}
                          type="button"
                          className={(locationModes[node.id] ?? "both") === mode ? "is-active" : ""}
                          onClick={() => setPlayerMode(node.id, mode)}
                        >
                          {mode === "played" ? "Played" : mode === "received" ? "Received" : "Both"}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </aside>
      </div>
      <section className="defensive-profile-panel possession-profile-panel">
        <div>
          <span className="eyebrow">In Possession Profile</span>
          <p>{possessionProfile.insight}</p>
        </div>
        <div className="defensive-profile-cards">
          {possessionProfile.profiles.filter((profile) => profile.score > 0).map((profile) => (
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
              <small>{selectedProfile === profile.name ? profile.selected : profile.description}</small>
              <small>{profile.detail}</small>
            </button>
          ))}
        </div>
        {selectedProfile && <button type="button" className="ghost-button" onClick={() => setSelectedProfile("")}>Clear profile highlight</button>}
      </section>
    </div>
  );
}
