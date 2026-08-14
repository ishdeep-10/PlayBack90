"use client";

import { geoMercator, geoOrthographic } from "d3-geo";
import type { CSSProperties, PointerEvent } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { ComposableMap, Geographies, Geography, Marker } from "react-simple-maps";

import type { League } from "../lib/api";
import { LEAGUE_PRESENTATION, type LeaguePresentation } from "../lib/leagues";

const COUNTRIES_URL = "https://cdn.jsdelivr.net/gh/nvkelso/natural-earth-vector@master/geojson/ne_110m_admin_0_countries.geojson";
const US_STATES_URL = "https://cdn.jsdelivr.net/npm/us-atlas@3/states-10m.json";
const NON_MAINLAND_US_IDS = new Set(["02", "15", "60", "66", "69", "72", "78"]);
const MAP_WIDTH = 800;
const MAP_HEIGHT = 600;

type ContinentKey = "North America" | "South America" | "Europe" | "Africa" | "Asia" | "Oceania";

const CONTINENTS: Array<{ key: ContinentKey; label: string; color: string; configured: boolean }> = [
  { key: "North America", label: "North America", color: "#2dd4bf", configured: true },
  { key: "South America", label: "South America", color: "#34d399", configured: false },
  { key: "Europe", label: "Europe", color: "#818cf8", configured: true },
  { key: "Africa", label: "Africa", color: "#f5b942", configured: false },
  { key: "Asia", label: "Asia", color: "#38bdf8", configured: false },
  { key: "Oceania", label: "Oceania", color: "#c084fc", configured: false },
];

const DETAIL_PROJECTIONS: Record<ContinentKey, { center: [number, number]; scale: number }> = {
  "North America": { center: [-100, 40], scale: 260 },
  "South America": { center: [-60, -18], scale: 315 },
  Europe: { center: [9, 51], scale: 650 },
  Africa: { center: [20, 2], scale: 315 },
  Asia: { center: [90, 34], scale: 245 },
  Oceania: { center: [145, -24], scale: 315 },
};

const DETAIL_CHIP_OFFSETS: Record<string, [number, number]> = {
  mls: [0, 48],
  "premier-league": [-85, -5],
  laliga: [-75, -10],
  bundesliga: [90, -5],
  "serie-a": [90, -5],
  "ligue-1": [-90, -5],
};

type GeoFeature = {
  rsmKey: string;
  id?: string | number;
  properties: { NAME?: string; ADMIN?: string; CONTINENT?: string; name?: string };
};

type Props = { leagues: League[] };

function continentForLeague(key: string): ContinentKey | null {
  if (key === "mls") return "North America";
  if (LEAGUE_PRESENTATION[key]) return "Europe";
  return null;
}

function countryName(geo: GeoFeature) {
  return geo.properties.NAME ?? geo.properties.ADMIN ?? geo.properties.name ?? "";
}

function continentSlug(value: string) {
  return value.toLowerCase().replace(/\s+/g, "-");
}

export function LeagueCoverageMap({ leagues }: Props) {
  const dragStart = useRef<{ x: number; y: number; rotation: [number, number] } | null>(null);
  const isDragging = useRef(false);
  const dragged = useRef(false);
  const [rotation, setRotation] = useState<[number, number]>([-18, -12]);
  const [selectedContinent, setSelectedContinent] = useState<ContinentKey | null>(null);
  const [hoveredKey, setHoveredKey] = useState<string | null>(null);

  useEffect(() => {
    if (selectedContinent) return;
    const timer = window.setInterval(() => {
      if (isDragging.current) return;
      setRotation(([longitude, latitude]) => [longitude - 0.32, latitude]);
    }, 40);
    return () => window.clearInterval(timer);
  }, [selectedContinent]);

  const globeProjection = useMemo(
    () => geoOrthographic().rotate(rotation).scale(245).translate([MAP_WIDTH / 2, MAP_HEIGHT / 2]).clipAngle(90),
    [rotation],
  );

  const detailProjection = useMemo(() => {
    if (!selectedContinent) return null;
    const config = DETAIL_PROJECTIONS[selectedContinent];
    return geoMercator().center(config.center).scale(config.scale).translate([MAP_WIDTH / 2, MAP_HEIGHT / 2]);
  }, [selectedContinent]);

  const coveredRegions = useMemo(
    () => leagues
      .map((league) => ({ league, region: LEAGUE_PRESENTATION[league.key] }))
      .filter((item): item is { league: League; region: LeaguePresentation } => Boolean(item.region)),
    [leagues],
  );

  const activeRegions = coveredRegions.filter(({ league }) => continentForLeague(league.key) === selectedContinent);
  const globeHighlightedCountries = new Set(coveredRegions.flatMap(({ region }) => region.mapNames));
  const highlightedCountries = new Set(activeRegions.flatMap(({ region }) => region.mapNames));
  const coverageByCountry = new Map(
    activeRegions.flatMap((item) => item.region.mapNames.map((name) => [name, item] as const)),
  );
  const selectedMeta = CONTINENTS.find(({ key }) => key === selectedContinent) ?? null;
  const hovered = activeRegions.find(({ league }) => league.key === hoveredKey) ?? null;
  const hoveredPoint = hovered && detailProjection ? detailProjection(hovered.region.coordinates) : null;
  const mlsCoverage = activeRegions.find(({ league }) => league.key === "mls") ?? null;

  const selectContinent = (continent: string | undefined) => {
    const valid = CONTINENTS.find(({ key }) => key === continent);
    if (!valid || dragged.current) return;
    setSelectedContinent(valid.key);
    setHoveredKey(null);
  };

  const handlePointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (selectedContinent) return;
    if ((event.target as HTMLElement).closest("button, a")) return;
    dragStart.current = { x: event.clientX, y: event.clientY, rotation };
    isDragging.current = true;
    dragged.current = false;
  };

  const handlePointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (!dragStart.current || selectedContinent) return;
    const dx = event.clientX - dragStart.current.x;
    const dy = event.clientY - dragStart.current.y;
    if (Math.abs(dx) + Math.abs(dy) > 4) {
      dragged.current = true;
      if (!event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.setPointerCapture(event.pointerId);
      }
    }
    setRotation([
      dragStart.current.rotation[0] + dx * 0.28,
      Math.max(-65, Math.min(65, dragStart.current.rotation[1] - dy * 0.22)),
    ]);
  };

  const handlePointerUp = () => {
    dragStart.current = null;
    isDragging.current = false;
    window.setTimeout(() => { dragged.current = false; }, 0);
  };

  return (
    <section className="coverage-explorer" aria-label="Explore PlayBack90 league coverage by continent">
      <div
        className={`coverage-globe-stage${selectedContinent ? " is-detail" : ""}`}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
      >
        <div className="coverage-ambient" />

        {!selectedContinent ? (
          <>
            <div className="coverage-globe-copy">
              <span>Global coverage</span>
              <strong>Drag to explore</strong>
              <small>The globe keeps moving. Select a continent to open its leagues.</small>
            </div>
            <ComposableMap className="coverage-globe" projection={globeProjection} width={MAP_WIDTH} height={MAP_HEIGHT}>
              <defs>
                <linearGradient id="coverage-country-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stopColor="#d9f99d" />
                  <stop offset="48%" stopColor="#34d399" />
                  <stop offset="100%" stopColor="#22d3ee" />
                </linearGradient>
              </defs>
              <circle className="coverage-globe-ocean" cx={MAP_WIDTH / 2} cy={MAP_HEIGHT / 2} r={245} />
              <Geographies geography={COUNTRIES_URL}>
                {({ geographies }: { geographies: GeoFeature[] }) => geographies.map((geo) => {
                  const continent = geo.properties.CONTINENT ?? "";
                  const meta = CONTINENTS.find(({ key }) => key === continent);
                  if (!meta || continent === "Antarctica") return null;
                  const isLeagueCountry = globeHighlightedCountries.has(countryName(geo));
                  return (
                    <Geography
                      key={geo.rsmKey}
                      geography={geo}
                      className={`coverage-globe-country continent-${continentSlug(continent)}${isLeagueCountry ? " is-league-country" : ""}`}
                      tabIndex={-1}
                      onClick={() => selectContinent(continent)}
                    />
                  );
                })}
              </Geographies>
            </ComposableMap>
            <nav className="coverage-continent-nav" aria-label="Continents">
              {CONTINENTS.map((continent) => (
                <button
                  key={continent.key}
                  type="button"
                  className={continent.configured ? "is-configured" : ""}
                  style={{ "--continent-color": continent.color } as CSSProperties}
                  onClick={() => selectContinent(continent.key)}
                >
                  <i />
                  <span>{continent.label}</span>
                  <small>{continent.configured ? "Leagues available" : "Coming soon"}</small>
                </button>
              ))}
            </nav>
          </>
        ) : (
          <>
            <header className="coverage-detail-head">
              <button type="button" onClick={() => setSelectedContinent(null)}>← Globe</button>
              <div>
                <span>Continent view</span>
                <h3>{selectedContinent}</h3>
                <p>{selectedMeta?.configured ? "Select a highlighted country or league crest." : "League coverage for this continent is coming soon."}</p>
              </div>
            </header>
            <ComposableMap
              className="coverage-continent-map"
              projection={detailProjection!}
              width={MAP_WIDTH}
              height={MAP_HEIGHT}
              role="img"
              aria-label={`${selectedContinent} league coverage map`}
            >
              <Geographies geography={COUNTRIES_URL}>
                {({ geographies }: { geographies: GeoFeature[] }) => geographies.map((geo) => {
                  if (geo.properties.CONTINENT !== selectedContinent) return null;
                  const name = countryName(geo);
                  const isUs = name === "United States of America";
                  const isCovered = !isUs && highlightedCountries.has(name);
                  const covered = isUs ? undefined : coverageByCountry.get(name);
                  return (
                    <Geography
                      key={geo.rsmKey}
                      geography={geo}
                      className={isCovered ? "coverage-country is-covered" : "coverage-country"}
                      tabIndex={-1}
                      onClick={() => covered && window.location.assign(`/matches/${covered.league.key}/latest`)}
                      onMouseEnter={() => covered && setHoveredKey(covered.league.key)}
                      onMouseLeave={() => covered && setHoveredKey(null)}
                    />
                  );
                })}
              </Geographies>

              {mlsCoverage ? (
                <Geographies geography={US_STATES_URL}>
                  {({ geographies }: { geographies: GeoFeature[] }) => geographies.map((geo) => {
                    const id = String(geo.id ?? "").padStart(2, "0");
                    if (NON_MAINLAND_US_IDS.has(id)) return null;
                    return (
                      <Geography
                        key={`mls-${geo.rsmKey}`}
                        geography={geo}
                        className="coverage-country is-covered"
                        tabIndex={-1}
                        onClick={() => window.location.assign(`/matches/${mlsCoverage.league.key}/latest`)}
                        onMouseEnter={() => setHoveredKey("mls")}
                        onMouseLeave={() => setHoveredKey(null)}
                      />
                    );
                  })}
                </Geographies>
              ) : null}

              {activeRegions.map(({ league, region }, index) => {
                const [offsetX, offsetY] = DETAIL_CHIP_OFFSETS[league.key] ?? [0, 44];
                return <Marker key={league.key} coordinates={region.coordinates}>
                  <line className="coverage-marker-connector" x1={0} y1={0} x2={offsetX} y2={offsetY + 14} />
                  <a
                    href={`/matches/${league.key}/latest`}
                    className="coverage-marker"
                    aria-label={`${region.name} — view latest matches`}
                    style={{ animationDelay: `${index * 120}ms` }}
                  >
                    <circle className="coverage-beacon-ring" r={7} />
                    <circle className="coverage-beacon-core" r={7} />
                  </a>
                </Marker>;
              })}
            </ComposableMap>

            {activeRegions.map(({ league, region }) => {
              const point = detailProjection?.(region.coordinates);
              if (!point) return null;
              const [offsetX, offsetY] = DETAIL_CHIP_OFFSETS[league.key] ?? [0, 44];
              return (
                <a
                  key={`chip-${league.key}`}
                  href={`/matches/${league.key}/latest`}
                  className={`coverage-logo-chip${hoveredKey === league.key ? " is-hot" : ""}`}
                  style={{ left: `${((point[0] + offsetX) / MAP_WIDTH) * 100}%`, top: `${((point[1] + offsetY) / MAP_HEIGHT) * 100}%` }}
                  onMouseEnter={() => setHoveredKey(league.key)}
                  onMouseLeave={() => setHoveredKey(null)}
                >
                  <img src={region.logo} alt="" />
                  <span>{region.name}</span>
                </a>
              );
            })}

            {hovered && hoveredPoint ? (
              <div className="coverage-hover-card" style={{ left: `${(hoveredPoint[0] / MAP_WIDTH) * 100}%`, top: `${(hoveredPoint[1] / MAP_HEIGHT) * 100}%` }}>
                <img src={hovered.region.logo} alt="" />
                <div><b>{hovered.region.name}</b><span>{hovered.region.country}</span><i>Latest matches →</i></div>
              </div>
            ) : null}
          </>
        )}
      </div>
    </section>
  );
}
