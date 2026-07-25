"use client";

import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
} from "react";
import type { CameraFraming } from "../../../lib/landing-sequences";
import { PitchRenderer, type ChapterConfig } from "./pitch/renderer";

export type PitchReplayHandle = {
  setChapter: (config: ChapterConfig) => void;
  setProgress: (t: number) => void;
  setCamera: (camera: CameraFraming) => void;
  setDim: (v: number) => void;
  setActive: (active: boolean) => void;
};

type Props = {
  className?: string;
  initialCamera: CameraFraming;
  // "scrub": progress driven externally (GSAP). "auto": loops on an internal
  // clock — used on mobile where chapters autoplay instead of pinning.
  mode?: "scrub" | "auto";
  autoChapter?: ChapterConfig;
  autoDurationMs?: number;
};

export const PitchReplayCanvas = forwardRef<PitchReplayHandle, Props>(
  function PitchReplayCanvas(
    { className, initialCamera, mode = "scrub", autoChapter, autoDurationMs = 9000 },
    ref,
  ) {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const rendererRef = useRef<PitchRenderer | null>(null);
    const activeRef = useRef(mode === "auto");
    const rafRef = useRef(0);

    if (!rendererRef.current) {
      rendererRef.current = new PitchRenderer(initialCamera);
    }

    useImperativeHandle(ref, () => ({
      setChapter: (config) =>
        rendererRef.current?.beginChapter(config, performance.now()),
      setProgress: (t) => rendererRef.current?.setProgress(t),
      setCamera: (camera) => rendererRef.current?.setCamera(camera),
      setDim: (v) => rendererRef.current?.setDim(v),
      setActive: (active) => {
        activeRef.current = active;
      },
    }));

    useEffect(() => {
      const canvas = canvasRef.current;
      const renderer = rendererRef.current;
      if (!canvas || !renderer) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      let width = 0;
      let height = 0;
      const resize = () => {
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        width = canvas.clientWidth;
        height = canvas.clientHeight;
        canvas.width = Math.round(width * dpr);
        canvas.height = Math.round(height * dpr);
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      };
      resize();
      const observer = new ResizeObserver(resize);
      observer.observe(canvas);

      if (mode === "auto" && autoChapter) {
        renderer.beginChapter(autoChapter, performance.now());
      }

      let start = performance.now();
      const loop = (now: number) => {
        rafRef.current = requestAnimationFrame(loop);
        if (!activeRef.current || width === 0) return;
        if (mode === "auto") {
          const t = ((now - start) % autoDurationMs) / autoDurationMs;
          renderer.setProgress(t);
        }
        renderer.draw(ctx, width, height, now);
      };
      rafRef.current = requestAnimationFrame(loop);

      return () => {
        cancelAnimationFrame(rafRef.current);
        observer.disconnect();
      };
    }, [mode, autoChapter, autoDurationMs]);

    return <canvas ref={canvasRef} className={className} aria-hidden="true" />;
  },
);
