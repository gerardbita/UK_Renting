export default function FilterRail({ filters, setFilters }) {
  function update(key, value) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  return (
    <aside className="filter-rail" aria-label="Listing filters">
      <div>
        <h2>Search controls</h2>
        <p>Rank homes by the commute tradeoff across both destinations.</p>
      </div>

      <label>
        Address, agent, keyword
        <input
          value={filters.query}
          onChange={(event) => update("query", event.target.value)}
          placeholder="Paddington, balcony, Foxtons"
        />
      </label>

      <div className="field-grid">
        <label>
          Max rent
          <input
            value={filters.maxRent}
            onChange={(event) => update("maxRent", event.target.value)}
            inputMode="numeric"
            placeholder="2250"
          />
        </label>
        <label>
          Min beds
          <input
            value={filters.minBeds}
            onChange={(event) => update("minBeds", event.target.value)}
            inputMode="numeric"
            placeholder="1"
          />
        </label>
      </div>

      <label>
        Sort by
        <select value={filters.sort} onChange={(event) => update("sort", event.target.value)}>
          <option value="score">Best balanced score</option>
          <option value="targetA">Fastest target 1 transit</option>
          <option value="targetB">Fastest target 2 transit</option>
          <option value="cycle">Fastest target 1 cycle</option>
          <option value="rent">Lowest rent</option>
          <option value="newest">Most recently seen</option>
        </select>
      </label>

      <div className="field-grid">
        <label>
          Target 1 max transit
          <input
            value={filters.maxTransitA}
            onChange={(event) => update("maxTransitA", event.target.value)}
            inputMode="numeric"
            placeholder="30"
          />
        </label>
        <label>
          Target 2 max transit
          <input
            value={filters.maxTransitB}
            onChange={(event) => update("maxTransitB", event.target.value)}
            inputMode="numeric"
            placeholder="35"
          />
        </label>
      </div>

      <label>
        Max cycle to either target
        <input
          value={filters.maxCycleAny}
          onChange={(event) => update("maxCycleAny", event.target.value)}
          inputMode="numeric"
          placeholder="25"
        />
      </label>

      <div className="toggle-stack">
        <Toggle label="Active only" checked={filters.activeOnly} onChange={(value) => update("activeOnly", value)} />
        <Toggle label="Garden or terrace" checked={filters.gardenOnly} onChange={(value) => update("gardenOnly", value)} />
        <Toggle label="Parking" checked={filters.parkingOnly} onChange={(value) => update("parkingOnly", value)} />
        <Toggle label="Hide missing routes" checked={filters.completeRoutesOnly} onChange={(value) => update("completeRoutesOnly", value)} />
      </div>
    </aside>
  );
}

function Toggle({ label, checked, onChange }) {
  return (
    <label className="toggle-row">
      <span>{label}</span>
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
    </label>
  );
}
