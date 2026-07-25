"use client";

import { useEffect } from "react";

/**
 * Mirrors client-side filter state into the URL query string (shallow, no
 * server round-trip) so every filtered view is shareable and survives reload.
 */
export function useSyncFiltersToUrl(params: Record<string, string | null | undefined>) {
  const serialized = JSON.stringify(params);

  useEffect(() => {
    const entries = JSON.parse(serialized) as Record<string, string | null | undefined>;
    const url = new URL(window.location.href);
    let changed = false;
    for (const [key, value] of Object.entries(entries)) {
      const current = url.searchParams.get(key);
      const next = value == null || value === "" ? null : String(value);
      if (next === null) {
        if (current !== null) {
          url.searchParams.delete(key);
          changed = true;
        }
      } else if (current !== next) {
        url.searchParams.set(key, next);
        changed = true;
      }
    }
    if (changed) {
      window.history.replaceState(window.history.state, "", url.toString());
    }
  }, [serialized]);
}
