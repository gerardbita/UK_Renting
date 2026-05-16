export default function CompareDrawer({ listings, targets, onRemove }) {
  if (listings.length === 0) return null;

  return (
    <aside className="compare-drawer" aria-label="Comparison drawer">
      <div className="compare-heading">
        <div>
          <h2>Compare shortlist</h2>
          <p>{listings.length} selected · route metrics stay side by side.</p>
        </div>
      </div>

      <div className="compare-table" role="table">
        <div className="compare-row compare-row--head" role="row">
          <span>Property</span>
          <span>Rent</span>
          <span>Score</span>
          {targets.map((target, index) => (
            <span key={target.name}>T{index + 1} transit</span>
          ))}
          <span />
        </div>
        {listings.map((listing) => (
          <div className="compare-row" role="row" key={listing.id}>
            <strong>{listing.address || listing.title || "Untitled listing"}</strong>
            <span>{listing.price_text || "-"}</span>
            <span>{listing.score}</span>
            {listing.routes.map((route) => (
              <span key={`${listing.id}:${route.name}`}>{formatRoute(route)}</span>
            ))}
            <button type="button" onClick={() => onRemove(listing.id)}>Remove</button>
          </div>
        ))}
      </div>
    </aside>
  );
}

function formatRoute(route) {
  if (route.transit_minutes == null) return "-";
  const distance = route.transit_distance_km == null ? "" : ` · ${Number(route.transit_distance_km).toFixed(2)} km`;
  return `${Math.round(Number(route.transit_minutes))} min${distance}`;
}
