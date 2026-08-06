"use client";

import { useEffect, useState } from "react";

import { PUBLIC_API_BASE, getAuthHeaders } from "../lib/api";
const PITCH_W = 105;
const PITCH_H = 68;

export type OppositionLineupPlayer = {
  player_id?: number | string | null;
  player: string;
  jersey?: number | string | null;
  slot?: number | null;
  position?: string | null;
  position_group?: string | null;
  captain?: boolean;
  x?: number | null;
  y?: number | null;
};

export type OppositionLineupView = {
  id: string;
  label: string;
  team: string;
  formation?: string | null;
  subtitle?: string | null;
  players: OppositionLineupPlayer[];
};

function lastName(full: string) {
  const parts = full.trim().split(/\s+/);
  return parts.length > 1 ? parts.slice(1).join(" ") : full;
}

function svgY(dataY: number, attackingRight: boolean) {
  return attackingRight ? PITCH_H - dataY : dataY;
}

function useSquadImages(team: string, names: string[]) {
  const [images, setImages] = useState<Record<string, string | null>>({});
  const namesKey = names.join(",");
  useEffect(() => {
    if (!team || !namesKey) return;
    let cancelled = false;
    getAuthHeaders()
      .then((headers) =>
        fetch(`${PUBLIC_API_BASE}/players/images?names=${encodeURIComponent(namesKey)}&team=${encodeURIComponent(team)}`, { headers })
      )
      .then((response) => response.json())
      .then((data: Record<string, string | null>) => {
        if (!cancelled) setImages((prev) => ({ ...prev, ...data }));
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [team, namesKey]);
  return images;
}

function PitchLines() {
  return (
    <g fill="none" stroke="var(--pitch-line)" strokeWidth="0.3">
      <rect x="0.3" y="0.3" width={PITCH_W - 0.6} height={PITCH_H - 0.6} rx="0.8" />
      <line x1={PITCH_W / 2} y1="0.3" x2={PITCH_W / 2} y2={PITCH_H - 0.3} />
      <circle cx={PITCH_W / 2} cy={PITCH_H / 2} r="9.15" />
      <rect x="0.3" y="13.84" width="16.5" height="40.32" />
      <rect x={PITCH_W - 16.8} y="13.84" width="16.5" height="40.32" />
      <rect x="0.3" y="24.84" width="5.5" height="18.32" />
      <rect x={PITCH_W - 5.8} y="24.84" width="5.5" height="18.32" />
    </g>
  );
}

function PlayerMarker({
  x,
  y,
  player,
  color,
  imageUrl,
  clipId,
}: {
  x: number;
  y: number;
  player: OppositionLineupPlayer;
  color: string;
  imageUrl?: string | null;
  clipId: string;
}) {
  const r = 2.1;
  const jersey = player.jersey || "";
  return (
    <g transform={`translate(${x}, ${y})`}>
      <circle r={r} fill={color} stroke={player.captain ? "#facc15" : "rgba(15,23,42,0.65)"} strokeWidth={0.35} />
      {imageUrl ? (
        <>
          <clipPath id={clipId}>
            <circle r={r - 0.25} />
          </clipPath>
          <image
            href={imageUrl}
            x={-(r - 0.25)}
            y={-(r - 0.25)}
            width={(r - 0.25) * 2}
            height={(r - 0.25) * 2}
            clipPath={`url(#${clipId})`}
            preserveAspectRatio="xMidYMid slice"
          />
        </>
      ) : (
        <text y={0.7} textAnchor="middle" className="lineup-player-jersey">{jersey}</text>
      )}
      <text y={r + 2} textAnchor="middle" className="lineup-player-name">
        {lastName(player.player)}{jersey ? ` (${jersey})` : ""}{player.captain ? " (C)" : ""}
      </text>
    </g>
  );
}

function hasPoint(player: OppositionLineupPlayer) {
  return typeof player.x === "number" && typeof player.y === "number";
}

function playerKey(player: OppositionLineupPlayer) {
  return String(player.player_id ?? player.player).trim().toLowerCase();
}

function lineupChangeRows(views: OppositionLineupView[]) {
  const chronological = [...views].reverse();
  return chronological.map((view, index) => {
    const currentKeys = new Set(view.players.slice(0, 11).map(playerKey));
    if (index === 0) {
      return {
        id: view.id,
        label: view.label,
        formation: view.formation,
        changes: 0,
        retained: currentKeys.size,
        isBaseline: true,
      };
    }
    const previousKeys = new Set(chronological[index - 1].players.slice(0, 11).map(playerKey));
    const retained = [...currentKeys].filter((key) => previousKeys.has(key)).length;
    return {
      id: view.id,
      label: view.label,
      formation: view.formation,
      changes: Math.max(0, 11 - retained),
      retained,
      isBaseline: false,
    };
  }).reverse();
}

function starterFrequencyRows(views: OppositionLineupView[]) {
  const counts = new Map<string, { player: string; starts: number }>();
  for (const view of views) {
    for (const player of view.players.slice(0, 11)) {
      const key = playerKey(player);
      const current = counts.get(key);
      counts.set(key, { player: player.player, starts: (current?.starts ?? 0) + 1 });
    }
  }
  return [...counts.values()].sort((a, b) => b.starts - a.starts || a.player.localeCompare(b.player));
}

function LineupStabilityVisual({ views }: { views: OppositionLineupView[] }) {
  if (!views.length) return null;
  const changes = lineupChangeRows(views);
  const comparable = changes.filter((row) => !row.isBaseline);
  const averageChanges = comparable.length
    ? comparable.reduce((sum, row) => sum + row.changes, 0) / comparable.length
    : 0;
  const everPresent = starterFrequencyRows(views).filter((row) => row.starts === views.length);
  const stabilityScore = Math.max(0, Math.min(100, ((11 - averageChanges) / 11) * 100));

  return (
    <div className="opposition-lineup-stability" aria-label="Starting lineup stability across recent lineups">
      <div className="opposition-lineup-stability-kpis">
        <div>
          <span>Avg XI changes</span>
          <strong>{averageChanges.toFixed(1)}</strong>
        </div>
        <div>
          <span>Unchanged core</span>
          <strong>{everPresent.length}</strong>
        </div>
        <div>
          <span>Recent</span>
          <strong>{views.length}</strong>
        </div>
      </div>
      <div className="opposition-lineup-stability-meter" aria-hidden="true">
        <i style={{ width: `${stabilityScore}%` }} />
      </div>
      <div className="opposition-lineup-change-strip">
        {changes.map((row) => (
          <div key={row.id} className={row.isBaseline ? "is-baseline" : ""}>
            <span>{row.isBaseline ? "Base" : `${row.changes} changes`}</span>
            <div title={row.label}>
              <i style={{ height: `${Math.max(10, row.isBaseline ? 12 : (row.changes / 11) * 100)}%` }} />
            </div>
            <small>{row.formation || "Shape"}</small>
          </div>
        ))}
      </div>
      {everPresent.length ? (
        <p className="opposition-lineup-core-note">
          Core starters: {everPresent.slice(0, 6).map((row) => row.player).join(", ")}{everPresent.length > 6 ? ` +${everPresent.length - 6}` : ""}
        </p>
      ) : (
        <p className="opposition-lineup-core-note">No player started every recent lineup shown.</p>
      )}
    </div>
  );
}

export function OppositionLineupVisual({
  latestView,
  sampleViews,
  teamColor = "#22c55e",
}: {
  latestView: OppositionLineupView;
  sampleViews: OppositionLineupView[];
  teamColor?: string;
}) {
  const [mode, setMode] = useState<"latest" | "sample">("latest");
  const [sampleId, setSampleId] = useState(sampleViews[0]?.id ?? "");
  const selectedSample = sampleViews.find((view) => view.id === sampleId) ?? sampleViews[0];
  const active = mode === "sample" && selectedSample ? selectedSample : latestView;
  const images = useSquadImages(active.team, active.players.map((player) => player.player));

  return (
    <section className="card stack opposition-lineups-card">
      <div className="chart-card-head">
        <div>
          <span className="eyebrow">Team Sheets</span>
          <h2 style={{ margin: "6px 0 0" }}>{active.label}</h2>
        </div>
        <div className="opposition-lineup-selector">
          <div className="lineup-toggle-group" role="tablist" aria-label="Lineup view">
            <button
              type="button"
              className={mode === "latest" ? "is-active" : ""}
              onClick={() => setMode("latest")}
            >
              Last Match XI
            </button>
            <button
              type="button"
              className={mode === "sample" ? "is-active" : ""}
              disabled={!sampleViews.length}
              onClick={() => setMode("sample")}
            >
              Recent Lineups
            </button>
          </div>
          {sampleViews.length ? (
            <select
              className="select opposition-lineup-sample-select"
              value={sampleId}
              onChange={(event) => {
                setSampleId(event.target.value);
                setMode("sample");
              }}
              aria-label="Select recent lineup"
            >
              {sampleViews.map((view) => (
                <option key={view.id} value={view.id}>{view.label}</option>
              ))}
            </select>
          ) : null}
        </div>
      </div>

      <div className="lineup-formation-meta is-average">
        <div className="lineup-formation-meta-item align-left" style={{ color: teamColor }}>
          <span className="lineup-formation-meta-team">{active.team}</span>
          {active.formation ? <span className="lineup-formation-meta-detail">{active.formation}</span> : null}
        </div>
      </div>

      <svg viewBox={`0 0 ${PITCH_W} ${PITCH_H}`} className="lineups-pitch-svg" aria-label={`${active.label} pitch`}>
        <rect x="0" y="0" width={PITCH_W} height={PITCH_H} rx="1" fill="rgba(148,163,184,0.08)" />
        <PitchLines />
        <g>
          {active.players.slice(0, 11).filter(hasPoint).map((player, index) => {
            const x = Number(player.x);
            const y = svgY(Number(player.y), true);
            return (
              <PlayerMarker
                key={`${active.id}-${player.player_id ?? player.player}-${index}`}
                x={x}
                y={y}
                player={player}
                color={teamColor}
                imageUrl={images[player.player]}
                clipId={`opposition-lineup-${active.id}-${player.player_id ?? index}`}
              />
            );
          })}
        </g>
      </svg>

      {active.subtitle ? <p className="chart-footnote">{active.subtitle}</p> : null}
      <LineupStabilityVisual views={sampleViews} />
    </section>
  );
}
