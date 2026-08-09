"use client";

import { ChevronDown, SlidersHorizontal } from "lucide-react";
import { useId, useState, type ReactNode } from "react";

export function MobileAnalysisControls({
  children,
  label = "Filters",
  summary = "Team, state and time",
}: {
  children: ReactNode;
  label?: string;
  summary?: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const contentId = useId();

  return (
    <div className={`mobile-analysis-controls${expanded ? " is-open" : ""}`}>
      <button
        type="button"
        className="mobile-analysis-controls-toggle"
        aria-expanded={expanded}
        aria-controls={contentId}
        onClick={() => setExpanded((current) => !current)}
      >
        <SlidersHorizontal aria-hidden="true" size={17} />
        <span>
          <strong>{label}</strong>
          <small>{summary}</small>
        </span>
        <ChevronDown aria-hidden="true" className="mobile-analysis-controls-chevron" size={18} />
      </button>
      <div id={contentId} className="mobile-analysis-controls-body">
        {children}
      </div>
    </div>
  );
}
