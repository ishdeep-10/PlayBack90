"use client";

import { useEffect, useState } from "react";

export function AnalysisRouteProgress() {
  const [active, setActive] = useState(false);

  useEffect(() => {
    setActive(false);
    const handleClick = (event: MouseEvent) => {
      const target = event.target as HTMLElement | null;
      const anchor = target?.closest("a");
      if (!anchor) return;
      const href = anchor.getAttribute("href");
      const targetAttr = anchor.getAttribute("target");
      if (!href || href.startsWith("#") || targetAttr === "_blank") return;
      try {
        const nextUrl = new URL(href, window.location.href);
        if (nextUrl.origin !== window.location.origin || nextUrl.href === window.location.href) return;
        setActive(true);
      } catch {
        setActive(true);
      }
    };
    window.addEventListener("click", handleClick, true);
    return () => window.removeEventListener("click", handleClick, true);
  }, []);

  return <div className={`route-progress${active ? " is-active" : ""}`} aria-hidden="true" />;
}
