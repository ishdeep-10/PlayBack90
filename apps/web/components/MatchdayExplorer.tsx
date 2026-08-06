"use client";

import { ArrowUpRight, ChevronDown, ChevronUp, Maximize2, Minimize2, X } from "lucide-react";
import type { Route } from "next";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { FixtureHubFixture } from "../lib/api";
import { findStadium, teamCode, teamLogo } from "../lib/stadiums";
import { CountryFixturesMap } from "./CountryFixturesMap";

type Props = {
  league: string;
  fixtures: FixtureHubFixture[];
  roundLabel: string;
  roundStage: string;
};

const DATE_FORMATTER = new Intl.DateTimeFormat("en-GB", {
  weekday: "short",
  day: "numeric",
  month: "short",
  timeZone: "UTC",
});

function formatFixtureDate(value: string) {
  const date = value.split("T")[0];
  return DATE_FORMATTER.format(new Date(`${date}T00:00:00Z`));
}

function cleanScore(score: string) {
  return String(score || "").replace(/--/g, "-").replace(/_/g, "-");
}

function fixtureHref(fixture: FixtureHubFixture) {
  return (fixture.post_match_href || fixture.opposition_href || "#") as Route;
}

function fixtureActionLabel(fixture: FixtureHubFixture) {
  if (fixture.state === "completed") return "Open match analysis";
  if (fixture.state === "upcoming") return "Analyse opposition";
  if (fixture.state === "postponed") return "Postponed";
  if (fixture.state === "cancelled") return "Cancelled";
  if (fixture.state === "live") return "Live";
  return "View fixture";
}

function fixtureScoreLabel(fixture: FixtureHubFixture) {
  return fixture.state === "completed" ? cleanScore(fixture.score) : "vs";
}

function TeamCrest({ league, team, crest }: { league: string; team: string; crest?: string | null }) {
  const logo = crest ?? teamLogo(team);
  if (logo) {
    return <img className="team-crest-img" src={logo} alt="" loading="lazy" />;
  }
  return <span className="team-crest" aria-hidden="true">{teamCode(league, team)}</span>;
}

export function MatchdayExplorer({ league, fixtures, roundLabel, roundStage }: Props) {
  const explorerRef = useRef<HTMLElement>(null);
  const rowRefs = useRef(new Map<string, HTMLDivElement>());
  const [hoverFixtureId, setHoverFixtureId] = useState<string | null>(null);
  const [selectedFixtureId, setSelectedFixtureId] = useState<string | null>(null);
  const [teamFilter, setTeamFilter] = useState("");
  const [isSheetExpanded, setIsSheetExpanded] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const teams = useMemo(
    () => Array.from(new Set(fixtures.flatMap((fixture) => [fixture.home_team, fixture.away_team]))).sort(),
    [fixtures],
  );
  const filteredFixtures = useMemo(
    () =>
      teamFilter
        ? fixtures.filter((fixture) => fixture.home_team === teamFilter || fixture.away_team === teamFilter)
        : fixtures,
    [fixtures, teamFilter],
  );
  const selectedFixture = fixtures.find((fixture) => fixture.fixture_id === selectedFixtureId) ?? null;
  const activeFixtureId = hoverFixtureId ?? selectedFixtureId;

  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(document.fullscreenElement === explorerRef.current);
    };
    document.addEventListener("fullscreenchange", handleFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", handleFullscreenChange);
  }, []);

  useEffect(() => {
    if (!activeFixtureId || !filteredFixtures.some((fixture) => fixture.fixture_id === activeFixtureId)) return;
    rowRefs.current.get(activeFixtureId)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [activeFixtureId, filteredFixtures]);

  useEffect(() => {
    setHoverFixtureId(null);
    setSelectedFixtureId(null);
  }, [teamFilter]);

  const toggleFullscreen = async () => {
    try {
      if (isFullscreen) {
        if (document.fullscreenElement === explorerRef.current) {
          await document.exitFullscreen();
        } else {
          setIsFullscreen(false);
        }
      } else {
        await explorerRef.current?.requestFullscreen();
      }
    } catch {
      setIsFullscreen((current) => !current);
    }
  };

  const fullscreenLabel = isFullscreen ? "Exit fullscreen" : "Open fullscreen";
  const FullscreenIcon = isFullscreen ? Minimize2 : Maximize2;
  const selectFixture = useCallback((fixtureId: string) => {
    setSelectedFixtureId(fixtureId);
    setHoverFixtureId(null);
    setIsSheetExpanded(false);
  }, []);
  const selectedStadium = selectedFixture ? findStadium(league, selectedFixture.home_team) : null;

  return (
    <section
      ref={explorerRef}
      className={isFullscreen ? "matchday-explorer is-fullscreen" : "matchday-explorer"}
      aria-label={`${roundLabel} matchday explorer`}
    >
      <CountryFixturesMap
        league={league}
        fixtures={filteredFixtures}
        activeFixtureId={activeFixtureId}
        onActiveFixtureChange={setHoverFixtureId}
        onSelectFixture={selectFixture}
        workspace
        overlay={
          selectedFixture ? (
            <article className="matchday-map-preview" aria-live="polite">
              <button
                type="button"
                className="matchday-map-preview-close"
                aria-label="Close match preview"
                title="Close match preview"
                onClick={() => setSelectedFixtureId(null)}
              >
                <X aria-hidden="true" size={17} />
              </button>
              <span className="fixture-list-kicker">
                {selectedStadium ? `${selectedStadium.stadium} · ${selectedStadium.city}` : roundLabel}
              </span>
              <time dateTime={selectedFixture.start_date}>{formatFixtureDate(selectedFixture.start_date)}</time>
              <div className="matchday-map-preview-matchup">
                <span>
                  <TeamCrest league={league} team={selectedFixture.home_team} crest={selectedFixture.home_crest} />
                  <strong>{selectedFixture.home_team}</strong>
                </span>
                <b>{fixtureScoreLabel(selectedFixture)}</b>
                <span>
                  <TeamCrest league={league} team={selectedFixture.away_team} crest={selectedFixture.away_crest} />
                  <strong>{selectedFixture.away_team}</strong>
                </span>
              </div>
              <Link className="matchday-map-preview-link" href={fixtureHref(selectedFixture)}>
                {fixtureActionLabel(selectedFixture)}
                <ArrowUpRight aria-hidden="true" size={16} />
              </Link>
            </article>
          ) : null
        }
        actions={(
          <button
            type="button"
            className="stadium-fullscreen-button"
            aria-label={fullscreenLabel}
            title={fullscreenLabel}
            onClick={toggleFullscreen}
          >
            <FullscreenIcon aria-hidden="true" size={18} strokeWidth={2} />
          </button>
        )}
      />

      <aside
        className={isSheetExpanded ? "matchday-fixture-rail is-expanded" : "matchday-fixture-rail"}
        aria-labelledby="round-matches-title"
      >
        <button
          type="button"
          className="matchday-sheet-handle"
          aria-label={isSheetExpanded ? "Collapse fixtures" : "Expand fixtures"}
          aria-expanded={isSheetExpanded}
          onClick={() => setIsSheetExpanded((current) => !current)}
        >
          <span />
          {isSheetExpanded ? <ChevronDown aria-hidden="true" size={18} /> : <ChevronUp aria-hidden="true" size={18} />}
        </button>
        <header className="matchday-fixture-rail-head">
          <div>
            <span className="fixture-list-kicker">{roundStage}</span>
            <h2 id="round-matches-title">{roundLabel}</h2>
          </div>
          <div className="matchday-fixture-rail-tools">
            <label className="sr-only" htmlFor="matchday-team-filter">Filter matches by team</label>
            <select
              id="matchday-team-filter"
              className="matchday-team-filter"
              value={teamFilter}
              onChange={(event) => setTeamFilter(event.target.value)}
            >
              <option value="">All teams</option>
              {teams.map((team) => <option key={team} value={team}>{team}</option>)}
            </select>
            <span className="fixture-list-count">{filteredFixtures.length}</span>
          </div>
        </header>

        <div className="matchday-fixture-scroll">
          {filteredFixtures.map((fixture) => {
            const isActive = activeFixtureId === fixture.fixture_id;
            return (
              <div
                key={fixture.fixture_id}
                ref={(node) => {
                  if (node) rowRefs.current.set(fixture.fixture_id, node);
                  else rowRefs.current.delete(fixture.fixture_id);
                }}
                className={isActive ? `explorer-fixture-row is-active is-${fixture.state}` : `explorer-fixture-row is-${fixture.state}`}
                onMouseEnter={() => setHoverFixtureId(fixture.fixture_id)}
                onMouseLeave={() => setHoverFixtureId(null)}
              >
                <button
                  type="button"
                  className="explorer-fixture-select"
                  aria-pressed={selectedFixtureId === fixture.fixture_id}
                  aria-label={`Preview ${fixture.home_team} versus ${fixture.away_team}`}
                  onClick={() => selectFixture(fixture.fixture_id)}
                  onFocus={() => setHoverFixtureId(fixture.fixture_id)}
                  onBlur={() => setHoverFixtureId(null)}
                >
                  <time className="explorer-fixture-date" dateTime={fixture.start_date}>
                    {formatFixtureDate(fixture.start_date)}
                  </time>
                  <span className={`fixture-state-badge is-${fixture.state}`}>{fixture.state}</span>
                  <span className="explorer-fixture-matchup">
                    <span className="explorer-fixture-team">
                      <TeamCrest league={league} team={fixture.home_team} crest={fixture.home_crest} />
                      <span>{fixture.home_team}</span>
                    </span>
                    <span className="explorer-fixture-score">{fixtureScoreLabel(fixture)}</span>
                    <span className="explorer-fixture-team away">
                      <span>{fixture.away_team}</span>
                      <TeamCrest league={league} team={fixture.away_team} crest={fixture.away_crest} />
                    </span>
                  </span>
                </button>
                <Link
                  className="explorer-fixture-action"
                  href={fixtureHref(fixture)}
                  aria-label={`${fixtureActionLabel(fixture)} for ${fixture.home_team} versus ${fixture.away_team}`}
                  title={fixtureActionLabel(fixture)}
                >
                  <ArrowUpRight aria-hidden="true" size={17} strokeWidth={2} />
                </Link>
              </div>
            );
          })}
        </div>
      </aside>
    </section>
  );
}
