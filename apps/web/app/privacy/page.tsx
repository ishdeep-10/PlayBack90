export const metadata = {
  title: "Privacy | PlayBack90",
  description: "What PlayBack90 collects, why, and who it's shared with.",
};

export default function PrivacyPage() {
  return (
    <main className="stack" style={{ marginTop: 24, maxWidth: 760 }}>
      <section className="card stack">
        <h1>Privacy</h1>
        <p className="muted">Last updated: 7 August 2026</p>

        <p>
          PlayBack90 is an independent football analytics project, not a company with a
          legal department — so treat this as a plain, honest account of what happens with
          your data rather than a formal legal document. If you have questions, reach out
          directly (see Contact below).
        </p>

        <h2>What we collect</h2>
        <ul>
          <li>
            <strong>Account info</strong> — when you sign up, our authentication provider
            (Clerk) collects your email address and manages your login. We don&apos;t see
            or store your password; Clerk handles that.
          </li>
          <li>
            <strong>Usage analytics</strong> — we use PostHog to see which pages and
            features are actually used (page views, button clicks, which analysis tabs get
            opened). This is tied to your account once you&apos;re signed in, not sold or
            shared with advertisers.
          </li>
          <li>
            <strong>Error reports</strong> — if something breaks, Sentry may capture the
            error and the page you were on to help us fix it.
          </li>
          <li>
            <strong>Files you upload</strong> — if you import a Wyscout or StatsBomb JSON
            file, it&apos;s processed in memory to generate your analysis and is not kept
            beyond your session.
          </li>
        </ul>

        <h2>What we don&apos;t do</h2>
        <ul>
          <li>We don&apos;t sell your data to anyone.</li>
          <li>We don&apos;t show ads or share data with advertisers.</li>
          <li>We don&apos;t use your uploaded match files for anything beyond generating your own analysis.</li>
        </ul>

        <h2>Who else touches your data</h2>
        <p>
          Only the infrastructure providers needed to run the app: Clerk (authentication),
          PostHog (analytics), Sentry (error monitoring), Cloudflare (network/CDN — sees
          your IP address as part of normal web traffic, same as any website), and
          Cloudflare R2 (stores match data — not personal data).
        </p>

        <h2>Your account</h2>
        <p>
          You can delete your account at any time from your account settings, which removes
          your Clerk profile. If you&apos;d like your analytics history removed too, contact
          us and we&apos;ll take care of it manually.
        </p>

        <h2>Contact</h2>
        <p>
          Questions or requests: <a href="mailto:ishdeepsinghchadha@gmail.com">ishdeepsinghchadha@gmail.com</a>
        </p>
      </section>
    </main>
  );
}
