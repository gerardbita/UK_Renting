import { Score } from "./SummaryPanel.jsx";

export default function ListingResults({ listings, targets, selectedIds, onToggleSelected, updatedAt }) {
  function exportCsv() {
    const header = [
      "rank",
      "address",
      "price_pcm",
      "bedrooms",
      "sources",
      "score",
      ...targets.flatMap((target) => [
        `${target.name} transit minutes`,
        `${target.name} transit km`,
        `${target.name} cycle minutes`,
        `${target.name} cycle km`,
      ]),
      "url",
    ];
    const rows = listings.slice(0, 500).map((listing, index) => [
      index + 1,
      listing.address || listing.title || "",
      listing.price_pcm || "",
      listing.bedrooms || "",
      sourceNames(listing).join(" + "),
      listing.score,
      ...listing.routes.flatMap((route) => [
        route.transit_minutes ?? "",
        route.transit_distance_km ?? "",
        route.cycling_minutes ?? "",
        route.cycling_distance_km ?? "",
      ]),
      listing.url || "",
    ]);
    const csv = [header, ...rows]
      .map((row) => row.map((value) => `"${String(value).replaceAll('"', '""')}"`).join(","))
      .join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "uk-renting-results.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="results-panel" aria-label="Ranked listings">
      <div className="results-heading">
        <div>
          <h2>{listings.length.toLocaleString("en-GB")} results</h2>
          <p>Updated {formatDateTime(updatedAt)}</p>
        </div>
        <div className="results-actions">
          <button type="button">Compare ({selectedIds.length})</button>
          <button type="button" onClick={exportCsv}>Export CSV</button>
        </div>
      </div>

      <div className="listing-table" style={{ "--target-count": targets.length }}>
        <div className="listing-head">
          <span>#</span>
          <span>Property</span>
          <span>Rent</span>
          <span>Beds</span>
          <span>Garden</span>
          <span>Parking</span>
          {targets.map((target, index) => (
            <span className="target-head" key={target.name}>
              <strong>{target.name} (T{index + 1})</strong>
              <small><b>Transit</b><b>Cycle</b></small>
            </span>
          ))}
          <span className="score-head">
            Balanced Score
            <small>0-100</small>
          </span>
          <span>Actions</span>
        </div>
        {listings.slice(0, 50).map((listing, index) => (
          <article className="listing-row" key={listing.id}>
            <div className="rank-cell">
              <input
                type="checkbox"
                checked={selectedIds.includes(listing.id)}
                onChange={() => onToggleSelected(listing.id)}
                aria-label={`Compare ${listing.address || listing.title || "listing"}`}
              />
              <span>{index + 1}</span>
            </div>

            <div className="listing-main">
              <div className="listing-thumb" aria-hidden="true">{initialsFor(listing)}</div>
              <h3>{listing.address || listing.title || "Untitled listing"}</h3>
              <p>
                {sourceNames(listing).join(" + ") || "Property listing"}
                {listing.agent ? ` · ${listing.agent}` : ""}
              </p>
            </div>

            <strong className="rent-cell">{listing.price_text || "-"}</strong>
            <span className="simple-cell">{listing.bedrooms || "-"}</span>
            <span className="bool-cell">{listing.has_garden ? "✓" : "–"}</span>
            <span className="bool-cell">{listing.has_parking ? "✓" : "–"}</span>

            {listing.routes.map((route) => (
              <RouteColumn route={route} key={`${listing.id}:${route.name}`} />
            ))}

            <div className="score-cell">
              <Score value={listing.score} />
              <i style={{ "--score": `${listing.score}%` }} />
            </div>

            <div className="action-row">
              {sourceLinks(listing).map((source) => (
                <a key={`${listing.id}:${source.source}`} href={source.url} target="_blank" rel="noreferrer">
                  {sourceLabel(source.source)}
                </a>
              ))}
              {targets.map((target, targetIndex) => (
                <a
                  key={`${listing.id}:${target.name}:map`}
                  href={directionsUrl(listing, target, "transit")}
                  target="_blank"
                  rel="noreferrer"
                >
                  Map {targetIndex + 1}
                </a>
              ))}
              <button type="button" onClick={() => onToggleSelected(listing.id)}>
                Compare
              </button>
            </div>
          </article>
        ))}
        <footer className="results-footer">
          <span>Showing 1-50 of {listings.length.toLocaleString("en-GB")} results</span>
          <div aria-label="Pagination preview">
            <button type="button" className="is-active">1</button>
            <button type="button">2</button>
            <button type="button">3</button>
            <span>...</span>
            <button type="button">{Math.max(1, Math.ceil(listings.length / 50))}</button>
          </div>
          <label>
            Rows per page
            <span className="rows-select">50</span>
          </label>
        </footer>
      </div>
    </section>
  );
}

function RouteColumn({ route }) {
  return (
    <div className="route-column">
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

function sourceLinks(listing) {
  if (Array.isArray(listing.sources) && listing.sources.length) {
    return listing.sources.filter((source) => source.url);
  }
  return listing.url ? [{ source: listing.source || "source", url: listing.url }] : [];
}

function sourceNames(listing) {
  return sourceLinks(listing).map((source) => sourceLabel(source.source));
}

function sourceLabel(source) {
  const labels = {
    rightmove: "Rightmove",
    zoopla: "Zoopla",
  };
  return labels[source] || String(source || "Source");
}

function formatMinutes(value) {
  return value === null || value === undefined ? "-" : `${Math.round(Number(value))} min`;
}

function formatDistance(value) {
  return value === null || value === undefined ? "not calculated" : `${Number(value).toFixed(2)} km`;
}

function formatDateTime(value) {
  if (!value) return "unknown";
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function initialsFor(listing) {
  const text = listing.address || listing.title || "UK";
  return text
    .split(/[,\s]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}
