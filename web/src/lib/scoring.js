import { routesForListing } from "./targets.js";

// Mirrors rentwatch/scoring.py so the dashboard can re-rank live as the user
// adjusts the per-target weight sliders, staying consistent with the score the
// Python exporter and Telegram alerts use.

const NEUTRAL_COMMUTE_MINUTES = 50;

export function enrichListings(listings, targets, weights = [1, 1]) {
  const percentiles = pricePercentiles(
    listings
      .filter((listing) => listing.status === "active")
      .map((listing) => listing.price_pcm),
  );

  return listings.map((listing) => {
    const routes = routesForListing(listing, targets);
    const commutes = routes.map((route) => bestCommute(route.transit_minutes, route.cycling_minutes));
    const { score, breakdown } = balancedScore({
      commutes,
      pricePercentile: percentiles.get(listing.price_pcm),
      letAgreed: Boolean(listing.let_agreed),
      sizeSqft: listing.size_sqft,
      hasGarden: Boolean(listing.has_garden),
      hasParking: Boolean(listing.has_parking),
      fresh: listing.freshness === "new" || listing.freshness === "reduced",
      weights,
    });
    return {
      ...listing,
      id: `${listing.search_name || "search"}:${listing.canonical_key || listing.url || listing.address}`,
      routes,
      score,
      score_breakdown: breakdown,
      best_commute_minutes: bestCommuteAverage(commutes),
    };
  });
}

export function bestCommute(transit, cycling) {
  const values = [transit, cycling].filter(isNumber);
  return values.length ? Math.min(...values) : null;
}

export function bestCommuteAverage(commutes) {
  const values = commutes.filter(isNumber);
  return values.length ? Math.round(values.reduce((a, b) => a + b, 0) / values.length) : null;
}

export function pricePercentiles(prices) {
  const valid = prices.filter(isNumber).sort((a, b) => a - b);
  const map = new Map();
  const n = valid.length;
  valid.forEach((price, index) => {
    if (!map.has(price)) map.set(price, n > 1 ? index / (n - 1) : 0);
  });
  return map;
}

export function balancedScore({
  commutes = [],
  pricePercentile,
  letAgreed = false,
  sizeSqft,
  hasGarden = false,
  hasParking = false,
  fresh = false,
  weights = [1, 1],
}) {
  const normWeights = normalizeWeights(weights, commutes.length);
  const known = commutes
    .map((commute, index) => [normWeights[index], commute])
    .filter(([, commute]) => isNumber(commute));
  const missing = commutes.length - known.length;

  let effective;
  let imbalance = 0;
  if (known.length) {
    const totalWeight = known.reduce((sum, [w]) => sum + w, 0) || 1;
    const weightedAvg = known.reduce((sum, [w, c]) => sum + w * c, 0) / totalWeight;
    const values = known.map(([, c]) => c);
    const worst = Math.max(...values);
    effective = 0.6 * worst + 0.4 * weightedAvg;
    imbalance = values.length > 1 ? Math.max(...values) - Math.min(...values) : 0;
  } else {
    effective = NEUTRAL_COMMUTE_MINUTES;
  }

  const breakdown = {};
  let score = 100;

  breakdown.commute = -round1(effective * 1.4);
  score += breakdown.commute;

  breakdown.imbalance = -round1(imbalance * 0.5);
  score += breakdown.imbalance;

  if (pricePercentile !== undefined && pricePercentile !== null) {
    breakdown.price = -round1(clamp(pricePercentile, 0, 1) * 18);
    score += breakdown.price;
  }
  if (missing) {
    breakdown.missing_routes = -(missing * 8);
    score += breakdown.missing_routes;
  }
  if (letAgreed) {
    breakdown.let_agreed = -25;
    score += -25;
  }
  const amenities = (hasGarden ? 4 : 0) + (hasParking ? 3 : 0);
  if (amenities) {
    breakdown.amenities = amenities;
    score += amenities;
  }
  const sizeBonus = sizeBonusFor(sizeSqft);
  if (sizeBonus) {
    breakdown.size = sizeBonus;
    score += sizeBonus;
  }
  if (fresh) {
    breakdown.freshness = 4;
    score += 4;
  }

  return { score: Math.round(clamp(score, 0, 100)), breakdown: pruneZero(breakdown) };
}

export function median(values) {
  const numbers = values.filter(isNumber).sort((a, b) => a - b);
  if (!numbers.length) return null;
  const mid = Math.floor(numbers.length / 2);
  return numbers.length % 2 ? numbers[mid] : Math.round((numbers[mid - 1] + numbers[mid]) / 2);
}

function sizeBonusFor(sizeSqft) {
  if (!isNumber(sizeSqft)) return 0;
  return round1(clamp((sizeSqft - 450) / 75, 0, 6));
}

function normalizeWeights(weights, count) {
  const base = Array.isArray(weights) ? [...weights] : [];
  while (base.length < count) base.push(1);
  return base.slice(0, count).map((w) => Math.max(0, Number(w) || 0));
}

function pruneZero(breakdown) {
  const out = {};
  for (const [key, value] of Object.entries(breakdown)) {
    if (value) out[key] = value;
  }
  return out;
}

function isNumber(value) {
  return typeof value === "number" && Number.isFinite(value);
}

function round1(value) {
  return Math.round(value * 10) / 10;
}

function clamp(value, low, high) {
  return Math.max(low, Math.min(high, value));
}
