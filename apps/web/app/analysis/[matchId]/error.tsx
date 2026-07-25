"use client";

export default function AnalysisError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="placeholder card" style={{ marginTop: 24 }}>
      <div className="stack">
        <h1>Something went wrong loading this analysis.</h1>
        <p className="muted">An unexpected error occurred while rendering the match view.</p>
        <div className="row">
          <button className="button" onClick={() => reset()}>
            Try again
          </button>
          <a className="ghost-button" href="/">
            Back to Coverage Map
          </a>
        </div>
      </div>
    </div>
  );
}
