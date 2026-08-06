"use client";

import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { ComposableMap, Geographies, Geography, Marker, ZoomableGroup } from "react-simple-maps";

import type { FixtureHubFixture } from "../lib/api";
import { LEAGUE_MAPS, findStadium, teamCode, teamLogo } from "../lib/stadiums";

const GEO_URL = "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-50m.json";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

type Props = {
  league: string;
  fixtures: FixtureHubFixture[];
  activeFixtureId?: string | null;
  onActiveFixtureChange?: (fixtureId: string | null) => void;
  onSelectFixture?: (fixtureId: string) => void;
  actions?: ReactNode;
  overlay?: ReactNode;
  workspace?: boolean;
};

type PlacedFixture = {
  fixture: FixtureHubFixture;
  coordinates: [number, number];
  stadium: string;
  city: string;
  homeCode: string;
  awayCode: string;
  homeLogo: string | null;
  awayLogo: string | null;
};

function fixtureHref(fixture: FixtureHubFixture) {
  return fixture.post_match_href || fixture.opposition_href || "#";
}

function fixtureActionLabel(fixture: FixtureHubFixture) {
  if (fixture.state === "completed") return "Open match analysis";
  if (fixture.state === "upcoming") return "Analyse opposition";
  return "View fixture";
}

function cleanScore(score: string) {
  return String(score || "").replace(/--/g, "-").replace(/_/g, "-");
}

function formatDay(iso: string) {
  const [datePart] = iso.split("T");
  const [year, month, day] = datePart.split("-").map(Number);
  if (!year || !month || !day) return iso;
  return `${day} ${MONTHS[month - 1]} ${year}`;
}

function dateRangeLabel(fixtures: FixtureHubFixture[]) {
  const dates = fixtures.map((f) => (f.start_date || f.start_date_label || "").split("T")[0]).filter(Boolean).sort();
  if (!dates.length) return "";
  const first = dates[0];
  const last = dates[dates.length - 1];
  if (first === last) return formatDay(first);
  return `${formatDay(first)} – ${formatDay(last)}`;
}

function StadiumGlyph() {
  return (
    <g className="stadium-glyph">
      <ellipse className="stadium-shadow" cx="0" cy="9" rx="21" ry="6.5" />
      <path className="stadium-wall" d="M -19 0 A 19 7 0 0 0 19 0 L 19 6.5 A 19 7 0 0 1 -19 6.5 Z" />
      <ellipse className="stadium-rim" cx="0" cy="0" rx="19" ry="7" />
      <ellipse className="stadium-bowl" cx="0" cy="0" rx="16" ry="5.6" />
      <ellipse className="stadium-pitch" cx="0" cy="0" rx="12" ry="4" />
      <ellipse className="stadium-centre" cx="0" cy="0" rx="3" ry="1.2" />
      <line className="stadium-halfway" x1="0" y1="-4" x2="0" y2="4" />
    </g>
  );
}

function Badge({ logo, code, x, y, r, away }: { logo: string | null; code: string; x: number; y: number; r: number; away?: boolean }) {
  if (logo) {
    return <image className="stadium-crest" href={logo} x={x - r} y={y - r} width={r * 2} height={r * 2} />;
  }
  return (
    <g>
      <circle className={away ? "stadium-badge away" : "stadium-badge home"} cx={x} cy={y} r={r} />
      <text className={away ? "stadium-badge-text small" : "stadium-badge-text"} x={x} y={y + (away ? 2.5 : 3)}>
        {code}
      </text>
    </g>
  );
}

export function CountryFixturesMap({
  league,
  fixtures,
  activeFixtureId,
  onActiveFixtureChange,
  onSelectFixture,
  actions,
  overlay,
  workspace = false,
}: Props) {
  const config = LEAGUE_MAPS[league];
  const panelRef = useRef<HTMLDivElement>(null);
  const [mounted, setMounted] = useState(false);
  const [hovered, setHovered] = useState<PlacedFixture | null>(null);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [position, setPosition] = useState<{ coordinates: [number, number]; zoom: number }>({
    coordinates: config?.center ?? [0, 0],
    zoom: 1,
  });

  const placed = useMemo(() => {
    if (!config) return [] as PlacedFixture[];
    const seen = new Map<string, number>();
    return fixtures
      .map((fixture) => {
        const stadium = findStadium(league, fixture.home_team);
        if (!stadium) return null;
        const key = stadium.coordinates.join(",");
        const bump = seen.get(key) ?? 0;
        seen.set(key, bump + 1);
        // Nudge repeat fixtures at the same ground so both stay clickable.
        const coordinates: [number, number] = [stadium.coordinates[0] + bump * 0.22, stadium.coordinates[1] - bump * 0.1];
        return {
          fixture,
          coordinates,
          stadium: stadium.stadium,
          city: stadium.city,
          homeCode: teamCode(league, fixture.home_team),
          awayCode: teamCode(league, fixture.away_team),
          homeLogo: fixture.home_crest ?? teamLogo(fixture.home_team),
          awayLogo: fixture.away_crest ?? teamLogo(fixture.away_team),
        };
      })
      .filter((item): item is PlacedFixture => item !== null);
  }, [config, fixtures, league]);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted || !config || !placed.length) return null;

  const countrySet = new Set(config.countries);
  const markerScale = 1 / position.zoom;
  const clusters = Array.from(
    placed.reduce((groups, item) => {
      const key = item.city.trim().toLowerCase();
      const group = groups.get(key) ?? [];
      group.push(item);
      groups.set(key, group);
      return groups;
    }, new Map<string, PlacedFixture[]>()),
  ).map(([city, items]) => ({
    city,
    items,
    coordinates: [
      items.reduce((sum, item) => sum + item.coordinates[0], 0) / items.length,
      items.reduce((sum, item) => sum + item.coordinates[1], 0) / items.length,
    ] as [number, number],
  }));
  const showClusters = position.zoom < 3;

  const handleHover = (item: PlacedFixture, event: React.MouseEvent) => {
    const bounds = panelRef.current?.getBoundingClientRect();
    if (bounds) {
      setTooltipPos({ x: event.clientX - bounds.left, y: event.clientY - bounds.top });
    }
    setHovered(item);
    onActiveFixtureChange?.(item.fixture.fixture_id);
  };

  const zoomTo = (zoom: number) => {
    setPosition((current) => ({ ...current, zoom: Math.min(12, Math.max(1, zoom)) }));
  };

  return (
    <div className={workspace ? "stadium-map-panel is-workspace" : "stadium-map-panel"} ref={panelRef}>
      <div className="stadium-map-head">
        <div>
          <span className="stadium-map-kicker">Matchday Map</span>
          <h2>Matches on {dateRangeLabel(fixtures)}</h2>
        </div>
        <div className="stadium-map-head-tools">
          <p className="stadium-map-hint">Scroll or use the controls to zoom, drag to pan, click a stadium to preview the match.</p>
          {actions}
        </div>
      </div>

      <div className="stadium-map-stage">
        <ComposableMap
          className="stadium-map-svg"
          projection="geoMercator"
          projectionConfig={{ scale: config.scale }}
          role="img"
          aria-label={`Map of fixtures by home stadium`}
        >
          <ZoomableGroup
            center={position.coordinates}
            zoom={position.zoom}
            minZoom={1}
            maxZoom={12}
            onMoveEnd={({ coordinates, zoom }: { coordinates: [number, number]; zoom: number }) =>
              setPosition({ coordinates, zoom })
            }
          >
            <Geographies geography={GEO_URL}>
              {({ geographies }: { geographies: Array<{ rsmKey: string; properties: { name?: string } }> }) =>
                geographies.map((geo) => {
                  const name = geo.properties.name ?? "";
                  const isFocus = countrySet.has(name);
                  return (
                    <Geography
                      key={geo.rsmKey}
                      geography={geo}
                      className={isFocus ? "stadium-country is-focus" : "stadium-country"}
                      tabIndex={-1}
                    />
                  );
                })
              }
            </Geographies>

            <Geographies geography={config.statesGeo}>
              {({ geographies }: { geographies: Array<{ rsmKey: string; properties: Record<string, unknown> }> }) =>
                geographies.map((geo) => (
                  <Geography key={geo.rsmKey} geography={geo} className="stadium-state" tabIndex={-1} />
                ))
              }
            </Geographies>

            {showClusters
              ? clusters.map((cluster, index) =>
                  cluster.items.length > 1 ? (
                    <Marker key={cluster.city} coordinates={cluster.coordinates}>
                      <g
                        className="stadium-cluster-scale"
                        style={{ transform: `scale(${markerScale})` }}
                        role="button"
                        tabIndex={0}
                        aria-label={`Zoom to ${cluster.items[0].city}, ${cluster.items.length} matches`}
                        onClick={() => setPosition({ coordinates: cluster.coordinates, zoom: 8 })}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            setPosition({ coordinates: cluster.coordinates, zoom: 8 });
                          }
                        }}
                      >
                        <g
                          className={
                            cluster.items.some((item) => item.fixture.fixture_id === activeFixtureId)
                              ? "stadium-cluster is-active"
                              : "stadium-cluster"
                          }
                          style={{ animationDelay: `${index * 90}ms` }}
                        >
                          <circle className="stadium-cluster-ring" r="25" />
                          <circle className="stadium-cluster-core" r="19" />
                          <text className="stadium-cluster-count" y="5">
                            {cluster.items.length}
                          </text>
                          <text className="stadium-cluster-city" y="38">
                            {cluster.items[0].city}
                          </text>
                        </g>
                      </g>
                    </Marker>
                  ) : (
                    <FixtureMarker
                      key={cluster.items[0].fixture.fixture_id}
                      item={cluster.items[0]}
                      index={index}
                      markerScale={markerScale}
                      activeFixtureId={activeFixtureId}
                      hoveredFixtureId={hovered?.fixture.fixture_id}
                      onHover={handleHover}
                      onLeave={() => {
                        setHovered(null);
                        onActiveFixtureChange?.(null);
                      }}
                      onActiveFixtureChange={onActiveFixtureChange}
                      onSelectFixture={onSelectFixture}
                    />
                  ),
                )
              : placed.map((item, index) => (
                  <FixtureMarker
                    key={item.fixture.fixture_id}
                    item={item}
                    index={index}
                    markerScale={markerScale}
                    activeFixtureId={activeFixtureId}
                    hoveredFixtureId={hovered?.fixture.fixture_id}
                    onHover={handleHover}
                    onLeave={() => {
                      setHovered(null);
                      onActiveFixtureChange?.(null);
                    }}
                    onActiveFixtureChange={onActiveFixtureChange}
                    onSelectFixture={onSelectFixture}
                  />
                ))}
          </ZoomableGroup>
        </ComposableMap>

        {overlay}

        <div className="stadium-zoom-controls">
          <button type="button" aria-label="Zoom in" onClick={() => zoomTo(position.zoom * 1.6)}>
            +
          </button>
          <button type="button" aria-label="Zoom out" onClick={() => zoomTo(position.zoom / 1.6)}>
            −
          </button>
          <button
            type="button"
            className="stadium-zoom-reset"
            aria-label="Reset view"
            onClick={() => setPosition({ coordinates: config.center, zoom: 1 })}
          >
            ⟲
          </button>
        </div>
      </div>

      {hovered ? (
        <div
          className="stadium-tooltip"
          style={{ left: Math.min(tooltipPos.x + 18, (panelRef.current?.clientWidth ?? 600) - 250), top: tooltipPos.y - 12 }}
        >
          <span className="stadium-tooltip-meta">
            {hovered.stadium} · {hovered.city}
          </span>
          <strong>
            {hovered.fixture.home_team} <b>{cleanScore(hovered.fixture.score)}</b> {hovered.fixture.away_team}
          </strong>
          <span className="stadium-tooltip-date">{formatDay(hovered.fixture.start_date || hovered.fixture.start_date_label)}</span>
          <span className="stadium-tooltip-cta">{fixtureActionLabel(hovered.fixture)} →</span>
        </div>
      ) : null}
    </div>
  );
}

type FixtureMarkerProps = {
  item: PlacedFixture;
  index: number;
  markerScale: number;
  activeFixtureId?: string | null;
  hoveredFixtureId?: string;
  onHover: (item: PlacedFixture, event: React.MouseEvent) => void;
  onLeave: () => void;
  onActiveFixtureChange?: (fixtureId: string | null) => void;
  onSelectFixture?: (fixtureId: string) => void;
};

function FixtureMarker({
  item,
  index,
  markerScale,
  activeFixtureId,
  hoveredFixtureId,
  onHover,
  onLeave,
  onActiveFixtureChange,
  onSelectFixture,
}: FixtureMarkerProps) {
  return (
    <Marker coordinates={item.coordinates}>
      <g className="stadium-marker-scale" style={{ transform: `scale(${markerScale})` }}>
        <a
          href={fixtureHref(item.fixture)}
          className={
            `${hoveredFixtureId === item.fixture.fixture_id || activeFixtureId === item.fixture.fixture_id
              ? "stadium-marker is-active"
              : "stadium-marker"} is-${item.fixture.state}`
          }
          style={{ animationDelay: `${index * 90}ms` }}
          aria-label={`${item.fixture.home_team} vs ${item.fixture.away_team} at ${item.stadium}`}
          onClick={(event) => {
            if (!onSelectFixture) return;
            event.preventDefault();
            onSelectFixture(item.fixture.fixture_id);
          }}
          onMouseEnter={(event) => onHover(item, event)}
          onMouseMove={(event) => onHover(item, event)}
          onMouseLeave={onLeave}
          onFocus={() => onActiveFixtureChange?.(item.fixture.fixture_id)}
          onBlur={() => onActiveFixtureChange?.(null)}
        >
          <StadiumGlyph />
          <g className="stadium-badges">
            <Badge logo={item.homeLogo} code={item.homeCode} x={-8} y={-19} r={9} />
            <Badge logo={item.awayLogo} code={item.awayCode} x={8} y={-24} r={7} away />
          </g>
        </a>
      </g>
    </Marker>
  );
}
