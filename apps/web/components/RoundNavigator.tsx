"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import type { Route } from "next";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useTransition } from "react";

import type { FixtureRound } from "../lib/api";

type Props = {
  rounds: FixtureRound[];
  selectedRoundId: string;
};

const DATE_FORMATTER = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  timeZone: "UTC",
});

function formatDate(value: string) {
  return DATE_FORMATTER.format(new Date(`${value}T00:00:00Z`));
}

function formatDateRange(round: FixtureRound) {
  if (round.start_date === round.end_date) return formatDate(round.start_date);
  return `${formatDate(round.start_date)} - ${formatDate(round.end_date)}`;
}

function roundLabel(round: FixtureRound) {
  return round.metadata_source === "manifest" ? round.label : formatDateRange(round);
}

export function RoundNavigator({ rounds, selectedRoundId }: Props) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();
  const selectedIndex = Math.max(0, rounds.findIndex((round) => round.id === selectedRoundId));
  const selected = rounds[selectedIndex];
  const previousRound = rounds[selectedIndex + 1];
  const nextRound = rounds[selectedIndex - 1];

  const navigateTo = (roundId: string) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("round", roundId);
    startTransition(() => router.push(`${pathname}?${params.toString()}` as Route));
  };

  const navigationButton = (
    target: FixtureRound | undefined,
    direction: "previous" | "next",
  ) => {
    const label = direction === "previous" ? "Previous round" : "Next round";
    const Icon = direction === "previous" ? ChevronLeft : ChevronRight;
    if (!target) {
      return (
        <button className="round-nav-button" type="button" aria-label={label} title={label} disabled>
          <Icon aria-hidden="true" size={20} strokeWidth={2} />
        </button>
      );
    }
    return (
      <button
        className="round-nav-button"
        type="button"
        aria-label={`${label}: ${roundLabel(target)}`}
        title={`${label}: ${roundLabel(target)}`}
        onClick={() => navigateTo(target.id)}
        disabled={isPending}
      >
        <Icon aria-hidden="true" size={20} strokeWidth={2} />
      </button>
    );
  };

  return (
    <nav className={isPending ? "round-navigator is-pending" : "round-navigator"} aria-label="Fixture round">
      {navigationButton(previousRound, "previous")}
      <div className="round-nav-selection">
        <span className="round-nav-stage">{selected.stage ?? "Match round"}</span>
        <label className="round-nav-select-wrap">
          <span className="sr-only">Select round</span>
          <select
            className="round-nav-select"
            value={selected.id}
            onChange={(event) => navigateTo(event.target.value)}
            disabled={isPending}
          >
            {rounds.map((round) => (
              <option key={round.id} value={round.id}>
                {roundLabel(round)} · {round.match_count} {round.match_count === 1 ? "match" : "matches"}
              </option>
            ))}
          </select>
        </label>
      </div>
      {navigationButton(nextRound, "next")}
    </nav>
  );
}
