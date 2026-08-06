"use client";

const PUBLIC_API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";

/** External images taint canvases (no CORS on the CDNs) — route them through
 *  the API proxy and inline as data URLs. */
export async function toProxiedDataUrl(src: string): Promise<string | null> {
  try {
    const target = /^https:\/\//.test(src)
      ? `${PUBLIC_API_BASE}/players/image-proxy?url=${encodeURIComponent(src)}`
      : src;
    const response = await fetch(target);
    if (!response.ok) return null;
    const blob = await response.blob();
    return await new Promise((resolve) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = () => resolve(null);
      reader.readAsDataURL(blob);
    });
  } catch {
    return null;
  }
}

function loadImageElement(src: string): Promise<HTMLImageElement | null> {
  return new Promise((resolve) => {
    const image = new window.Image();
    image.onload = () => resolve(image);
    image.onerror = () => resolve(null);
    image.src = src;
  });
}

/** Player headshot composed into a circle with a colored ring, as a data URL. */
export async function circularImageDataUrl(src: string, borderColor: string, px = 64): Promise<string | null> {
  const dataUrl = await toProxiedDataUrl(src);
  if (!dataUrl) return null;
  const image = await loadImageElement(dataUrl);
  if (!image) return null;
  const canvas = document.createElement("canvas");
  canvas.width = px;
  canvas.height = px;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  const half = px / 2;
  ctx.save();
  ctx.beginPath();
  ctx.arc(half, half, half - 2, 0, Math.PI * 2);
  ctx.clip();
  ctx.fillStyle = "#0f172a";
  ctx.fillRect(0, 0, px, px);
  ctx.drawImage(image, 0, 0, px, px);
  ctx.restore();
  ctx.beginPath();
  ctx.arc(half, half, half - 2, 0, Math.PI * 2);
  ctx.lineWidth = 3;
  ctx.strokeStyle = borderColor;
  ctx.stroke();
  return canvas.toDataURL("image/png");
}

function svgDataUrl(svg: string): string {
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

export const CARD_ICON_YELLOW = svgDataUrl(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><rect x="7" y="3" width="11" height="17" rx="2" fill="#facc15" stroke="#0f172a" stroke-width="1" transform="rotate(8 12.5 11.5)"/></svg>'
);

export const CARD_ICON_RED = svgDataUrl(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><rect x="7" y="3" width="11" height="17" rx="2" fill="#ef4444" stroke="#0f172a" stroke-width="1" transform="rotate(8 12.5 11.5)"/></svg>'
);

export const CARD_ICON_SECOND_YELLOW = svgDataUrl(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 28 24">'
  + '<rect x="4.5" y="4" width="10" height="16" rx="1.8" fill="#facc15" stroke="#0f172a" stroke-width="1" transform="rotate(-8 9.5 12)"/>'
  + '<rect x="13.5" y="3" width="10" height="16" rx="1.8" fill="#ef4444" stroke="#0f172a" stroke-width="1" transform="rotate(8 18.5 11)"/>'
  + "</svg>"
);

export const SUB_ICON = svgDataUrl(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
  + '<path d="M8 20V7M8 7L4 11M8 7l4 4" fill="none" stroke="#4ade80" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>'
  + '<path d="M16 4v13m0 0l-4-4m4 4l4-4" fill="none" stroke="#f87171" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>'
  + "</svg>"
);
