"use client";

import dynamic from "next/dynamic";
import { createElement, useEffect, useRef, useState } from "react";
import type { ComponentType, CSSProperties } from "react";

type PlotlyModule = {
  version?: string;
  react: (...args: unknown[]) => unknown;
  register: (modules: unknown[]) => void;
};
type ModuleWithDefault<T> = T | { default?: T };

let plotlyPromise: Promise<PlotlyModule> | null = null;

function unwrapDefault<T>(mod: ModuleWithDefault<T>): T {
  return ((mod as { default?: T }).default ?? mod) as T;
}

export function getPlotly() {
  if (!plotlyPromise) {
    plotlyPromise = Promise.all([
      import("plotly.js/lib/core"),
      import("plotly.js/lib/scatter"),
      import("plotly.js/lib/bar"),
      import("plotly.js/lib/scatterpolar"),
      import("plotly.js/lib/heatmap"),
      import("plotly.js/lib/histogram2dcontour"),
    ]).then(([coreModule, ...traceModules]) => {
      const plotly = unwrapDefault<PlotlyModule>(coreModule as unknown as ModuleWithDefault<PlotlyModule>);
      if (!plotly?.version || typeof plotly.react !== "function") {
        throw new Error("Plotly failed to load in the browser.");
      }
      plotly.register(traceModules.map((module) => unwrapDefault(module)));
      return plotly;
    });
  }
  return plotlyPromise;
}

// Single shared react-plotly component so every chart reuses one plotly.js load.
const LoadedPlot = dynamic(
  async () => {
    const [factoryModule, plotly] = await Promise.all([import("react-plotly.js/factory"), getPlotly()]);
    const createPlotlyComponent = unwrapDefault<(plotly: PlotlyModule) => ComponentType<Record<string, unknown>>>(
      factoryModule
    );
    return createPlotlyComponent(plotly);
  },
  { ssr: false }
);

// Plotly is expensive to parse and initialise. Load charts shortly before they
// enter the viewport while preserving their layout space during the wait.
export function Plot(props: Record<string, unknown>) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [isNearViewport, setIsNearViewport] = useState(false);

  useEffect(() => {
    const host = hostRef.current;
    if (!host || typeof IntersectionObserver === "undefined") {
      setIsNearViewport(true);
      return;
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        setIsNearViewport(true);
        observer.disconnect();
      },
      { rootMargin: "500px 0px" },
    );
    observer.observe(host);
    return () => observer.disconnect();
  }, []);

  if (isNearViewport) return createElement(LoadedPlot, props);
  return createElement("div", {
    ref: hostRef,
    className: props.className,
    style: props.style as CSSProperties | undefined,
    "aria-hidden": true,
  });
}
