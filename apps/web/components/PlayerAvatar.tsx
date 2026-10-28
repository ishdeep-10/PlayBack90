"use client";

import { useEffect, useState } from "react";

import { PUBLIC_API_BASE, getAuthHeaders } from "../lib/api";

const imageCache = new Map<string, string | null>();
const pendingByTeam = new Map<string, Set<string>>();
let pendingPromise: Promise<void> | null = null;
const subscribers = new Set<() => void>();

function cacheKey(name: string, team?: string) {
  return `${name}|${team ?? ""}`;
}

const API_BATCH_SIZE = 80;
const RETRY_AFTER_MS = 30_000;
const failedAt = new Map<string, number>();

function requestImage(name: string, team?: string) {
  const key = cacheKey(name, team);
  if (imageCache.has(key)) return;
  // A failed batch is not cached as "no image" (that would blank those players until reload); retry after a pause.
  if (Date.now() - (failedAt.get(key) ?? 0) < RETRY_AFTER_MS) return;
  const teamKey = team ?? "";
  const bucket = pendingByTeam.get(teamKey) ?? new Set<string>();
  bucket.add(name);
  pendingByTeam.set(teamKey, bucket);
  if (!pendingPromise) {
    pendingPromise = new Promise((resolve) => setTimeout(resolve, 50)).then(async () => {
      const batches = [...pendingByTeam.entries()];
      pendingByTeam.clear();
      pendingPromise = null;
      await Promise.all(
        batches.map(async ([teamKey, namesSet]) => {
          const all = [...namesSet];
          const headers = await getAuthHeaders();
          const teamParam = teamKey ? `&team=${encodeURIComponent(teamKey)}` : "";
          for (let i = 0; i < all.length; i += API_BATCH_SIZE) {
            const batch = all.slice(i, i + API_BATCH_SIZE);
            try {
              const response = await fetch(`${PUBLIC_API_BASE}/players/images?names=${encodeURIComponent(batch.join(","))}${teamParam}`, { headers });
              if (!response.ok) throw new Error(`player images ${response.status}`);
              const data = (await response.json()) as Record<string, string | null>;
              for (const key of batch) imageCache.set(cacheKey(key, teamKey || undefined), data[key] ?? null);
            } catch {
              for (const key of batch) failedAt.set(cacheKey(key, teamKey || undefined), Date.now());
            }
          }
        })
      );
      subscribers.forEach((notify) => notify());
    });
  }
}

export function getCachedPlayerImage(name: string, team?: string) {
  return imageCache.get(cacheKey(name, team)) ?? null;
}

/** Warm the shared cache for a batch of players (same batching as PlayerAvatar). */
export function prefetchPlayerImages(names: string[], team?: string) {
  names.filter(Boolean).forEach((name) => requestImage(name, team));
}

/** Notifies whenever a pending image batch resolves. Returns an unsubscribe. */
export function subscribePlayerImages(notify: () => void) {
  subscribers.add(notify);
  return () => {
    subscribers.delete(notify);
  };
}

function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export function PlayerAvatar({ name, team, size = 32 }: { name: string; team?: string; size?: number }) {
  const [, bump] = useState(0);
  const [broken, setBroken] = useState(false);

  useEffect(() => {
    const notify = () => bump((n) => n + 1);
    subscribers.add(notify);
    requestImage(name, team);
    return () => {
      subscribers.delete(notify);
    };
  }, [name, team]);

  const src = imageCache.get(cacheKey(name, team));
  if (src && !broken) {
    return (
      <img
        className="player-avatar"
        src={src}
        alt={`${name} headshot`}
        width={size}
        height={size}
        loading="lazy"
        onError={() => setBroken(true)}
      />
    );
  }
  return (
    <span className="player-avatar player-avatar-fallback" style={{ width: size, height: size, fontSize: size * 0.34 }} aria-hidden="true">
      {initials(name)}
    </span>
  );
}
