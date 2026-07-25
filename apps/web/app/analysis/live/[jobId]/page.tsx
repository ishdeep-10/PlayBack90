"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";

import { getLiveScrapeJob } from "../../../../lib/api";


type Props = {
  jobId: string;
};


function LiveAnalysisClient({ jobId }: Props) {
  const [status, setStatus] = useState<string>("queued");
  const [message, setMessage] = useState<string>("Loading job...");
  const [error, setError] = useState<string | null>(null);
  const [matchId, setMatchId] = useState<string | null>(null);

  useEffect(() => {
    if (!jobId) return;

    let cancelled = false;

    async function poll() {
      try {
        const job = await getLiveScrapeJob(jobId);
        if (cancelled) return;
        setStatus(job.status);
        setMessage(job.message ?? "Job updated.");
        setError(job.error ?? null);
        setMatchId(job.context?.match_id ?? null);

        if (job.status === "queued" || job.status === "running") {
          window.setTimeout(poll, 3000);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load job.");
        }
      }
    }

    poll();
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  return (
    <div className="placeholder card">
      <div className="stack" style={{ maxWidth: 620 }}>
        <span className="pill">Live analysis job</span>
        <h1 style={{ margin: 0 }}>Background scrape status: {status}</h1>
        <p className="muted">{error ?? message}</p>
        {status === "completed" && matchId ? (
          <>
            <p className="muted">
              The worker has finished scraping and this job can now open inside the hosted analysis workspace.
            </p>
            <div className="row" style={{ justifyContent: "center" }}>
              <Link className="button" href={`/analysis/${matchId}?source=live&jobId=${encodeURIComponent(jobId)}`}>
                Open Live Analysis
              </Link>
            </div>
          </>
        ) : null}
        <div className="row" style={{ justifyContent: "center" }}>
          <Link href="/" className="ghost-button">
            Back Home
          </Link>
        </div>
      </div>
    </div>
  );
}


export default function LiveAnalysisPage({ params }: { params: Promise<{ jobId: string }> }) {
  const { jobId } = use(params);
  return <LiveAnalysisClient jobId={jobId} />;
}
