"use client";

import Link from "next/link";
import type { Route } from "next";
import { useEffect, useRef } from "react";

type AnalysisViewLink = {
  id: string;
  label: string;
  href: string;
};

export function AnalysisViewNav({ links, activeView }: { links: AnalysisViewLink[]; activeView: string }) {
  const navRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const activeLink = navRef.current?.querySelector<HTMLElement>("[aria-current='page']");
    activeLink?.scrollIntoView({ behavior: "instant", block: "nearest", inline: "center" });
  }, [activeView]);

  return (
    <nav ref={navRef} className="tab-bar" aria-label="Analysis views">
      {links.map((link) => (
        <Link
          key={link.id}
          href={link.href as Route}
          prefetch={false}
          aria-current={activeView === link.id ? "page" : undefined}
          className={`tab-link${activeView === link.id ? " active" : ""}`}
        >
          {link.label}
        </Link>
      ))}
    </nav>
  );
}
