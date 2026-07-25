// Plotly shape builders for a football pitch (105m x 68m coordinate space).

export type PitchShape = Record<string, unknown>;

// Juego de posición zone boundaries used for zone grids and binning.
export const JUEGO_X = [0, 17.5, 35, 52.5, 70, 87.5, 105];
export const JUEGO_Y = [0, 13.6, 24.84, 43.16, 54.4, 68];

export type HorizontalPitchOptions = {
  /** Outer boundary line width (default 2). */
  outerWidth?: number;
  /** Halfway line width (default 1.5). */
  midlineWidth?: number;
  /** Centre circle line width (default 1.2). */
  circleWidth?: number;
  /** Penalty/six-yard box line width (default 1.5). */
  boxWidth?: number;
  /** Draw juego de posición zone lines (default false). */
  zoneLines?: boolean;
  /** Add a transparent fill to the outer rectangle (default false). */
  transparentFill?: boolean;
};

/** Horizontal pitch: 105 wide x 68 tall. */
export function horizontalPitchShapes(lineColor: string, opts: HorizontalPitchOptions = {}): PitchShape[] {
  const {
    outerWidth = 2,
    midlineWidth = 1.5,
    circleWidth = 1.2,
    boxWidth = 1.5,
    zoneLines = false,
    transparentFill = false,
  } = opts;
  const zoneLineShapes = zoneLines
    ? [
        ...JUEGO_X.slice(1, -1).map((x) => ({
          type: "line",
          x0: x,
          y0: 0,
          x1: x,
          y1: 68,
          line: { color: lineColor, width: x === 35 || x === 70 ? 1.35 : 1, dash: x === 35 || x === 70 ? "solid" : "dot" },
        })),
        ...JUEGO_Y.slice(1, -1).map((y) => ({
          type: "line",
          x0: 0,
          y0: y,
          x1: 105,
          y1: y,
          line: { color: lineColor, width: 1, dash: "dot" },
        })),
      ]
    : [];
  return [
    {
      type: "rect",
      x0: 0,
      y0: 0,
      x1: 105,
      y1: 68,
      line: { color: lineColor, width: outerWidth },
      ...(transparentFill ? { fillcolor: "rgba(0,0,0,0)" } : {}),
    },
    { type: "line", x0: 52.5, y0: 0, x1: 52.5, y1: 68, line: { color: lineColor, width: midlineWidth } },
    { type: "circle", x0: 43.35, y0: 24.85, x1: 61.65, y1: 43.15, line: { color: lineColor, width: circleWidth } },
    { type: "rect", x0: 0, y0: 13.84, x1: 16.5, y1: 54.16, line: { color: lineColor, width: boxWidth } },
    { type: "rect", x0: 88.5, y0: 13.84, x1: 105, y1: 54.16, line: { color: lineColor, width: boxWidth } },
    { type: "rect", x0: 0, y0: 24.84, x1: 5.5, y1: 43.16, line: { color: lineColor, width: boxWidth } },
    { type: "rect", x0: 99.5, y0: 24.84, x1: 105, y1: 43.16, line: { color: lineColor, width: boxWidth } },
    ...zoneLineShapes,
  ];
}

/** Vertical pitch: 68 wide x 105 tall. */
export function verticalPitchShapes(lineColor: string): PitchShape[] {
  return [
    { type: "rect", x0: 0, y0: 0, x1: 68, y1: 105, line: { color: lineColor, width: 2 } },
    { type: "line", x0: 0, y0: 52.5, x1: 68, y1: 52.5, line: { color: lineColor, width: 1.4 } },
    { type: "circle", x0: 24.85, y0: 43.35, x1: 43.15, y1: 61.65, line: { color: lineColor, width: 1 } },
    { type: "rect", x0: 13.84, y0: 0, x1: 54.16, y1: 16.5, line: { color: lineColor, width: 1.4 } },
    { type: "rect", x0: 24.84, y0: 0, x1: 43.16, y1: 5.5, line: { color: lineColor, width: 1.4 } },
    { type: "rect", x0: 13.84, y0: 88.5, x1: 54.16, y1: 105, line: { color: lineColor, width: 1.4 } },
    { type: "rect", x0: 24.84, y0: 99.5, x1: 43.16, y1: 105, line: { color: lineColor, width: 1.4 } },
  ];
}
