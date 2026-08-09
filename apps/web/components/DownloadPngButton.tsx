"use client";

import { useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Share2 } from "lucide-react";

import { toProxiedDataUrl as toDataUrl } from "../lib/images";
import { getPlotly } from "../lib/plotly";
import { capture } from "../lib/posthog";
import { CHART_FONT_FAMILY } from "../lib/theme";
import { useShareMatchInfo } from "./ShareExportContext";

type Props = {
  filename: string;
  /** CSS selector for the ancestor that scopes which chart gets exported. */
  scopeSelector?: string;
  /** Visual title shown on the branded export (falls back to a cleaned filename).
   *  Accepts a function so it can be resolved lazily at click time. */
  title?: string | (() => string);
  /** Active filter labels rendered as chips on the export.
   *  Accepts a function so values can be resolved lazily at click time. */
  filters?: string[] | (() => string[]);
  /** Caption drawn above each captured chart (index-aligned with the grid). */
  chartLabels?: string[] | (() => string[]);
  /** Small subtitle under each chart caption (e.g. active checkbox options). */
  chartSubtitles?: string[] | (() => string[]);
  /** Per-chart stat lines drawn as a sub-panel below that chart column. */
  chartStats?: () => string[][];
  /** Structured per-chart panel: metric chips + legend, drawn like the in-app
   *  panel under each pitch. Takes precedence over chartStats. */
  chartPanels?: () => ChartPanel[];
  /** Extra full-width stat lines rendered under the charts (resolved at click time). */
  statLines?: () => string[];
  /** Structured table rendered in a panel on the right-hand side of the charts
   *  (resolved at click time). The chart area shrinks to make room. */
  sideTable?: () => SideTable | null;
  /** Profile cards (name + score + meter, like the in-app profile panel) drawn
   *  in a grid under the charts (resolved at click time). */
  profileCards?: () => ProfileCard[];
  /** Optional headshot/thumbnail URLs drawn next to the export title.
   *  Accepts a function so URLs can be resolved lazily at click time. */
  titleImages?: string[] | (() => string[]);
  /** Optional player/profile identity shown once above each chart row. */
  chartRowProfiles?: ChartRowProfile[] | (() => ChartRowProfile[]);
  /** Maximum number of charts captured from the scope (side-by-side grid). */
  maxCharts?: number;
  /**
   * When set, overrides the capture height as `Math.round(clientWidth * captureAspect)`.
   * Use this for pitch visuals where `scaleanchor` leaves empty bands above/below —
   * pass the y/x axis unit ratio so the image tightly wraps the pitch.
   * Example: a 108×71 axis range → captureAspect = 71/108.
   */
  captureAspect?: number;
  /** When set, charts are captured per matching group element; multiple plots
   *  inside one group are stacked vertically into a single column image. */
  chartGroupSelector?: string;
  /** Charts per grid row (defaults to all charts on one row). Extra charts wrap
   *  onto additional rows — used for multi-player comparisons. */
  chartsPerRow?: number;
  /** Give wrapped chart rows a full-size vertical budget instead of squeezing
   *  them into the default social canvas. */
  expandCanvasForRows?: boolean;
  /** Override the logical canvas height for compact single-chart exports. */
  canvasHeight?: number;
};

export type SideTableRow = {
  label?: string;
  value?: string;
  header?: string;
  /** Headshot URL — presence (even null) renders the row as an avatar table row. */
  image?: string | null;
  /** Muted secondary line under the label (avatar rows only). */
  sub?: string;
};
export type SideTable = { title?: string; rows: SideTableRow[]; large?: boolean };
export type ProfileCard = { name: string; score: number; description?: string; detail?: string };
export type ChartPanelStat = { label: string; value: string; active?: boolean };
export type ChartPanelGroup = { title?: string; stats: ChartPanelStat[] };
export type ChartLegendItem = { label: string; color: string; shape?: "line" | "circle" | "square" | "ring" };
export type ChartPanel = { groups?: ChartPanelGroup[]; legend?: ChartLegendItem[] };
export type ChartRowProfile = { name: string; sub?: string; image?: string | null; color?: string };

const SCALE = 2;

function loadImage(src: string): Promise<HTMLImageElement | null> {
  return new Promise((resolve) => {
    const image = new window.Image();
    image.crossOrigin = "anonymous";
    image.onload = () => resolve(image);
    image.onerror = () => resolve(null);
    image.src = src;
  });
}


async function loadImageSafe(src: string): Promise<HTMLImageElement | null> {
  if (/^https:\/\//.test(src)) {
    const dataUrl = await toDataUrl(src);
    return dataUrl ? loadImage(dataUrl) : loadImage(src);
  }
  return loadImage(src);
}

function cssVar(name: string, fallback: string) {
  const value = window.getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

const SVG_INLINE_PROPS = [
  "fill",
  "stroke",
  "stroke-width",
  "stroke-dasharray",
  "font-family",
  "font-size",
  "font-weight",
  "letter-spacing",
  "opacity",
  "paint-order",
  "text-anchor",
] as const;

async function svgToImage(svg: SVGSVGElement): Promise<HTMLImageElement | null> {
  const clone = svg.cloneNode(true) as SVGSVGElement;
  const rect = svg.getBoundingClientRect();
  clone.setAttribute("width", String(rect.width * SCALE));
  clone.setAttribute("height", String(rect.height * SCALE));
  // The page's CSS classes are not available inside a serialized SVG image, so
  // copy the computed presentation styles onto each element inline.
  const sourceNodes = svg.querySelectorAll<SVGElement>("*");
  const cloneNodes = clone.querySelectorAll<SVGElement>("*");
  sourceNodes.forEach((sourceNode, index) => {
    const target = cloneNodes[index];
    if (!target || sourceNode.tagName === "style") return;
    const computed = window.getComputedStyle(sourceNode);
    let styleText = "";
    for (const prop of SVG_INLINE_PROPS) {
      const value = computed.getPropertyValue(prop);
      if (value) styleText += `${prop}:${value};`;
    }
    if (styleText) target.setAttribute("style", styleText);
  });
  // Inline external images as data URLs so the export canvas stays untainted.
  await Promise.all(
    [...clone.querySelectorAll("image")].map(async (node) => {
      const href = node.getAttribute("href") ?? node.getAttribute("xlink:href") ?? "";
      if (!/^https:\/\//.test(href)) return;
      const dataUrl = await toDataUrl(href);
      if (dataUrl) {
        node.setAttribute("href", dataUrl);
      } else {
        node.remove();
      }
    })
  );
  // Inline currently-computed CSS variables used by the pitch SVGs.
  const styles = window.getComputedStyle(document.documentElement);
  const inline = document.createElementNS("http://www.w3.org/2000/svg", "style");
  inline.textContent = `svg { --pitch-line: ${styles.getPropertyValue("--pitch-line") || "rgba(148,163,184,0.4)"}; --text: ${styles.getPropertyValue("--text") || "#e5eef7"}; --muted: ${styles.getPropertyValue("--muted") || "#9fb0c3"}; --font-display: ${styles.getPropertyValue("--font-display") || "sans-serif"}; --accent: ${styles.getPropertyValue("--accent") || "#22c55e"}; --bg-muted: ${styles.getPropertyValue("--bg-muted") || "rgba(148,163,184,0.08)"}; }`;
  clone.prepend(inline);
  const blob = new Blob([new XMLSerializer().serializeToString(clone)], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const image = await loadImage(url);
  URL.revokeObjectURL(url);
  return image;
}

function drawCircularImage(
  ctx: CanvasRenderingContext2D,
  image: HTMLImageElement,
  x: number,
  y: number,
  size: number,
  ringColor?: string,
  ringWidth = 0
) {
  ctx.save();
  ctx.beginPath();
  ctx.arc(x + size / 2, y + size / 2, size / 2 - ringWidth / 2, 0, Math.PI * 2);
  ctx.clip();
  ctx.fillStyle = "#0f172a";
  ctx.fillRect(x, y, size, size);
  ctx.drawImage(image, x, y, size, size);
  ctx.restore();
  if (ringColor && ringWidth > 0) {
    ctx.beginPath();
    ctx.arc(x + size / 2, y + size / 2, size / 2 - ringWidth / 2, 0, Math.PI * 2);
    ctx.lineWidth = ringWidth;
    ctx.strokeStyle = ringColor;
    ctx.stroke();
    ctx.lineWidth = 1;
  }
}

export function DownloadPngButton({
  filename,
  scopeSelector = ".card",
  title,
  filters = [],
  titleImages = [],
  chartRowProfiles = [],
  chartLabels,
  chartSubtitles,
  chartStats,
  chartPanels,
  statLines,
  sideTable,
  profileCards,
  maxCharts = 1,
  chartGroupSelector,
  chartsPerRow,
  expandCanvasForRows = false,
  captureAspect,
  canvasHeight,
}: Props) {
  const anchorRef = useRef<HTMLButtonElement>(null);
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<string | null>(null);
  const match = useShareMatchInfo();

  const cleanName = `${filename.replace(/[^a-z0-9-_ ]/gi, "").trim().replace(/\s+/g, "-")}.png`;

  const stackImages = async (images: HTMLImageElement[]): Promise<HTMLImageElement | null> => {
    const gapPx = 10 * SCALE;
    const width = Math.max(...images.map((img) => img.width));
    const height = images.reduce((sum, img) => sum + img.height, 0) + gapPx * (images.length - 1);
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    if (!ctx) return images[0] ?? null;
    let y = 0;
    for (const img of images) {
      ctx.drawImage(img, (width - img.width) / 2, y);
      y += img.height + gapPx;
    }
    return loadImage(canvas.toDataURL("image/png"));
  };

  const capturePlot = async (
    plotly: {
      relayout: (el: HTMLElement, update: Record<string, unknown>) => Promise<unknown>;
      toImage: (el: HTMLElement, opts: Record<string, unknown>) => Promise<string>;
      newPlot: (el: HTMLElement, data: unknown, layout: Record<string, unknown>, config?: Record<string, unknown>) => Promise<unknown>;
      purge: (el: HTMLElement) => void;
    },
    plotEl: HTMLElement,
    background: string
  ): Promise<HTMLImageElement | null> => {
    const gd = plotEl as HTMLElement & {
      data?: unknown[];
      layout?: Record<string, unknown> & { paper_bgcolor?: string };
    };
    const captureW = plotEl.clientWidth || 900;
    const captureH = captureAspect
      ? Math.round(captureW * captureAspect)
      : plotEl.clientHeight || 600;
    if (captureAspect && gd.data && gd.layout) {
      // Plotly writes the axis domains computed for the on-page size back into
      // the layout, so exporting a scaleanchor pitch at a different aspect
      // keeps its letterboxed domain (and relayout instantly recomputes it for
      // the on-page size again). Render a fresh off-DOM copy at the capture
      // size with the domains reset so the constraint fits that canvas.
      const src = gd.layout as Record<string, unknown>;
      const host = document.createElement("div");
      host.style.cssText = `position:fixed;left:-10000px;top:0;width:${captureW}px;height:${captureH}px;`;
      document.body.appendChild(host);
      try {
        const layout = {
          ...src,
          autosize: false,
          width: captureW,
          height: captureH,
          paper_bgcolor: background,
          xaxis: { ...((src.xaxis as Record<string, unknown>) ?? {}), domain: [0, 1] },
          yaxis: { ...((src.yaxis as Record<string, unknown>) ?? {}), domain: [0, 1] },
        };
        await plotly.newPlot(host, gd.data, layout, { staticPlot: true });
        const dataUrl = await plotly.toImage(host, { format: "png", scale: SCALE, width: captureW, height: captureH });
        return loadImage(dataUrl);
      } finally {
        plotly.purge(host);
        host.remove();
      }
    }
    const originalBg = gd.layout?.paper_bgcolor ?? "rgba(0,0,0,0)";
    await plotly.relayout(plotEl, { paper_bgcolor: background });
    const dataUrl = await plotly.toImage(plotEl, {
      format: "png",
      scale: SCALE,
      width: captureW,
      height: captureH,
    });
    await plotly.relayout(plotEl, { paper_bgcolor: originalBg });
    return loadImage(dataUrl);
  };

  const captureCharts = async (
    scope: Element | Document,
    stackedFlags: boolean[]
  ): Promise<HTMLImageElement[]> => {
    if (chartGroupSelector) {
      const groups = [...scope.querySelectorAll<HTMLElement>(chartGroupSelector)].slice(0, maxCharts);
      if (groups.length) {
        const plotly = (await getPlotly()) as unknown as {
          relayout: (el: HTMLElement, update: Record<string, unknown>) => Promise<unknown>;
          toImage: (el: HTMLElement, opts: Record<string, unknown>) => Promise<string>;
          newPlot: (el: HTMLElement, data: unknown, layout: Record<string, unknown>, config?: Record<string, unknown>) => Promise<unknown>;
          purge: (el: HTMLElement) => void;
        };
        const background = cssVar("--panel", "#0b1622");
        const images: HTMLImageElement[] = [];
        for (const group of groups) {
          const plots = [...group.querySelectorAll<HTMLElement>(".js-plotly-plot")];
          const captured: HTMLImageElement[] = [];
          for (const plotEl of plots) {
            const image = await capturePlot(plotly, plotEl, background);
            if (image) captured.push(image);
          }
          if (captured.length === 1) {
            images.push(captured[0]);
            stackedFlags.push(false);
          } else if (captured.length > 1) {
            const stacked = await stackImages(captured);
            if (stacked) {
              images.push(stacked);
              stackedFlags.push(true);
            }
          } else {
            const svg = group.querySelector<SVGSVGElement>("svg");
            if (svg) {
              const image = await svgToImage(svg);
              if (image) {
                images.push(image);
                stackedFlags.push(false);
              }
            }
          }
        }
        return images;
      }
    }
    const plotEls = [...scope.querySelectorAll<HTMLElement>(".js-plotly-plot")].slice(0, maxCharts);
    if (plotEls.length) {
      const plotly = (await getPlotly()) as unknown as {
        relayout: (el: HTMLElement, update: Record<string, unknown>) => Promise<unknown>;
        toImage: (el: HTMLElement, opts: Record<string, unknown>) => Promise<string>;
        newPlot: (el: HTMLElement, data: unknown, layout: Record<string, unknown>, config?: Record<string, unknown>) => Promise<unknown>;
        purge: (el: HTMLElement) => void;
      };
      const background = cssVar("--panel", "#0b1622");
      const images: HTMLImageElement[] = [];
      for (const plotEl of plotEls) {
        const image = await capturePlot(plotly, plotEl, background);
        if (image) images.push(image);
      }
      return images;
    }
    const svgs = [...scope.querySelectorAll<SVGSVGElement>("svg")].slice(0, maxCharts);
    const images: HTMLImageElement[] = [];
    for (const svg of svgs) {
      const image = await svgToImage(svg);
      if (image) images.push(image);
    }
    return images;
  };

  const buildPreview = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const scope = anchorRef.current?.closest(scopeSelector) ?? document;
      const stackedColumns: boolean[] = [];
      const charts = await captureCharts(scope, stackedColumns);
      const resolvedSideTable = sideTable ? sideTable() : null;
      const hasSideTable = Boolean(resolvedSideTable?.rows?.length);
      if (!charts.length && !hasSideTable) return;
      const footnote = (scope as Element).querySelector?.(".chart-footnote")?.textContent?.trim() ?? "";
      const resolvedFilters = typeof filters === "function" ? filters() : filters;
      const resolvedChartLabels = typeof chartLabels === "function" ? chartLabels() : chartLabels ?? [];
      const resolvedChartSubtitles = typeof chartSubtitles === "function" ? chartSubtitles() : chartSubtitles ?? [];
      const resolvedChartStats = chartStats ? chartStats() : [];
      const resolvedChartPanels = chartPanels ? chartPanels() : [];
      const resolvedStatLines = statLines ? statLines().filter(Boolean) : [];
      const resolvedProfileCards = profileCards ? profileCards().slice(0, 6) : [];
      const resolvedChartRowProfiles =
        typeof chartRowProfiles === "function" ? chartRowProfiles() : chartRowProfiles;
      const resolvedTitle = typeof title === "function" ? title() : title;
      const displayTitle = resolvedTitle ?? filename.replace(/[-_]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

      const isDark = document.documentElement.classList.contains("dark");
      const background = cssVar("--panel", isDark ? "#0b1622" : "#ffffff");
      const textColor = cssVar("--text", isDark ? "#e5eef7" : "#0f172a");
      const mutedColor = cssVar("--muted", "#9fb0c3");
      const accentColor = cssVar("--accent", "#22c55e");
      const lineColor = "rgba(148,163,184,0.28)";

      const resolvedTitleImages = typeof titleImages === "function" ? titleImages() : titleImages;
      const [brandImg, homeLogo, awayLogo, ...headshots] = await Promise.all([
        loadImage(isDark ? "/logos/Logo-Dark.png" : "/logos/Logo-Light.png"),
        match?.homeLogoUrl ? loadImageSafe(match.homeLogoUrl) : Promise.resolve(null),
        match?.awayLogoUrl ? loadImageSafe(match.awayLogoUrl) : Promise.resolve(null),
        ...resolvedTitleImages.map((src) => loadImageSafe(src)),
      ]);
      const validHeadshots = headshots.filter(Boolean) as HTMLImageElement[];
      const sideTableImages = resolvedSideTable
        ? await Promise.all(resolvedSideTable.rows.map((row) => (row.image ? loadImageSafe(row.image) : Promise.resolve(null))))
        : [];
      const chartRowProfileImages = await Promise.all(
        resolvedChartRowProfiles.map((profile) =>
          profile.image ? loadImageSafe(profile.image) : Promise.resolve(null)
        )
      );

      const width = 1600 * SCALE;
      const margin = 44 * SCALE;
      const gap = 22 * SCALE;
      const contentW = width - margin * 2;
      const sideGap = 26 * SCALE;
      const hasCharts = charts.length > 0;
      const sideTableW = hasSideTable ? (hasCharts ? 430 * SCALE : contentW) : 0;
      const chartsW = hasCharts ? contentW - (hasSideTable ? sideTableW + sideGap : 0) : 0;
      const perRow = Math.max(1, Math.min(chartsPerRow ?? charts.length, charts.length));
      const rowCount = Math.ceil(charts.length / perRow);
      const baseHeight = canvasHeight ?? (expandCanvasForRows && rowCount > 1 ? 900 + (rowCount - 1) * 560 : 900);
      const height = baseHeight * SCALE;
      const columnCount = Math.min(perRow, charts.length);
      const colWidth = (chartsW - gap * (columnCount - 1)) / columnCount;
      const singleRow = rowCount === 1;

      const measure = document.createElement("canvas").getContext("2d");
      const wrapText = (raw: string, font: string, maxWidth: number): string[] => {
        if (!measure) return [raw];
        measure.font = font;
        const wrapped: string[] = [];
        let line = "";
        for (const word of raw.split(/\s+/)) {
          const candidate = line ? `${line} ${word}` : word;
          if (measure.measureText(candidate).width > maxWidth && line) {
            wrapped.push(line);
            line = word;
          } else {
            line = candidate;
          }
        }
        if (line) wrapped.push(line);
        return wrapped;
      };

      // ── header block metrics ──
      const headshotSize = validHeadshots.length ? 72 * SCALE : 0;
      const titleRowH = Math.max(50 * SCALE, headshotSize);
      const matchRowH = match ? 34 * SCALE : 0;
      const chipsRowH = resolvedFilters.length ? 30 * SCALE : 0;
      const headerBlockH = titleRowH + matchRowH + chipsRowH + 14 * SCALE;

      const hasChartLabels = resolvedChartLabels.some(Boolean);
      const hasChartSubtitles = resolvedChartSubtitles.some(Boolean);
      const rowProfileH = resolvedChartRowProfiles.length ? 48 * SCALE : 0;
      const chartHeaderH =
        rowProfileH + (hasChartLabels ? 30 * SCALE : 0) + (hasChartSubtitles ? 20 * SCALE : 0);

      // ── per-column stat panels (chips + legend) ──
      type PanelOp =
        | { kind: "chip"; x: number; y: number; w: number; h: number; label: string; value: string; active?: boolean }
        | { kind: "title"; x: number; y: number; text: string }
        | { kind: "legend"; x: number; y: number; item: ChartLegendItem };
      const chipLabelFont = `700 ${8.5 * SCALE}px ${CHART_FONT_FAMILY}`;
      const chipValueFont = `800 ${10.5 * SCALE}px ${CHART_FONT_FAMILY}`;
      const groupTitleFont = `800 ${9 * SCALE}px ${CHART_FONT_FAMILY}`;
      const legendFont = `600 ${10.5 * SCALE}px ${CHART_FONT_FAMILY}`;
      const layoutPanel = (panel: ChartPanel, panelWidth: number, flowGroups = false): { ops: PanelOp[]; height: number } => {
        if (!measure) return { ops: [], height: 0 };
        const ops: PanelOp[] = [];
        const padX = 4 * SCALE;
        const maxRight = panelWidth - padX;
        const chipH = 19 * SCALE;
        const chipGap = 5 * SCALE;
        const groupGap = 22 * SCALE;
        let y = 3 * SCALE;
        let flowX = padX;
        for (const group of panel.groups ?? []) {
          if (!group.stats.length) continue;
          // Estimate the group width so flowed groups wrap as a unit.
          let groupW = 0;
          if (group.title) {
            measure.font = groupTitleFont;
            groupW += measure.measureText(group.title.toUpperCase()).width + 7 * SCALE;
          }
          for (const stat of group.stats) {
            measure.font = chipLabelFont;
            const labelW = measure.measureText(stat.label.toUpperCase()).width;
            measure.font = chipValueFont;
            groupW += labelW + measure.measureText(stat.value).width + 22 * SCALE + chipGap;
          }
          let x = padX;
          if (flowGroups) {
            if (flowX > padX && flowX + groupW > maxRight) {
              flowX = padX;
              y += chipH + chipGap;
            }
            x = flowX;
          }
          if (group.title) {
            measure.font = groupTitleFont;
            const titleW = measure.measureText(group.title.toUpperCase()).width;
            ops.push({ kind: "title", x, y: y + chipH / 2 + 2.5 * SCALE, text: group.title.toUpperCase() });
            x += titleW + 7 * SCALE;
          }
          for (const stat of group.stats) {
            measure.font = chipLabelFont;
            const labelW = measure.measureText(stat.label.toUpperCase()).width;
            measure.font = chipValueFont;
            const valueW = measure.measureText(stat.value).width;
            const w = labelW + valueW + 22 * SCALE;
            if (x + w > maxRight && x > padX) {
              x = padX;
              y += chipH + chipGap;
            }
            ops.push({ kind: "chip", x, y, w, h: chipH, label: stat.label, value: stat.value, active: stat.active });
            x += w + chipGap;
          }
          if (flowGroups) {
            flowX = x + groupGap - chipGap;
          } else {
            y += chipH + 5 * SCALE;
          }
        }
        if (flowGroups && (panel.groups ?? []).some((group) => group.stats.length)) {
          y += chipH + 5 * SCALE;
        }
        if (panel.legend?.length) {
          const itemH = 14 * SCALE;
          let x = padX;
          y += 1.5 * SCALE;
          for (const item of panel.legend) {
            measure.font = legendFont;
            const w = 13 * SCALE + measure.measureText(item.label).width + 10 * SCALE;
            if (x + w > maxRight && x > padX) {
              x = padX;
              y += itemH;
            }
            ops.push({ kind: "legend", x, y, item });
            x += w;
          }
          y += itemH + 2 * SCALE;
        }
        return { ops, height: y };
      };
      const colStatFont = `600 ${10.5 * SCALE}px ${CHART_FONT_FAMILY}`;
      const colLineH = 16 * SCALE;
      const columnStatLines: string[][] = charts.map((_, index) =>
        (resolvedChartStats[index] ?? []).filter(Boolean).flatMap((raw) => wrapText(raw, colStatFont, colWidth - 8 * SCALE))
      );
      const columnPanels = charts.map((_, index) => {
        const panel = resolvedChartPanels[index];
        if (!panel) return null;
        // Stacked columns (e.g. goal mouth + shotmap) keep their legend inline
        // below the counters so the charts get the full column width.
        const columnOnly: ChartPanel = {
          groups: (panel.groups ?? []).filter((group) => !group.title),
          legend: stackedColumns[index] ? panel.legend : undefined,
        };
        return (columnOnly.groups!.length > 0 || (columnOnly.legend?.length ?? 0) > 0)
          ? layoutPanel(columnOnly, colWidth)
          : null;
      });

      // Legends stack vertically beside their pitch (right-hand side) instead of
      // eating vertical space below it.
      const legendItemH = 19 * SCALE;
      const columnLegends = charts.map((_, index) => (stackedColumns[index] ? [] : resolvedChartPanels[index]?.legend ?? []));
      const columnLegendWidths = columnLegends.map((items) => {
        if (!items.length || !measure) return 0;
        measure.font = legendFont;
        return Math.max(...items.map((item) => 15 * SCALE + measure.measureText(item.label).width)) + 8 * SCALE;
      });

      // Titled breakdown groups become a small table under their own pitch column.
      type TableOp =
        | { kind: "bg"; x: number; y: number; w: number; h: number }
        | { kind: "rowTitle"; x: number; y: number; text: string }
        | { kind: "cellLabel"; x: number; y: number; text: string }
        | { kind: "cellValue"; x: number; y: number; text: string }
        | { kind: "line"; x1: number; y1: number; x2: number; y2: number };
      const tableTitleFont = `800 ${8.5 * SCALE}px ${CHART_FONT_FAMILY}`;
      const tableLabelFont = `600 ${8.5 * SCALE}px ${CHART_FONT_FAMILY}`;
      const tableValueFont = `800 ${10 * SCALE}px ${CHART_FONT_FAMILY}`;
      const layoutTable = (groups: ChartPanelGroup[], tableWidth: number): { ops: TableOp[]; height: number } => {
        if (!measure) return { ops: [], height: 0 };
        const ops: TableOp[] = [];
        const rowPadY = 5.5 * SCALE;
        const lineH = 14 * SCALE;
        const titleColW = Math.min(
          92 * SCALE,
          Math.max(...groups.map((group) => {
            measure.font = tableTitleFont;
            return measure.measureText((group.title ?? "").toUpperCase()).width;
          })) + 12 * SCALE
        );
        let y = 0;
        groups.forEach((group, groupIndex) => {
          const statsX = titleColW + 6 * SCALE;
          const maxRight = tableWidth - 6 * SCALE;
          // Lay out "label value" pairs, wrapping within the stats cell.
          const cells: Array<{ label: string; value: string; x: number; row: number }> = [];
          let x = statsX;
          let row = 0;
          for (const stat of group.stats) {
            measure.font = tableLabelFont;
            const labelW = measure.measureText(stat.label).width;
            measure.font = tableValueFont;
            const pairW = labelW + measure.measureText(stat.value).width + 9 * SCALE;
            if (x + pairW > maxRight && x > statsX) {
              x = statsX;
              row += 1;
            }
            cells.push({ label: stat.label, value: stat.value, x, row });
            x += pairW + 13 * SCALE;
          }
          const rowH = rowPadY * 2 + (row + 1) * lineH;
          if (groupIndex % 2 === 0) {
            ops.push({ kind: "bg", x: 0, y, w: tableWidth, h: rowH });
          }
          ops.push({ kind: "rowTitle", x: 6 * SCALE, y: y + rowPadY + lineH - 4 * SCALE, text: (group.title ?? "").toUpperCase() });
          for (const cell of cells) {
            const cellY = y + rowPadY + (cell.row + 1) * lineH - 4 * SCALE;
            ops.push({ kind: "cellLabel", x: cell.x, y: cellY, text: cell.label });
            measure.font = tableLabelFont;
            ops.push({ kind: "cellValue", x: cell.x + measure.measureText(cell.label).width + 4 * SCALE, y: cellY, text: cell.value });
          }
          y += rowH;
          ops.push({ kind: "line", x1: 0, y1: y, x2: tableWidth, y2: y });
        });
        return { ops, height: y };
      };
      const columnTables = charts.map((_, index) => {
        if (!singleRow) return null;
        const groups = (resolvedChartPanels[index]?.groups ?? []).filter((group) => group.title);
        return groups.length ? layoutTable(groups, colWidth) : null;
      });
      const breakdownHeight = columnTables.some(Boolean)
        ? Math.max(...columnTables.map((table) => table?.height ?? 0)) + 14 * SCALE
        : 0;
      const columnHeights = charts.map((_, index) =>
        columnPanels[index] ? columnPanels[index]!.height : (columnStatLines[index]?.length ?? 0) * colLineH
      );
      const rowPanelHeights = Array.from({ length: rowCount }, (_, row) => {
        const heights = columnHeights.slice(row * perRow, (row + 1) * perRow);
        return heights.some((h) => h > 0) ? Math.max(...heights) + 16 * SCALE : 0;
      });
      const colStatsHeight = rowPanelHeights.reduce((sum, h) => sum + h, 0);

      // ── profile card grid metrics ──
      const cardCols = Math.min(3, Math.max(1, resolvedProfileCards.length));
      const cardRows = Math.ceil(resolvedProfileCards.length / cardCols);
      const cardH = 64 * SCALE;
      const cardGap = 10 * SCALE;
      const profileCardsHeight = resolvedProfileCards.length
        ? cardRows * cardH + (cardRows - 1) * cardGap + 14 * SCALE
        : 0;

      // ── full-width stats + footnote ──
      const statFont = `650 ${12 * SCALE}px ${CHART_FONT_FAMILY}`;
      const statLineHeight = 19 * SCALE;
      const statTextLines: string[] = resolvedStatLines.flatMap((raw) => wrapText(raw, statFont, contentW));
      const statsHeight = statTextLines.length ? statTextLines.length * statLineHeight + 10 * SCALE : 0;
      const footnoteFont = `500 ${11 * SCALE}px ${CHART_FONT_FAMILY}`;
      const footnoteLineHeight = 16 * SCALE;
      const footnoteLines = footnote ? wrapText(footnote, footnoteFont, contentW) : [];
      const footnoteHeight = footnoteLines.length ? footnoteLines.length * footnoteLineHeight + 10 * SCALE : 0;
      const footerHeight = 26 * SCALE;

      // Remaining vertical budget for the chart rows.
      const rowSpacing = rowCount > 1 ? 14 * SCALE : 0;
      const chartAreaTotal = rowCount > 0 ? Math.max(
        120 * SCALE,
        height - margin * 2 - headerBlockH - chartHeaderH * rowCount - colStatsHeight - breakdownHeight - profileCardsHeight - statsHeight - footnoteHeight - footerHeight - 24 * SCALE - rowSpacing * (rowCount - 1)
      ) : 0;
      const chartAreaH = rowCount > 0 ? chartAreaTotal / rowCount : 0;

      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      ctx.fillStyle = background;
      ctx.fillRect(0, 0, width, height);

      // ── header ──
      let cursorY = margin;
      let titleX = margin;
      const titleBaseline = cursorY + titleRowH / 2 + 9 * SCALE;
      const focusTeam = resolvedFilters[0] ?? "";
      const headshotRing =
        match && focusTeam && focusTeam === match.home && match.homeColor
          ? match.homeColor
          : match && focusTeam && focusTeam === match.away && match.awayColor
            ? match.awayColor
            : accentColor;
      for (const shot of validHeadshots.slice(0, 3)) {
        drawCircularImage(ctx, shot, titleX, cursorY + (titleRowH - headshotSize) / 2, headshotSize, headshotRing, 3 * SCALE);
        titleX += headshotSize + 12 * SCALE;
      }
      ctx.fillStyle = textColor;
      ctx.font = `800 ${36 * SCALE}px ${CHART_FONT_FAMILY}`;
      ctx.fillText(displayTitle, titleX, titleBaseline);
      if (brandImg) {
        const logoSize = 86 * SCALE;
        ctx.drawImage(brandImg, width - margin - logoSize, cursorY + (titleRowH - logoSize) / 2, logoSize, logoSize);
      }
      cursorY += titleRowH;

      if (match) {
        cursorY += matchRowH - 8 * SCALE;
        let x = margin;
        const logoSize = 34 * SCALE;
        if (homeLogo) {
          ctx.drawImage(homeLogo, x, cursorY - logoSize + 5 * SCALE, logoSize, logoSize);
          x += logoSize + 7 * SCALE;
        }
        ctx.fillStyle = mutedColor;
        ctx.font = `700 ${17 * SCALE}px ${CHART_FONT_FAMILY}`;
        const scorePart = match.score ? ` ${match.score} ` : " vs ";
        const homeAway = `${match.home}${scorePart}${match.away}`;
        ctx.fillText(homeAway, x, cursorY);
        x += ctx.measureText(homeAway).width + 7 * SCALE;
        if (awayLogo) {
          ctx.drawImage(awayLogo, x, cursorY - logoSize + 5 * SCALE, logoSize, logoSize);
          x += logoSize + 7 * SCALE;
        }
        const meta = [match.league, match.dateLabel].filter(Boolean).join(" · ");
        if (meta) {
          ctx.font = `600 ${15 * SCALE}px ${CHART_FONT_FAMILY}`;
          ctx.fillText(`· ${meta}`, x + 2 * SCALE, cursorY);
        }
        cursorY += 8 * SCALE;
      }

      if (resolvedFilters.length) {
        cursorY += chipsRowH - 6 * SCALE;
        let chipX = margin;
        ctx.font = `700 ${12 * SCALE}px ${CHART_FONT_FAMILY}`;
        for (const label of resolvedFilters) {
          const text = label.toUpperCase();
          const textWidth = ctx.measureText(text).width;
          const chipW = textWidth + 20 * SCALE;
          const chipH = 21 * SCALE;
          ctx.strokeStyle = lineColor;
          ctx.fillStyle = "rgba(148,163,184,0.12)";
          ctx.beginPath();
          ctx.roundRect(chipX, cursorY - chipH + 4 * SCALE, chipW, chipH, 9 * SCALE);
          ctx.fill();
          ctx.stroke();
          ctx.fillStyle = mutedColor;
          ctx.fillText(text, chipX + 9 * SCALE, cursorY);
          chipX += chipW + 8 * SCALE;
        }
        cursorY += 6 * SCALE;
      }

      // Divider under the header.
      const headerBottom = margin + headerBlockH;
      ctx.strokeStyle = lineColor;
      ctx.beginPath();
      ctx.moveTo(margin, headerBottom - 4 * SCALE);
      ctx.lineTo(width - margin, headerBottom - 4 * SCALE);
      ctx.stroke();

      // ── chart grid (rows × columns) ──
      const gridTop = headerBottom + 8 * SCALE;
      const rowTops: number[] = [];
      {
        let y = gridTop;
        for (let row = 0; row < rowCount; row += 1) {
          rowTops.push(y);
          y += chartHeaderH + chartAreaH + rowPanelHeights[row] + rowSpacing;
        }
      }
      charts.forEach((img, index) => {
        const row = Math.floor(index / perRow);
        const col = index % perRow;
        const colX = margin + col * (colWidth + gap);
        const chartHeaderTop = rowTops[row];
        const chartsTop = chartHeaderTop + chartHeaderH;
        // All charts share the same height budget so pitches render equal-sized
        // regardless of how tall each column's stat panel is.
        const columnChartH = chartAreaH;
        const rowProfile = resolvedChartRowProfiles[row];
        if (col === 0 && rowProfile) {
          const profileY = chartHeaderTop + 5 * SCALE;
          const avatarSize = 34 * SCALE;
          const profileImage = chartRowProfileImages[row];
          if (profileImage) {
            drawCircularImage(
              ctx,
              profileImage,
              margin,
              profileY,
              avatarSize,
              rowProfile.color ?? accentColor,
              2 * SCALE
            );
          }
          const profileX = margin + (profileImage ? avatarSize + 10 * SCALE : 0);
          ctx.fillStyle = textColor;
          ctx.font = `800 ${16 * SCALE}px ${CHART_FONT_FAMILY}`;
          ctx.fillText(rowProfile.name, profileX, profileY + 15 * SCALE);
          if (rowProfile.sub) {
            ctx.fillStyle = mutedColor;
            ctx.font = `700 ${10 * SCALE}px ${CHART_FONT_FAMILY}`;
            ctx.fillText(rowProfile.sub.toUpperCase(), profileX, profileY + 31 * SCALE);
          }
          ctx.strokeStyle = lineColor;
          ctx.beginPath();
          ctx.moveTo(margin, chartHeaderTop + rowProfileH - 4 * SCALE);
          ctx.lineTo(margin + chartsW, chartHeaderTop + rowProfileH - 4 * SCALE);
          ctx.stroke();
        }
        const label = resolvedChartLabels[index];
        if (label) {
          ctx.fillStyle = textColor;
          ctx.font = `800 ${17 * SCALE}px ${CHART_FONT_FAMILY}`;
          const labelWidth = ctx.measureText(label).width;
          ctx.fillText(
            label,
            colX + Math.max(0, (colWidth - labelWidth) / 2),
            chartHeaderTop + rowProfileH + 17 * SCALE
          );
        }
        const subtitle = resolvedChartSubtitles[index];
        if (subtitle) {
          ctx.fillStyle = mutedColor;
          ctx.font = `600 ${12 * SCALE}px ${CHART_FONT_FAMILY}`;
          const subtitleWidth = ctx.measureText(subtitle).width;
          ctx.fillText(
            subtitle,
            colX + Math.max(0, (colWidth - subtitleWidth) / 2),
            chartHeaderTop + rowProfileH + (hasChartLabels ? 30 : 0) * SCALE + 13 * SCALE
          );
        }
        // Scale the captured chart to fit its column and its own height budget.
        const legendItems = columnLegends[index];
        const legendW = columnLegendWidths[index];
        const availableW = colWidth - (legendItems.length ? legendW + 6 * SCALE : 0);
        const scale = Math.min(availableW / img.width, columnChartH / img.height);
        const drawW = img.width * scale;
        const drawH = img.height * scale;
        const chartDrawX = legendItems.length ? colX : colX + (colWidth - drawW) / 2;
        ctx.drawImage(img, chartDrawX, chartsTop, drawW, drawH);
        if (legendItems.length) {
          let legendY = chartsTop + 10 * SCALE;
          // Tuck the legend against the pitch (the captured image carries its own
          // internal padding, so a slight overlap reads as "next to" the pitch).
          const legendX = chartDrawX + drawW - 22 * SCALE;
          for (const item of legendItems) {
            ctx.fillStyle = item.color;
            ctx.strokeStyle = item.color;
            if (item.shape === "line") {
              ctx.lineWidth = 1.8 * SCALE;
              ctx.beginPath();
              ctx.moveTo(legendX, legendY + 4.5 * SCALE);
              ctx.lineTo(legendX + 10 * SCALE, legendY + 4.5 * SCALE);
              ctx.stroke();
              ctx.lineWidth = 1;
            } else if (item.shape === "square") {
              ctx.fillRect(legendX + 1 * SCALE, legendY + 1 * SCALE, 7 * SCALE, 7 * SCALE);
            } else if (item.shape === "ring") {
              ctx.lineWidth = 1.8 * SCALE;
              ctx.beginPath();
              ctx.arc(legendX + 5 * SCALE, legendY + 4.5 * SCALE, 3.4 * SCALE, 0, Math.PI * 2);
              ctx.stroke();
              ctx.lineWidth = 1;
            } else {
              ctx.beginPath();
              ctx.arc(legendX + 5 * SCALE, legendY + 4.5 * SCALE, 3.4 * SCALE, 0, Math.PI * 2);
              ctx.fill();
            }
            ctx.fillStyle = mutedColor;
            ctx.font = legendFont;
            ctx.fillText(item.label, legendX + 14 * SCALE, legendY + 8 * SCALE);
            legendY += legendItemH;
          }
        }

        // The stat panel attaches directly under this column's chart.
        const colStatsTop = chartsTop + drawH + 18 * SCALE;
        const panelLayout = columnPanels[index];
        const colLines = columnStatLines[index] ?? [];
        if (panelLayout || colLines.length) {
          ctx.strokeStyle = lineColor;
          ctx.beginPath();
          ctx.moveTo(colX, colStatsTop - 10 * SCALE);
          ctx.lineTo(colX + colWidth, colStatsTop - 10 * SCALE);
          ctx.stroke();
        }
        if (panelLayout) {
          for (const op of panelLayout.ops) {
            if (op.kind === "title") {
              ctx.fillStyle = mutedColor;
              ctx.font = groupTitleFont;
              ctx.fillText(op.text, colX + op.x, colStatsTop + op.y);
            } else if (op.kind === "chip") {
              const chipX = colX + op.x;
              const chipY = colStatsTop + op.y;
              ctx.fillStyle = op.active ? "rgba(74,222,128,0.14)" : "rgba(148,163,184,0.10)";
              ctx.strokeStyle = op.active ? accentColor : lineColor;
              ctx.beginPath();
              ctx.roundRect(chipX, chipY, op.w, op.h, 5.5 * SCALE);
              ctx.fill();
              ctx.stroke();
              ctx.fillStyle = mutedColor;
              ctx.font = chipLabelFont;
              ctx.fillText(op.label.toUpperCase(), chipX + 6.5 * SCALE, chipY + op.h / 2 + 2.5 * SCALE);
              const labelW = ctx.measureText(op.label.toUpperCase()).width;
              ctx.fillStyle = op.active ? accentColor : textColor;
              ctx.font = chipValueFont;
              ctx.fillText(op.value, chipX + 6.5 * SCALE + labelW + 5 * SCALE, chipY + op.h / 2 + 3 * SCALE);
            } else {
              const legendX = colX + op.x;
              const legendY = colStatsTop + op.y;
              const { item } = op;
              ctx.fillStyle = item.color;
              ctx.strokeStyle = item.color;
              if (item.shape === "line") {
                ctx.lineWidth = 1.8 * SCALE;
                ctx.beginPath();
                ctx.moveTo(legendX, legendY + 4 * SCALE);
                ctx.lineTo(legendX + 9 * SCALE, legendY + 4 * SCALE);
                ctx.stroke();
                ctx.lineWidth = 1;
              } else if (item.shape === "square") {
                ctx.fillRect(legendX + 1 * SCALE, legendY + 1 * SCALE, 6 * SCALE, 6 * SCALE);
              } else if (item.shape === "ring") {
                ctx.lineWidth = 1.6 * SCALE;
                ctx.beginPath();
                ctx.arc(legendX + 4.5 * SCALE, legendY + 4 * SCALE, 3 * SCALE, 0, Math.PI * 2);
                ctx.stroke();
                ctx.lineWidth = 1;
              } else {
                ctx.beginPath();
                ctx.arc(legendX + 4.5 * SCALE, legendY + 4 * SCALE, 3 * SCALE, 0, Math.PI * 2);
                ctx.fill();
              }
              ctx.fillStyle = mutedColor;
              ctx.font = legendFont;
              ctx.fillText(item.label, legendX + 12.5 * SCALE, legendY + 6.5 * SCALE);
            }
          }
        } else if (colLines.length) {
          ctx.fillStyle = textColor;
          ctx.font = colStatFont;
          let colY = colStatsTop + 6 * SCALE;
          for (const line of colLines) {
            ctx.fillText(line, colX + 4 * SCALE, colY);
            colY += colLineH;
          }
        }
      });

      // ── right-hand side table panel ──
      if (hasSideTable && resolvedSideTable) {
        const large = Boolean(resolvedSideTable.large);
        const f = large ? 1.35 : 1;
        const panelX = hasCharts ? margin + chartsW + sideGap : margin;
        const panelTop = gridTop + 4 * SCALE;
        const panelBottom = height - margin - footerHeight;
        const padX = 18 * SCALE;
        const innerW = sideTableW - padX * 2;
        const textX = panelX + padX;
        const rightX = panelX + sideTableW - padX;
        ctx.fillStyle = "rgba(148,163,184,0.06)";
        ctx.strokeStyle = lineColor;
        ctx.beginPath();
        ctx.roundRect(panelX, panelTop, sideTableW, panelBottom - panelTop, 10 * SCALE);
        ctx.fill();
        ctx.stroke();
        const sideFont = (weight: number, size: number) => `${weight} ${size * SCALE}px ${CHART_FONT_FAMILY}`;
        const titleSize = 12 * f;
        const headerSize = 13 * f;
        const labelSize = 11 * f;
        const valueSize = 12.5 * f;
        const subSize = 10.5 * f;
        const rowGap = (large ? 13 : 8) * SCALE;
        let y = panelTop + 20 * SCALE; // top cursor (baseline = top + font size)
        let imageRowIndex = 0;
        if (resolvedSideTable.title) {
          ctx.fillStyle = accentColor;
          ctx.font = sideFont(800, titleSize);
          ctx.fillText(resolvedSideTable.title.toUpperCase(), textX, y + titleSize * SCALE);
          y += titleSize * SCALE + 11 * SCALE;
          ctx.strokeStyle = lineColor;
          ctx.beginPath();
          ctx.moveTo(textX, y);
          ctx.lineTo(rightX, y);
          ctx.stroke();
          y += 10 * SCALE;
        }
        for (let rowIndex = 0; rowIndex < resolvedSideTable.rows.length; rowIndex += 1) {
          const row = resolvedSideTable.rows[rowIndex];
          if (y > panelBottom - 26 * SCALE) break;
          if (row.header) {
            if (rowIndex > 0) {
              y += 7 * SCALE;
              ctx.strokeStyle = lineColor;
              ctx.beginPath();
              ctx.moveTo(textX, y);
              ctx.lineTo(rightX, y);
              ctx.stroke();
              y += 10 * SCALE;
            }
            ctx.fillStyle = textColor;
            ctx.font = sideFont(800, headerSize);
            for (const line of wrapText(row.header, sideFont(800, headerSize), innerW)) {
              ctx.fillText(line, textX, y + headerSize * SCALE);
              y += (headerSize + 7) * SCALE;
            }
            y += 3 * SCALE;
            imageRowIndex = 0;
            continue;
          }
          if (row.image !== undefined) {
            const imgSize = (large ? 40 : 32) * SCALE;
            const subLines = row.sub ? wrapText(row.sub, sideFont(600, subSize), innerW - imgSize - 12 * SCALE) : [];
            const textH = valueSize * SCALE + subLines.length * (subSize + 4.5) * SCALE;
            const rowH = Math.max(imgSize, textH) + 10 * SCALE;
            if (imageRowIndex % 2 === 0) {
              ctx.fillStyle = "rgba(148,163,184,0.08)";
              ctx.fillRect(panelX + 8 * SCALE, y, sideTableW - 16 * SCALE, rowH);
            }
            const img = sideTableImages[rowIndex];
            if (img) {
              drawCircularImage(ctx, img, textX, y + (rowH - imgSize) / 2, imgSize, headshotRing, 2 * SCALE);
            }
            const nameX = textX + imgSize + 10 * SCALE;
            const contentTop = y + (rowH - textH) / 2;
            ctx.fillStyle = textColor;
            ctx.font = sideFont(800, valueSize);
            ctx.fillText(row.label ?? "", nameX, contentTop + valueSize * SCALE);
            if (row.value) {
              const valueW = ctx.measureText(row.value).width;
              ctx.fillText(row.value, rightX - valueW, contentTop + valueSize * SCALE);
            }
            ctx.fillStyle = mutedColor;
            ctx.font = sideFont(600, subSize);
            let subY = contentTop + valueSize * SCALE + (subSize + 4.5) * SCALE;
            for (const line of subLines) {
              ctx.fillText(line, nameX, subY);
              subY += (subSize + 4.5) * SCALE;
            }
            y += rowH + 4 * SCALE;
            imageRowIndex += 1;
            continue;
          }
          const label = (row.label ?? "").toUpperCase();
          const value = row.value ?? "";
          ctx.font = sideFont(700, labelSize);
          const labelW = ctx.measureText(label).width;
          ctx.font = sideFont(700, valueSize);
          const valueW = ctx.measureText(value).width;
          if (labelW + valueW + 16 * SCALE <= innerW) {
            ctx.fillStyle = mutedColor;
            ctx.font = sideFont(700, labelSize);
            ctx.fillText(label, textX, y + valueSize * SCALE);
            ctx.fillStyle = textColor;
            ctx.font = sideFont(700, valueSize);
            ctx.fillText(value, rightX - valueW, y + valueSize * SCALE);
            y += valueSize * SCALE + rowGap;
          } else {
            ctx.fillStyle = mutedColor;
            ctx.font = sideFont(700, labelSize);
            ctx.fillText(label, textX, y + labelSize * SCALE);
            y += (labelSize + 6) * SCALE;
            ctx.fillStyle = textColor;
            ctx.font = sideFont(700, valueSize);
            for (const line of wrapText(value, sideFont(700, valueSize), innerW - 8 * SCALE)) {
              if (y > panelBottom - 18 * SCALE) break;
              ctx.fillText(line, textX + 8 * SCALE, y + valueSize * SCALE);
              y += (valueSize + 5) * SCALE;
            }
            y += rowGap - 4 * SCALE;
          }
        }
      }

      // ── profile card grid (under the charts, in-app card format) ──
      const lastRowBottom = rowTops[rowCount - 1] + chartHeaderH + chartAreaH + rowPanelHeights[rowCount - 1];
      if (resolvedProfileCards.length) {
        const cardsTop = lastRowBottom + 8 * SCALE;
        const cardW = (chartsW - cardGap * (cardCols - 1)) / cardCols;
        const pad = 12 * SCALE;
        resolvedProfileCards.forEach((card, index) => {
          const cardX = margin + (index % cardCols) * (cardW + cardGap);
          const cardY = cardsTop + Math.floor(index / cardCols) * (cardH + cardGap);
          ctx.fillStyle = "rgba(148,163,184,0.07)";
          ctx.strokeStyle = lineColor;
          ctx.beginPath();
          ctx.roundRect(cardX, cardY, cardW, cardH, 8 * SCALE);
          ctx.fill();
          ctx.stroke();
          ctx.fillStyle = textColor;
          ctx.font = `800 ${13 * SCALE}px ${CHART_FONT_FAMILY}`;
          ctx.fillText(card.name, cardX + pad, cardY + 19 * SCALE);
          const scoreText = String(Math.round(card.score));
          ctx.fillStyle = accentColor;
          ctx.font = `800 ${15 * SCALE}px ${CHART_FONT_FAMILY}`;
          ctx.fillText(scoreText, cardX + cardW - pad - ctx.measureText(scoreText).width, cardY + 19 * SCALE);
          const barY = cardY + 26 * SCALE;
          const barW = cardW - pad * 2;
          ctx.fillStyle = "rgba(148,163,184,0.18)";
          ctx.beginPath();
          ctx.roundRect(cardX + pad, barY, barW, 5 * SCALE, 3 * SCALE);
          ctx.fill();
          ctx.fillStyle = accentColor;
          ctx.beginPath();
          ctx.roundRect(cardX + pad, barY, barW * (Math.max(0, Math.min(100, card.score)) / 100), 5 * SCALE, 3 * SCALE);
          ctx.fill();
          ctx.fillStyle = mutedColor;
          ctx.font = `600 ${9.5 * SCALE}px ${CHART_FONT_FAMILY}`;
          const truncate = (raw: string) => {
            if (ctx.measureText(raw).width <= barW) return raw;
            let text = raw;
            while (text.length > 1 && ctx.measureText(`${text}…`).width > barW) text = text.slice(0, -2);
            return `${text}…`;
          };
          if (card.description) ctx.fillText(truncate(card.description), cardX + pad, barY + 16 * SCALE);
          if (card.detail) ctx.fillText(truncate(card.detail), cardX + pad, barY + 28 * SCALE);
        });
      }

      // ── per-pitch breakdown tables (aligned under their own column) ──
      const breakdownTop = lastRowBottom + (profileCardsHeight ? profileCardsHeight + 4 * SCALE : 0) + 10 * SCALE;
      if (columnTables.some(Boolean)) {
        columnTables.forEach((table, index) => {
          if (!table) return;
          const colX = margin + index * (colWidth + gap);
          ctx.strokeStyle = lineColor;
          ctx.strokeRect(colX, breakdownTop, colWidth, table.height);
          for (const op of table.ops) {
            if (op.kind === "bg") {
              ctx.fillStyle = "rgba(148,163,184,0.07)";
              ctx.fillRect(colX + op.x, breakdownTop + op.y, op.w, op.h);
            } else if (op.kind === "line") {
              ctx.strokeStyle = "rgba(148,163,184,0.16)";
              ctx.beginPath();
              ctx.moveTo(colX + op.x1, breakdownTop + op.y1);
              ctx.lineTo(colX + op.x2, breakdownTop + op.y2);
              ctx.stroke();
            } else if (op.kind === "rowTitle") {
              ctx.fillStyle = mutedColor;
              ctx.font = tableTitleFont;
              ctx.fillText(op.text, colX + op.x, breakdownTop + op.y);
            } else if (op.kind === "cellLabel") {
              ctx.fillStyle = mutedColor;
              ctx.font = tableLabelFont;
              ctx.fillText(op.text, colX + op.x, breakdownTop + op.y);
            } else {
              ctx.fillStyle = textColor;
              ctx.font = tableValueFont;
              ctx.fillText(op.text, colX + op.x, breakdownTop + op.y);
            }
          }
        });
      }

      // ── full-width stats + footnote + footer ──
      const belowColumns = breakdownTop + (breakdownHeight ? breakdownHeight - 14 * SCALE : 0) + 6 * SCALE;
      if (statTextLines.length) {
        ctx.fillStyle = textColor;
        ctx.font = statFont;
        let lineY = belowColumns + 12 * SCALE;
        for (const line of statTextLines) {
          ctx.fillText(line, margin, lineY);
          lineY += statLineHeight;
        }
      }
      if (footnoteLines.length) {
        ctx.fillStyle = mutedColor;
        ctx.font = footnoteFont;
        let lineY = belowColumns + statsHeight + 13 * SCALE;
        for (const line of footnoteLines) {
          ctx.fillText(line, margin, lineY);
          lineY += footnoteLineHeight;
        }
      }

      const footerY = height - margin + 8 * SCALE;
      ctx.fillStyle = mutedColor;
      ctx.font = `600 ${11 * SCALE}px ${CHART_FONT_FAMILY}`;
      ctx.fillText("Generated with PlayBack90", margin, footerY);
      const rightText = new Date().toISOString().slice(0, 10);
      ctx.fillText(rightText, width - margin - ctx.measureText(rightText).width, footerY);

      setPreview(canvas.toDataURL("image/png"));
      capture("share_export_opened", { filename });
    } catch {
      // Export is best-effort; leave the chart untouched on failure.
    } finally {
      setBusy(false);
    }
  };

  const download = () => {
    if (!preview) return;
    const link = document.createElement("a");
    link.href = preview;
    link.download = cleanName;
    link.click();
    capture("share_export_downloaded", { filename });
    setPreview(null);
  };

  return (
    <>
      <button
        ref={anchorRef}
        type="button"
        className="png-download-button"
        onClick={buildPreview}
        disabled={busy}
        aria-label="Share this visual as an image"
        title="Share as image"
      >
        <span className="png-download-button-glow" aria-hidden="true" />
        <Share2 aria-hidden="true" size={15} strokeWidth={2.4} />
        <span>{busy ? "Preparing…" : "Share"}</span>
      </button>
      {preview && typeof document !== "undefined"
        ? createPortal(
            <div className="png-preview-overlay" role="dialog" aria-modal="true" aria-label="Export preview" onClick={() => setPreview(null)}>
              <div className="png-preview-dialog" onClick={(event) => event.stopPropagation()}>
                <div className="png-preview-head">
                  <strong>Share preview</strong>
                  <span className="muted" style={{ fontSize: "0.8rem" }}>{cleanName}</span>
                </div>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={preview} alt="Branded export preview" className="png-preview-image" />
                <div className="png-preview-actions">
                  <button type="button" className="button" onClick={() => setPreview(null)}>Cancel</button>
                  <button type="button" className="button primary" onClick={download}>⤓ Download PNG</button>
                </div>
              </div>
            </div>,
            document.body
          )
        : null}
    </>
  );
}
