import { useEffect, useRef } from "react";
import L from "leaflet";
import { scoreColor } from "./Charts.jsx";
import { pcm } from "../lib/format.js";

const CELL_PX = 56;

export default function DashboardMap({ listings, targets, activeId, onOpen, onHover, fullHeight }) {
  const mapRef = useRef(null);
  const markerLayer = useRef(null);
  const targetLayer = useRef(null);
  const dataRef = useRef({ listings, activeId });
  const markerIndex = useRef(new Map());

  dataRef.current = { listings, activeId };

  useEffect(() => {
    if (mapRef.current) return undefined;
    const map = L.map("rental-map", {
      zoomControl: false,
      scrollWheelZoom: true,
      preferCanvas: true,
      zoomSnap: 0.5,
    }).setView([51.5074, -0.1278], 11);
    L.control.zoom({ position: "bottomright" }).addTo(map);
    L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap &copy; CARTO",
    }).addTo(map);
    targetLayer.current = L.layerGroup().addTo(map);
    markerLayer.current = L.layerGroup().addTo(map);
    mapRef.current = map;

    const rerender = () => renderMarkers();
    map.on("zoomend moveend", rerender);
    return () => {
      map.off("zoomend moveend", rerender);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Targets + initial fit.
  useEffect(() => {
    const map = mapRef.current;
    const layer = targetLayer.current;
    if (!map || !layer) return;
    layer.clearLayers();
    const points = [];
    targets.forEach((target, index) => {
      const marker = L.marker([target.latitude, target.longitude], {
        icon: L.divIcon({
          className: "target-pin",
          html: `<span>${index + 1}</span><b>${escapeHtml(firstWord(target.name))}</b>`,
          iconSize: [120, 26],
          iconAnchor: [13, 13],
        }),
        zIndexOffset: 1000,
      }).addTo(layer);
      marker.bindPopup(`<strong>${escapeHtml(target.name)}</strong>`);
      points.push([target.latitude, target.longitude]);
    });
    if (targets.length >= 2) {
      L.polyline(points, { color: "#60a5fa", weight: 2, dashArray: "6 7", opacity: 0.7 }).addTo(layer);
    }
    const center = points.length
      ? [points.reduce((s, p) => s + p[0], 0) / points.length, points.reduce((s, p) => s + p[1], 0) / points.length]
      : [51.5074, -0.1278];
    map.setView(center, map.getSize().x < 700 ? 10.5 : 11.5);
  }, [targets]);

  // Re-render markers when listings change.
  useEffect(() => {
    renderMarkers();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [listings]);

  // Highlight + pan to the active listing without a full rebuild.
  useEffect(() => {
    renderMarkers();
    const map = mapRef.current;
    if (!map || !activeId) return;
    const target = listings.find((listing) => listing.id === activeId);
    if (target && Number.isFinite(Number(target.latitude))) {
      map.panTo([Number(target.latitude), Number(target.longitude)], { animate: true, duration: 0.4 });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId]);

  function renderMarkers() {
    const map = mapRef.current;
    const layer = markerLayer.current;
    if (!map || !layer) return;
    layer.clearLayers();
    markerIndex.current = new Map();

    const { listings: items, activeId: active } = dataRef.current;
    const located = items.filter(
      (item) => Number.isFinite(Number(item.latitude)) && Number.isFinite(Number(item.longitude)),
    );

    // Grid cluster in screen space at the current zoom.
    const cells = new Map();
    for (const item of located) {
      const point = map.latLngToContainerPoint([Number(item.latitude), Number(item.longitude)]);
      const key = `${Math.floor(point.x / CELL_PX)}:${Math.floor(point.y / CELL_PX)}`;
      if (!cells.has(key)) cells.set(key, []);
      cells.get(key).push(item);
    }

    for (const group of cells.values()) {
      const hasActive = group.some((item) => item.id === active);
      if (group.length === 1 || hasActive) {
        for (const item of group) drawPin(layer, item, item.id === active);
      } else {
        drawCluster(layer, group);
      }
    }
  }

  function drawPin(layer, item, isActive) {
    const marker = L.circleMarker([Number(item.latitude), Number(item.longitude)], {
      radius: isActive ? 10 : 6 + Math.round((item.score || 0) / 25),
      color: isActive ? "#ffffff" : scoreColor(item.score),
      weight: isActive ? 3 : 1.5,
      fillColor: scoreColor(item.score),
      fillOpacity: 0.85,
    }).addTo(layer);
    marker.on("click", () => onOpen(item.id));
    marker.on("mouseover", () => onHover(item.id));
    marker.on("mouseout", () => onHover(null));
    marker.bindTooltip(popupHtml(item), { direction: "top", offset: [0, -6], opacity: 1, className: "map-tip" });
    markerIndex.current.set(item.id, marker);
  }

  function drawCluster(layer, group) {
    const lat = group.reduce((s, i) => s + Number(i.latitude), 0) / group.length;
    const lng = group.reduce((s, i) => s + Number(i.longitude), 0) / group.length;
    const best = Math.max(...group.map((i) => i.score || 0));
    const size = group.length > 50 ? 44 : group.length > 15 ? 38 : 32;
    const marker = L.marker([lat, lng], {
      icon: L.divIcon({
        className: "cluster-pin",
        html: `<span style="--c:${scoreColor(best)}">${group.length}</span>`,
        iconSize: [size, size],
        iconAnchor: [size / 2, size / 2],
      }),
    }).addTo(layer);
    marker.on("click", () => {
      const map = mapRef.current;
      map.setView([lat, lng], Math.min(map.getZoom() + 2, 17));
    });
  }

  return (
    <section className={`map-card${fullHeight ? " map-card--full" : ""}`} aria-label="Map">
      <div className="map-overlay-head">
        <div>
          <h2>Commute map</h2>
          <p>{listings.filter((l) => l.latitude).length.toLocaleString("en-GB")} located · pins by score</p>
        </div>
        <div className="map-legend">
          <i style={{ background: "#34d399" }} /> High
          <i style={{ background: "#fbbf24" }} /> Mid
          <i style={{ background: "#f87171" }} /> Low
        </div>
      </div>
      <div id="rental-map" />
    </section>
  );
}

function popupHtml(item) {
  const photo = item.main_image
    ? `<div class="tip-photo"><img src="${escapeAttr(item.main_image)}" alt=""/></div>`
    : "";
  const routes = (item.routes || [])
    .map((route, index) => `<span>${escapeHtml(firstWord(route.name) || `T${index + 1}`)}: ${route.transit_minutes ?? "—"}m</span>`)
    .join("");
  return `
    <div class="map-tip-card">
      ${photo}
      <strong>${escapeHtml(pcm(item.price_pcm, item.price_text))}</strong>
      <span class="tip-addr">${escapeHtml(item.address || item.title || "Listing")}</span>
      <div class="tip-routes">${routes}</div>
    </div>`;
}

function firstWord(name) {
  return String(name || "").split(/[\s']/)[0];
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll("'", "&#039;");
}
