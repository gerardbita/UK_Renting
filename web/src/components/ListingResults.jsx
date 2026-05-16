import { Score } from "./SummaryPanel.jsx";

export default function ListingResults({ listings, targets, selectedIds, onToggleSelected }) {
  return (
    <section className="results-panel" aria-label="Ranked listings">
      <div className="results-heading">
        <div>
          <h2>Ranked homes</h2>
          <p>Balanced by rent, amenities, and route time to both destinations.</p>
        </div>
        <span>{listings.length.toLocaleString("en-GB")} results</span>
      </div>

      <div className="listing-table">
        {listings.slice(0, 120).map((listing, index) => (
          <article className="listing-row" key={listing.id}>
            <div className="rank-cell">
              <span>{index + 1}</span>
              <Score value={listing.score} />
            </div>

            <div className="listing-main">
              <h3>{listing.address || listing.title || "Untitled listing"}</h3>
              <p>
                {listing.price_text || "Price unavailable"}
                {listing.bedrooms ? ` · ${listing.bedrooms} bed` : ""}
                {listing.has_garden ? " · Garden/terrace" : ""}
                {listing.has_parking ? " · Parking" : ""}
                {listing.agent ? ` · ${listing.agent}` : ""}
              </p>
              <div className="action-row">
                <a href={listing.url} target="_blank" rel="noreferrer">Rightmove</a>
                {targets.map((target, targetIndex) => (
                  <a
                    key={`${listing.id}:${target.name}:map`}
                    href={directionsUrl(listing, target, "transit")}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Map to {targetIndex + 1}
                  </a>
                ))}
                <button type="button" onClick={() => onToggleSelected(listing.id)}>
                  {selectedIds.includes(listing.id) ? "Remove compare" : "Compare"}
                </button>
              </div>
            </div>

            <div className="route-columns">
              {listing.routes.map((route, routeIndex) => (
                <RouteColumn route={route} index={routeIndex} key={`${listing.id}:${route.name}`} />
              ))}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function RouteColumn({ route, index }) {
  return (
    <div className="route-column">
      <h4>
        <span>{index + 1}</span>
        {route.name}
      </h4>
      <div className="route-values">
        <Metric label="Transit" minutes={route.transit_minutes} distance={route.transit_distance_km} />
        <Metric label="Cycle" minutes={route.cycling_minutes} distance={route.cycling_distance_km} />
      </div>
    </div>
  );
}

function Metric({ label, minutes, distance }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{formatMinutes(minutes)}</strong>
      <small>{formatDistance(distance)}</small>
    </div>
  );
}

function directionsUrl(listing, target, mode) {
  const origin = `${listing.latitude},${listing.longitude}`;
  const destination = `${target.latitude},${target.longitude}`;
  return `https://www.google.com/maps/dir/?api=1&origin=${encodeURIComponent(origin)}&destination=${encodeURIComponent(destination)}&travelmode=${mode}`;
}

function formatMinutes(value) {
  return value === null || value === undefined ? "-" : `${Math.round(Number(value))} min`;
}

function formatDistance(value) {
  return value === null || value === undefined ? "not calculated" : `${Number(value).toFixed(2)} km`;
}
