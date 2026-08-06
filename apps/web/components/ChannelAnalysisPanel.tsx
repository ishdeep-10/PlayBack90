"use client";

import { DownloadPngButton, type SideTable } from "./DownloadPngButton";

import { useEffect, useState } from "react";

import { getAnalysisView } from "../lib/api";
import { colorWithAlpha } from "../lib/theme";
import { PlayerAvatar, getCachedPlayerImage } from "./PlayerAvatar";

type AreaStats = {
  touches: number;
  passes: number;
  passes_completed: number;
  progressive_actions: number;
  xt: number;
  xt_gained: number;
  xt_lost: number;
  xt_share: number;
  flow_dx: number;
  flow_dy: number;
  flow_count: number;
  top_player: string;
  top_player_xt: number;
};

type ChannelRow = AreaStats & {
  channel: string;
  label: string;
  y_start: number;
  y_end: number;
  final_third_entries: number;
};

type ZoneRow = AreaStats & {
  zone: string;
  label: string;
  long_label: string;
  x_start: number;
  x_end: number;
  y_start: number;
  y_end: number;
};

type Props = {
  matchId: string;
  source: string;
  league?: string;
  season?: string;
  jobId?: string;
  team: string;
  teamColor: string;
};

type ViewMode = "channels" | "zones";
type Perspective = "origin" | "destination";

const PITCH_LINES_PATH =
  "M0 0 H105 V68 H0 Z M52.5 0 V68 M52.5 34 m-9.15 0 a9.15 9.15 0 1 0 18.3 0 a9.15 9.15 0 1 0 -18.3 0 M0 13.84 H16.5 V54.16 H0 Z M105 13.84 H88.5 V54.16 H105 Z M0 24.84 H5.5 V43.16 H0 Z M105 24.84 H99.5 V43.16 H105 Z";

// Juego de Posición grid lines (mplsoccer uefa positional dims).
const ZONE_X_LINES = [16.5, 34.5, 52.5, 70.5, 88.5];
const ZONE_Y_LINES = [13.84, 24.84, 43.16, 54.16];

function shortName(name: string) {
  const parts = name.trim().split(/\s+/);
  return parts.length > 1 ? `${parts[0][0]}. ${parts[parts.length - 1]}` : name;
}

export function ChannelAnalysisPanel({ matchId, source, league, season, jobId, team, teamColor }: Props) {
  const [channels, setChannels] = useState<ChannelRow[]>([]);
  const [zones, setZones] = useState<ZoneRow[]>([]);
  const [channelsReceived, setChannelsReceived] = useState<ChannelRow[]>([]);
  const [zonesReceived, setZonesReceived] = useState<ZoneRow[]>([]);
  const [mode, setMode] = useState<ViewMode>("channels");
  const [perspective, setPerspective] = useState<Perspective>("origin");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    const filters: Record<string, string | undefined> = { team };
    if (source !== "r2") filters.job_id = jobId;
    const body =
      source !== "r2"
        ? { match_id: matchId, source, filters }
        : { match_id: matchId, source: "r2", league, season, filters };
    getAnalysisView("channel-analysis", body)
      .then((view) => {
        if (cancelled) return;
        const payload = (view.payload ?? {}) as Record<string, unknown>;
        setChannels((payload.channels as ChannelRow[] | undefined) ?? []);
        setZones((payload.zones as ZoneRow[] | undefined) ?? []);
        setChannelsReceived((payload.channels_received as ChannelRow[] | undefined) ?? []);
        setZonesReceived((payload.zones_received as ZoneRow[] | undefined) ?? []);
      })
      .catch(() => {
        if (!cancelled) {
          setChannels([]);
          setZones([]);
          setChannelsReceived([]);
          setZonesReceived([]);
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [matchId, source, league, season, jobId, team]);

  if (!isLoading && !channels.length) return null;

  const isDestination = perspective === "destination";
  const activeChannels = isDestination && channelsReceived.length ? channelsReceived : channels;
  const activeZones = isDestination && zonesReceived.length ? zonesReceived : zones;

  const maxShare = Math.max(0.001, ...activeChannels.map((row) => row.xt_share));
  const maxZoneShare = Math.max(0.001, ...activeZones.map((row) => row.xt_share));
  // Losses are shaded on the same magnitude scale as gains so a marginal
  // negative zone reads faint, not alarming.
  const maxZoneAbs = Math.max(0.001, ...activeZones.map((row) => Math.abs(row.xt)));
  const sortedZones = [...activeZones].sort((a, b) => b.xt - a.xt);

  const netLabel = (row: { xt: number; xt_gained: number; xt_lost: number }) =>
    `${row.xt >= 0 ? "+" : ""}${row.xt.toFixed(2)} (▲${row.xt_gained.toFixed(2)} ▼${Math.abs(row.xt_lost).toFixed(2)})`;

  const perspectiveLabel = isDestination ? "arriving in" : "created from";

  const buildSideTable = (): SideTable => {
    const withTopPlayer = (row: AreaStats & { label: string }) => ({
      image: row.top_player ? getCachedPlayerImage(row.top_player, team) : null,
      label: row.label,
      value: `${netLabel(row)} · ${Math.round(row.xt_share * 100)}%`,
      sub: row.top_player ? `Top: ${row.top_player} · +${row.top_player_xt.toFixed(2)} xT` : undefined,
    });
    if (mode === "zones") {
      return {
        title: `${team} · Half-space grid xT ${perspectiveLabel} (open play)`,
        large: true,
        rows: sortedZones
          .filter((row) => row.xt_gained > 0 || row.xt_lost < 0)
          .slice(0, 9)
          .map(withTopPlayer),
      };
    }
    return {
      title: `${team} · Channel xT ${perspectiveLabel} (open play)`,
      large: true,
      rows: [...activeChannels].sort((a, b) => b.xt_share - a.xt_share).map(withTopPlayer),
    };
  };

  const flowArrow = (row: ZoneRow) => {
    if (row.flow_count < 2 || row.xt_gained <= 0) return null;
    const length = Math.hypot(row.flow_dx, row.flow_dy);
    if (length < 1) return null;
    const displayLength = Math.min(9, Math.max(4, length * 0.35));
    const unitX = row.flow_dx / length;
    const unitY = -row.flow_dy / length; // svg y grows downward
    const centerX = (row.x_start + row.x_end) / 2;
    const centerY = 68 - (row.y_start + row.y_end) / 2;
    return {
      x1: centerX - (unitX * displayLength) / 2,
      y1: centerY - (unitY * displayLength) / 2,
      x2: centerX + (unitX * displayLength) / 2,
      y2: centerY + (unitY * displayLength) / 2,
    };
  };

  return (
    <section className={`card stack${isLoading ? " is-loading-soft" : ""}`}>
      <div className="chart-card-head">
        <div>
          <span className="eyebrow">Channels &amp; Half-Spaces</span>
          <h2 style={{ margin: "6px 0 0" }}>Where {team} builds danger</h2>
        </div>
        <div className="channel-mode-controls">
          <div className="channel-mode-toggle" role="group" aria-label="Threat perspective">
            {([
              ["origin", "Created from"],
              ["destination", "Arrives in"],
            ] as Array<[Perspective, string]>).map(([value, label]) => (
              <button
                key={value}
                type="button"
                className={perspective === value ? "button" : "ghost-button"}
                onClick={() => setPerspective(value)}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="channel-mode-toggle" role="group" aria-label="Channel view mode">
            {([
              ["channels", "Vertical channels"],
              ["zones", "Half-space grid"],
            ] as Array<[ViewMode, string]>).map(([value, label]) => (
              <button
                key={value}
                type="button"
                className={mode === value ? "button" : "ghost-button"}
                onClick={() => setMode(value)}
              >
                {label}
              </button>
            ))}
          </div>
          <DownloadPngButton
            filename={`${team}-channels`}
            title={() => `${mode === "zones" ? "Half-Space Grid (Juego de Posición)" : "Channels & Half-Spaces"} — xT ${perspective === "destination" ? "arrives in" : "created from"}`}
            filters={[team]}
            sideTable={buildSideTable}
          />
        </div>
      </div>
      <p className="muted-copy" style={{ margin: 0 }}>
        {mode === "zones"
          ? `Juego de Posición grid, open play only (attacking left → right). Zones are colored by their share of xT ${perspectiveLabel} — red zones lost more threat than they created. Arrows show the average direction of progressive actions; ▲ gained / ▼ lost.`
          : `Threat ${perspectiveLabel} per vertical corridor, open play only (attacking left → right). Band intensity shows each channel's share of xT gained; entries count receptions in the final third of that channel. ▲ gained / ▼ lost.`}
      </p>
      <div className="channel-analysis-grid">
        {mode === "channels" ? (
          <svg viewBox="0 0 105 68" className="channel-pitch-svg" role="img" aria-label={`${team} channel threat map`}>
            <rect x="0" y="0" width="105" height="68" fill="var(--bg-muted)" />
            {activeChannels.map((row) => (
              <rect
                key={row.channel}
                x="0"
                y={68 - row.y_end}
                width="105"
                height={row.y_end - row.y_start}
                fill={teamColor}
                opacity={0.08 + (row.xt_share / maxShare) * 0.55}
              />
            ))}
            {activeChannels.slice(0, -1).map((row) => (
              <line key={`sep-${row.channel}`} x1="0" x2="105" y1={68 - row.y_end} y2={68 - row.y_end} stroke="rgba(148,163,184,0.4)" strokeWidth="0.3" strokeDasharray="1.6 1.6" />
            ))}
            <path d={PITCH_LINES_PATH} fill="none" stroke="rgba(226,232,240,0.55)" strokeWidth="0.45" />
            {activeChannels.map((row) => {
              const midY = 68 - (row.y_start + row.y_end) / 2;
              return (
                <g key={`text-${row.channel}`}>
                  <text x={53.5} y={midY - 1.2} className="channel-pitch-label" textAnchor="middle">
                    {row.label}
                  </text>
                  <text x={53.5} y={midY + 3.6} className="channel-pitch-sublabel" textAnchor="middle">
                    {Math.round(row.xt_share * 100)}% xT · {row.final_third_entries} entries
                  </text>
                </g>
              );
            })}
          </svg>
        ) : (
          <svg viewBox="0 0 105 68" className="channel-pitch-svg" role="img" aria-label={`${team} half-space grid threat map`}>
            <defs>
              <marker id="zone-flow-arrow" viewBox="0 0 6 6" refX="4.6" refY="3" markerWidth="4.5" markerHeight="4.5" orient="auto-start-reverse">
                <path d="M0 0 L6 3 L0 6 Z" fill="rgba(248,250,252,0.9)" />
              </marker>
            </defs>
            <rect x="0" y="0" width="105" height="68" fill="var(--bg-muted)" />
            {activeZones.map((row) => {
              const isNetNegative = row.xt < 0;
              return (
                <rect
                  key={row.zone}
                  x={row.x_start}
                  y={68 - row.y_end}
                  width={row.x_end - row.x_start}
                  height={row.y_end - row.y_start}
                  fill={isNetNegative ? "#ef4444" : teamColor}
                  opacity={isNetNegative
                    ? 0.08 + (Math.abs(row.xt) / maxZoneAbs) * 0.5
                    : row.xt_gained > 0
                      ? 0.06 + (row.xt_share / maxZoneShare) * 0.62
                      : 0.02}
                >
                  <title>{`${row.long_label}: net xT ${row.xt.toFixed(2)} (▲${row.xt_gained.toFixed(2)} ▼${Math.abs(row.xt_lost).toFixed(2)}) · ${Math.round(row.xt_share * 100)}%${row.top_player ? ` · Top: ${row.top_player}` : ""}`}</title>
                </rect>
              );
            })}
            {ZONE_X_LINES.map((x) => (
              <line key={`zx-${x}`} x1={x} x2={x} y1="0" y2="68" stroke="rgba(148,163,184,0.45)" strokeWidth="0.28" strokeDasharray="1.4 1.4" />
            ))}
            {ZONE_Y_LINES.map((y) => (
              <line key={`zy-${y}`} x1="0" x2="105" y1={68 - y} y2={68 - y} stroke="rgba(148,163,184,0.45)" strokeWidth="0.28" strokeDasharray="1.4 1.4" />
            ))}
            {/* six-yard depth divider across the box lanes */}
            <line x1={99.5} x2={99.5} y1={68 - 54.16} y2={68 - 13.84} stroke="rgba(148,163,184,0.45)" strokeWidth="0.28" strokeDasharray="1.4 1.4" />
            <path d={PITCH_LINES_PATH} fill="none" stroke="rgba(226,232,240,0.55)" strokeWidth="0.45" />
            {activeZones.map((row) => {
              const arrow = flowArrow(row);
              if (!arrow) return null;
              return (
                <line
                  key={`flow-${row.zone}`}
                  x1={arrow.x1}
                  y1={arrow.y1}
                  x2={arrow.x2}
                  y2={arrow.y2}
                  stroke="rgba(248,250,252,0.85)"
                  strokeWidth="0.55"
                  markerEnd="url(#zone-flow-arrow)"
                />
              );
            })}
            {activeZones.filter((row) => row.xt_share >= 0.03).map((row) => (
              <text
                key={`zt-${row.zone}`}
                x={(row.x_start + row.x_end) / 2}
                y={68 - (row.y_start + row.y_end) / 2 + 4.2}
                className="channel-pitch-sublabel"
                textAnchor="middle"
              >
                {Math.round(row.xt_share * 100)}%
              </text>
            ))}
          </svg>
        )}
        {mode === "channels" ? (
          <div className="channel-stat-list">
            {[...activeChannels].sort((a, b) => b.xt_share - a.xt_share).map((row) => (
              <div key={row.channel} className="channel-stat-row">
                <span className="channel-stat-swatch" style={{ background: colorWithAlpha(teamColor, 0.15 + (row.xt_share / maxShare) * 0.6) }} />
                <div>
                  <strong>{row.label}</strong>
                  <span>
                    {row.passes_completed}/{row.passes} passes · {row.progressive_actions} progressive · xT {netLabel(row)}
                  </span>
                  {row.top_player && (
                    <span className="channel-top-player">
                      <PlayerAvatar name={row.top_player} team={team} size={18} />
                      Top: {shortName(row.top_player)} · +{row.top_player_xt.toFixed(2)} xT
                    </span>
                  )}
                </div>
                <b>{Math.round(row.xt_share * 100)}%</b>
              </div>
            ))}
          </div>
        ) : (
          <div className="channel-zone-table-wrap">
            <table className="table channel-zone-table">
              <thead>
                <tr>
                  <th>Zone</th>
                  <th>Passes</th>
                  <th>Prog</th>
                  <th>▲ xT</th>
                  <th>▼ xT</th>
                  <th>Net</th>
                  <th>Share</th>
                  <th>Top player</th>
                </tr>
              </thead>
              <tbody>
                {sortedZones.map((row) => (
                  <tr key={row.zone}>
                    <td>
                      <span className="channel-zone-name">
                        <span
                          className="channel-stat-swatch"
                          style={{
                            background: row.xt < 0
                              ? colorWithAlpha("#ef4444", 0.15 + (Math.abs(row.xt) / maxZoneAbs) * 0.55)
                              : colorWithAlpha(teamColor, row.xt_gained > 0 ? 0.12 + (row.xt_share / maxZoneShare) * 0.62 : 0.05),
                          }}
                        />
                        {row.long_label}
                      </span>
                    </td>
                    <td>{row.passes_completed}/{row.passes}</td>
                    <td>{row.progressive_actions}</td>
                    <td>{row.xt_gained.toFixed(2)}</td>
                    <td className={row.xt_lost < 0 ? "is-xt-lost" : ""}>{Math.abs(row.xt_lost).toFixed(2)}</td>
                    <td className={row.xt < 0 ? "is-xt-lost" : ""}>{row.xt >= 0 ? "+" : ""}{row.xt.toFixed(2)}</td>
                    <td><b>{Math.round(row.xt_share * 100)}%</b></td>
                    <td>
                      {row.top_player ? (
                        <span className="channel-zone-name channel-zone-top-player">
                          <PlayerAvatar name={row.top_player} team={team} size={20} />
                          {shortName(row.top_player)}
                        </span>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
