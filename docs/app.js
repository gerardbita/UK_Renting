const state = {
  listings: [],
  filtered: [],
  routing: {},
  map: null,
  markers: null,
};

const elements = {
  activeCount: document.querySelector("#activeCount"),
  medianTransit: document.querySelector("#medianTransit"),
  medianCycle: document.querySelector("#medianCycle"),
  targetName: document.querySelector("#targetName"),
  targetCoords: document.querySelector("#targetCoords"),
  routeProfile: document.querySelector("#routeProfile"),
  generatedAt: document.querySelector("#generatedAt"),
  searchInput: document.querySelector("#searchInput"),
  maxRent: document.querySelector("#maxRent"),
  maxTransit: document.querySelector("#maxTransit"),
  bedroomsFilter: document.querySelector("#bedroomsFilter"),
  gardenFilter: document.querySelector("#gardenFilter"),
  parkingFilter: document.querySelector("#parkingFilter"),
  sortSelect: document.querySelector("#sortSelect"),
  mapCount: document.querySelector("#mapCount"),
  resultCount: document.querySelector("#resultCount"),
  listingsGrid: document.querySelector("#listingsGrid"),
  emptyState: document.querySelector("#emptyState"),
};

async function init() {
  try {
    const response = await fetch("data/listings.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    state.listings = payload.listings || [];
    state.routing = payload.routing || {};
    renderSummary(payload.generated_at);
    bindControls();
    initMap();
    applyFilters();
  } catch (error) {
    elements.resultCount.textContent = "Could not load listings data.";
    elements.emptyState.hidden = false;
    elements.emptyState.textContent = error.message;
  }
}

function bindControls() {
  for (const element of [
    elements.searchInput,
    elements.maxRent,
    elements.maxTransit,
    elements.bedroomsFilter,
    elements.gardenFilter,
    elements.parkingFilter,
    elements.sortSelect,
  ]) {
    element.addEventListener("input", applyFilters);
    element.addEventListener("change", applyFilters);
  }
}

function renderSummary(generatedAt) {
  const active = state.listings.filter((item) => item.status === "active");
  elements.activeCount.textContent = active.length.toLocaleString("en-GB");
  elements.medianTransit.textContent = formatMinutes(median(active.map((item) => item.transit_minutes)));
  elements.medianCycle.textContent = formatMinutes(median(active.map((item) => item.cycling_minutes)));
  elements.targetName.textContent = state.routing.target_name || "Target";
  elements.targetCoords.textContent =
    state.routing.target_latitude && state.routing.target_longitude
      ? `${state.routing.target_latitude}, ${state.routing.target_longitude}`
      : "No routing target";
  elements.routeProfile.textContent =
    state.routing.departure_day && state.routing.departure_time
      ? `${capitalize(state.routing.departure_day)} ${state.routing.departure_time}`
      : "Not configured";
  elements.generatedAt.textContent = generatedAt
    ? new Date(generatedAt).toLocaleString("en-GB", {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "-";
}

function applyFilters() {
  const query = elements.searchInput.value.trim().toLowerCase();
  const maxRent = parseNumber(elements.maxRent.value);
  const maxTransit = parseNumber(elements.maxTransit.value);
  const bedrooms = elements.bedroomsFilter.value;
  const garden = elements.gardenFilter.value;
  const parking = elements.parkingFilter.value;
  const sort = elements.sortSelect.value;

  state.filtered = state.listings.filter((item) => {
    const haystack = [item.address, item.agent, item.title, item.search_name]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    if (query && !haystack.includes(query)) return false;
    if (maxRent !== null && Number(item.price_pcm || 0) > maxRent) return false;
    if (bedrooms === "1" && Number(item.bedrooms) !== 1) return false;
    if (bedrooms === "2" && Number(item.bedrooms) !== 2) return false;
    if (bedrooms === "3" && Number(item.bedrooms) < 3) return false;
    if (garden === "yes" && !item.has_garden) return false;
    if (parking === "yes" && !item.has_parking) return false;
    if (
      maxTransit !== null &&
      (item.transit_minutes === null || Number(item.transit_minutes) > maxTransit)
    ) {
      return false;
    }
    return true;
  });

  state.filtered.sort(sortListings(sort));
  renderListings();
  renderMap();
}

function sortListings(sort) {
  return (a, b) => {
    if (a.status !== b.status) return a.status === "active" ? -1 : 1;
    if (sort === "cycling") return compareNullable(a.cycling_minutes, b.cycling_minutes);
    if (sort === "price") return compareNullable(a.price_pcm, b.price_pcm);
    if (sort === "newest") {
      return new Date(b.search_last_seen_at || 0) - new Date(a.search_last_seen_at || 0);
    }
    return compareNullable(a.transit_minutes, b.transit_minutes);
  };
}

function renderListings() {
  elements.resultCount.textContent = `${state.filtered.length.toLocaleString("en-GB")} of ${state.listings.length.toLocaleString("en-GB")} listings`;
  elements.emptyState.hidden = state.filtered.length !== 0;
  elements.listingsGrid.innerHTML = state.filtered.map(renderCard).join("");
}

function renderCard(item) {
  const statusClass = item.status === "removed" ? " status-removed" : "";
  const mapUrl = directionsUrl(item, "driving");
  const transitUrl = directionsUrl(item, "transit");
  const cyclingUrl = directionsUrl(item, "bicycling");
  return `
    <article class="listing-card${statusClass}">
      <div>
        <h3>${escapeHtml(item.address || item.title || "Untitled listing")}</h3>
        <p class="listing-meta">
          ${escapeHtml(item.price_text || "Price unavailable")}
          ${item.bedrooms ? ` · ${item.bedrooms} bed` : ""}
          ${item.has_garden ? ` · Garden/terrace` : ""}
          ${item.has_parking ? ` · Parking` : ""}
          ${item.agent ? ` · ${escapeHtml(item.agent)}` : ""}
          ${item.status === "removed" ? ` · <span class="status-label">Removed</span>` : ""}
        </p>
        <div class="listing-actions">
          <a href="${item.url}" target="_blank" rel="noreferrer">Rightmove</a>
          ${mapUrl ? `<a href="${mapUrl}" target="_blank" rel="noreferrer">Map</a>` : ""}
          ${transitUrl ? `<a href="${transitUrl}" target="_blank" rel="noreferrer">Transit</a>` : ""}
          ${cyclingUrl ? `<a href="${cyclingUrl}" target="_blank" rel="noreferrer">Cycle</a>` : ""}
        </div>
      </div>
      <div class="route-grid">
        ${routePill("Transit", item.transit_minutes, item.transit_distance_km)}
        ${routePill("Cycle", item.cycling_minutes, item.cycling_distance_km)}
      </div>
    </article>
  `;
}

function initMap() {
  if (!window.L || !document.querySelector("#map")) {
    elements.mapCount.textContent = "Map library unavailable.";
    return;
  }

  state.map = L.map("map", { scrollWheelZoom: false }).setView([51.5074, -0.1278], 11);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(state.map);
  state.markers = L.layerGroup().addTo(state.map);
}

function renderMap() {
  if (!state.map || !state.markers) return;

  state.markers.clearLayers();
  const mappable = state.filtered.filter((item) => item.latitude && item.longitude);
  const bounds = [];

  for (const item of mappable) {
    const marker = L.circleMarker([item.latitude, item.longitude], {
      radius: 7,
      color: "#174b32",
      weight: 2,
      fillColor: item.has_parking ? "#1f6f43" : "#77a982",
      fillOpacity: 0.85,
    });
    marker.bindPopup(renderPopup(item), { maxWidth: 280 });
    marker.addTo(state.markers);
    bounds.push([item.latitude, item.longitude]);
  }

  elements.mapCount.textContent = `${mappable.length.toLocaleString("en-GB")} mapped listings`;
  if (bounds.length > 0) {
    state.map.fitBounds(bounds, { padding: [24, 24], maxZoom: 14 });
  }
}

function renderPopup(item) {
  return `
    <div class="map-popup">
      <strong>${escapeHtml(item.address || item.title || "Untitled listing")}</strong>
      <span>${escapeHtml(item.price_text || "Price unavailable")}${item.bedrooms ? ` · ${item.bedrooms} bed` : ""}</span>
      <span>Transit: ${formatMinutes(item.transit_minutes)} · Cycle: ${formatMinutes(item.cycling_minutes)}</span>
      <span>${item.has_garden ? "Garden/terrace" : "No garden flag"} · ${item.has_parking ? "Parking" : "No parking flag"}</span>
      <a href="${item.url}" target="_blank" rel="noreferrer">Open Rightmove</a>
    </div>
  `;
}

function routePill(label, minutes, distanceKm) {
  return `
    <div class="route-pill">
      <span>${label}</span>
      <strong>${formatMinutes(minutes)}</strong>
      <small>${formatDistance(distanceKm)}</small>
    </div>
  `;
}

function directionsUrl(item, mode) {
  if (!item.latitude || !item.longitude) return "";
  if (!state.routing.target_latitude || !state.routing.target_longitude) return "";
  const origin = `${item.latitude},${item.longitude}`;
  const destination = `${state.routing.target_latitude},${state.routing.target_longitude}`;
  return `https://www.google.com/maps/dir/?api=1&origin=${encodeURIComponent(origin)}&destination=${encodeURIComponent(destination)}&travelmode=${mode}`;
}

function median(values) {
  const numbers = values
    .filter((value) => value !== null && value !== undefined && !Number.isNaN(Number(value)))
    .map(Number)
    .sort((a, b) => a - b);
  if (numbers.length === 0) return null;
  const middle = Math.floor(numbers.length / 2);
  return numbers.length % 2 ? numbers[middle] : Math.round((numbers[middle - 1] + numbers[middle]) / 2);
}

function compareNullable(a, b) {
  if (a === null || a === undefined) return 1;
  if (b === null || b === undefined) return -1;
  return Number(a) - Number(b);
}

function parseNumber(value) {
  if (value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function formatMinutes(value) {
  if (value === null || value === undefined) return "-";
  return `${Math.round(Number(value))} min`;
}

function formatDistance(value) {
  if (value === null || value === undefined) return "Not calculated";
  return `${Number(value).toFixed(2)} km`;
}

function capitalize(value) {
  if (!value) return "";
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

init();
