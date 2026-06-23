import { gbp } from "../lib/format.js";

export function Sparkline({ points, width = 220, height = 48 }) {
  const values = (points || []).map((point) => Number(point.p)).filter(Number.isFinite);
  if (values.length < 2) {
    return <div className="sparkline-empty">No price history yet</div>;
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const stepX = width / (values.length - 1);
  const coords = values.map((value, index) => {
    const x = index * stepX;
    const y = height - ((value - min) / span) * (height - 8) - 4;
    return [x, y];
  });
  const path = coords.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const last = values[values.length - 1];
  const first = values[0];
  const dropped = last < first;

  return (
    <div className="sparkline">
      <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height} preserveAspectRatio="none">
        <path d={path} fill="none" stroke={dropped ? "#34d399" : "#f59e0b"} strokeWidth="2" />
        {coords.map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r={i === coords.length - 1 ? 3 : 1.6} fill={dropped ? "#34d399" : "#f59e0b"} />
        ))}
      </svg>
      <div className="sparkline-legend">
        <span>{gbp(first)}</span>
        <span className={dropped ? "down" : "up"}>{dropped ? "▼" : first === last ? "" : "▲"} {gbp(last)}</span>
      </div>
    </div>
  );
}

export function ScatterPlot({ points, xLabel, yLabel, size = 260, onSelect, selectedId }) {
  const valid = (points || []).filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y));
  if (!valid.length) return <div className="chart-empty">No commute data to plot</div>;
  const pad = 26;
  const maxX = Math.max(...valid.map((p) => p.x), 10);
  const maxY = Math.max(...valid.map((p) => p.y), 10);
  const scaleX = (x) => pad + (x / maxX) * (size - pad * 1.4);
  const scaleY = (y) => size - pad - (y / maxY) * (size - pad * 1.4);

  return (
    <svg className="scatter" viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`${xLabel} vs ${yLabel}`}>
      <line x1={pad} y1={size - pad} x2={size - 6} y2={size - pad} className="axis" />
      <line x1={pad} y1={6} x2={pad} y2={size - pad} className="axis" />
      <line x1={pad} y1={size - pad} x2={scaleX(maxX)} y2={scaleY(maxY)} className="diagonal" />
      {valid.map((point) => (
        <circle
          key={point.id}
          cx={scaleX(point.x)}
          cy={scaleY(point.y)}
          r={point.id === selectedId ? 6 : 3.5}
          className={`dot${point.id === selectedId ? " is-selected" : ""}`}
          style={{ fill: scoreColor(point.score) }}
          onClick={() => onSelect?.(point.id)}
        >
          <title>{point.label}</title>
        </circle>
      ))}
      <text x={size / 2} y={size - 6} className="axis-label">{xLabel}</text>
      <text x={10} y={size / 2} className="axis-label" transform={`rotate(-90 10 ${size / 2})`}>{yLabel}</text>
    </svg>
  );
}

export function Histogram({ values, bins = 12, width = 260, height = 120, format = gbp }) {
  const nums = (values || []).filter(Number.isFinite);
  if (nums.length < 2) return <div className="chart-empty">Not enough data</div>;
  const min = Math.min(...nums);
  const max = Math.max(...nums);
  const span = max - min || 1;
  const buckets = new Array(bins).fill(0);
  for (const value of nums) {
    const index = Math.min(bins - 1, Math.floor(((value - min) / span) * bins));
    buckets[index] += 1;
  }
  const peak = Math.max(...buckets) || 1;
  const barW = width / bins;

  return (
    <div className="histogram">
      <svg viewBox={`0 0 ${width} ${height}`} width="100%" height={height} preserveAspectRatio="none">
        {buckets.map((count, index) => {
          const barH = (count / peak) * (height - 4);
          return (
            <rect
              key={index}
              x={index * barW + 1}
              y={height - barH}
              width={barW - 2}
              height={barH}
              rx="2"
              className="hist-bar"
            >
              <title>{count} listings</title>
            </rect>
          );
        })}
      </svg>
      <div className="histogram-axis">
        <span>{format(min)}</span>
        <span>{format(max)}</span>
      </div>
    </div>
  );
}

export function scoreColor(score) {
  if (score >= 78) return "#34d399";
  if (score >= 62) return "#a3e635";
  if (score >= 45) return "#fbbf24";
  return "#f87171";
}
