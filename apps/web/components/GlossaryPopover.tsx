"use client";

import { useEffect, useRef, useState } from "react";

import { GLOSSARY } from "../lib/glossary";

export function GlossaryPopover({ viewId }: { viewId: string }) {
  const [open, setOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const terms = GLOSSARY[viewId] ?? [];

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!panelRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onEscape);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onEscape);
    };
  }, [open]);

  if (!terms.length) return null;

  return (
    <div className="glossary-anchor" ref={panelRef}>
      <button
        type="button"
        className="glossary-button"
        aria-expanded={open}
        aria-label="Glossary of terms for this tab"
        title="Glossary"
        onClick={() => setOpen((value) => !value)}
      >
        ?
      </button>
      {open ? (
        <div className="glossary-panel" role="dialog" aria-label="Glossary">
          <span className="glossary-panel-kicker">Glossary</span>
          <dl>
            {terms.map(({ term, definition }) => (
              <div key={term} className="glossary-entry">
                <dt>{term}</dt>
                <dd>{definition}</dd>
              </div>
            ))}
          </dl>
        </div>
      ) : null}
    </div>
  );
}
