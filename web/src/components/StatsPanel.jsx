import { Histogram, ScatterPlot } from "./Charts.jsx";
import { ScorePill } from "./Badges.jsx";
import { gbp, minutes, pcm } from "../lib/format.js";
import { median } from "../lib/scoring.js";

export default function StatsPanel({ listings, targets, onOpen, onHover, activeId }) {
  const active = listings.filter((listing) => listing.status === "active");
  const medianRent = median(active.map((l) => l.price_pcm));
  const shortlist = [...listings].sort((a, b) => b.score - a.score).slice(0, 5);

  const scatter = active
    .map((listing) => ({
      id: listing.id,
      x: listing.routes[0]?.transit_minutes,
      y: listing.routes[1]?.transit_minutes,
      score: listing.score,
      label: `${listing.address || listing.title || "Listing"} · ${pcm(listing.price_pcm)}`,
    }))
    .filter((point) => Number.isFinite(Number(point.x)) && Number.isFinite(Number(point.y)));

  const targetMedians = targets.map((target, index) => ({
    name: target.name,
    transit: median(active.map((l) => l.routes[index]?.transit_minutes)),
    cycle: median(active.map((l) => l.routes[index]?.cycling_minutes)),
  }));

  return (
    <aside className="stats-panel" aria-label="Insights">
      <section className="stat-card">
        <h2>Snapshot</h2>
        <div className="stat-grid">
          <Metric label="Visible" value={listings.length.toLocaleString("en-GB")} />
          <Metric label="Active" value={active.length.toLocaleString("en-GB")} />
          <Metric label="Median rent" value={medianRent ? gbp(medianRent) : "—"} />
          <Metric label="Top score" value={shortlist[0]?.score ?? "—"} />
        </div>
      </section>

      <section className="stat-card">
        <h2>Commute balance</h2>
        <p className="stat-hint">Each dot is a home. Closer to the line = fairer for both. Click to open.</p>
        <ScatterPlot
          points={scatter}
          xLabel={short(targets[0]?.name, "Target 1")}
          yLabel={short(targets[1]?.name, "Target 2")}
          onSelect={onOpen}
          selectedId={activeId}
        />
      </section>

      <section className="stat-card">
        <h2>Rent distribution</h2>
        <Histogram values={active.map((l) => l.price_pcm)} format={gbp} />
      </section>

      <section className="stat-card">
        <h2>Median commute</h2>
        {targetMedians.map((target) => (
          <div className="median-row" key={target.name}>
            <strong>{short(target.name, target.name)}</strong>
            <span>🚇 {minutes(target.transit)}</span>
            <span>🚲 {minutes(target.cycle)}</span>
          </div>
        ))}
      </section>

      <section className="stat-card">
        <h2>Best balanced</h2>
        <div className="shortlist">
          {shortlist.map((listing) => (
            <button
              type="button"
              key={listing.id}
              className="shortlist-item"
              onClick={() => onOpen(listing.id)}
              onMouseEnter={() => onHover(listing.id)}
              onMouseLeave={() => onHover(null)}
            >
              <div className="shortlist-thumb">
                {listing.main_image ? <img src={listing.main_image} alt="" loading="lazy" /> : null}
              </div>
              <div className="shortlist-text">
                <strong>{listing.address || listing.title || "Listing"}</strong>
                <span>{pcm(listing.price_pcm, listing.price_text)}</span>
              </div>
              <ScorePill value={listing.score} size="sm" />
            </button>
          ))}
        </div>
      </section>
    </aside>
  );
}

function Metric({ label, value }) {
  return (
    <div className="metric">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function short(name, fallback) {
  if (!name) return fallback;
  return name.length > 14 ? `${name.slice(0, 13)}…` : name;
}
