"use client";

import type React from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { geoAzimuthalEqualArea } from "d3-geo";
import { ComposableMap, Geographies, Geography, Marker } from "react-simple-maps";

import type { League } from "../lib/api";


const GEO_URL = "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json";

const MAP_WIDTH = 800;
const MAP_HEIGHT = 600;

// Top-5 league countries only.
const COVERAGE: Record<
  string,
  {
    mapName: string;
    country: string;
    competition: string;
    coordinates: [number, number];
    logo: string;
  }
> = {
  "premier-league": {
    mapName: "United Kingdom",
    country: "England",
    competition: "Premier League",
    coordinates: [-1.6, 52.9],
    logo: "/logos/premier-league.png",
  },
  laliga: {
    mapName: "Spain",
    country: "Spain",
    competition: "LaLiga",
    coordinates: [-3.7, 40.2],
    logo: "/logos/laliga.png",
  },
  bundesliga: {
    mapName: "Germany",
    country: "Germany",
    competition: "Bundesliga",
    coordinates: [10.4, 51.1],
    logo: "/logos/bundesliga.png",
  },
  "serie-a": {
    mapName: "Italy",
    country: "Italy",
    competition: "Serie A",
    coordinates: [12.6, 42.8],
    logo: "/logos/serie-a.png",
  },
  "ligue-1": {
    mapName: "France",
    country: "France",
    competition: "Ligue 1",
    coordinates: [2.3, 46.4],
    logo: "/logos/ligue-1.png",
  },
};

type Props = {
  leagues: League[];
};

export function LeagueCoverageMap({ leagues }: Props) {
  const panelRef = useRef<HTMLDivElement>(null);
  const frame = useRef<number | null>(null);
  const [hoveredKey, setHoveredKey] = useState<string | null>(null);

  useEffect(() => () => {
    if (frame.current !== null) cancelAnimationFrame(frame.current);
  }, []);

  // Azimuthal equal-area centered between Paris and Frankfurt frames the five
  // league countries (UK down to Spain and Italy) inside the 800x600 viewBox.
  const projection = useMemo(
    () =>
      geoAzimuthalEqualArea()
        .rotate([-4.5, -48.5, 0])
        .scale(1250)
        .translate([MAP_WIDTH / 2, MAP_HEIGHT / 2]),
    [],
  );

  const handlePointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const panel = panelRef.current;
    if (!panel) return;
    const bounds = panel.getBoundingClientRect();
    const x = (event.clientX - bounds.left) / bounds.width - 0.5;
    const y = (event.clientY - bounds.top) / bounds.height - 0.5;
    if (frame.current !== null) cancelAnimationFrame(frame.current);
    frame.current = requestAnimationFrame(() => {
      panel.style.setProperty("--drift-x", `${Math.round(x * 26)}px`);
      panel.style.setProperty("--drift-y", `${Math.round(y * 20)}px`);
    });
  };

  const handlePointerLeave = () => {
    const panel = panelRef.current;
    if (!panel) return;
    panel.style.setProperty("--drift-x", "0px");
    panel.style.setProperty("--drift-y", "0px");
  };

  const coveredRegions = useMemo(
    () =>
      leagues
        .map((league) => ({ league, region: COVERAGE[league.key] }))
        .filter((item): item is { league: League; region: (typeof COVERAGE)[keyof typeof COVERAGE] } =>
          Boolean(item.region)
        ),
    [leagues]
  );
  const highlightedCountries = new Set(coveredRegions.map(({ region }) => region.mapName));
  const coverageByCountry = new Map(coveredRegions.map((item) => [item.region.mapName, item]));
  const hovered = coveredRegions.find(({ league }) => league.key === hoveredKey) ?? null;
  const hoveredPoint = hovered ? projection(hovered.region.coordinates) : null;

  return (
    <section className="coverage-landing coverage-landing-map-only" aria-label="Select a competition from the map of Europe">
      <div
        className="coverage-map-panel is-map-only"
        ref={panelRef}
        onPointerMove={handlePointerMove}
        onPointerLeave={handlePointerLeave}
      >
        <div className="coverage-ambient" />
        <div className="coverage-map-glow" />
        <div className="coverage-map-tilt">
          <ComposableMap
            className="coverage-landing-map"
            projection={projection}
            width={MAP_WIDTH}
            height={MAP_HEIGHT}
            role="img"
            aria-label="Map of Europe showing PlayBack90 league coverage"
          >
            <Geographies geography={GEO_URL}>
              {({ geographies }: { geographies: Array<{ rsmKey: string; properties: { name?: string } }> }) =>
                geographies.map((geo) => {
                  const name = geo.properties.name ?? "";
                  const isCovered = highlightedCountries.has(name);
                  const covered = coverageByCountry.get(name);
                  const openCompetition = () => {
                    if (covered) window.location.assign(`/matches/${covered.league.key}/latest`);
                  };

                  return (
                    <Geography
                      key={geo.rsmKey}
                      geography={geo}
                      className={isCovered ? "coverage-country is-covered" : "coverage-country"}
                      tabIndex={-1}
                      onClick={openCompetition}
                      onMouseEnter={() => covered && setHoveredKey(covered.league.key)}
                      onMouseLeave={() => covered && setHoveredKey((k) => (k === covered.league.key ? null : k))}
                    />
                  );
                })
              }
            </Geographies>

            {coveredRegions.map(({ league, region }, index) => (
              <Marker key={league.key} coordinates={region.coordinates}>
                <a
                  href={`/matches/${league.key}/latest`}
                  className="coverage-marker"
                  aria-label={`${region.competition} — view latest match`}
                  style={{ animationDelay: `${index * 140}ms` }}
                  onMouseEnter={() => setHoveredKey(league.key)}
                  onMouseLeave={() => setHoveredKey((k) => (k === league.key ? null : k))}
                  onFocus={() => setHoveredKey(league.key)}
                  onBlur={() => setHoveredKey((k) => (k === league.key ? null : k))}
                >
                  <title>{region.competition}</title>
                  <circle className="coverage-marker-hit" r={19} />
                  <circle className="coverage-beacon-ring" r={7} />
                  <circle className="coverage-beacon-ring delay" r={7} />
                  <circle className="coverage-beacon-core" r={7} />
                </a>
              </Marker>
            ))}
          </ComposableMap>

          {coveredRegions.map(({ league, region }) => {
            const point = projection(region.coordinates);
            if (!point) return null;
            return (
              <a
                key={`chip-${league.key}`}
                href={`/matches/${league.key}/latest`}
                className={`coverage-logo-chip${hoveredKey === league.key ? " is-hot" : ""}`}
                style={{
                  left: `${(point[0] / MAP_WIDTH) * 100}%`,
                  top: `${(point[1] / MAP_HEIGHT) * 100}%`,
                }}
                aria-label={`${region.competition} — view latest match`}
                onMouseEnter={() => setHoveredKey(league.key)}
                onMouseLeave={() => setHoveredKey((k) => (k === league.key ? null : k))}
                onFocus={() => setHoveredKey(league.key)}
                onBlur={() => setHoveredKey((k) => (k === league.key ? null : k))}
              >
                <img src={region.logo} alt="" />
                <span>{region.competition}</span>
              </a>
            );
          })}

          {hovered && hoveredPoint ? (
            <div
              className="coverage-hover-card"
              style={{
                left: `${(hoveredPoint[0] / MAP_WIDTH) * 100}%`,
                top: `${(hoveredPoint[1] / MAP_HEIGHT) * 100}%`,
              }}
              aria-hidden="true"
            >
              <img src={hovered.region.logo} alt="" />
              <div>
                <b>{hovered.region.competition}</b>
                <span>{hovered.region.country}</span>
                <i>Latest match →</i>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}
