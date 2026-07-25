"use client";

import { useEffect, useRef, useState } from "react";

const PUBLIC_API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";

type Props = {
  matchId: string;
  source: string;
  filePath?: string;
  jobId?: string;
  view: string;
  team?: string;
};

export function AiInsightCard({ matchId, source, filePath, jobId, view, team }: Props) {
  const [text, setText] = useState("");
  const [status, setStatus] = useState<"loading" | "streaming" | "done" | "error">("loading");
  const [aiAvailable, setAiAvailable] = useState(false);
  const [mode, setMode] = useState<"baseline" | "ai">("baseline");
  const requestSeq = useRef(0);

  const generate = async (requestMode: "baseline" | "ai") => {
    const seq = ++requestSeq.current;
    setStatus(requestMode === "ai" ? "streaming" : "loading");
    setText("");
    try {
      const filters: Record<string, string | undefined> = { team };
      if (source !== "r2") filters.job_id = jobId;
      const response = await fetch(
        `${PUBLIC_API_BASE}/analysis/ai/insights?view=${encodeURIComponent(view)}&mode=${requestMode}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(
            source !== "r2"
              ? { match_id: matchId, source, filters }
              : { match_id: matchId, source: "r2", file_path: filePath, filters }
          ),
        }
      );
      if (seq !== requestSeq.current) return;
      if (!response.ok || !response.body) {
        setStatus("error");
        return;
      }
      setAiAvailable(response.headers.get("X-AI-Available") === "1");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let collected = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (seq !== requestSeq.current) return;
        if (done) break;
        collected += decoder.decode(value, { stream: true });
        setText(collected);
      }
      setMode(requestMode);
      setStatus("done");
    } catch {
      if (seq === requestSeq.current) setStatus("error");
    }
  };

  useEffect(() => {
    generate("baseline");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, team, filePath, jobId]);

  const bullets = text
    .split("\n")
    .map((line) => line.replace(/^[-•]\s*/, "").trim())
    .filter(Boolean);

  return (
    <section className="card stack ai-insight-card">
      <div className="chart-card-head">
        <div>
          <span className="eyebrow ai-eyebrow">Insights</span>
          <h2 style={{ margin: "6px 0 0", fontSize: "1.05rem" }}>
            Key takeaways{team ? ` — ${team}` : ""}
          </h2>
        </div>
        {aiAvailable ? (
          <button
            type="button"
            className="button ai-generate-button"
            onClick={() => generate(mode === "ai" ? "baseline" : "ai")}
            disabled={status === "streaming" || status === "loading"}
          >
            {status === "streaming" ? "Analysing…" : mode === "ai" ? "Back to baseline" : "✦ AI deep dive"}
          </button>
        ) : null}
      </div>
      {status === "error" ? (
        <p className="muted-copy" style={{ margin: 0 }}>
          Insights couldn&apos;t be generated for this view.{" "}
          <button type="button" className="button" onClick={() => generate("baseline")}>
            Retry
          </button>
        </p>
      ) : null}
      {bullets.length ? (
        <ul className="ai-insight-list">
          {bullets.map((bullet, index) => (
            <li key={index}>{bullet}</li>
          ))}
          {status === "streaming" ? <li className="ai-cursor" aria-hidden="true" /> : null}
        </ul>
      ) : status === "loading" || status === "streaming" ? (
        <p className="muted-copy ai-shimmer" style={{ margin: 0 }}>Reading the match data…</p>
      ) : null}
    </section>
  );
}
