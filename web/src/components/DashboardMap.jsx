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
      zoomSnap: 0.25,
      zoomDelta: 0.5,
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
    const focusBounds = [];
    const focusCenter = targetCenter(targets);

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
      focusBounds.push([target.latitude, target.longitude]);
    }

    if (targets.length >= 2) {
      L.polyline(
        targets.map((target) => [target.latitude, target.longitude]),
        {
          color: "#1976d2",
          dashArray: "8 8",
          weight: 3,
          opacity: 0.75,
        },
      ).addTo(layer);
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
      if (focusCenter && distanceKm(focusCenter, [Number(listing.latitude), Number(listing.longitude)]) <= 14.5) {
        focusBounds.push([Number(listing.latitude), Number(listing.longitude)]);
      }
    }

    if (focusCenter) {
      map.setView(focusCenter, map.getSize().x < 700 ? 10.25 : 11.25);
    } else if (focusBounds.length > targets.length) {
      map.fitBounds(focusBounds, { padding: [28, 28], maxZoom: 12 });
    } else if (bounds.length) {
      map.fitBounds(bounds, { padding: [28, 28], maxZoom: 12 });
    }
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
      <div className="map-legend">
        <strong>Balanced Score</strong>
        <div><span>High</span><i /><span>Low</span></div>
        <small>Scores combine rent and route time to both targets.</small>
      </div>
    </section>
  );
}

function scoreColor(score) {
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

function targetCenter(targets) {
  if (!targets.length) return null;
  const total = targets.reduce(
    (accumulator, target) => [
      accumulator[0] + Number(target.latitude),
      accumulator[1] + Number(target.longitude),
    ],
    [0, 0],
  );
  return [total[0] / targets.length, total[1] / targets.length];
}

function distanceKm([latA, lonA], [latB, lonB]) {
  const latKm = (latA - latB) * 111;
  const lonKm = (lonA - lonB) * 69 * Math.cos(((latA + latB) / 2) * (Math.PI / 180));
  return Math.sqrt(latKm * latKm + lonKm * lonKm);
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
