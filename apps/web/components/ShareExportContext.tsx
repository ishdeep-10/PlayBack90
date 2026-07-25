"use client";

import { createContext, useContext, type ReactNode } from "react";

export type ShareMatchInfo = {
  home: string;
  away: string;
  score?: string;
  league?: string;
  dateLabel?: string;
  homeLogoUrl?: string | null;
  awayLogoUrl?: string | null;
  homeColor?: string;
  awayColor?: string;
};

const ShareExportContext = createContext<ShareMatchInfo | null>(null);

export function ShareExportProvider({ value, children }: { value: ShareMatchInfo; children: ReactNode }) {
  return <ShareExportContext.Provider value={value}>{children}</ShareExportContext.Provider>;
}

export function useShareMatchInfo() {
  return useContext(ShareExportContext);
}
