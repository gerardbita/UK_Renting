import { useEffect, useMemo, useState } from "react";
import DashboardMap from "./components/DashboardMap.jsx";
import FilterRail from "./components/FilterRail.jsx";
import ListingResults from "./components/ListingResults.jsx";
import SummaryPanel from "./components/SummaryPanel.jsx";
import CompareDrawer from "./components/CompareDrawer.jsx";
import { enrichListings } from "./lib/scoring.js";
import { resolveTargets } from "./lib/targets.js";

const initialFilters = {
  query: "",
  maxRent: "",
  minBeds: "",
  maxTransitA: "",
  maxTransitB: "",
  maxCycleAny: "",
  gardenOnly: false,
  parkingOnly: false,
  activeOnly: true,
  completeRoutesOnly: false,
  sort: "score",
};

export default function App() {
  const [payload, setPayload] = useState(null);
  const [loadState, setLoadState] = useState({ status: "loading", error: "" });
  const [filters, setFilters] = useState(initialFilters);
  const [selectedIds, setSelectedIds] = useState([]);

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

  const targets = useMemo(() => resolveTargets(payload?.routing), [payload]);
  const listings = useMemo(
    () => enrichListings(payload?.listings || [], targets),
    [payload, targets],
  );
  const filteredListings = useMemo(
    () => filterAndSortListings(listings, filters),
    [listings, filters],
  );
  const selectedListings = selectedIds
    .map((id) => listings.find((listing) => listing.id === id))
    .filter(Boolean);

  function toggleSelected(id) {
    setSelectedIds((current) => {
      if (current.includes(id)) return current.filter((item) => item !== id);
      return [...current, id].slice(-5);
    });
  }

  if (loadState.status === "loading") {
    return (
      <main className="app-shell app-shell--loading">
        <div className="loading-card">
          <span className="loading-mark" />
          <h1>Loading UK Renting</h1>
          <p>Preparing listings, map pins, commute scores, and comparison controls.</p>
        </div>
      </main>
    );
  }

  if (loadState.status === "error") {
    return (
      <main className="app-shell app-shell--loading">
        <div className="loading-card">
          <h1>Data could not load</h1>
          <p>{loadState.error}</p>
        </div>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-block">
          <span className="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 24 24" role="img">
              <path d="M3 11.4 12 3l9 8.4" />
              <path d="M5.5 10.5V21h13V10.5" />
              <path d="M9 21v-6h6v6" />
            </svg>
          </span>
          <h1>UK Renting</h1>
        </div>
        <div className="update-block">
          <span className="clock-mark" aria-hidden="true">◷</span>
          <span>Last updated: {formatDateTime(payload?.generated_at)}</span>
          <strong>Live</strong>
        </div>
        <div className="target-strip" aria-label="Route targets">
          {targets.map((target, index) => (
            <span key={`${target.latitude}:${target.longitude}`}>
              <strong>{index + 1}</strong>
              {target.name}
            </span>
          ))}
        </div>
        <a className="deploy-status" href="https://github.com/gerardbita/UK_Renting" target="_blank" rel="noreferrer">
          GitHub Pages <span /> Deployed
        </a>
      </header>

      <section className="dashboard-grid">
        <FilterRail
          filters={filters}
          setFilters={setFilters}
          onReset={() => setFilters(initialFilters)}
          onApply={() => {
            document.querySelector(".results-panel")?.scrollIntoView({
              behavior: "smooth",
              block: "start",
            });
          }}
        />

        <section className="main-stage" aria-label="Map and listing results">
          <DashboardMap listings={filteredListings} targets={targets} />
          <ListingResults
            listings={filteredListings}
            targets={targets}
            selectedIds={selectedIds}
            onToggleSelected={toggleSelected}
            updatedAt={payload?.generated_at}
          />
        </section>

        <SummaryPanel listings={filteredListings} allListings={listings} targets={targets} />
      </section>

      <CompareDrawer
        listings={selectedListings}
        targets={targets}
        onRemove={(id) => setSelectedIds((current) => current.filter((item) => item !== id))}
      />
    </main>
  );
}

async function loadListingsData(signal) {
  const basePath = import.meta.env.BASE_URL || "/";
  const candidates = [
    `${basePath.replace(/\/$/, "")}/data/listings.json`,
    "/data/listings.json",
  ];
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

function filterAndSortListings(listings, filters) {
  const query = filters.query.trim().toLowerCase();
  const maxRent = parseOptionalNumber(filters.maxRent);
  const minBeds = parseOptionalNumber(filters.minBeds);
  const maxTransitA = parseOptionalNumber(filters.maxTransitA);
  const maxTransitB = parseOptionalNumber(filters.maxTransitB);
  const maxCycleAny = parseOptionalNumber(filters.maxCycleAny);

  return listings
    .filter((listing) => {
      if (filters.activeOnly && listing.status === "removed") return false;
      if (query && !searchText(listing).includes(query)) return false;
      if (maxRent !== null && Number(listing.price_pcm || Infinity) > maxRent) return false;
      if (minBeds !== null && Number(listing.bedrooms || 0) < minBeds) return false;
      if (filters.gardenOnly && !listing.has_garden) return false;
      if (filters.parkingOnly && !listing.has_parking) return false;
      if (filters.completeRoutesOnly && listing.routes.some((route) => route.transit_minutes == null && route.cycling_minutes == null)) return false;
      if (maxTransitA !== null && Number(listing.routes[0]?.transit_minutes ?? Infinity) > maxTransitA) return false;
      if (maxTransitB !== null && Number(listing.routes[1]?.transit_minutes ?? Infinity) > maxTransitB) return false;
      if (maxCycleAny !== null && listing.routes.some((route) => Number(route.cycling_minutes ?? Infinity) > maxCycleAny)) return false;
      return true;
    })
    .sort((a, b) => {
      if (filters.sort === "rent") return compareNullable(a.price_pcm, b.price_pcm);
      if (filters.sort === "targetA") return compareNullable(a.routes[0]?.transit_minutes, b.routes[0]?.transit_minutes);
      if (filters.sort === "targetB") return compareNullable(a.routes[1]?.transit_minutes, b.routes[1]?.transit_minutes);
      if (filters.sort === "cycle") return compareNullable(a.routes[0]?.cycling_minutes, b.routes[0]?.cycling_minutes);
      if (filters.sort === "newest") return String(b.search_last_seen_at || "").localeCompare(String(a.search_last_seen_at || ""));
      return b.score - a.score;
    });
}

function searchText(listing) {
  return [listing.address, listing.title, listing.agent, listing.summary, listing.price_text]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function parseOptionalNumber(value) {
  if (value === "" || value === null || value === undefined) return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function compareNullable(a, b) {
  if (a === null || a === undefined) return 1;
  if (b === null || b === undefined) return -1;
  return Number(a) - Number(b);
}

function formatDateTime(value) {
  if (!value) return "unknown";
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
