"use client";

import { useEffect, useState } from "react";

import { getTeamForm } from "../lib/api";

type FormMatch = { date: string; opponent: string; result: string; goals_for: number; goals_against: number };

type Props = {
  league?: string | null;
  season?: string | null;
  team: string;
};

export function TeamFormStrip({ league, season, team }: Props) {
  const [matches, setMatches] = useState<FormMatch[]>([]);

  useEffect(() => {
    if (!league || !season || !team) return;
    let cancelled = false;
    getTeamForm(league, season, team, 5)
      .then((data) => {
        if (!cancelled) setMatches((data.matches as FormMatch[]) ?? []);
      })
      .catch(() => {
        if (!cancelled) setMatches([]);
      });
    return () => {
      cancelled = true;
    };
  }, [league, season, team]);

  if (!matches.length) return null;

  return (
    <span className="form-strip" aria-label={`${team} recent form`}>
      {matches.map((match, index) => (
        <i
          key={`${match.date}-${index}`}
          className={`form-strip-chip form-${match.result.toLowerCase()}`}
          title={`${match.date} vs ${match.opponent}: ${match.goals_for}-${match.goals_against}`}
        >
          {match.result}
        </i>
      ))}
    </span>
  );
}
