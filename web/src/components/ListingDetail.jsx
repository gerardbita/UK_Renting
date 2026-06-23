import { useEffect, useState } from "react";
import { Sparkline } from "./Charts.jsx";
import { ListingBadges, ScorePill, sourceLinks } from "./Badges.jsx";
import { directionsUrl, gbp, km, minutes, pcm, shortDate, sourceLabel } from "../lib/format.js";

const BREAKDOWN_LABELS = {
  commute: "Commute",
  imbalance: "Commute balance",
  price: "Rent vs market",
  missing_routes: "Missing routes",
  let_agreed: "Let agreed",
  amenities: "Amenities",
  size: "Floor area",
  freshness: "Freshly listed",
};

export default function ListingDetail({ listing, targets, onClose, onCompare, isComparing }) {
  const [activeImage, setActiveImage] = useState(0);

  useEffect(() => {
    setActiveImage(0);
  }, [listing?.id]);

  useEffect(() => {
    function onKey(event) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  if (!listing) return null;
  const images = listing.images && listing.images.length ? listing.images : listing.main_image ? [listing.main_image] : [];

  return (
    <>
      <div className="overlay" onClick={onClose} />
      <aside className="detail-panel" aria-label="Listing detail">
        <header className="detail-head">
          <div>
            <h2>{listing.address || listing.title || "Untitled listing"}</h2>
            <p>{[listing.property_subtype, listing.title].filter(Boolean).join(" · ") || "Property"}</p>
          </div>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close">✕</button>
        </header>

        <div className="detail-gallery">
          {images.length ? (
            <>
              <img src={images[activeImage]} alt="" loading="lazy" />
              {images.length > 1 ? (
                <div className="thumb-strip">
                  {images.slice(0, 8).map((src, index) => (
                    <button
                      key={src}
                      type="button"
                      className={index === activeImage ? "is-active" : ""}
                      onClick={() => setActiveImage(index)}
                    >
                      <img src={src} alt="" loading="lazy" />
                    </button>
                  ))}
                </div>
              ) : null}
            </>
          ) : (
            <div className="detail-noimage">No photos captured yet</div>
          )}
        </div>

        <div className="detail-headline">
          <div>
            <strong className="detail-price">{pcm(listing.price_pcm, listing.price_text)}</strong>
            <ListingBadges listing={listing} />
          </div>
          <ScorePill value={listing.score} size="lg" />
        </div>

        <div className="detail-facts">
          <Fact label="Beds" value={listing.bedrooms ?? "—"} />
          <Fact label="Baths" value={listing.bathrooms ?? "—"} />
          <Fact label="Size" value={listing.size_sqft ? `${listing.size_sqft} sqft` : "—"} />
          <Fact label="EPC" value={listing.epc_rating || "—"} />
          <Fact label="Deposit" value={listing.deposit_pcm ? gbp(listing.deposit_pcm) : "—"} />
          <Fact label="Available" value={listing.available_date ? shortDate(listing.available_date) : "—"} />
        </div>

        <section className="detail-section">
          <h3>Commute</h3>
          <div className="detail-commutes">
            {listing.routes.map((route, index) => (
              <div className="detail-commute" key={route.name || index}>
                <strong>{route.name || `Target ${index + 1}`}</strong>
                <div className="commute-modes">
                  <span>🚇 {minutes(route.transit_minutes)} <small>{km(route.transit_distance_km)}</small></span>
                  <span>🚲 {minutes(route.cycling_minutes)} <small>{km(route.cycling_distance_km)}</small></span>
                </div>
                {Number.isFinite(Number(listing.latitude)) ? (
                  <div className="commute-links">
                    <a href={directionsUrl(listing, route, "transit")} target="_blank" rel="noreferrer">Transit map</a>
                    <a href={directionsUrl(listing, route, "bicycling")} target="_blank" rel="noreferrer">Cycle map</a>
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </section>

        {listing.price_history && listing.price_history.length > 1 ? (
          <section className="detail-section">
            <h3>Price history</h3>
            <Sparkline points={listing.price_history} width={320} height={64} />
          </section>
        ) : null}

        {listing.score_breakdown && Object.keys(listing.score_breakdown).length ? (
          <section className="detail-section">
            <h3>Why this score</h3>
            <ul className="score-breakdown">
              {Object.entries(listing.score_breakdown)
                .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
                .map(([key, value]) => (
                  <li key={key}>
                    <span>{BREAKDOWN_LABELS[key] || key}</span>
                    <span className={value >= 0 ? "pos" : "neg"}>{value > 0 ? "+" : ""}{value}</span>
                  </li>
                ))}
            </ul>
          </section>
        ) : null}

        {listing.key_features && listing.key_features.length ? (
          <section className="detail-section">
            <h3>Key features</h3>
            <ul className="feature-list">
              {listing.key_features.map((feature) => (
                <li key={feature}>{feature}</li>
              ))}
            </ul>
          </section>
        ) : null}

        {listing.summary ? (
          <section className="detail-section">
            <h3>Description</h3>
            <p className="detail-summary">{listing.summary}</p>
          </section>
        ) : null}

        <footer className="detail-actions">
          <button type="button" className={`btn ${isComparing ? "btn--ghost" : "btn--primary"}`} onClick={() => onCompare(listing.id)}>
            {isComparing ? "In compare" : "Add to compare"}
          </button>
          {sourceLinks(listing).map((source) => (
            <a key={source.url} className="btn btn--source" href={source.url} target="_blank" rel="noreferrer">
              View on {sourceLabel(source.source)} ↗
            </a>
          ))}
        </footer>
      </aside>
    </>
  );
}

function Fact({ label, value }) {
  return (
    <div className="fact">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
