export function gbp(value) {
  if (value === null || value === undefined || value === "") return "—";
  return `£${Number(value).toLocaleString("en-GB")}`;
}

export function pcm(value, text) {
  if (text) return text;
  if (value === null || value === undefined || value === "") return "—";
  return `£${Number(value).toLocaleString("en-GB")} pcm`;
}

export function minutes(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "—";
  return `${Math.round(Number(value))}m`;
}

export function km(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "";
  return `${Number(value).toFixed(1)} km`;
}

export function dateTime(value) {
  if (!value) return "unknown";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "unknown";
  return new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

export function shortDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short" }).format(date);
}

export function relativeTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const seconds = (Date.now() - date.getTime()) / 1000;
  const rtf = new Intl.RelativeTimeFormat("en-GB", { numeric: "auto" });
  const units = [
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
  ];
  for (const [unit, secs] of units) {
    if (Math.abs(seconds) >= secs || unit === "minute") {
      return rtf.format(-Math.round(seconds / secs), unit);
    }
  }
  return "just now";
}

export function initials(text) {
  return String(text || "UK")
    .split(/[,\s]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

export function sourceLabel(source) {
  if (!source) return "Source";
  if (source === "rightmove") return "Rightmove";
  return source.charAt(0).toUpperCase() + source.slice(1);
}

export function directionsUrl(listing, target, mode = "transit") {
  const origin = `${listing.latitude},${listing.longitude}`;
  const destination = `${target.latitude},${target.longitude}`;
  return `https://www.google.com/maps/dir/?api=1&origin=${encodeURIComponent(
    origin,
  )}&destination=${encodeURIComponent(destination)}&travelmode=${mode}`;
}
