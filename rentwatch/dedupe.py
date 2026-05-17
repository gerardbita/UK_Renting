from __future__ import annotations

import math
import re
from dataclasses import dataclass
from hashlib import sha1

from .models import Listing


AUTO_MERGE_SCORE = 80


@dataclass(slots=True)
class MatchResult:
    canonical_key: str
    score: int
    reasons: list[str]


def canonical_key_for_listing(listing: Listing) -> str:
    if listing.canonical_key:
        return listing.canonical_key
    return f"property:{listing.source}:{listing.property_id}"


def assign_canonical_keys(
    listings: list[Listing],
    existing_listings: list[Listing],
    *,
    threshold: int = AUTO_MERGE_SCORE,
) -> None:
    existing_by_listing_key = {
        listing.listing_key: listing for listing in existing_listings
    }
    candidates = list(existing_listings)

    for listing in listings:
        existing = existing_by_listing_key.get(listing.listing_key)
        if existing and existing.canonical_key:
            listing.canonical_key = existing.canonical_key
        else:
            match = best_match(listing, candidates, threshold=threshold)
            listing.canonical_key = match.canonical_key
        candidates.append(listing)


def best_match(
    listing: Listing,
    candidates: list[Listing],
    *,
    threshold: int = AUTO_MERGE_SCORE,
) -> MatchResult:
    best: MatchResult | None = None
    for candidate in candidates:
        if candidate.listing_key == listing.listing_key:
            continue
        if candidate.source == listing.source:
            continue
        score, reasons = match_score(listing, candidate)
        if best is None or score > best.score:
            best = MatchResult(
                canonical_key=canonical_key_for_listing(candidate),
                score=score,
                reasons=reasons,
            )

    if best is not None and best.score >= threshold:
        return best
    return MatchResult(
        canonical_key=canonical_key_for_listing(listing),
        score=0,
        reasons=[],
    )


def match_score(left: Listing, right: Listing) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []

    distance = coordinate_distance_m(left, right)
    if distance is not None:
        if distance <= 20:
            score += 45
            reasons.append("coordinates within 20m")
        elif distance <= 50:
            score += 35
            reasons.append("coordinates within 50m")
        elif distance <= 100:
            score += 20
            reasons.append("coordinates within 100m")

    left_postcode = postcode(left)
    right_postcode = postcode(right)
    if left_postcode and right_postcode and left_postcode == right_postcode:
        score += 20
        reasons.append("same postcode")

    if left.bedrooms is not None and right.bedrooms is not None:
        if left.bedrooms == right.bedrooms:
            score += 15
            reasons.append("same bedrooms")
        else:
            score -= 25
            reasons.append("different bedrooms")

    if left.price_pcm is not None and right.price_pcm is not None:
        difference = abs(left.price_pcm - right.price_pcm)
        if difference <= 25:
            score += 15
            reasons.append("rent within GBP25")
        elif difference <= 100:
            score += 10
            reasons.append("rent within GBP100")
        elif difference > 350:
            score -= 10
            reasons.append("rent differs by more than GBP350")

    image_overlap = shared_image_count(left, right)
    if image_overlap:
        score += min(25, 12 + image_overlap * 4)
        reasons.append("shared listing photos")

    title_similarity = token_similarity(
        normalize_text(left.address or left.title),
        normalize_text(right.address or right.title),
    )
    if title_similarity >= 0.75:
        score += 12
        reasons.append("similar address/title")
    elif title_similarity >= 0.5:
        score += 6
        reasons.append("partly similar address/title")

    description_similarity = token_similarity(
        normalize_text(left.summary),
        normalize_text(right.summary),
    )
    if description_similarity >= 0.6:
        score += 8
        reasons.append("similar description")

    return max(0, min(100, score)), reasons


def coordinate_distance_m(left: Listing, right: Listing) -> float | None:
    if (
        left.latitude is None
        or left.longitude is None
        or right.latitude is None
        or right.longitude is None
    ):
        return None
    return haversine_m(left.latitude, left.longitude, right.latitude, right.longitude)


def haversine_m(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    radius_m = 6371000
    phi_a = math.radians(lat_a)
    phi_b = math.radians(lat_b)
    delta_phi = math.radians(lat_b - lat_a)
    delta_lambda = math.radians(lon_b - lon_a)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi_a) * math.cos(phi_b) * math.sin(delta_lambda / 2) ** 2
    )
    return radius_m * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def postcode(listing: Listing) -> str:
    text = " ".join([listing.address, listing.title, listing.summary])
    match = re.search(
        r"\b([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}|[A-Z]{1,2}\d[A-Z\d]?)\b",
        text.upper(),
    )
    return re.sub(r"\s+", "", match.group(1)) if match else ""


def shared_image_count(left: Listing, right: Listing) -> int:
    left_images = {image_fingerprint(url) for url in image_urls(left)}
    right_images = {image_fingerprint(url) for url in image_urls(right)}
    return len(left_images & right_images)


def image_urls(listing: Listing) -> list[str]:
    raw_images = listing.raw.get("image_urls", [])
    if not isinstance(raw_images, list):
        return []
    return [str(url) for url in raw_images if url]


def image_fingerprint(url: str) -> str:
    cleaned = re.sub(r"[_-](?:homepage|small|medium|large)\.[a-z0-9]+$", "", url, flags=re.I)
    cleaned = cleaned.split("?", 1)[0].lower()
    return sha1(cleaned.encode("utf-8")).hexdigest()


def normalize_text(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    value = re.sub(r"\b(flat|apartment|property|london|to|rent|bed|bedroom|bedrooms)\b", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def token_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
