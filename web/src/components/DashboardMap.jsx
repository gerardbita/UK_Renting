import { useEffect, useRef } from "react";
import L from "leaflet";

export default function DashboardMap({ listings, targets }) {
  const mapRef = useRef(null);
  const layerRef = useRef(null);

  useEffect(() => {
    if (mapRef.current) return;
    const map = L.map("rental-map", {
      zoomControl: false,
      scrollWheelZoom: false,
    }).setView([51.5074, -0.1278], 11);
    L.control.zoom({ position: "bottomright" }).addTo(map);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap",
    }).addTo(map);
    layerRef.current = L.layerGroup().addTo(map);
    mapRef.current = map;
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    const layer = layerRef.current;
    if (!map || !layer) return;

    layer.clearLayers();
    const bounds = [];

    for (const target of targets) {
      const marker = L.marker([target.latitude, target.longitude], {
        icon: L.divIcon({
          className: "target-marker",
          html: `<span>${escapeHtml(target.name)}</span>`,
          iconSize: [150, 32],
          iconAnchor: [12, 16],
        }),
      }).addTo(layer);
      marker.bindPopup(`<strong>${escapeHtml(target.name)}</strong><br>${target.latitude.toFixed(5)}, ${target.longitude.toFixed(5)}`);
      bounds.push([target.latitude, target.longitude]);
    }

    for (const listing of listings.slice(0, 600)) {
      if (!Number.isFinite(Number(listing.latitude)) || !Number.isFinite(Number(listing.longitude))) continue;
      const marker = L.circleMarker([Number(listing.latitude), Number(listing.longitude)], {
        radius: scoreRadius(listing.score),
        color: scoreColor(listing.score),
        fillColor: scoreColor(listing.score),
        fillOpacity: 0.72,
        weight: 2,
      }).addTo(layer);
      marker.bindPopup(renderPopup(listing));
      bounds.push([Number(listing.latitude), Number(listing.longitude)]);
    }

    if (bounds.length) map.fitBounds(bounds, { padding: [28, 28], maxZoom: 13 });
  }, [listings, targets]);

  return (
    <section className="map-card" aria-label="London rentals map">
      <div className="map-heading">
        <div>
          <h2>London commute map</h2>
          <p>Pins are coloured by balanced score across both destinations.</p>
        </div>
        <span>{Math.min(listings.length, 600).toLocaleString("en-GB")} pins</span>
      </div>
      <div id="rental-map" />
    </section>
  );
}

export function scoreColor(score) {
  if (score >= 78) return "#0d7a49";
  if (score >= 62) return "#5d8f2f";
  if (score >= 45) return "#c58a1b";
  return "#b43b37";
}

function scoreRadius(score) {
  if (score >= 80) return 8;
  if (score >= 60) return 7;
  return 6;
}

function renderPopup(listing) {
  const routes = listing.routes
    .map(
      (route) =>
        `<span>${escapeHtml(route.name)}: transit ${formatMinutes(route.transit_minutes)}, cycle ${formatMinutes(route.cycling_minutes)}</span>`,
    )
    .join("");
  return `
    <div class="map-popup">
      <strong>${escapeHtml(listing.address || listing.title || "Untitled listing")}</strong>
      <span>${escapeHtml(listing.price_text || "Price unavailable")}</span>
      ${routes}
      <a href="${listing.url}" target="_blank" rel="noreferrer">Open Rightmove</a>
    </div>
  `;
}

function formatMinutes(value) {
  return value === null || value === undefined ? "-" : `${Math.round(Number(value))} min`;
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
