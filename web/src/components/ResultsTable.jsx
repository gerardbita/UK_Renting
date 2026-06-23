import { useVirtualList } from "../hooks/useVirtualList.js";
import { ScorePill, FreshBadge } from "./Badges.jsx";
import { initials, minutes, pcm } from "../lib/format.js";

const ROW_HEIGHT = 64;

export default function ResultsTable({
  listings,
  targets,
  selectedIds,
  onToggleSelect,
  onOpen,
  onHover,
  activeId,
}) {
  const { ref, range, totalHeight } = useVirtualList({ count: listings.length, rowHeight: ROW_HEIGHT });
  const visible = listings.slice(range.start, range.end);

  return (
    <div className="table-wrap" style={{ "--targets": targets.length }}>
      <div className="table-head">
        <span />
        <span>Property</span>
        <span className="num">Rent</span>
        <span className="num">Beds</span>
        <span className="num">Size</span>
        {targets.map((target, index) => (
          <span className="num target-col" key={target.name}>
            {shortName(target.name, index)}
            <small>🚇 / 🚲</small>
          </span>
        ))}
        <span className="num">Score</span>
      </div>

      <div className="table-body" ref={ref}>
        {listings.length === 0 ? (
          <div className="empty-state">No listings match these filters.</div>
        ) : (
          <div style={{ height: totalHeight, position: "relative" }}>
            {visible.map((listing, offset) => {
              const index = range.start + offset;
              const selected = selectedIds.includes(listing.id);
              return (
                <article
                  key={listing.id}
                  className={`table-row${listing.id === activeId ? " is-active" : ""}${selected ? " is-selected" : ""}`}
                  style={{ position: "absolute", top: index * ROW_HEIGHT, height: ROW_HEIGHT }}
                  onMouseEnter={() => onHover(listing.id)}
                  onMouseLeave={() => onHover(null)}
                  onClick={() => onOpen(listing.id)}
                >
                  <label className="row-check" onClick={(event) => event.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={selected}
                      onChange={() => onToggleSelect(listing.id)}
                      aria-label="Add to compare"
                    />
                  </label>

                  <div className="row-property">
                    <div className="row-thumb">
                      {listing.main_image ? (
                        <img src={listing.main_image} alt="" loading="lazy" />
                      ) : (
                        <span>{initials(listing.address || listing.title)}</span>
                      )}
                    </div>
                    <div className="row-text">
                      <strong>
                        {listing.address || listing.title || "Untitled listing"}
                        <FreshBadge freshness={listing.freshness} />
                        {listing.let_agreed ? <span className="badge badge--let">Let agreed</span> : null}
                      </strong>
                      <span>
                        {[listing.property_subtype, listing.agent].filter(Boolean).join(" · ") || "Property"}
                      </span>
                    </div>
                  </div>

                  <span className="num rent">{pcm(listing.price_pcm, listing.price_text)}</span>
                  <span className="num">{listing.bedrooms ?? "—"}</span>
                  <span className="num">{listing.size_sqft ? `${listing.size_sqft}` : "—"}</span>

                  {listing.routes.map((route, routeIndex) => (
                    <span className="num target-col" key={`${listing.id}:${routeIndex}`}>
                      <b>{minutes(route.transit_minutes)}</b>
                      <small>{minutes(route.cycling_minutes)}</small>
                    </span>
                  ))}

                  <span className="num score-col">
                    <ScorePill value={listing.score} size="sm" />
                  </span>
                </article>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

function shortName(name, index) {
  if (!name) return `Target ${index + 1}`;
  return name.length > 12 ? `${name.slice(0, 11)}…` : name;
}
