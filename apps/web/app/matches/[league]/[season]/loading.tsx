import { OrbLoader } from "../../../../components/OrbLoader";

export default function LoadingFixtures() {
  return (
    <div className="stack fixtures-page">
      <section className="fixtures-hero">
        <div className="fixtures-hero-title">
          <div className="skeleton skeleton-logo" />
          <div>
            <div className="skeleton skeleton-kicker" />
            <div className="skeleton skeleton-title" />
            <div className="skeleton skeleton-sub" />
          </div>
        </div>
      </section>
      <div className="skeleton skeleton-round-nav" />
      <section className="matchday-explorer skeleton-matchday-explorer">
        <div className="skeleton skeleton-matchday-map">
          <OrbLoader label="Plotting stadiums" />
        </div>
        <aside className="matchday-fixture-rail">
          <div className="skeleton skeleton-rail-head" />
          <div>
            {Array.from({ length: 8 }).map((_, index) => (
              <div key={index} className="skeleton skeleton-fixture-row" style={{ animationDelay: `${index * 60}ms` }} />
            ))}
          </div>
        </aside>
      </section>
    </div>
  );
}
