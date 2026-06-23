import { useEffect } from "react";
import { ScorePill, sourceLinks } from "./Badges.jsx";
import { gbp, km, minutes, pcm, sourceLabel } from "../lib/format.js";

export default function CompareModal({ listings, targets, onClose, onRemove }) {
  useEffect(() => {
    function onKey(event) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  if (!listings.length) return null;

  const rows = [
    { label: "Score", render: (l) => <ScorePill value={l.score} /> },
    { label: "Rent", render: (l) => <strong>{pcm(l.price_pcm, l.price_text)}</strong> },
    { label: "Beds / Baths", render: (l) => `${l.bedrooms ?? "—"} / ${l.bathrooms ?? "—"}` },
    { label: "Size", render: (l) => (l.size_sqft ? `${l.size_sqft} sqft` : "—") },
    { label: "Deposit", render: (l) => (l.deposit_pcm ? gbp(l.deposit_pcm) : "—") },
    ...targets.map((target, index) => ({
      label: `${target.name} 🚇 / 🚲`,
      render: (l) => `${minutes(l.routes[index]?.transit_minutes)} / ${minutes(l.routes[index]?.cycling_minutes)}`,
    })),
    { label: "Distance T1", render: (l) => km(l.routes[0]?.transit_distance_km) || "—" },
    {
      label: "Links",
      render: (l) =>
        sourceLinks(l).map((s) => (
          <a key={s.url} href={s.url} target="_blank" rel="noreferrer" className="mini-link">
            {sourceLabel(s.source)} ↗
          </a>
        )),
    },
  ];

  return (
    <>
      <div className="overlay" onClick={onClose} />
      <div className="compare-modal" role="dialog" aria-label="Compare listings">
        <header className="compare-modal-head">
          <h2>Compare {listings.length} listings</h2>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close">✕</button>
        </header>
        <div className="compare-grid" style={{ "--cols": listings.length }}>
          <div className="compare-col compare-col--labels">
            <div className="compare-card-head">&nbsp;</div>
            {rows.map((row) => (
              <div className="compare-cell compare-cell--label" key={row.label}>{row.label}</div>
            ))}
          </div>
          {listings.map((listing) => (
            <div className="compare-col" key={listing.id}>
              <div className="compare-card-head">
                {listing.main_image ? <img src={listing.main_image} alt="" loading="lazy" /> : <div className="compare-noimg" />}
                <strong>{listing.address || listing.title || "Listing"}</strong>
                <button type="button" className="remove-link" onClick={() => onRemove(listing.id)}>Remove</button>
              </div>
              {rows.map((row) => (
                <div className="compare-cell" key={row.label}>{row.render(listing)}</div>
              ))}
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
