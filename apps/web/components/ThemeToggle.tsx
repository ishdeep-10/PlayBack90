"use client";

import { useEffect, useState } from "react";

export function ThemeToggle() {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem("pb90-theme");
    const useDark = stored ? stored === "dark" : true;
    document.documentElement.classList.toggle("dark", useDark);
    setDark(useDark);
  }, []);

  function toggle() {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem("pb90-theme", next ? "dark" : "light");
  }

  return (
    <button className="theme-toggle" onClick={toggle} aria-label="Toggle theme" title={dark ? "Use light theme" : "Use dark theme"}>
      <span className={dark ? "theme-toggle-icon is-sun" : "theme-toggle-icon is-moon"} aria-hidden="true" />
    </button>
  );
}
