import { useEffect, useMemo, useState } from "react";
import TopBar from "./components/TopBar.jsx";
import FilterRail from "./components/FilterRail.jsx";
import DashboardMap from "./components/DashboardMap.jsx";
import ResultsTable from "./components/ResultsTable.jsx";
import GalleryView from "./components/GalleryView.jsx";
import StatsPanel from "./components/StatsPanel.jsx";
import ListingDetail from "./components/ListingDetail.jsx";
import CompareModal from "./components/CompareModal.jsx";
import { enrichListings } from "./lib/scoring.js";
import { resolveTargets } from "./lib/targets.js";

const DEFAULT_FILTERS = {
  query: "",
  minRent: "",
  maxRent: "",
  minBeds: "",
  maxTransitA: "",
  maxTransitB: "",
  maxCycleAny: "",
  activeOnly: true,
  photosOnly: false,
  hideLetAgreed: true,
  freshOnly: false,
  gardenOnly: false,
  parkingOnly: false,
  completeRoutesOnly: false,
  sort: "score",
  weights: [1, 1],
};

export default function App() {
  const [payload, setPayload] = useState(null);
  const [loadState, setLoadState] = useState({ status: "loading", error: "" });
  const [filters, setFilters] = useState(() => ({ ...DEFAULT_FILTERS, ...decodeFilters() }));
  const [view, setView] = useState("table");
  const [selectedIds, setSelectedIds] = useState([]);
  const [openId, setOpenId] = useState(null);
  const [activeId, setActiveId] = useState(null);
  const [compareOpen, setCompareOpen] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    loadListingsData(controller.signal)
      .then((data) => {
        setPayload(data);
        setLoadState({ status: "ready", error: "" });
      })
      .catch((error) => {
        if (error.name === "AbortError") return;
        setLoadState({ status: "error", error: error.message });
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    encodeFilters(filters);
  }, [filters]);

  const targets = useMemo(() => resolveTargets(payload?.routing), [payload]);
  const listings = useMemo(
    () => enrichListings(payload?.listings || [], targets, filters.weights),
    [payload, targets, filters.weights],
  );
  const filtered = useMemo(() => filterAndSort(listings, filters), [listings, filters]);

  const byId = useMemo(() => new Map(listings.map((listing) => [listing.id, listing])), [listings]);
  const openListing = openId ? byId.get(openId) : null;
  const compareListings = selectedIds.map((id) => byId.get(id)).filter(Boolean);

  function toggleSelect(id) {
    setSelectedIds((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id].slice(-4),
    );
  }

  if (loadState.status === "loading") {
    return <LoadingShell />;
  }
  if (loadState.status === "error") {
    return (
      <main className="app-shell app-shell--center">
        <div className="message-card">
          <h1>Data could not load</h1>
          <p>{loadState.error}</p>
        </div>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <TopBar
        meta={payload?.meta}
        generatedAt={payload?.generated_at}
        view={view}
        onView={setView}
        compareCount={selectedIds.length}
        onOpenCompare={() => setCompareOpen(true)}
      />

      <div className="layout">
        <FilterRail
          filters={filters}
          setFilters={setFilters}
          targets={targets}
          onReset={() => setFilters({ ...DEFAULT_FILTERS })}
          resultCount={filtered.length}
        />

        <section className="stage">
          {view !== "map" ? (
            <DashboardMap
              listings={filtered}
              targets={targets}
              activeId={activeId}
              onOpen={setOpenId}
              onHover={setActiveId}
            />
          ) : null}

          {view === "table" ? (
            <ResultsTable
              listings={filtered}
              targets={targets}
              selectedIds={selectedIds}
              onToggleSelect={toggleSelect}
              onOpen={setOpenId}
              onHover={setActiveId}
              activeId={activeId}
            />
          ) : null}

          {view === "gallery" ? (
            <GalleryView
              listings={filtered}
              targets={targets}
              selectedIds={selectedIds}
              onToggleSelect={toggleSelect}
              onOpen={setOpenId}
              onHover={setActiveId}
              activeId={activeId}
            />
          ) : null}

          {view === "map" ? (
            <DashboardMap
              listings={filtered}
              targets={targets}
              activeId={activeId}
              onOpen={setOpenId}
              onHover={setActiveId}
              fullHeight
            />
          ) : null}
        </section>

        <StatsPanel
          listings={filtered}
          targets={targets}
          onOpen={setOpenId}
          onHover={setActiveId}
          activeId={activeId}
        />
      </div>

      {openListing ? (
        <ListingDetail
          listing={openListing}
          targets={targets}
          onClose={() => setOpenId(null)}
          onCompare={toggleSelect}
          isComparing={selectedIds.includes(openListing.id)}
        />
      ) : null}

      {compareOpen ? (
        <CompareModal
          listings={compareListings}
          targets={targets}
          onClose={() => setCompareOpen(false)}
          onRemove={toggleSelect}
        />
      ) : null}
    </main>
  );
}

function LoadingShell() {
  return (
    <main className="app-shell app-shell--center">
      <div className="message-card">
        <span className="loading-mark" />
        <h1>Loading RentWatch</h1>
        <p>Scoring listings, plotting commutes, and building the dashboard…</p>
      </div>
    </main>
  );
}

async function loadListingsData(signal) {
  const basePath = import.meta.env.BASE_URL || "/";
  const candidates = [`${basePath.replace(/\/$/, "")}/data/listings.json`, "/data/listings.json"];
  let lastError = null;
  for (const url of [...new Set(candidates)]) {
    try {
      const response = await fetch(url, { signal });
      const contentType = response.headers.get("content-type") || "";
      if (!response.ok || !contentType.includes("json")) {
        throw new Error(`Could not load listings data from ${url}`);
      }
      return response.json();
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError || new Error("Could not load listings data");
}

function filterAndSort(listings, filters) {
  const query = filters.query.trim().toLowerCase();
  const minRent = num(filters.minRent);
  const maxRent = num(filters.maxRent);
  const minBeds = num(filters.minBeds);
  const maxTransitA = num(filters.maxTransitA);
  const maxTransitB = num(filters.maxTransitB);
  const maxCycleAny = num(filters.maxCycleAny);

  const result = listings.filter((listing) => {
    if (filters.activeOnly && listing.status !== "active") return false;
    if (filters.photosOnly && !listing.main_image) return false;
    if (filters.hideLetAgreed && listing.let_agreed) return false;
    if (filters.freshOnly && !(listing.freshness === "new" || listing.freshness === "reduced")) return false;
    if (filters.gardenOnly && !listing.has_garden) return false;
    if (filters.parkingOnly && !listing.has_parking) return false;
    if (query && !searchText(listing).includes(query)) return false;
    if (minRent !== null && Number(listing.price_pcm ?? 0) < minRent) return false;
    if (maxRent !== null && Number(listing.price_pcm ?? Infinity) > maxRent) return false;
    if (minBeds !== null && Number(listing.bedrooms ?? 0) < minBeds) return false;
    if (filters.completeRoutesOnly && listing.routes.some((r) => r.transit_minutes == null && r.cycling_minutes == null)) return false;
    if (maxTransitA !== null && Number(listing.routes[0]?.transit_minutes ?? Infinity) > maxTransitA) return false;
    if (maxTransitB !== null && Number(listing.routes[1]?.transit_minutes ?? Infinity) > maxTransitB) return false;
    if (maxCycleAny !== null && !listing.routes.some((r) => Number(r.cycling_minutes ?? Infinity) <= maxCycleAny)) return false;
    return true;
  });

  result.sort((a, b) => {
    switch (filters.sort) {
      case "rent_asc":
        return nullable(a.price_pcm, b.price_pcm);
      case "rent_desc":
        return nullable(b.price_pcm, a.price_pcm);
      case "commute":
        return nullable(worstCommute(a), worstCommute(b));
      case "targetA":
        return nullable(a.routes[0]?.transit_minutes, b.routes[0]?.transit_minutes);
      case "targetB":
        return nullable(a.routes[1]?.transit_minutes, b.routes[1]?.transit_minutes);
      case "newest":
        return String(b.search_last_seen_at || "").localeCompare(String(a.search_last_seen_at || ""));
      default:
        return b.score - a.score;
    }
  });
  return result;
}

function worstCommute(listing) {
  const values = listing.routes
    .map((route) => route.transit_minutes ?? route.cycling_minutes)
    .filter((value) => Number.isFinite(Number(value)));
  return values.length ? Math.max(...values.map(Number)) : null;
}

function searchText(listing) {
  return [listing.address, listing.title, listing.agent, listing.summary, listing.property_subtype, (listing.key_features || []).join(" ")]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function num(value) {
  if (value === "" || value === null || value === undefined) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function nullable(a, b) {
  if (a === null || a === undefined) return 1;
  if (b === null || b === undefined) return -1;
  return Number(a) - Number(b);
}

// --- URL state (shareable filters) ---
const URL_KEYS = ["query", "minRent", "maxRent", "minBeds", "maxTransitA", "maxTransitB", "maxCycleAny", "sort"];
const BOOL_KEYS = ["activeOnly", "photosOnly", "hideLetAgreed", "freshOnly", "gardenOnly", "parkingOnly", "completeRoutesOnly"];

function encodeFilters(filters) {
  const params = new URLSearchParams();
  for (const key of URL_KEYS) {
    if (filters[key]) params.set(key, filters[key]);
  }
  for (const key of BOOL_KEYS) {
    if (filters[key] !== DEFAULT_FILTERS[key]) params.set(key, filters[key] ? "1" : "0");
  }
  if (filters.weights?.some((w, i) => w !== DEFAULT_FILTERS.weights[i])) {
    params.set("w", filters.weights.join(","));
  }
  const query = params.toString();
  const url = `${window.location.pathname}${query ? `?${query}` : ""}`;
  window.history.replaceState(null, "", url);
}

function decodeFilters() {
  const params = new URLSearchParams(window.location.search);
  const out = {};
  for (const key of URL_KEYS) {
    if (params.has(key)) out[key] = params.get(key);
  }
  for (const key of BOOL_KEYS) {
    if (params.has(key)) out[key] = params.get(key) === "1";
  }
  if (params.has("w")) {
    const weights = params.get("w").split(",").map(Number).filter(Number.isFinite);
    if (weights.length) out.weights = weights;
  }
  return out;
}
