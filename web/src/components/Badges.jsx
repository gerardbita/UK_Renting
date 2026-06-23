import { scoreColor } from "./Charts.jsx";
import { sourceLabel } from "../lib/format.js";

export function ScorePill({ value, size = "md" }) {
  return (
    <span className={`score-pill score-pill--${size}`} style={{ "--score-color": scoreColor(value) }}>
      <strong>{value}</strong>
    </span>
  );
}

export function FreshBadge({ freshness }) {
  if (freshness === "new") return <span className="badge badge--new">New</span>;
  if (freshness === "reduced") return <span className="badge badge--reduced">Reduced</span>;
  return null;
}

export function ListingBadges({ listing }) {
  return (
    <span className="badge-row">
      <FreshBadge freshness={listing.freshness} />
      {listing.let_agreed ? <span className="badge badge--let">Let agreed</span> : null}
      {listing.has_garden ? <span className="badge badge--soft">Garden</span> : null}
      {listing.has_parking ? <span className="badge badge--soft">Parking</span> : null}
      {listing.source_count > 1 ? <span className="badge badge--soft">{listing.source_count} sources</span> : null}
    </span>
  );
}

export function SourcePills({ listing }) {
  const sources = sourceLinks(listing);
  if (!sources.length) return null;
  return (
    <span className="source-pills">
      {sources.map((source) => (
        <a key={source.url} href={source.url} target="_blank" rel="noreferrer" className="source-pill">
          {sourceLabel(source.source)} ↗
        </a>
      ))}
    </span>
  );
}

export function sourceLinks(listing) {
  if (Array.isArray(listing.sources) && listing.sources.length) {
    return listing.sources.filter((source) => source.url);
  }
  return listing.url ? [{ source: listing.source || "source", url: listing.url }] : [];
}
