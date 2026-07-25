"use client";

import { useEffect, useState } from "react";

const PUBLIC_API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";

const imageCache = new Map<string, string | null>();
const pendingByTeam = new Map<string, Set<string>>();
let pendingPromise: Promise<void> | null = null;
const subscribers = new Set<() => void>();

function cacheKey(name: string, team?: string) {
  return `${name}|${team ?? ""}`;
}

function requestImage(name: string, team?: string) {
  if (imageCache.has(cacheKey(name, team))) return;
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
          const batch = [...namesSet];
          if (!batch.length) return;
          try {
            const teamParam = teamKey ? `&team=${encodeURIComponent(teamKey)}` : "";
            const response = await fetch(
              `${PUBLIC_API_BASE}/players/images?names=${encodeURIComponent(batch.join(","))}${teamParam}`
            );
            const data = (await response.json()) as Record<string, string | null>;
            for (const key of batch) imageCache.set(cacheKey(key, teamKey || undefined), data[key] ?? null);
          } catch {
            for (const key of batch) imageCache.set(cacheKey(key, teamKey || undefined), null);
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
