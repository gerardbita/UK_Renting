import { useEffect, useState } from "react";
import { ScorePill, ListingBadges } from "./Badges.jsx";
import { initials, minutes, pcm } from "../lib/format.js";

const PAGE = 48;

export default function GalleryView({ listings, targets, selectedIds, onToggleSelect, onOpen, onHover, activeId }) {
  const [limit, setLimit] = useState(PAGE);

  useEffect(() => {
    setLimit(PAGE);
  }, [listings]);

  if (!listings.length) {
    return <div className="empty-state">No listings match these filters.</div>;
  }

  const shown = listings.slice(0, limit);

  return (
    <div className="gallery-wrap">
      <div className="gallery-grid">
        {shown.map((listing) => {
          const selected = selectedIds.includes(listing.id);
          return (
            <article
              key={listing.id}
              className={`gcard${listing.id === activeId ? " is-active" : ""}${selected ? " is-selected" : ""}`}
              onMouseEnter={() => onHover(listing.id)}
              onMouseLeave={() => onHover(null)}
              onClick={() => onOpen(listing.id)}
            >
              <div className="gcard-media">
                {listing.main_image ? (
                  <img src={listing.main_image} alt="" loading="lazy" />
                ) : (
                  <div className="gcard-noimg">{initials(listing.address || listing.title)}</div>
                )}
                <ScorePill value={listing.score} size="sm" />
                <label className="gcard-check" onClick={(event) => event.stopPropagation()}>
                  <input type="checkbox" checked={selected} onChange={() => onToggleSelect(listing.id)} aria-label="Add to compare" />
                </label>
              </div>
              <div className="gcard-body">
                <div className="gcard-price">
                  <strong>{pcm(listing.price_pcm, listing.price_text)}</strong>
                  <span>{listing.bedrooms ?? "—"} bed{listing.bathrooms ? ` · ${listing.bathrooms} bath` : ""}</span>
                </div>
                <p className="gcard-address">{listing.address || listing.title || "Untitled listing"}</p>
                <div className="gcard-commute">
                  {listing.routes.map((route, index) => (
                    <span key={index}>
                      {shortName(route.name, index)} 🚇 {minutes(route.transit_minutes)}
                    </span>
                  ))}
                </div>
                <ListingBadges listing={listing} />
              </div>
            </article>
          );
        })}
      </div>
      {limit < listings.length ? (
        <button type="button" className="btn btn--ghost load-more" onClick={() => setLimit((value) => value + PAGE)}>
          Show more ({listings.length - limit} remaining)
        </button>
      ) : null}
    </div>
  );
}

function shortName(name, index) {
  if (!name) return `T${index + 1}`;
  return name.split(/[\s']/)[0];
}
