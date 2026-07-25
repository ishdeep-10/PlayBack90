import type { CameraFraming } from "../../../../lib/landing-sequences";

export type Projected = { sx: number; sy: number; scale: number };
export type Projection = (x: number, y: number) => Projected;

// Perspective camera over the Opta 0-100 pitch, drawn directly in canvas 2D so
// text stays upright and marker layering survives (a CSS rotateX on the canvas
// would blur strokes and tilt labels). Pitch length runs horizontally; pitch
// width (y) is the depth axis — y=0 is the far touchline.
export function createProjection(
  camera: CameraFraming,
  width: number,
  height: number,
): Projection {
  const rad = (camera.tiltDeg * Math.PI) / 180;
  const persp = Math.sin(rad) * 0.85;
  const foreshorten = Math.max(Math.cos(rad), 0.4);
  const yaw = ((camera.yawDeg ?? 0) * Math.PI) / 180;
  const cosYaw = Math.cos(yaw);
  const sinYaw = Math.sin(yaw);
  const unit = width / camera.span;
  const [cx, cy] = camera.center;
  const screenCx = width * (0.5 + (camera.screenOffsetX ?? 0));
  // Opta coords are 0-100 on both axes but the real pitch is 105x68m:
  // compress the width axis so proportions match a real pitch.
  const ASPECT = 68 / 105;

  return (x: number, y: number): Projected => {
    let rx = x - cx;
    let ry = (y - cy) * ASPECT;
    if (yaw !== 0) {
      const tx = rx * cosYaw - ry * sinYaw;
      ry = rx * sinYaw + ry * cosYaw;
      rx = tx;
    }
    const depth = -ry; // positive = far side of the pitch
    const k = Math.max(1 + (depth / 70) * persp, 0.45);
    return {
      sx: screenCx + (rx * unit) / k,
      sy: height / 2 - (depth * unit * foreshorten) / k,
      // relative to a reference span of 90 so zooming the camera in
      // (smaller span) genuinely enlarges markers and the ball
      scale: 90 / camera.span / k,
    };
  };
}

export function lerpCamera(
  a: CameraFraming,
  b: CameraFraming,
  t: number,
): CameraFraming {
  const mix = (u: number, v: number) => u + (v - u) * t;
  return {
    center: [mix(a.center[0], b.center[0]), mix(a.center[1], b.center[1])],
    span: mix(a.span, b.span),
    tiltDeg: mix(a.tiltDeg, b.tiltDeg),
    yawDeg: mix(a.yawDeg ?? 0, b.yawDeg ?? 0),
    screenOffsetX: mix(a.screenOffsetX ?? 0, b.screenOffsetX ?? 0),
  };
}
