"use client";

import { useMemo, useState } from "react";

import { DownloadPngButton, type SideTable } from "./DownloadPngButton";

type Props = {
  filename: string;
  title: string;
  filters: string[];
  summaryRows: Array<{ label: string; value: string }>;
};

export function OppositionReportActions({ filename, title, filters, summaryRows }: Props) {
  const [copied, setCopied] = useState(false);
  const sideTable = useMemo<SideTable>(
    () => ({
      title: "Opposition dossier",
      rows: summaryRows,
      large: true,
    }),
    [summaryRows],
  );

  async function copyLink() {
    if (typeof window === "undefined") return;
    await window.navigator.clipboard.writeText(window.location.href);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }

  return (
    <div className="opposition-actions">
      <button type="button" className="ghost-button opposition-action-button" onClick={copyLink}>
        {copied ? "Copied" : "Copy link"}
      </button>
      <DownloadPngButton
        filename={filename}
        title={title}
        filters={filters}
        sideTable={() => sideTable}
        scopeSelector=".opposition-export-scope"
        canvasHeight={760}
      />
    </div>
  );
}
