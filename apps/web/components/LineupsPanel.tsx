"use client";

import { useEffect, useMemo, useState } from "react";

import { colorWithAlpha } from "../lib/theme";
import { DownloadPngButton } from "./DownloadPngButton";

const PUBLIC_API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";

type LineupPlayer = {
  player_id: number;
  player: string;
  jersey: string;
  slot: number;
  position: string | null;
  position_group: string;
  captain: boolean;
  x: number;
  y: number;
  avg?: { x: number; y: number; touches: number } | null;
};

type TeamLineup = {
  formation_id: number;
  formation: string;
  starters: LineupPlayer[];
  bench: LineupPlayer[];
};

type Phase = {
  start: number;
  end: number;
  label: string;
  formation_id: number;
  formation: string;
  players: LineupPlayer[];
};

type Substitution = {
  team: string;
  minute: number;
  player_on: string;
  player_off: string;
};

type Props = {
  teams: [string, string];
  teamColors: Record<string, string>;
  lineups: Record<string, TeamLineup>;
  substitutions: Substitution[];
  phases?: Record<string, Phase[]>;
};

type Point = [number, number];

const PITCH_W = 105;
const PITCH_H = 68;

function lastName(full: string) {
  const parts = full.trim().split(/\s+/);
  return parts.length > 1 ? parts.slice(1).join(" ") : full;
}

// Event data has y=0 on the attacking team's right touchline; SVG y grows
// downward, so a team attacking left→right renders as svgY = 68 - y.
function svgY(dataY: number, attackingRight: boolean) {
  return attackingRight ? PITCH_H - dataY : dataY;
}

// Voronoi via half-plane clipping (Sutherland–Hodgman against each bisector).
// Fine for the 11 on-pitch points we draw.
function voronoiCells(points: Point[]): Point[][] {
  const bounds: Point[] = [[0, 0], [PITCH_W, 0], [PITCH_W, PITCH_H], [0, PITCH_H]];
  return points.map(([px, py], i) => {
    let cell = bounds;
    for (let j = 0; j < points.length; j += 1) {
      if (j === i || !cell.length) continue;
      const [qx, qy] = points[j];
      const mx = (px + qx) / 2;
      const my = (py + qy) / 2;
      const dx = qx - px;
      const dy = qy - py;
      const inside = ([x, y]: Point) => (x - mx) * dx + (y - my) * dy <= 0;
      const next: Point[] = [];
      for (let k = 0; k < cell.length; k += 1) {
        const current = cell[k];
        const previous = cell[(k + cell.length - 1) % cell.length];
        const currentIn = inside(current);
        const previousIn = inside(previous);
        if (currentIn !== previousIn) {
          const t =
            ((mx - previous[0]) * dx + (my - previous[1]) * dy) /
            ((current[0] - previous[0]) * dx + (current[1] - previous[1]) * dy);
          next.push([previous[0] + t * (current[0] - previous[0]), previous[1] + t * (current[1] - previous[1])]);
        }
        if (currentIn) next.push(current);
      }
      cell = next;
    }
    return cell;
  });
}

function useSquadImages(team: string, names: string[]) {
  const [images, setImages] = useState<Record<string, string | null>>({});
  const namesKey = names.join(",");
  useEffect(() => {
    if (!team || !namesKey) return;
    let cancelled = false;
    fetch(`${PUBLIC_API_BASE}/players/images?names=${encodeURIComponent(namesKey)}&team=${encodeURIComponent(team)}`)
      .then((response) => response.json())
      .then((data: Record<string, string | null>) => {
        if (!cancelled) setImages((prev) => ({ ...prev, ...data }));
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
  player: LineupPlayer;
  color: string;
  imageUrl?: string | null;
  clipId: string;
}) {
  const r = 2.1;
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
        <text y={0.7} textAnchor="middle" className="lineup-player-jersey">{player.jersey}</text>
      )}
      <text y={r + 2} textAnchor="middle" className="lineup-player-name">
        {lastName(player.player)} ({player.jersey}){player.captain ? " (C)" : ""}
      </text>
    </g>
  );
}

export function LineupsPanel({ teams, teamColors, lineups, substitutions, phases = {} }: Props) {
  const [mode, setMode] = useState<"formation" | "average">("formation");
  const [teamA, teamB] = teams;
  const [avgTeam, setAvgTeam] = useState(teamA);
  const [phaseIndexByTeam, setPhaseIndexByTeam] = useState<Record<string, number>>({});
  const lineupA = lineups[teamA];
  const lineupB = lineups[teamB];

  const teamPhases = (team: string): Phase[] => phases[team] ?? [];
  const phaseFor = (team: string): Phase | undefined => {
    const list = teamPhases(team);
    if (!list.length) return undefined;
    return list[Math.min(phaseIndexByTeam[team] ?? 0, list.length - 1)];
  };
  const setPhaseFor = (team: string, index: number) =>
    setPhaseIndexByTeam((prev) => ({ ...prev, [team]: index }));

  const phasePlayersFor = (team: string): LineupPlayer[] => {
    const phase = phaseFor(team);
    if (phase?.players?.length) return phase.players;
    return (team === teamA ? lineupA : lineupB)?.starters ?? [];
  };
  const phaseFormationFor = (team: string): string => {
    const phase = phaseFor(team);
    if (phase?.formation) return phase.formation;
    return (team === teamA ? lineupA : lineupB)?.formation ?? "";
  };

  const allNamesA = useMemo(
    () => [...new Set(teamPhases(teamA).flatMap((p) => p.players.map((pl) => pl.player)).concat((lineupA?.starters ?? []).map((p) => p.player)))],
    [phases, teamA, lineupA] // eslint-disable-line react-hooks/exhaustive-deps
  );
  const allNamesB = useMemo(
    () => [...new Set(teamPhases(teamB).flatMap((p) => p.players.map((pl) => pl.player)).concat((lineupB?.starters ?? []).map((p) => p.player)))],
    [phases, teamB, lineupB] // eslint-disable-line react-hooks/exhaustive-deps
  );
  const imagesA = useSquadImages(teamA, allNamesA);
  const imagesB = useSquadImages(teamB, allNamesB);

  // Average positions: home attacks left→right, away right→left.
  const avgAttacksRight = avgTeam === teamA;
  const avgColor = teamColors[avgTeam] ?? "#22c55e";
  const avgImages = avgTeam === teamA ? imagesA : imagesB;
  const avgPhase = phaseFor(avgTeam);
  const avgPlayers = useMemo(() => phasePlayersFor(avgTeam), [avgPhase, avgTeam, lineupA, lineupB]); // eslint-disable-line react-hooks/exhaustive-deps

  // Players without touches in a short phase fall back to their formation slot
  // so the full XI is always visible.
  const avgPoint = (player: LineupPlayer): Point => {
    const source = player.avg ?? { x: player.x, y: player.y };
    const x = avgAttacksRight ? source.x : PITCH_W - source.x;
    const y = avgAttacksRight ? PITCH_H - source.y : source.y;
    return [x, y];
  };
  const voronoi = useMemo(() => {
    if (mode !== "average" || avgPlayers.length < 3) return [];
    return voronoiCells(avgPlayers.map(avgPoint));
  }, [mode, avgPlayers, avgAttacksRight]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!lineupA && !lineupB) return null;

  const phaseChips = (team: string) => {
    const list = teamPhases(team);
    if (list.length < 2) return null;
    const active = Math.min(phaseIndexByTeam[team] ?? 0, list.length - 1);
    return (
      <div className="lineup-phase-row" role="tablist" aria-label={`${team} match phases`}>
        <span className="lineup-phase-team" style={{ color: teamColors[team] ?? "var(--text)" }}>{team}</span>
        {list.map((p, index) => (
          <button
            key={p.label + index}
            type="button"
            className={`lineup-phase-chip${index === active ? " is-active" : ""}`}
            onClick={() => setPhaseFor(team, index)}
          >
            {p.label}
            {index > 0 ? <span className="lineup-phase-sub" aria-hidden="true">⇄</span> : null}
          </button>
        ))}
      </div>
    );
  };

  const activeFilterLabels = () => {
    const labels: string[] = [];
    if (mode === "average") {
      labels.push(avgTeam, "Avg positions");
      const phase = phaseFor(avgTeam);
      if (phase && teamPhases(avgTeam).length > 1) labels.push(phase.label);
    }
    return labels;
  };
  const formationMeta =
    mode === "formation"
      ? [
          { team: teamA, formation: phaseFormationFor(teamA), align: "left" as const },
          { team: teamB, formation: phaseFormationFor(teamB), align: "right" as const },
        ]
      : [
          {
            team: avgTeam,
            formation: `${phaseFormationFor(avgTeam) || "Average positions"} · attacking ${avgAttacksRight ? "→" : "←"}${
              avgPhase && teamPhases(avgTeam).length > 1 ? ` · ${avgPhase.label}` : ""
            }`,
            align: avgAttacksRight ? ("left" as const) : ("right" as const),
          },
        ];

  return (
    <section className="card stack">
      <div className="chart-card-head">
        <div>
          <span className="eyebrow">Team Sheets</span>
          <h2 style={{ margin: "6px 0 0" }}>Starting Lineups &amp; Substitutions</h2>
        </div>
        <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
          {mode === "average" ? (
            <div className="lineup-toggle-group" role="tablist" aria-label="Team">
              {[teamA, teamB].map((team) => (
                <button
                  key={team}
                  type="button"
                  className={avgTeam === team ? "is-active" : ""}
                  style={avgTeam === team ? { background: teamColors[team] ?? "var(--accent)", color: "#04121f" } : undefined}
                  onClick={() => setAvgTeam(team)}
                >
                  {team}
                </button>
              ))}
            </div>
          ) : null}
          <div className="lineup-toggle-group" role="tablist" aria-label="Lineup display mode">
            <button type="button" className={mode === "formation" ? "is-active" : ""} onClick={() => setMode("formation")}>
              Formation
            </button>
            <button type="button" className={mode === "average" ? "is-active" : ""} onClick={() => setMode("average")}>
              Avg positions
            </button>
          </div>
          <DownloadPngButton
            filename={`${teamA}-vs-${teamB}-lineups`}
            title="Starting Lineups"
            filters={activeFilterLabels()}
          />
        </div>
      </div>

      {mode === "formation" ? (
        <>
          {phaseChips(teamA)}
          {phaseChips(teamB)}
        </>
      ) : (
        phaseChips(avgTeam)
      )}

      <div className={`lineup-formation-meta ${mode === "average" ? "is-average" : ""}`}>
        {formationMeta.map((item) => (
          <div
            key={item.team}
            className={`lineup-formation-meta-item align-${item.align}`}
            style={{ color: teamColors[item.team] ?? "var(--text)" }}
          >
            <span className="lineup-formation-meta-team">{item.team}</span>
            {item.formation ? <span className="lineup-formation-meta-detail">{item.formation}</span> : null}
          </div>
        ))}
      </div>

      <svg viewBox={`0 0 ${PITCH_W} ${PITCH_H}`} className="lineups-pitch-svg" aria-label="Starting lineups pitch">
        <rect x="0" y="0" width={PITCH_W} height={PITCH_H} rx="1" fill="rgba(148,163,184,0.08)" />
        {mode === "average" && voronoi.length ? (
          <g>
            {voronoi.map((cell, index) =>
              cell.length ? (
                <polygon
                  key={index}
                  points={cell.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(" ")}
                  fill={colorWithAlpha(avgColor, 0.09)}
                  stroke={colorWithAlpha(avgColor, 0.45)}
                  strokeWidth={0.22}
                />
              ) : null
            )}
          </g>
        ) : null}
        <PitchLines />

        {mode === "formation" ? (
          <>
            {[{ team: teamA, images: imagesA, side: "left" as const }, { team: teamB, images: imagesB, side: "right" as const }].map(
              ({ team, images, side }) => {
                const players = phasePlayersFor(team);
                if (!players.length) return null;
                return (
                  <g key={team}>
                    {players.map((player) => {
                      const rawX = player.x * 0.5;
                      const x = side === "left" ? rawX : PITCH_W - rawX;
                      // Left team attacks right (flip y); right team is mirrored back.
                      const y = side === "left" ? svgY(player.y, true) : PITCH_H - svgY(player.y, true);
                      return (
                        <PlayerMarker
                          key={player.player_id}
                          x={x}
                          y={y}
                          player={player}
                          color={teamColors[team] ?? (side === "left" ? "#22c55e" : "#60a5fa")}
                          imageUrl={images[player.player]}
                          clipId={`lineup-clip-${team === teamA ? "a" : "b"}-${player.player_id}`}
                        />
                      );
                    })}
                  </g>
                );
              }
            )}
          </>
        ) : (
          <g>
            {avgPlayers.map((player) => {
              const [x, y] = avgPoint(player);
              return (
                <PlayerMarker
                  key={player.player_id}
                  x={x}
                  y={y}
                  player={player}
                  color={avgColor}
                  imageUrl={avgImages[player.player]}
                  clipId={`lineup-avg-clip-${player.player_id}`}
                />
              );
            })}
          </g>
        )}
      </svg>

      <div className="grid grid-2">
        {[teamA, teamB].map((team) => {
          const subs = substitutions.filter((sub) => sub.team === team);
          return (
            <div key={team} className="stack" style={{ gap: 8 }}>
              <strong style={{ color: teamColors[team] ?? "var(--text)" }}>{team} — substitutions</strong>
              {subs.length ? (
                <ul className="lineup-subs-list">
                  {subs.map((sub, index) => (
                    <li key={index}>
                      <span className="lineup-sub-minute">{sub.minute}&apos;</span>
                      <span className="lineup-sub-on">▲ {sub.player_on}</span>
                      {sub.player_off ? <span className="lineup-sub-off">▼ {sub.player_off}</span> : null}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="muted-copy" style={{ margin: 0 }}>No substitutions recorded.</p>
              )}
            </div>
          );
        })}
      </div>
      <p className="chart-footnote">
        Team sheets from the official lineup data ({lineupA?.formation || "—"} vs {lineupB?.formation || "—"}); captains are ringed in gold. Each team&apos;s phase chips split the match at its own substitutions and formation changes — pick a phase to see the XI (and formation) actually on the pitch. Avg positions show mean touch locations within the phase (home attacks →, away ←); players without touches in a phase sit at their formation slot.
      </p>
    </section>
  );
}
