import { LiveScrapeForm } from "../../components/LiveScrapeForm";


export default function LiveScrapePage() {
  return (
    <main className="tool-page">
      <section className="tool-hero">
        <span className="pill">Import Match</span>
        <div className="stack" style={{ gap: 10 }}>
          <h1>Import a match analysis source.</h1>
          <p>Add a WhoScored URL, upload provider JSON, or open an official StatsBomb sample match.</p>
        </div>
      </section>

      <section className="scraper-card">
        <LiveScrapeForm />
      </section>
    </main>
  );
}
