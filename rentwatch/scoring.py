"""Canonical balanced-score model shared by the exporter and notifications.

The score answers one question for a two-commuter household: *how good a base
is this home, balancing both commutes against rent and quality?* It deliberately
penalises the **worse** of the two commutes (both people must get to work) rather
than the average, so a flat that is 15 minutes for one person and 70 for the other
does not look as good as a balanced 40/40.

All functions are pure and operate on plain numbers/dicts so they can be reused
from the export pipeline (where amenity flags are derived) and from anywhere a
``Listing`` is available.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Neutral commute (minutes) assumed when a listing has no route data at all, so a
# missing-route listing scores below a known-good commute but is not zeroed out.
NEUTRAL_COMMUTE_MINUTES = 50.0


@dataclass(slots=True)
class ScoreInput:
    commutes: list[float | None]  # best (transit/cycle) minutes per target
    price_pcm: int | None = None
    price_percentile: float | None = None  # 0 = cheapest in set, 1 = priciest
    let_agreed: bool = False
    size_sqft: int | None = None
    has_garden: bool = False
    has_parking: bool = False
    fresh: bool = False
    weights: tuple[float, float] = (1.0, 1.0)


@dataclass(slots=True)
class ScoreResult:
    score: int
    breakdown: dict[str, float] = field(default_factory=dict)


def best_commute_minutes(
    transit_minutes: float | None, cycling_minutes: float | None
) -> float | None:
    values = [v for v in (transit_minutes, cycling_minutes) if _is_number(v)]
    return min(values) if values else None


def price_percentiles(prices: list[int | None]) -> dict[int, float]:
    """Map each distinct price to its percentile rank within the active set."""
    valid = sorted(p for p in prices if _is_number(p))
    if not valid:
        return {}
    n = len(valid)
    ranks: dict[int, float] = {}
    for index, price in enumerate(valid):
        # Average rank for ties keeps the mapping stable and monotonic.
        ranks.setdefault(price, index / (n - 1) if n > 1 else 0.0)
    return ranks


def balanced_score(data: ScoreInput) -> ScoreResult:
    weights = _normalize_weights(data.weights, len(data.commutes))
    known = [(w, c) for w, c in zip(weights, data.commutes) if _is_number(c)]
    missing = len(data.commutes) - len(known)

    if known:
        total_weight = sum(w for w, _ in known) or 1.0
        weighted_avg = sum(w * c for w, c in known) / total_weight
        worst = max(c for _, c in known)
        # Bottleneck-biased effective commute: the slower commute dominates.
        effective = 0.6 * worst + 0.4 * weighted_avg
        values = [c for _, c in known]
        imbalance = max(values) - min(values) if len(values) > 1 else 0.0
    else:
        effective = NEUTRAL_COMMUTE_MINUTES
        imbalance = 0.0

    breakdown: dict[str, float] = {}
    score = 100.0

    breakdown["commute"] = -round(effective * 1.4, 1)
    score += breakdown["commute"]

    breakdown["imbalance"] = -round(imbalance * 0.5, 1)
    score += breakdown["imbalance"]

    if data.price_percentile is not None:
        breakdown["price"] = -round(_clamp(data.price_percentile, 0.0, 1.0) * 18.0, 1)
        score += breakdown["price"]

    if missing:
        breakdown["missing_routes"] = -float(missing * 8)
        score += breakdown["missing_routes"]

    if data.let_agreed:
        breakdown["let_agreed"] = -25.0
        score += breakdown["let_agreed"]

    amenities = (4.0 if data.has_garden else 0.0) + (3.0 if data.has_parking else 0.0)
    if amenities:
        breakdown["amenities"] = amenities
        score += amenities

    size_bonus = _size_bonus(data.size_sqft)
    if size_bonus:
        breakdown["size"] = size_bonus
        score += size_bonus

    if data.fresh:
        breakdown["freshness"] = 4.0
        score += 4.0

    return ScoreResult(score=int(round(_clamp(score, 0.0, 100.0))), breakdown=breakdown)


def _size_bonus(size_sqft: int | None) -> float:
    if not _is_number(size_sqft):
        return 0.0
    # +0 at 450 sq ft, capped at +6 around 900 sq ft.
    return round(_clamp((size_sqft - 450) / 75.0, 0.0, 6.0), 1)


def _normalize_weights(weights: tuple[float, float], count: int) -> list[float]:
    base = list(weights) if weights else []
    while len(base) < count:
        base.append(1.0)
    return [max(0.0, float(w)) for w in base[:count]] or [1.0] * count


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
