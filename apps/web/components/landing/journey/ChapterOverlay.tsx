"use client";

import Link from "next/link";
import type { JourneyChapter } from "./chapters";

export function ChapterOverlay({
  chapter,
  index,
  active,
}: {
  chapter: JourneyChapter;
  index: number;
  active: boolean;
}) {
  return (
    <article
      className={`pbj-overlay${active ? " is-active" : ""}${index % 2 ? " is-right" : ""}`}
      data-index={index}
      aria-hidden={!active}
    >
      <div className="pbj-overlay-card">
        <div className="pbj-overlay-kicker">
          <span>{String(index + 1).padStart(2, "0")}</span>
          {chapter.kicker}
        </div>
        <h2>{chapter.headline}</h2>
        <p>{chapter.support}</p>
        <div className="pbj-overlay-chips">
          {chapter.sequence.metrics.map((metric) => (
            <span className="pbj-chip" key={metric.label}>
              <b>{metric.value}</b>
              {metric.label}
            </span>
          ))}
        </div>
        <div className="pbj-overlay-match">
          <span>
            {chapter.league} · {chapter.date}
          </span>
          <strong>{chapter.match}</strong>
          <b>{chapter.score}</b>
        </div>
        <div className="pbj-overlay-actions">
          <Link className="pbj-overlay-link" href={chapter.href} tabIndex={active ? 0 : -1}>
            Open this match
            <span aria-hidden="true">↗</span>
          </Link>
        </div>
      </div>
    </article>
  );
}
