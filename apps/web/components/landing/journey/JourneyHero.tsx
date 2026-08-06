"use client";

import Link from "next/link";
import { forwardRef } from "react";

export const JourneyHero = forwardRef<HTMLDivElement>(function JourneyHero(_, ref) {
  return (
    <div className="pbj-hero" ref={ref}>
      <span className="pbj-hero-kicker">Football, translated</span>
      <h1>PlayBack90</h1>
      <p>
        Follow the match from the stadium to the evidence. Every visual keeps
        actions, players, and tactical context connected.
      </p>
      <div className="pbj-hero-actions">
        <a
          className="button"
          href="#league-coverage"
          onClick={(event) => {
            event.preventDefault();
            document.getElementById("league-coverage")?.scrollIntoView({ behavior: "smooth" });
          }}
        >
          Explore Match Analysis
        </a>
        <Link className="ghost-button" href="/live-scrape">
          Import Match
        </Link>
      </div>
      <span className="pbj-hero-scroll" aria-hidden="true">
        Scroll to enter the stadium
      </span>
    </div>
  );
});
