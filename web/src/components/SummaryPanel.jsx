import { median, minDefined } from "../lib/scoring.js";

export default function SummaryPanel({ listings, allListings, targets }) {
  const active = listings.filter((listing) => listing.status !== "removed");
  const best = [...listings].sort((a, b) => b.score - a.score).slice(0, 4);
  const medianRent = median(active.map((listing) => listing.price_pcm));
  const targetMedians = targets.map((target, index) => ({
    name: target.name,
    transit: median(active.map((listing) => listing.routes[index]?.transit_minutes)),
    cycle: median(active.map((listing) => listing.routes[index]?.cycling_minutes)),
  }));

  return (
    <aside className="summary-panel" aria-label="Summary">
      <section className="metric-block">
        <h2>Decision view</h2>
        <div className="metric-grid">
          <Metric label="Visible homes" value={listings.length.toLocaleString("en-GB")} />
          <Metric label="Active homes" value={active.length.toLocaleString("en-GB")} />
          <Metric label="Median rent" value={medianRent ? `£${medianRent.toLocaleString("en-GB")}` : "-"} />
          <Metric label="Total tracked" value={allListings.length.toLocaleString("en-GB")} />
        </div>
      </section>

      <section className="target-metrics">
        <h2>Median commute</h2>
        {targetMedians.map((target) => (
          <div className="target-metric" key={target.name}>
            <strong>{target.name}</strong>
            <span>Transit {formatMinutes(target.transit)}</span>
            <span>Cycle {formatMinutes(target.cycle)}</span>
          </div>
        ))}
      </section>

      <section className="shortlist-panel">
        <h2>Best balanced</h2>
        {best.map((listing) => (
          <article key={listing.id} className="mini-result">
            <div>
              <strong>{listing.address || listing.title || "Untitled listing"}</strong>
              <span>{listing.price_text || "Price unavailable"}</span>
            </div>
            <Score value={listing.score} />
          </article>
        ))}
      </section>
    </aside>
  );
}

function Metric({ label, value }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export function Score({ value }) {
  return (
    <div className="score-chip" style={{ "--score": `${value}%` }}>
      <strong>{value}</strong>
      <span>score</span>
    </div>
  );
}

function formatMinutes(value) {
  const number = minDefined(value);
  return number === null ? "-" : `${Math.round(number)} min`;
}
