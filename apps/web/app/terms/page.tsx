export const metadata = {
  title: "Terms | PlayBack90",
  description: "The rules for using PlayBack90: what you can do with the analysis, and what you can't.",
};

export default function TermsPage() {
  return (
    <main className="stack" style={{ marginTop: 24, maxWidth: 760 }}>
      <section className="card stack">
        <h1>Terms of use</h1>
        <p className="muted">Last updated: 28 October 2026</p>

        <p>
          PlayBack90 is an independent football analytics project. These terms are the rules
          for using it. By creating an account or using the app you agree to them. If you
          don&apos;t agree, please don&apos;t use it.
        </p>

        <h2>What PlayBack90 is</h2>
        <p>
          A set of football match visuals, tables and written summaries built on event data
          and our own models. It is for your own analysis and enjoyment. It is not betting,
          financial or professional advice, and numbers such as xG, xA and the AI-written
          summaries are estimates that can be wrong.
        </p>

        <h2>Your account</h2>
        <ul>
          <li>Keep your login to yourself. One account is for one person; don&apos;t share or resell access.</li>
          <li>You are responsible for what happens under your account.</li>
          <li>Access may be limited during beta, and we may change, pause or remove features.</li>
        </ul>

        <h2>Paid access</h2>
        <p>
          Some or all of the app may require a paid subscription. Prices, billing periods and
          how to cancel are shown when you subscribe, and the price you accepted stays the
          same for the period you paid for. Refunds are handled as described at checkout
          and as required by law.
        </p>

        <h2>What you can do</h2>
        <ul>
          <li>Use the app for your own analysis, scouting, study and fandom.</li>
          <li>
            Download the images and PDF reports the app offers, and share them (for example
            on social media) as long as you keep the PlayBack90 name and the data credit that
            appear on them.
          </li>
        </ul>

        <h2>What you can&apos;t do</h2>
        <ul>
          <li>
            <strong>Scrape or extract data.</strong> No bots, scripts, crawlers or other
            automated tools to read the app or its API, and no bulk or systematic copying of
            what it shows.
          </li>
          <li>
            <strong>Redistribute data.</strong> Don&apos;t republish, sell, sublicense or
            build a product or dataset from the underlying match data or figures behind the
            visuals, and don&apos;t reconstruct them from what the app sends to your browser.
          </li>
          <li>Don&apos;t get around login, usage limits or other protections, and don&apos;t overload the service.</li>
          <li>Don&apos;t reverse-engineer the app or use it to build a competing data service.</li>
          <li>Don&apos;t upload files you have no right to use, or anything unlawful.</li>
        </ul>
        <p>
          If you break these rules we may limit or suspend your account, with no refund for
          the period affected.
        </p>

        <h2>Data and ownership</h2>
        <p>
          Match data is supplied to PlayBack90 by Dribble (dribble360.com) under licence.
          That licence covers displaying it inside PlayBack90; it does not pass the raw data
          on to users. The visuals, models, summaries, design and code of PlayBack90 belong
          to PlayBack90. Team, player and competition names and logos belong to their
          owners and are used only to identify them.
        </p>
        <p>
          If you upload a match file to analyse, it stays yours. You confirm you are allowed
          to use it, and we use it only to produce your analysis, as described in the{" "}
          <a href="/privacy">privacy page</a>.
        </p>

        <h2>No guarantees</h2>
        <p>
          The app is provided as it is. Data can be late, incomplete or wrong, and the
          service may be unavailable at times. To the fullest extent the law allows,
          PlayBack90 is not liable for losses that come from using it, including decisions
          made on its analysis, and our total liability to you is limited to the amount you
          paid us in the 12 months before the claim.
        </p>

        <h2>Changes and ending</h2>
        <p>
          We may update these terms; the date above shows the latest version, and material
          changes will be announced in the app or by email. Continuing to use the app after
          that means you accept them. You can stop using PlayBack90 and delete your account
          at any time.
        </p>

        <h2>Contact</h2>
        <p>
          Questions: <a href="mailto:ishdeepsinghchadha@gmail.com">ishdeepsinghchadha@gmail.com</a>
        </p>
      </section>
    </main>
  );
}
