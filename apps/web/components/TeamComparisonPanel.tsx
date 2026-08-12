"use client";

import { useState } from "react";
import Image from "next/image";
import { SeasonDeltaChip } from "./season/SeasonDeltaChip";
import { DistributionStrip } from "./season/DistributionStrip";
import { metricByKey, type BaselineMetric, type TeamBaseline } from "./season/baselineTypes";

/** Recast the vs-opponent distribution as a strip-compatible metric. */
function vsOpponentMetric(metric: BaselineMetric | undefined): BaselineMetric | undefined {
  if (
    !metric ||
    metric.vsOpponentMin === undefined ||
    metric.vsOpponentMax === undefined ||
    metric.vsOpponentP25 === undefined ||
    metric.vsOpponentP75 === undefined ||
    metric.vsOpponentMedian === undefined ||
    (metric.nVsOpponent ?? 0) < 4
  ) {
    return undefined;
  }
  return {
    ...metric,
    min: metric.vsOpponentMin,
    max: metric.vsOpponentMax,
    p25: metric.vsOpponentP25,
    p75: metric.vsOpponentP75,
    seasonMedian: metric.vsOpponentMedian,
    seasonAvg: metric.vsOpponentAvg,
    nMatches: metric.nVsOpponent ?? 0,
    gameRank: undefined,
    last5Avg: undefined,
  };
}

type SummaryRow = Record<string, string | number>;
type Breakdowns = Record<string, Record<string, unknown>>;

type Props = {
  teamA: string;
  teamB: string;
  summaryTeamA: SummaryRow;
  summaryTeamB: SummaryRow;
  teamAColor?: string;
  teamBColor?: string;
  teamALogoUrl?: string | null;
  teamBLogoUrl?: string | null;
  breakdowns: Breakdowns;
  seasonBaselines?: Record<string, TeamBaseline>;
};

type StatConfig = {
  label: string;
  key: string;
  kind?: "number" | "decimal" | "percent" | "xg" | "big-chances" | "shots";
  lowerIsBetter?: boolean;
  breakdownKey?: string;
};

const STAT_ROWS: StatConfig[] = [
  { label: "Goals", key: "goals", breakdownKey: "goals" },
  { label: "xG", key: "xg", kind: "xg", breakdownKey: "xg" },
  { label: "Shots (OT)", key: "shots", kind: "shots", breakdownKey: "shots" },
  { label: "Possession", key: "possession_pct", kind: "percent", breakdownKey: "possession_pct" },
  { label: "Pass Accuracy", key: "pass_accuracy", kind: "percent", breakdownKey: "pass_accuracy" },
  { label: "Big Chances", key: "big_chances_created", kind: "big-chances", breakdownKey: "big_chances" },
  { label: "PPDA", key: "ppda", kind: "decimal", lowerIsBetter: true, breakdownKey: "ppda" },
  { label: "Turnovers", key: "turnovers", lowerIsBetter: true, breakdownKey: "turnovers" },
  { label: "Corners", key: "corners_taken", breakdownKey: "corners_taken" },
  { label: "xT", key: "xt", kind: "xg", breakdownKey: "xt" },
];

const METRIC_LABELS: Record<string, string> = {
  open_play: "Open play",
  set_piece: "Set piece",
  penalty: "Penalty",
  non_penalty: "Non-penalty",
  first_half: "1st half",
  second_half: "2nd half",
  on_target: "On target",
  off_target: "Off target",
  blocked: "Blocked",
  woodwork: "Woodwork",
  defensive: "Defensive 3rd",
  middle: "Middle 3rd",
  final: "Final 3rd",
  left: "Left side",
  right: "Right side",
  total: "Total",
  passes: "From passes",
  carries: "From carries",
};

function formatValue(row: SummaryRow, stat: StatConfig) {
  if (stat.kind === "big-chances") return `${Number(row.big_chances_created ?? 0)} (${Number(row.big_chances_missed ?? 0)})`;
  if (stat.kind === "shots") return `${Number(row.shots ?? 0)} (${Number(row.shots_on_target ?? 0)})`;
  const value = Number(row[stat.key] ?? 0);
  if (stat.kind === "percent") return `${value.toFixed(1)}%`;
  if (stat.kind === "xg") return value.toFixed(2);
  if (stat.kind === "decimal") return value.toFixed(1);
  return String(Math.round(value));
}

function metricLabel(key: string) {
  return METRIC_LABELS[key] ?? key.replace(/_/g, " ");
}

type EventRow = { player: string; minute: number; second?: number; xg?: number; penalty?: boolean; own_goal?: boolean; kind?: string };

function isEventList(value: unknown): value is EventRow[] {
  return Array.isArray(value);
}

function EventList({ events, color, statKey }: { events: EventRow[]; color?: string; statKey: string }) {
  if (!events.length) return <p className="muted-copy" style={{ margin: 0, fontSize: "0.8rem" }}>—</p>;
  return (
    <ul className="stat-breakdown-events">
      {events.map((event, index) => (
        <li key={index}>
          <span className="stat-breakdown-minute">{event.minute}&apos;</span>
          <span style={{ color: color ?? "var(--text)", fontWeight: 700 }}>{event.player}</span>
          {statKey === "goals" ? (
            <span className="muted" style={{ fontSize: "0.78rem" }}>
              {event.own_goal ? "OG" : event.penalty ? "pen" : `xG ${Number(event.xg ?? 0).toFixed(2)}`}
            </span>
          ) : null}
          {statKey === "big_chances" && event.kind ? (
            <span className="muted" style={{ fontSize: "0.78rem" }}>{event.kind}</span>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

function formatMetricValue(statKey: string, _metric: string, value: unknown) {
  if (value && typeof value === "object") {
    const detail = value as Record<string, unknown>;
    if ("pct" in detail) return `${Number(detail.pct ?? 0).toFixed(1)}% (${Number(detail.completed ?? 0)}/${Number(detail.passes ?? 0)})`;
    return "—";
  }
  const num = Number(value ?? 0);
  if (statKey === "possession_pct") return `${num.toFixed(1)}%`;
  if (statKey === "xg" || statKey === "xt") return num.toFixed(2);
  if (statKey === "ppda") return num.toFixed(1);
  return String(Math.round(num));
}

function metricNumber(value: unknown): number {
  if (value && typeof value === "object") {
    const detail = value as Record<string, unknown>;
    if ("pct" in detail) return Number(detail.pct ?? 0);
    return 0;
  }
  return Number(value ?? 0);
}

const LOWER_IS_BETTER_STATS = new Set(["ppda", "turnovers"]);

function BreakdownPanel({
  statKey,
  teamA,
  teamB,
  teamAColor,
  teamBColor,
  breakdown,
}: {
  statKey: string;
  teamA: string;
  teamB: string;
  teamAColor?: string;
  teamBColor?: string;
  breakdown: Record<string, unknown>;
}) {
  const dataA = breakdown[teamA];
  const dataB = breakdown[teamB];

  if (isEventList(dataA) || isEventList(dataB)) {
    return (
      <div className="stat-breakdown-panel">
        <div className="stat-breakdown-grid" style={{ alignItems: "start" }}>
          <EventList events={isEventList(dataA) ? dataA : []} color={teamAColor} statKey={statKey} />
          <span className="stat-breakdown-metric">{statKey === "goals" ? "Scorers" : "Events"}</span>
          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <EventList events={isEventList(dataB) ? dataB : []} color={teamBColor} statKey={statKey} />
          </div>
        </div>
      </div>
    );
  }

  const metricsA = (dataA ?? {}) as Record<string, unknown>;
  const metricsB = (dataB ?? {}) as Record<string, unknown>;
  const metricKeys = Array.from(new Set([...Object.keys(metricsA), ...Object.keys(metricsB)]));
  if (!metricKeys.length) {
    return (
      <div className="stat-breakdown-panel">
        <p className="muted-copy" style={{ margin: 0, fontSize: "0.8rem" }}>No breakdown available for this stat.</p>
      </div>
    );
  }
  const lowerIsBetter = LOWER_IS_BETTER_STATS.has(statKey);
  return (
    <div className="stat-breakdown-panel">
      {metricKeys.map((metric) => {
        const left = metricNumber(metricsA[metric]);
        const right = metricNumber(metricsB[metric]);
        const leftWins = left !== right && (lowerIsBetter ? left < right : left > right);
        const rightWins = left !== right && !leftWins;
        return (
          <div key={metric} className="stat-breakdown-grid">
            <span className={`stat-breakdown-cell${leftWins ? " is-best" : ""}`}>{formatMetricValue(statKey, metric, metricsA[metric])}</span>
            <span className="stat-breakdown-metric">{metricLabel(metric)}</span>
            <span className={`stat-breakdown-cell${rightWins ? " is-best" : ""}`}>{formatMetricValue(statKey, metric, metricsB[metric])}</span>
          </div>
        );
      })}
    </div>
  );
}

export function TeamComparisonPanel({
  teamA,
  teamB,
  summaryTeamA,
  summaryTeamB,
  teamAColor,
  teamBColor,
  teamALogoUrl,
  teamBLogoUrl,
  breakdowns,
  seasonBaselines,
}: Props) {
  const [openStat, setOpenStat] = useState<string | null>(null);
  const baselineA = seasonBaselines?.[teamA];
  const baselineB = seasonBaselines?.[teamB];
  const hasBaselines = Boolean(
    (baselineA && !baselineA.lowSample && baselineA.metrics.length) ||
    (baselineB && !baselineB.lowSample && baselineB.metrics.length)
  );

  const winnerClass = (left: number, right: number, side: "left" | "right", lowerIsBetter = false) => {
    if (left === right) return "";
    const leftWins = lowerIsBetter ? left < right : left > right;
    return (side === "left" ? leftWins : !leftWins) ? " is-best" : "";
  };

  return (
    <section className="card stack">
      <div>
        <span className="eyebrow">Match Summary</span>
        <h2 style={{ margin: "6px 0 0" }}>Team Comparison</h2>
      </div>
      <div className="team-summary-compare">
        <div className="team-summary-compare-head">
          <strong className="team-summary-team team-summary-team-left" style={{ color: teamAColor ?? "var(--text)" }}>
            {teamALogoUrl ? <Image className="team-summary-logo" src={teamALogoUrl} alt={`${teamA} logo`} width={28} height={28} /> : null}
            <span>{teamA}</span>
          </strong>
          <span>Stat</span>
          <strong className="team-summary-team team-summary-team-right" style={{ color: teamBColor ?? "var(--text)" }}>
            <span>{teamB}</span>
            {teamBLogoUrl ? <Image className="team-summary-logo" src={teamBLogoUrl} alt={`${teamB} logo`} width={28} height={28} /> : null}
          </strong>
        </div>
        {STAT_ROWS.map((stat) => {
          const leftValue = Number(summaryTeamA[stat.key] ?? 0);
          const rightValue = Number(summaryTeamB[stat.key] ?? 0);
          const metricA = baselineA && !baselineA.lowSample ? metricByKey(baselineA, stat.key) : undefined;
          const metricB = baselineB && !baselineB.lowSample ? metricByKey(baselineB, stat.key) : undefined;
          const breakdown = (stat.breakdownKey ? breakdowns[stat.breakdownKey] : undefined) as Record<string, unknown> | undefined;
          const expandable = Boolean((breakdown && Object.keys(breakdown).length) || metricA || metricB);
          const isOpen = openStat === stat.key;
          return (
            <div key={stat.label}>
              <div
                className={`team-summary-compare-row${expandable ? " is-expandable" : ""}${isOpen ? " is-open" : ""}`}
                role={expandable ? "button" : undefined}
                tabIndex={expandable ? 0 : undefined}
                aria-expanded={expandable ? isOpen : undefined}
                onClick={() => expandable && setOpenStat(isOpen ? null : stat.key)}
                onKeyDown={(event) => {
                  if (expandable && (event.key === "Enter" || event.key === " ")) {
                    event.preventDefault();
                    setOpenStat(isOpen ? null : stat.key);
                  }
                }}
              >
                <span className={`team-summary-value${winnerClass(leftValue, rightValue, "left", stat.lowerIsBetter)}`}>
                  {formatValue(summaryTeamA, stat)}
                  <SeasonDeltaChip metric={metricA} />
                </span>
                <span className="team-summary-label">
                  {stat.label}
                  {expandable ? <span aria-hidden="true" style={{ marginLeft: 6, opacity: 0.7 }}>{isOpen ? "▾" : "▸"}</span> : null}
                </span>
                <span className={`team-summary-value${winnerClass(leftValue, rightValue, "right", stat.lowerIsBetter)}`}>
                  {formatValue(summaryTeamB, stat)}
                  <SeasonDeltaChip metric={metricB} />
                </span>
              </div>
              {isOpen && (metricA || metricB) ? (
                <div className="season-strip-row">
                  {metricA ? <DistributionStrip metric={metricA} markerColor={teamAColor} /> : <span />}
                  <span className="season-strip-row-label">Season range</span>
                  {metricB ? <DistributionStrip metric={metricB} markerColor={teamBColor} /> : <span />}
                </div>
              ) : null}
              {isOpen && (vsOpponentMetric(metricA) || vsOpponentMetric(metricB)) ? (
                <div className="season-strip-row">
                  {(() => {
                    const vsA = vsOpponentMetric(metricA);
                    if (!vsA) return <span />;
                    const fmtNum = (v: number) => (Math.abs(v) >= 10 ? v.toFixed(0) : v.toFixed(Math.abs(v) < 1 ? 2 : 1));
                    return (
                      <DistributionStrip
                        metric={vsA}
                        markerColor={teamAColor}
                        caption={`teams usually get ${fmtNum(vsA.seasonMedian ?? 0)} vs ${teamB} — tonight ${fmtNum(vsA.matchValue)}`}
                      />
                    );
                  })()}
                  <span className="season-strip-row-label">Typical vs opponent</span>
                  {(() => {
                    const vsB = vsOpponentMetric(metricB);
                    if (!vsB) return <span />;
                    const fmtNum = (v: number) => (Math.abs(v) >= 10 ? v.toFixed(0) : v.toFixed(Math.abs(v) < 1 ? 2 : 1));
                    return (
                      <DistributionStrip
                        metric={vsB}
                        markerColor={teamBColor}
                        caption={`teams usually get ${fmtNum(vsB.seasonMedian ?? 0)} vs ${teamA} — tonight ${fmtNum(vsB.matchValue)}`}
                      />
                    );
                  })()}
                </div>
              ) : null}
              {isOpen && breakdown ? (
                <BreakdownPanel
                  statKey={stat.breakdownKey ?? stat.key}
                  teamA={teamA}
                  teamB={teamB}
                  teamAColor={teamAColor}
                  teamBColor={teamBColor}
                  breakdown={breakdown}
                />
              ) : null}
            </div>
          );
        })}
      </div>
      <p className="chart-footnote">
        Full-match totals side by side — click any stat to expand how it was accumulated (situations, halves and pitch thirds). Green marks the better side.
        {hasBaselines ? " Chips compare each side against its season average (excluding this match); expanded rows show the full season range (middle-half band, median tick, this match as the dot) plus what teams league-wide usually manage against tonight's opponent." : ""}
      </p>
    </section>
  );
}
