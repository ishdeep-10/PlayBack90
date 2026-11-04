"use client";

export type AgeBand = "all" | "u21" | "u23" | "u25";
export const AGE_LIMIT: Record<AgeBand, number> = { all: 99, u21: 21, u23: 23, u25: 25 };
const LABELS: Record<AgeBand, string> = { all: "All ages", u21: "U21", u23: "U23", u25: "U25" };

/** Players under the age limit today (U21 = younger than 21). */
export const inAgeBand = (age: number | undefined, band: AgeBand) => band === "all" || (typeof age === "number" && age < AGE_LIMIT[band]);

/** Age chips for the filter rows; rendered only when the data carries ages. */
export function AgeChips({ value, onChange }: { value: AgeBand; onChange: (band: AgeBand) => void }) {
  return (
    <>
      {(Object.keys(LABELS) as AgeBand[]).map((b) => (
        <button key={b} type="button" className={`season-chip${value === b ? " is-on" : ""}`} style={{ "--chip": "#c084fc" } as React.CSSProperties} onClick={() => onChange(b)} aria-pressed={value === b}>
          {LABELS[b]}
        </button>
      ))}
    </>
  );
}
