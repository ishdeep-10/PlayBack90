import type { BaselineMetric } from "./baselineTypes";

type Props = {
  metric: BaselineMetric | undefined;
  /** Compare per-90 values instead of raw match totals (player tables). */
  per90?: boolean;
  format?: (value: number) => string;
};

const TYPICAL_Z = 0.25;
const MIN_MATCHES = 4;

/**
 * ▲ / ▼ / · vs the season average. Direction glyph + tone class carry the
 * signal together, so meaning never rests on color alone.
 */
export function SeasonDeltaChip({ metric, per90 = false, format }: Props) {
  if (!metric || metric.nMatches < MIN_MATCHES) return null;

  let delta: number | undefined;
  if (per90) {
    if (metric.matchValuePer90 === undefined || metric.seasonPer90 === undefined) return null;
    delta = metric.matchValuePer90 - metric.seasonPer90;
  } else {
    delta = metric.delta;
  }
  if (delta === undefined) return null;

  const z = metric.zScore ?? 0;
  const typical = !per90 && Math.abs(z) < TYPICAL_Z;
  const better = metric.lowerIsBetter ? delta < 0 : delta > 0;
  const tone = typical ? "is-typical" : better ? "is-up" : "is-down";
  const glyph = typical ? "·" : delta > 0 ? "▲" : "▼";
  const fmt = format ?? ((v: number) => (Math.abs(v) >= 10 ? v.toFixed(0) : v.toFixed(Math.abs(v) < 1 ? 2 : 1)));
  const isRate = metric.kind === "rate";
  const title = per90
    ? `Season: ${fmt(metric.seasonPer90 ?? 0)}${isRate ? "" : " per 90"} (${metric.nMatches} matches)`
    : `Season avg: ${fmt(metric.seasonAvg ?? 0)} · median ${fmt(metric.seasonMedian ?? 0)} (${metric.nMatches} matches)`;

  return (
    <span className={`season-chip ${tone}`} title={title} aria-label={`${delta >= 0 ? "+" : ""}${fmt(delta)} vs season average`}>
      <span aria-hidden="true">{glyph}</span>
      {typical ? "typical" : `${delta > 0 ? "+" : "−"}${fmt(Math.abs(delta))}`}
    </span>
  );
}
