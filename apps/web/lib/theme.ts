// Single chart typeface so in-visual text matches card titles (h1-h3 use Space Grotesk).
export const CHART_FONT_FAMILY = "'Space Grotesk', 'Inter', system-ui, sans-serif";

export type ThemeColors = {
  text: string;
  muted: string;
  surface: string;
  panel: string;
  pitchLine: string;
  mode: "dark" | "light";
  font: string;
  hoverBg: string;
  hoverText: string;
  accent: string;
  accent2: string;
};

export function readThemeColors(): ThemeColors {
  if (typeof window === "undefined") {
    return {
      text: "#e5eef7",
      muted: "#9fb0c3",
      surface: "rgba(148,163,184,0.08)",
      panel: "rgba(15,23,42,0.88)",
      pitchLine: "rgba(226,232,240,0.28)",
      mode: "dark",
      font: "Inter, system-ui, -apple-system, sans-serif",
      hoverBg: "rgba(15,23,42,0.95)",
      hoverText: "#f8fafc",
      accent: "#22c55e",
      accent2: "#38bdf8",
    };
  }
  const styles = window.getComputedStyle(document.documentElement);
  const isDark = document.documentElement.classList.contains("dark");
  return {
    text: styles.getPropertyValue("--text").trim() || "#e5eef7",
    muted: styles.getPropertyValue("--muted").trim() || "#9fb0c3",
    surface: styles.getPropertyValue("--bg-subtle").trim() || "rgba(148,163,184,0.08)",
    panel: styles.getPropertyValue("--panel").trim() || "rgba(15,23,42,0.88)",
    pitchLine: isDark ? "rgba(226,232,240,0.28)" : "rgba(71,85,105,0.24)",
    mode: isDark ? "dark" : "light",
    font: styles.getPropertyValue("font-family").trim() || "Inter, system-ui, -apple-system, sans-serif",
    hoverBg: isDark ? "rgba(15,23,42,0.95)" : "rgba(255,255,255,0.97)",
    hoverText: isDark ? "#f8fafc" : "#0f172a",
    accent: styles.getPropertyValue("--accent").trim() || "#22c55e",
    accent2: styles.getPropertyValue("--accent-2").trim() || "#38bdf8",
  };
}

export function num(value: unknown, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function parseRange(value: string, fallbackStart: number, fallbackEnd: number) {
  const [rawStart, rawEnd] = value.split("-");
  const start = Number(rawStart);
  const end = Number(rawEnd);
  if (!Number.isFinite(start) || !Number.isFinite(end)) {
    return [fallbackStart, fallbackEnd] as const;
  }
  return [start, end] as const;
}

export function colorWithAlpha(color: string, alpha: number) {
  const hex = color.trim().replace("#", "");
  const fullHex = hex.length === 3 ? hex.split("").map((char) => char + char).join("") : hex;
  const value = Number.parseInt(fullHex.slice(0, 6), 16);
  if (!Number.isFinite(value)) return `rgba(34,197,94,${alpha})`;
  return `rgba(${(value >> 16) & 255}, ${(value >> 8) & 255}, ${value & 255}, ${alpha})`;
}

export function fallbackTeamColor(name: string) {
  const palette = ["#22c55e", "#60a5fa", "#f97316", "#eab308", "#a855f7", "#14b8a6", "#ef4444", "#f59e0b"];
  return palette[[...name].reduce((sum, char) => sum + char.charCodeAt(0), 0) % palette.length];
}
