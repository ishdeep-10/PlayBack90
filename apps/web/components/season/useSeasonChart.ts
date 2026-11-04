"use client";

import { useEffect, useState } from "react";

import { getSeasonFile, type SeasonFileKind } from "../../lib/api";
import { toProxiedDataUrl } from "../../lib/images";
import { readThemeColors } from "../../lib/theme";

// One fetch per file per visit: switching tabs back and forth does not download the same table again.
const cache = new Map<string, Promise<unknown>>();

export function loadSeasonFile<T>(league: string, season: string, kind: SeasonFileKind): Promise<T> {
  const key = `${league}/${season}/${kind}`;
  if (!cache.has(key)) {
    cache.set(
      key,
      getSeasonFile<T>(league, season, kind).catch((error) => {
        cache.delete(key);
        throw error;
      }),
    );
  }
  return cache.get(key) as Promise<T>;
}

export function useSeasonFile<T>(league: string, season: string, kind: SeasonFileKind, enabled = true) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!enabled) return; // keeps what was loaded; nothing is requested until it is needed
    let live = true;
    setData(null);
    setError(null);
    loadSeasonFile<T>(league, season, kind)
      .then((d) => live && setData(d))
      .catch(() => live && setError("Could not load these figures."));
    return () => {
      live = false;
    };
  }, [league, season, kind, enabled]);
  return { data, error };
}

/** Theme colours that follow the light/dark switch, and the pixel width of the chart's container. */
export function useChartFrame() {
  const [themeColors, setThemeColors] = useState(readThemeColors);
  const [width, setWidth] = useState(900);
  const [host, setHost] = useState<HTMLDivElement | null>(null);

  useEffect(() => {
    const update = () => setThemeColors(readThemeColors());
    update();
    const observer = new MutationObserver(update);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "data-theme"] });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!host || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(280, Math.floor(entry.contentRect.width))));
    observer.observe(host);
    return () => observer.disconnect();
  }, [host]);

  return { themeColors, width, setHost, compact: width < 560 };
}

export const fmtNum = (v: number) => (Math.abs(v) >= 100 ? v.toFixed(0) : Math.abs(v) >= 10 ? v.toFixed(1) : v.toFixed(2));


// Photos and crests come from CDNs without CORS headers, which blanks them in a Share export. Inlining them as data URLs (through the
// API image proxy) makes the exported chart match the screen.
const dataUrlCache = new Map<string, Promise<string | null>>();

export function useInlineImages(urls: string[]): Record<string, string> {
  const [done, setDone] = useState<Record<string, string>>({});
  const key = urls.join("|");
  useEffect(() => {
    let live = true;
    for (const url of urls) {
      if (!url || url.startsWith("data:")) continue;
      if (!dataUrlCache.has(url)) dataUrlCache.set(url, toProxiedDataUrl(url));
      dataUrlCache.get(url)!.then((data) => {
        if (live && data) setDone((prev) => (prev[url] === data ? prev : { ...prev, [url]: data }));
      });
    }
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return done;
}
