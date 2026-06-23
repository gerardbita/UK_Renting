import { dateTime, relativeTime } from "../lib/format.js";

const VIEWS = [
  { key: "table", label: "Table" },
  { key: "gallery", label: "Gallery" },
  { key: "map", label: "Map" },
];

export default function TopBar({ meta, generatedAt, view, onView, compareCount, onOpenCompare }) {
  const counts = meta?.counts || {};
  const freshness = meta?.freshness || {};
  return (
    <header className="topbar">
      <div className="brand-block">
        <span className="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 24 24" role="img">
            <path d="M3 11.4 12 3l9 8.4" />
            <path d="M5.5 10.5V21h13V10.5" />
            <path d="M9 21v-6h6v6" />
          </svg>
        </span>
        <div>
          <h1>RentWatch</h1>
          <span className="brand-sub">London commute intelligence</span>
        </div>
      </div>

      <div className="topbar-stats">
        <Stat value={(counts.active ?? 0).toLocaleString("en-GB")} label="Active" tone="live" />
        <Stat value={(counts.new ?? freshness.new ?? 0).toLocaleString("en-GB")} label="New" tone="new" />
        <Stat value={(freshness.reduced ?? 0).toLocaleString("en-GB")} label="Reduced" tone="reduced" />
        <Stat value={(counts.with_photos ?? 0).toLocaleString("en-GB")} label="With photos" />
      </div>

      <div className="topbar-right">
        <div className="view-toggle" role="tablist" aria-label="View">
          {VIEWS.map((option) => (
            <button
              key={option.key}
              type="button"
              role="tab"
              aria-selected={view === option.key}
              className={view === option.key ? "is-active" : ""}
              onClick={() => onView(option.key)}
            >
              {option.label}
            </button>
          ))}
        </div>
        <button type="button" className="compare-btn" onClick={onOpenCompare} disabled={!compareCount}>
          Compare <span>{compareCount}</span>
        </button>
        <div className="update-block" title={dateTime(generatedAt)}>
          <span className="pulse" aria-hidden="true" />
          <span>Updated {relativeTime(generatedAt) || dateTime(generatedAt)}</span>
        </div>
      </div>
    </header>
  );
}

function Stat({ value, label, tone }) {
  return (
    <div className={`topstat${tone ? ` topstat--${tone}` : ""}`}>
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}
