"use client";

import { useEffect, useRef, useState } from "react";
import type { CameraFraming } from "../../../lib/landing-sequences";
import { lerpCamera } from "./pitch/projection";
import { useThemeVariant } from "../useThemeVariant";
import { AERIAL_CAMERA, JOURNEY_CHAPTERS } from "./chapters";
import { ChapterOverlay } from "./ChapterOverlay";
import { JourneyHero } from "./JourneyHero";
import {
  PitchReplayCanvas,
  type PitchReplayHandle,
} from "./PitchReplayCanvas";

// Scroll-progress segmentation of the journey (fractions of total scroll).
const HERO_FADE_END = 0.07;
const DESCENT_START = 0.05;
const DESCENT_END = 0.15;
const OUTRO_SPAN = 0.05;
const CHAPTER_SPAN = (1 - DESCENT_END - OUTRO_SPAN) / JOURNEY_CHAPTERS.length;

const clamp01 = (t: number) => Math.max(0, Math.min(1, t));
const easeInOut = (t: number) => t * t * (3 - 2 * t);

type Variant = "full" | "mobile" | "static";

export function LandingJourney() {
  const isDark = useThemeVariant();
  // Start from the poster-backed static variant during SSR/hydration. Starting
  // with the desktop video makes mobile browsers request both video files
  // before the media-query effect can switch variants.
  const [variant, setVariant] = useState<Variant>("static");

  useEffect(() => {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    const coarse = window.matchMedia("(max-width: 768px)");
    const sync = () =>
      setVariant(reduced.matches ? "static" : coarse.matches ? "mobile" : "full");
    sync();
    reduced.addEventListener("change", sync);
    coarse.addEventListener("change", sync);
    return () => {
      reduced.removeEventListener("change", sync);
      coarse.removeEventListener("change", sync);
    };
  }, []);

  if (variant === "static") return <StaticJourney isDark={isDark} />;
  if (variant === "mobile") return <MobileJourney />;
  return <FullJourney />;
}

// --- Full desktop experience: sticky stage + GSAP-scrubbed progress -------

function FullJourney() {
  const rootRef = useRef<HTMLElement>(null);
  const heroRef = useRef<HTMLDivElement>(null);
  const videoWrapRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasWrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<PitchReplayHandle>(null);
  const progressRef = useRef<HTMLDivElement>(null);
  const [activeChapter, setActiveChapter] = useState(-1); // -1 = hero

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    let disposed = false;
    let cleanup: (() => void) | undefined;

    const setup = async () => {
      const [{ gsap }, { ScrollTrigger }] = await Promise.all([
        import("gsap"),
        import("gsap/ScrollTrigger"),
      ]);
      if (disposed) return;
      gsap.registerPlugin(ScrollTrigger);

      let lastChapter = -2;
      const applyProgress = (p: number) => {
        const hero = heroRef.current;
        const videoWrap = videoWrapRef.current;
        const video = videoRef.current;
        const canvasWrap = canvasWrapRef.current;
        const canvas = canvasRef.current;
        const bar = progressRef.current;
        if (!canvas) return;

        if (bar) bar.style.transform = `scaleX(${p})`;

        // keep the site nav hidden until the stadium hero is scrolled through
        document.documentElement.classList.toggle(
          "pbj-hero-active",
          p < DESCENT_END * 0.85,
        );

        // hero copy out
        if (hero) {
          const f = clamp01(p / HERO_FADE_END);
          hero.style.opacity = String(1 - f);
          hero.style.transform = `translateY(${-46 * f}px)`;
          hero.style.pointerEvents = f > 0.6 ? "none" : "";
        }

        // descent: video out, canvas in, camera dives from aerial to chapter 1
        const descent = easeInOut(
          clamp01((p - DESCENT_START) / (DESCENT_END - DESCENT_START)),
        );
        if (videoWrap && video) {
          videoWrap.style.opacity = String(1 - descent);
          videoWrap.style.transform = `scale(${1 + descent * 0.18})`;
          if (descent >= 1 && !video.paused) video.pause();
          else if (descent < 1 && video.paused) void video.play().catch(() => undefined);
        }

        let chapterIndex: number;
        let camera: CameraFraming;
        let outroFade = 0;
        if (p < DESCENT_END) {
          chapterIndex = -1;
          camera = lerpCamera(AERIAL_CAMERA, JOURNEY_CHAPTERS[0].camera, descent);
          canvas.setChapter({
            treatment: JOURNEY_CHAPTERS[0].treatment,
            sequence: JOURNEY_CHAPTERS[0].sequence,
          });
          canvas.setProgress(0);
        } else if (p >= 1 - OUTRO_SPAN) {
          const last = JOURNEY_CHAPTERS[JOURNEY_CHAPTERS.length - 1];
          const local = clamp01((p - (1 - OUTRO_SPAN)) / OUTRO_SPAN);
          chapterIndex = JOURNEY_CHAPTERS.length;
          camera = lerpCamera(last.camera, AERIAL_CAMERA, easeInOut(local));
          canvas.setProgress(1);
          outroFade = local;
        } else {
          const i = Math.min(
            Math.floor((p - DESCENT_END) / CHAPTER_SPAN),
            JOURNEY_CHAPTERS.length - 1,
          );
          const chapter = JOURNEY_CHAPTERS[i];
          const local = clamp01((p - DESCENT_END - i * CHAPTER_SPAN) / CHAPTER_SPAN);
          chapterIndex = i;
          const prevCamera = i === 0 ? chapter.camera : JOURNEY_CHAPTERS[i - 1].camera;
          camera = lerpCamera(prevCamera, chapter.camera, easeInOut(clamp01(local / 0.12)));
          if (chapter.finaleCamera) {
            // dive from broadcast height down to pitch level, following the
            // ball toward the goal over the back stretch of the chapter
            const dive = easeInOut(clamp01((local - 0.56) / 0.24));
            camera = lerpCamera(camera, chapter.finaleCamera, dive);
          }
          canvas.setChapter({ treatment: chapter.treatment, sequence: chapter.sequence });
          canvas.setProgress(clamp01((local - 0.08) / 0.72));
        }
        canvas.setCamera(camera);
        canvas.setDim(0.18 * clamp01(descent) + 0.3 * outroFade);
        if (canvasWrap) canvasWrap.style.opacity = String(descent * (1 - outroFade * 0.5));

        if (chapterIndex !== lastChapter) {
          lastChapter = chapterIndex;
          setActiveChapter(chapterIndex);
        }
      };

      const proxy = { p: 0 };
      const tween = gsap.to(proxy, {
        p: 1,
        ease: "none",
        onUpdate: () => applyProgress(proxy.p),
        scrollTrigger: {
          trigger: root,
          start: "top top",
          end: "bottom bottom",
          scrub: 1,
          onToggle: (self) => {
            canvasRef.current?.setActive(self.isActive);
            const video = videoRef.current;
            if (video && !self.isActive) video.pause();
          },
        },
      });
      applyProgress(0);
      canvasRef.current?.setActive(true);

      cleanup = () => {
        tween.scrollTrigger?.kill();
        tween.kill();
        document.documentElement.classList.remove("pbj-hero-active");
      };
    };

    void setup();
    return () => {
      disposed = true;
      cleanup?.();
    };
  }, []);

  const scrollToProgress = (targetP: number) => {
    const root = rootRef.current;
    if (!root) return;
    const rect = root.getBoundingClientRect();
    const top = window.scrollY + rect.top;
    const distance = root.offsetHeight - window.innerHeight;
    window.scrollTo({ top: top + targetP * distance, behavior: "smooth" });
  };
  const chapterTarget = (i: number) => DESCENT_END + i * CHAPTER_SPAN + CHAPTER_SPAN * 0.55;

  return (
    <section className="pbj" ref={rootRef} aria-label="PlayBack90 match analysis journey">
      <div className="pbj-stage">
        <div className="pbj-video" ref={videoWrapRef} aria-hidden="true">
          <video
            ref={videoRef}
            autoPlay
            loop
            muted
            playsInline
            poster="/media/landing/manchester-stadium-poster.webp"
            preload="metadata"
          >
            <source src="/media/landing/manchester-stadium-hero.m4v" type="video/mp4" />
          </video>
          <span className="pbj-video-credit">Etihad Stadium aerial · Pexels 28165138</span>
        </div>
        <div className="pbj-canvas" ref={canvasWrapRef}>
          <PitchReplayCanvas
            ref={canvasRef}
            className="pbj-canvas-el"
            initialCamera={AERIAL_CAMERA}
          />
        </div>
        <div className="pbj-grade" aria-hidden="true" />

        <JourneyHero ref={heroRef} />

        {JOURNEY_CHAPTERS.map((chapter, index) => (
          <ChapterOverlay
            chapter={chapter}
            index={index}
            active={activeChapter === index}
            key={chapter.key}
          />
        ))}

        <div className="pbj-progress" aria-hidden="true">
          <div className="pbj-progress-bar" ref={progressRef} />
        </div>

        <nav className="pbj-rail" aria-label="Analysis story progress">
          <button
            type="button"
            className={activeChapter === -1 ? "is-active" : ""}
            aria-label="Hero"
            onClick={() => scrollToProgress(0)}
          />
          {JOURNEY_CHAPTERS.map((chapter, index) => (
            <button
              type="button"
              className={activeChapter === index ? "is-active" : ""}
              aria-label={chapter.kicker}
              key={chapter.key}
              onClick={() => scrollToProgress(chapterTarget(index))}
            />
          ))}
        </nav>
      </div>
    </section>
  );
}

// --- Mobile: stacked sections, each replay autoplays when visible ---------

function MobileChapter({
  chapter,
  index,
}: {
  chapter: (typeof JOURNEY_CHAPTERS)[number];
  index: number;
}) {
  const canvasRef = useRef<PitchReplayHandle>(null);
  const sectionRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const section = sectionRef.current;
    if (!section) return;
    canvasRef.current?.setCamera(chapter.camera);
    const observer = new IntersectionObserver(
      ([entry]) => canvasRef.current?.setActive(entry.isIntersecting),
      { threshold: 0.2 },
    );
    observer.observe(section);
    return () => observer.disconnect();
  }, [chapter]);

  return (
    <section className="pbj-m-chapter" ref={sectionRef}>
      <div className="pbj-m-canvas">
        <PitchReplayCanvas
          ref={canvasRef}
          className="pbj-canvas-el"
          initialCamera={chapter.camera}
          mode="auto"
          autoChapter={{ treatment: chapter.treatment, sequence: chapter.sequence }}
        />
      </div>
      <ChapterOverlay chapter={chapter} index={index} active />
    </section>
  );
}

function MobileJourney() {
  return (
    <section className="pbj pbj-mobile" aria-label="PlayBack90 match analysis journey">
      <div className="pbj-m-hero">
        <img
          src="/media/landing/manchester-stadium-poster.webp"
          alt="Aerial view of a football stadium"
          fetchPriority="high"
        />
        <JourneyHero />
      </div>
      {JOURNEY_CHAPTERS.map((chapter, index) => (
        <MobileChapter chapter={chapter} index={index} key={chapter.key} />
      ))}
    </section>
  );
}

// --- Reduced motion: static sections with the existing screenshots --------

function StaticJourney({ isDark }: { isDark: boolean }) {
  return (
    <section className="pbj pbj-static" aria-label="PlayBack90 match analysis journey">
      <div className="pbj-m-hero">
        <img
          src="/media/landing/manchester-stadium-poster.webp"
          alt="Aerial view of a football stadium"
        />
        <JourneyHero />
      </div>
      {JOURNEY_CHAPTERS.map((chapter, index) => (
        <section className="pbj-m-chapter" key={chapter.key}>
          <img
            className="pbj-static-shot"
            src={isDark ? chapter.screenshot.dark : chapter.screenshot.light}
            alt={chapter.screenshot.alt}
            loading={index === 0 ? "eager" : "lazy"}
          />
          <ChapterOverlay chapter={chapter} index={index} active />
        </section>
      ))}
    </section>
  );
}
