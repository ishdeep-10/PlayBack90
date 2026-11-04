"use client";

type Metric = { key: string; label: string; category?: string };

const CATEGORY_ORDER = [
  "Shooting", "Chance creation", "Shot-creating actions", "Passing", "Carrying and dribbling", "Possession", "Defending", "Goalkeeping",
  "Attack", "Defence", "Pressing and duels", "Style and possession", "Crossing",
];

/** Metrics grouped by category (<optgroup>), categories in a fixed, football-sensible order. */
export function groupMetrics<T extends Metric>(metrics: T[]): [string, T[]][] {
  const by = new Map<string, T[]>();
  for (const m of metrics) by.set(m.category ?? "Other", [...(by.get(m.category ?? "Other") ?? []), m]);
  const rank = (c: string) => (CATEGORY_ORDER.indexOf(c) === -1 ? 99 : CATEGORY_ORDER.indexOf(c));
  return [...by.entries()].sort((a, b) => rank(a[0]) - rank(b[0])).map(([c, list]) => [c, [...list].sort((a, b) => a.label.localeCompare(b.label))]);
}

type Props<T extends Metric> = {
  metrics: T[];
  value: string;
  onChange: (key: string) => void;
  disabled?: boolean;
  /** label shown for an option (e.g. to note that it is unavailable) */
  describe?: (m: T) => string;
  isDisabled?: (m: T) => boolean;
  allowNone?: string;
};

export function MetricSelect<T extends Metric>({ metrics, value, onChange, disabled, describe, isDisabled, allowNone }: Props<T>) {
  return (
    <select className="select" value={value} onChange={(e) => onChange(e.target.value)} disabled={disabled}>
      {allowNone ? <option value="">{allowNone}</option> : null}
      {groupMetrics(metrics).map(([category, list]) => (
        <optgroup key={category} label={category}>
          {list.map((m) => (
            <option key={m.key} value={m.key} disabled={isDisabled?.(m)}>{describe ? describe(m) : m.label}</option>
          ))}
        </optgroup>
      ))}
    </select>
  );
}
