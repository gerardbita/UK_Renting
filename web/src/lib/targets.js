export const DEFAULT_TARGETS = [
  {
    name: "Noémie's work",
    latitude: 51.5209823,
    longitude: -0.1770073,
  },
  {
    name: "Gerard's work",
    latitude: 51.4928449,
    longitude: -0.2198001,
  },
];

export function resolveTargets(routing = {}) {
  const configured = Array.isArray(routing.targets) ? routing.targets : [];
  const targets = configured
    .filter((target) => isFiniteNumber(target.latitude) && isFiniteNumber(target.longitude))
    .map((target, index) => ({
      name: target.name || `Target ${index + 1}`,
      latitude: Number(target.latitude),
      longitude: Number(target.longitude),
    }));

  if (
    targets.length === 0 &&
    isFiniteNumber(routing.target_latitude) &&
    isFiniteNumber(routing.target_longitude)
  ) {
    targets.push({
      name: routing.target_name || DEFAULT_TARGETS[0].name,
      latitude: Number(routing.target_latitude),
      longitude: Number(routing.target_longitude),
    });
  }

  for (const fallback of DEFAULT_TARGETS) {
    const exists = targets.some(
      (target) =>
        Math.abs(target.latitude - fallback.latitude) < 0.00001 &&
        Math.abs(target.longitude - fallback.longitude) < 0.00001,
    );
    if (!exists) targets.push(fallback);
  }

  return targets.slice(0, 2);
}

export function routesForListing(listing, targets) {
  const routeTargets = Array.isArray(listing.route_targets) ? listing.route_targets : [];

  return targets.map((target, index) => {
    const exact = routeTargets.find(
      (route) =>
        isFiniteNumber(route.latitude) &&
        isFiniteNumber(route.longitude) &&
        Math.abs(Number(route.latitude) - target.latitude) < 0.00001 &&
        Math.abs(Number(route.longitude) - target.longitude) < 0.00001,
    );
    const route = exact || routeTargets[index] || {};

    if (index === 0 && routeTargets.length === 0) {
      return {
        ...target,
        transit_minutes: listing.transit_minutes,
        transit_distance_km: listing.transit_distance_km,
        cycling_minutes: listing.cycling_minutes,
        cycling_distance_km: listing.cycling_distance_km,
      };
    }

    return {
      ...target,
      transit_minutes: route.transit_minutes ?? null,
      transit_distance_km: route.transit_distance_km ?? null,
      cycling_minutes: route.cycling_minutes ?? null,
      cycling_distance_km: route.cycling_distance_km ?? null,
    };
  });
}

function isFiniteNumber(value) {
  return Number.isFinite(Number(value));
}
