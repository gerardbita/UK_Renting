import { useState } from "react";

const SAVED_KEY = "rentwatch-saved-searches";

export default function FilterRail({ filters, setFilters, targets, onReset, resultCount }) {
  const [saved, setSaved] = useState(() => readSaved());
  const [name, setName] = useState("");

  function set(key, value) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  function saveCurrent() {
    const label = name.trim() || `View ${saved.length + 1}`;
    const next = [...saved.filter((item) => item.name !== label), { name: label, filters }];
    window.localStorage.setItem(SAVED_KEY, JSON.stringify(next));
    setSaved(next);
    setName("");
  }

  function applySaved(item) {
    setFilters({ ...item.filters });
  }

  function deleteSaved(label) {
    const next = saved.filter((item) => item.name !== label);
    window.localStorage.setItem(SAVED_KEY, JSON.stringify(next));
    setSaved(next);
  }

  return (
    <aside className="filter-rail" aria-label="Filters">
      <div className="rail-head">
        <h2>Filters</h2>
        <button type="button" className="link-btn" onClick={onReset}>Reset</button>
      </div>
      <p className="rail-count">{resultCount.toLocaleString("en-GB")} matching</p>

      <label className="field">
        <span>Search</span>
        <input
          value={filters.query}
          onChange={(event) => set("query", event.target.value)}
          placeholder="Area, agent, feature…"
        />
      </label>

      <div className="field-grid">
        <label className="field">
          <span>Min rent</span>
          <input value={filters.minRent} inputMode="numeric" placeholder="1000" onChange={(e) => set("minRent", e.target.value)} />
        </label>
        <label className="field">
          <span>Max rent</span>
          <input value={filters.maxRent} inputMode="numeric" placeholder="2200" onChange={(e) => set("maxRent", e.target.value)} />
        </label>
      </div>

      <fieldset className="segmented">
        <legend>Min beds</legend>
        {["", "1", "2", "3"].map((value) => (
          <button
            key={value || "any"}
            type="button"
            className={String(filters.minBeds) === value ? "is-active" : ""}
            onClick={() => set("minBeds", value)}
          >
            {value || "Any"}
          </button>
        ))}
      </fieldset>

      <label className="field">
        <span>Sort by</span>
        <select value={filters.sort} onChange={(event) => set("sort", event.target.value)}>
          <option value="score">Best balanced score</option>
          <option value="rent_asc">Lowest rent</option>
          <option value="rent_desc">Highest rent</option>
          <option value="commute">Shortest worst-commute</option>
          <option value="targetA">Fastest {short(targets[0]?.name, "Target 1")}</option>
          <option value="targetB">Fastest {short(targets[1]?.name, "Target 2")}</option>
          <option value="newest">Most recent</option>
        </select>
      </label>

      <section className="rail-section">
        <h3>Commute priority</h3>
        <p className="rail-hint">Weight whose commute matters more. Re-ranks instantly.</p>
        {targets.map((target, index) => (
          <label className="slider-row" key={target.name}>
            <span>{short(target.name, `Target ${index + 1}`)}</span>
            <input
              type="range"
              min="0"
              max="3"
              step="0.5"
              value={filters.weights[index] ?? 1}
              onChange={(event) => {
                const weights = [...filters.weights];
                weights[index] = Number(event.target.value);
                set("weights", weights);
              }}
            />
            <strong>{(filters.weights[index] ?? 1).toFixed(1)}×</strong>
          </label>
        ))}
      </section>

      <section className="rail-section">
        <h3>Commute limits (min)</h3>
        <div className="field-grid">
          <label className="field">
            <span>{short(targets[0]?.name, "T1")} transit</span>
            <input value={filters.maxTransitA} inputMode="numeric" placeholder="35" onChange={(e) => set("maxTransitA", e.target.value)} />
          </label>
          <label className="field">
            <span>{short(targets[1]?.name, "T2")} transit</span>
            <input value={filters.maxTransitB} inputMode="numeric" placeholder="40" onChange={(e) => set("maxTransitB", e.target.value)} />
          </label>
        </div>
        <label className="field">
          <span>Max cycle to either</span>
          <input value={filters.maxCycleAny} inputMode="numeric" placeholder="30" onChange={(e) => set("maxCycleAny", e.target.value)} />
        </label>
      </section>

      <section className="rail-section toggles">
        <Toggle label="Active only" checked={filters.activeOnly} onChange={(v) => set("activeOnly", v)} />
        <Toggle label="With photos" checked={filters.photosOnly} onChange={(v) => set("photosOnly", v)} />
        <Toggle label="Hide let agreed" checked={filters.hideLetAgreed} onChange={(v) => set("hideLetAgreed", v)} />
        <Toggle label="New or reduced" checked={filters.freshOnly} onChange={(v) => set("freshOnly", v)} />
        <Toggle label="Garden / terrace" checked={filters.gardenOnly} onChange={(v) => set("gardenOnly", v)} />
        <Toggle label="Parking" checked={filters.parkingOnly} onChange={(v) => set("parkingOnly", v)} />
        <Toggle label="Both commutes known" checked={filters.completeRoutesOnly} onChange={(v) => set("completeRoutesOnly", v)} />
      </section>

      <section className="rail-section">
        <h3>Saved searches</h3>
        <div className="save-row">
          <input value={name} placeholder="Name this view" onChange={(event) => setName(event.target.value)} />
          <button type="button" className="btn btn--primary btn--sm" onClick={saveCurrent}>Save</button>
        </div>
        {saved.length ? (
          <ul className="saved-list">
            {saved.map((item) => (
              <li key={item.name}>
                <button type="button" className="link-btn" onClick={() => applySaved(item)}>{item.name}</button>
                <button type="button" className="remove-link" onClick={() => deleteSaved(item.name)}>✕</button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="rail-hint">No saved views yet.</p>
        )}
      </section>
    </aside>
  );
}

function Toggle({ label, checked, onChange }) {
  return (
    <label className="toggle">
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      <span>{label}</span>
    </label>
  );
}

function short(name, fallback) {
  if (!name) return fallback;
  return name.length > 16 ? `${name.slice(0, 15)}…` : name;
}

function readSaved() {
  try {
    const raw = window.localStorage.getItem(SAVED_KEY);
    const data = raw ? JSON.parse(raw) : [];
    return Array.isArray(data) ? data : [];
  } catch {
    return [];
  }
}
