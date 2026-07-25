// Shared cache of player headshots; drawn once loaded, dots until then.
const imageCache = new Map<string, HTMLImageElement>();

export function preloadImages(urls: Record<string, string> | undefined) {
  if (!urls || typeof window === "undefined") return;
  for (const url of Object.values(urls)) {
    if (imageCache.has(url)) continue;
    // no crossOrigin: the CDN sends no CORS headers and we never read the
    // canvas back, so a tainted canvas is acceptable
    const img = new Image();
    img.src = url;
    imageCache.set(url, img);
  }
}

export function loadedImage(url: string | undefined) {
  if (!url) return null;
  const img = imageCache.get(url);
  return img && img.complete && img.naturalWidth > 0 ? img : null;
}
