"use client";

import { useEffect, useRef, useState } from "react";

export type SliceSelection = { states: boolean[]; buckets: boolean[]; phases: boolean[] };

export const STATE_LABELS = ["Leading", "Drawing", "Trailing"];
export const BUCKET_LABELS = ["0-15", "15-30", "30-45", "45-60", "60-75", "75+"];
export const PHASE_LABELS = ["Open play", "Set pieces"];
const N_TIME = STATE_LABELS.length * BUCKET_LABELS.length; // minutes are kept per (state, time bucket)

export const ALL_SELECTED: SliceSelection = { states: [true, true, true], buckets: [true, true, true, true, true, true], phases: [true, true] };

export const isFiltered = (s: SliceSelection) => [...s.states, ...s.buckets, ...s.phases].some((v) => !v);

/** Count cells (phase * 18 + state * 6 + time bucket) covered by the selection. */
export function selectedCells(s: SliceSelection): number[] {
  const out: number[] = [];
  s.phases.forEach((ph, pi) => ph && s.states.forEach((on, si) => on && s.buckets.forEach((b, bi) => b && out.push(pi * N_TIME + si * BUCKET_LABELS.length + bi))));
  return out;
}

/** Minute cells (state * 6 + time bucket): minutes do not depend on the play phase. */
export function selectedMinuteCells(s: SliceSelection): number[] {
  const out: number[] = [];
  s.states.forEach((on, si) => on && s.buckets.forEach((b, bi) => b && out.push(si * BUCKET_LABELS.length + bi)));
  return out;
}

export const sumCells = (arr: number[] | undefined, cells: number[]) => (arr ? cells.reduce((a, c) => a + (arr[c] ?? 0), 0) : 0);

/** Which set-piece phase an events filter keeps: null = both. */
export const phaseOnly = (s: SliceSelection): 0 | 1 | null => (s.phases[0] && s.phases[1] ? null : s.phases[0] ? 0 : 1);

export const describeSelection = (s: SliceSelection): string[] => {
  const out: string[] = [];
  if (s.states.some((v) => !v)) out.push(STATE_LABELS.filter((_, i) => s.states[i]).join(" / "));
  if (s.buckets.some((v) => !v)) out.push(`Minutes ${BUCKET_LABELS.filter((_, i) => s.buckets[i]).join(", ")}`);
  if (s.phases.some((v) => !v)) out.push(PHASE_LABELS.filter((_, i) => s.phases[i]).join(" / "));
  return out;
};

type Props = {
  value: SliceSelection;
  onChange: (next: SliceSelection) => void;
  note?: string;
  /** hide a group (the pitch views only know the play phase) */
  show?: { state?: boolean; time?: boolean; phase?: boolean };
};

type Group = { key: keyof SliceSelection; title: string; labels: string[] };
const GROUPS: Group[] = [
  { key: "phases", title: "Play phase", labels: PHASE_LABELS },
  { key: "states", title: "Game state", labels: STATE_LABELS },
  { key: "buckets", title: "Match time", labels: BUCKET_LABELS },
];

/** One line of three small pop-over menus (play phase, game state, match time) plus a reset link. */
export function SliceFilters({ value, onChange, note, show }: Props) {
  const [open, setOpen] = useState<keyof SliceSelection | null>(null);
  const bar = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (bar.current && !bar.current.contains(e.target as Node)) setOpen(null);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const visible = GROUPS.filter((g) => (g.key === "phases" ? show?.phase : g.key === "states" ? show?.state : show?.time) ?? true);
  const toggle = (key: keyof SliceSelection, i: number) => {
    const next = value[key].map((v, j) => (j === i ? !v : v));
    onChange({ ...value, [key]: next.some(Boolean) ? next : value[key] }); // never leave a group empty
  };
  const summary = (g: Group) => {
    const on = g.labels.filter((_, i) => value[g.key][i]);
    return on.length === g.labels.length ? "All" : on.length <= 2 ? on.join(" + ") : `${on.length} of ${g.labels.length}`;
  };

  return (
    <div className="season-filter-bar" ref={bar}>
      {visible.map((g) => {
        const narrowed = !value[g.key].every(Boolean);
        return (
          <div key={g.key} className="season-filter-pop">
            <button type="button" className={`season-filter-btn${narrowed ? " is-narrowed" : ""}`} onClick={() => setOpen(open === g.key ? null : g.key)} aria-expanded={open === g.key} aria-haspopup="true">
              <span className="muted">{g.title}</span> <b>{summary(g)}</b>
              <svg viewBox="0 0 10 6" width="9" height="6" aria-hidden="true"><path d="M1 1l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.5" /></svg>
            </button>
            {open === g.key ? (
              <div className="season-filter-menu" role="menu">
                {g.labels.map((label, i) => (
                  <label key={label} className="season-filter-option">
                    <input type="checkbox" checked={value[g.key][i]} onChange={() => toggle(g.key, i)} />
                    <span>{label}</span>
                  </label>
                ))}
                <button type="button" className="season-filter-all" onClick={() => onChange({ ...value, [g.key]: value[g.key].map(() => true) })}>Select all</button>
              </div>
            ) : null}
          </div>
        );
      })}
      {isFiltered(value) ? (
        <button type="button" className="season-filter-reset" onClick={() => onChange(ALL_SELECTED)}>Reset</button>
      ) : null}
      {note ? <span className="muted season-filter-note">{note}</span> : null}
    </div>
  );
}
