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
        <link data-pb90-icon rel="icon" type="image/png" href="/logos/Logo-Dark.png" />
        <script
          dangerouslySetInnerHTML={{
            __html:
              "try{var t=localStorage.getItem('pb90-theme');var d=t?t==='dark':true;document.documentElement.classList.toggle('dark',d);var l=document.querySelector('link[data-pb90-icon]')||document.createElement('link');l.rel='icon';l.type='image/png';l.href=d?'/logos/Logo-Dark.png':'/logos/Logo-Light.png';l.setAttribute('data-pb90-icon','');document.head.appendChild(l)}catch(e){document.documentElement.classList.add('dark')}"
          }}
        />
      </head>
      <body suppressHydrationWarning>
        <AuthProvider>
        <header className="site-nav">
          <div className="nav-inner">
            <Link href="/" className="nav-brand">
              <Image className="nav-brand-logo nav-brand-logo-dark" src="/logos/FLogo-Dark.png" alt="PlayBack90" width={178} height={100} priority />
              <Image className="nav-brand-logo nav-brand-logo-light" src="/logos/FLogo-Light.png" alt="PlayBack90" width={178} height={100} priority />
            </Link>
            <nav className="nav-links">
              <Link href="/" className="ghost-button nav-link">Home</Link>
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
