import { routesForListing } from "./targets.js";

export function enrichListings(listings, targets) {
  return listings.map((listing) => {
    const routes = routesForListing(listing, targets);
    const score = scoreListing(listing, routes);
    return {
      ...listing,
      id: `${listing.search_name || "search"}:${listing.url || listing.address}`,
      routes,
      score,
      best_commute_minutes: bestCommuteAverage(routes),
    };
  });
}

export function scoreListing(listing, routes) {
  const routeScores = routes
    .map((route) => minDefined(route.transit_minutes, route.cycling_minutes))
    .filter((value) => value !== null);
  const missingRoutes = routes.length - routeScores.length;
  const commuteAverage = average(routeScores);
  const imbalance = routeScores.length > 1 ? Math.abs(routeScores[0] - routeScores[1]) : 0;
  const rentPenalty = listing.price_pcm ? Math.max(0, (Number(listing.price_pcm) - 1800) / 45) : 8;
  const missingPenalty = missingRoutes * 5;
  const amenityBonus = (listing.has_garden ? 4 : 0) + (listing.has_parking ? 3 : 0);
  return clamp(Math.round(100 - commuteAverage * 1.45 - imbalance * 0.65 - rentPenalty - missingPenalty + amenityBonus), 0, 100);
}

export function bestCommuteAverage(routes) {
  const values = routes
    .map((route) => minDefined(route.transit_minutes, route.cycling_minutes))
    .filter((value) => value !== null);
  return values.length ? Math.round(average(values)) : null;
}

export function median(values) {
  const numbers = values
    .filter((value) => value !== null && value !== undefined && Number.isFinite(Number(value)))
    .map(Number)
    .sort((a, b) => a - b);
  if (numbers.length === 0) return null;
  const middle = Math.floor(numbers.length / 2);
  return numbers.length % 2 ? numbers[middle] : Math.round((numbers[middle - 1] + numbers[middle]) / 2);
}

export function minDefined(...values) {
  const numbers = values
    .filter((value) => value !== null && value !== undefined && Number.isFinite(Number(value)))
    .map(Number);
  return numbers.length ? Math.min(...numbers) : null;
}

function average(values) {
  if (values.length === 0) return 45;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}
