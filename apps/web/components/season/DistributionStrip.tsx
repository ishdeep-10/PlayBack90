import type { BaselineMetric } from "./baselineTypes";

type Props = {
  metric: BaselineMetric;
  /** Dot color for this match's value; defaults to the accent token. */
  markerColor?: string;
  format?: (value: number) => string;
  /** Overrides the default "Nth best of M matches" caption. */
  caption?: string;
};

const W = 220;
const H = 26;
const PAD = 8;
const MID = H / 2;

function ordinal(n: number): string {
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return `${n}${s[(v - 20) % 10] ?? s[v] ?? s[0]}`;
}

/**
 * Season distribution strip: min–max line, p25–p75 band, median tick and a
 * dot for this match. Pure SVG so it can sit inline in tables and panels.
 */
export function DistributionStrip({ metric, markerColor, format, caption }: Props) {
  const { min, max, p25, p75, seasonMedian, matchValue, last5Avg } = metric;
  if (min === undefined || max === undefined || p25 === undefined || p75 === undefined || seasonMedian === undefined) {
    return null;
  }
  if (metric.nMatches < 4) return null;
  const lo = Math.min(min, matchValue);
  const hi = Math.max(max, matchValue);
  const span = hi - lo || 1;
  const x = (v: number) => PAD + ((v - lo) / span) * (W - PAD * 2);

  const fmt = format ?? ((v: number) => (Math.abs(v) >= 10 ? v.toFixed(0) : v.toFixed(Math.abs(v) < 1 ? 2 : 1)));
  const rankText =
    caption ??
    (metric.gameRank !== undefined && metric.lowerIsBetter !== undefined
      ? `${ordinal(metric.gameRank)} ${metric.lowerIsBetter ? "best (lowest)" : "best"} of ${metric.nMatches + 1} matches`
      : "");

  return (
    <span className="season-strip" role="img" aria-label={`${metric.label}: this match ${fmt(matchValue)}, season median ${fmt(seasonMedian)}, range ${fmt(min)}–${fmt(max)}. ${rankText}`}>
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
        <title>{`${metric.label} — season range ${fmt(min)}–${fmt(max)}, middle half ${fmt(p25)}–${fmt(p75)}, median ${fmt(seasonMedian)}. This match: ${fmt(matchValue)}${rankText ? ` (${rankText})` : ""}`}</title>
        {/* min–max line */}
        <line x1={x(min)} x2={x(max)} y1={MID} y2={MID} className="season-strip-range" />
        {/* p25–p75 band */}
        <rect x={x(p25)} y={MID - 5} width={Math.max(2, x(p75) - x(p25))} height={10} rx={2} className="season-strip-band" />
        {/* median tick */}
        <line x1={x(seasonMedian)} x2={x(seasonMedian)} y1={MID - 8} y2={MID + 8} className="season-strip-median" />
        {/* last-5 hollow tick */}
        {last5Avg !== undefined ? (
          <circle cx={x(last5Avg)} cy={MID} r={4} className="season-strip-last5" />
        ) : null}
        {/* this match */}
        <circle cx={x(matchValue)} cy={MID} r={5} className="season-strip-match" style={markerColor ? { fill: markerColor } : undefined} />
      </svg>
      {rankText ? <span className="season-strip-caption">{rankText}</span> : null}
    </span>
  );
}
