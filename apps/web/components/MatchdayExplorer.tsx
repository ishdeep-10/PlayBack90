"use client";

import { ArrowUpRight, ChevronDown, ChevronUp, Maximize2, Minimize2, X } from "lucide-react";
import type { Route } from "next";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { Fixture } from "../lib/api";
import { findStadium, teamCode, teamLogo } from "../lib/stadiums";
import { CountryFixturesMap } from "./CountryFixturesMap";

type Props = {
  league: string;
  fixtures: Fixture[];
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

function analysisHref(fixture: Fixture) {
  return `/analysis/${fixture.match_id}?source=r2&filePath=${encodeURIComponent(fixture.file_path)}` as Route;
}

function TeamCrest({ league, team }: { league: string; team: string }) {
  const logo = teamLogo(team);
  if (logo) {
    return <img className="team-crest-img" src={logo} alt="" loading="lazy" />;
  }
  return <span className="team-crest" aria-hidden="true">{teamCode(league, team)}</span>;
}

export function MatchdayExplorer({ league, fixtures, roundLabel, roundStage }: Props) {
  const explorerRef = useRef<HTMLElement>(null);
  const rowRefs = useRef(new Map<string, HTMLDivElement>());
  const [hoverMatchId, setHoverMatchId] = useState<string | null>(null);
  const [selectedMatchId, setSelectedMatchId] = useState<string | null>(null);
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
  const selectedFixture = fixtures.find((fixture) => fixture.match_id === selectedMatchId) ?? null;
  const activeMatchId = hoverMatchId ?? selectedMatchId;

  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(document.fullscreenElement === explorerRef.current);
    };
    document.addEventListener("fullscreenchange", handleFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", handleFullscreenChange);
  }, []);

  useEffect(() => {
    if (!activeMatchId || !filteredFixtures.some((fixture) => fixture.match_id === activeMatchId)) return;
    rowRefs.current.get(activeMatchId)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [activeMatchId, filteredFixtures]);

  useEffect(() => {
    setHoverMatchId(null);
    setSelectedMatchId(null);
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
  const selectMatch = useCallback((matchId: string) => {
    setSelectedMatchId(matchId);
    setHoverMatchId(null);
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
        activeMatchId={activeMatchId}
        onActiveMatchChange={setHoverMatchId}
        onSelectMatch={selectMatch}
        workspace
        overlay={
          selectedFixture ? (
            <article className="matchday-map-preview" aria-live="polite">
              <button
                type="button"
                className="matchday-map-preview-close"
                aria-label="Close match preview"
                title="Close match preview"
                onClick={() => setSelectedMatchId(null)}
              >
                <X aria-hidden="true" size={17} />
              </button>
              <span className="fixture-list-kicker">
                {selectedStadium ? `${selectedStadium.stadium} · ${selectedStadium.city}` : roundLabel}
              </span>
              <time dateTime={selectedFixture.start_date}>{formatFixtureDate(selectedFixture.start_date)}</time>
              <div className="matchday-map-preview-matchup">
                <span>
                  <TeamCrest league={league} team={selectedFixture.home_team} />
                  <strong>{selectedFixture.home_team}</strong>
                </span>
                <b>{cleanScore(selectedFixture.score)}</b>
                <span>
                  <TeamCrest league={league} team={selectedFixture.away_team} />
                  <strong>{selectedFixture.away_team}</strong>
                </span>
              </div>
              <Link className="matchday-map-preview-link" href={analysisHref(selectedFixture)}>
                Open match analysis
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
            const isActive = activeMatchId === fixture.match_id;
            return (
              <div
                key={fixture.match_id}
                ref={(node) => {
                  if (node) rowRefs.current.set(fixture.match_id, node);
                  else rowRefs.current.delete(fixture.match_id);
                }}
                className={isActive ? "explorer-fixture-row is-active" : "explorer-fixture-row"}
                onMouseEnter={() => setHoverMatchId(fixture.match_id)}
                onMouseLeave={() => setHoverMatchId(null)}
              >
                <button
                  type="button"
                  className="explorer-fixture-select"
                  aria-pressed={selectedMatchId === fixture.match_id}
                  aria-label={`Preview ${fixture.home_team} versus ${fixture.away_team}, ${cleanScore(fixture.score)}`}
                  onClick={() => selectMatch(fixture.match_id)}
                  onFocus={() => setHoverMatchId(fixture.match_id)}
                  onBlur={() => setHoverMatchId(null)}
                >
                  <time className="explorer-fixture-date" dateTime={fixture.start_date}>
                    {formatFixtureDate(fixture.start_date)}
                  </time>
                  <span className="explorer-fixture-matchup">
                    <span className="explorer-fixture-team">
                      <TeamCrest league={league} team={fixture.home_team} />
                      <span>{fixture.home_team}</span>
                    </span>
                    <span className="explorer-fixture-score">{cleanScore(fixture.score)}</span>
                    <span className="explorer-fixture-team away">
                      <span>{fixture.away_team}</span>
                      <TeamCrest league={league} team={fixture.away_team} />
                    </span>
                  </span>
                </button>
                <Link
                  className="explorer-fixture-action"
                  href={analysisHref(fixture)}
                  aria-label={`Open analysis for ${fixture.home_team} versus ${fixture.away_team}`}
                  title="Open match analysis"
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
