import "./globals.css";

import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";

import { AuthControls } from "../components/AuthControls";
import { AuthProvider } from "../components/AuthProvider";
import { ThemeToggle } from "../components/ThemeToggle";


export const metadata: Metadata = {
  title: "PlayBack90",
  description: "Hosted football analytics for match review and tactical analysis."
};


export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html:
              "try{var t=localStorage.getItem('pb90-theme');var d=t?t==='dark':true;document.documentElement.classList.toggle('dark',d)}catch(e){document.documentElement.classList.add('dark')}"
          }}
        />
      </head>
      <body suppressHydrationWarning>
        <AuthProvider>
        <header className="site-nav">
          <div className="nav-inner">
            <Link href="/" className="nav-brand">
              <Image src="/logos/PB90.png" alt="PlayBack90" width={32} height={32} style={{ borderRadius: 6 }} />
              <span>PlayBack90</span>
            </Link>
            <nav className="nav-links">
              <Link href="/" className="ghost-button nav-link">Home</Link>
              <span
                className="ghost-button nav-link nav-link-coming-soon"
                role="link"
                aria-disabled="true"
                aria-label="Season Stats, coming soon"
                tabIndex={0}
                data-tooltip="Coming soon"
              >
                Season Stats
              </span>
              <span
                className="ghost-button nav-link nav-link-coming-soon"
                role="link"
                aria-disabled="true"
                aria-label="Opposition Analysis, coming soon"
                tabIndex={0}
                data-tooltip="Coming soon"
              >
                Opposition Analysis
              </span>
              <Link href="/live-scrape" className="ghost-button nav-link">Import Match</Link>
              <ThemeToggle />
              <AuthControls />
            </nav>
          </div>
        </header>
        <div className="container" style={{ paddingTop: 24, paddingBottom: 40 }}>
          {children}
        </div>
        </AuthProvider>
      </body>
    </html>
  );
}
