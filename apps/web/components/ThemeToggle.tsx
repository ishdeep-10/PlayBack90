"use client";

import { useEffect, useState } from "react";

function updateFavicon(dark: boolean) {
  const icon = document.querySelector<HTMLLinkElement>("link[data-pb90-icon]") ?? document.createElement("link");
  icon.rel = "icon";
  icon.type = "image/png";
  icon.href = dark ? "/logos/Logo-Dark.png" : "/logos/Logo-Light.png";
  icon.setAttribute("data-pb90-icon", "");
  document.head.appendChild(icon);
}

export function ThemeToggle() {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem("pb90-theme");
    const useDark = stored ? stored === "dark" : true;
    document.documentElement.classList.toggle("dark", useDark);
    updateFavicon(useDark);
    setDark(useDark);
  }, []);

  function toggle() {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem("pb90-theme", next ? "dark" : "light");
    updateFavicon(next);
  }

  return (
    <button className="theme-toggle" onClick={toggle} aria-label="Toggle theme" title={dark ? "Use light theme" : "Use dark theme"}>
      <span className={dark ? "theme-toggle-icon is-sun" : "theme-toggle-icon is-moon"} aria-hidden="true" />
    </button>
  );
}
