from __future__ import annotations

from dataclasses import dataclass

import requests

from .config import TelegramConfig, TelegramRouteFilterConfig
from .models import Listing, ListingEvent


class NotificationError(RuntimeError):
    pass


@dataclass(slots=True)
class TelegramNotifier:
    config: TelegramConfig
    timeout_seconds: int = 15

    def enabled(self) -> bool:
        return bool(
            self.config.enabled
            and self.config.bot_token
            and self.config.recipient_chat_ids()
        )

    def send(self, message: str) -> None:
        if not self.enabled():
            return
        url = f"https://api.telegram.org/bot{self.config.bot_token}/sendMessage"
        failures = []
        for chat_id in self.config.recipient_chat_ids():
            response = requests.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": message,
                    "disable_web_page_preview": False,
                },
                timeout=self.timeout_seconds,
            )
            if response.status_code >= 400:
                failures.append(
                    f"{chat_id}: HTTP {response.status_code}: {response.text[:200]}"
                )
        if failures:
            raise NotificationError("Telegram send failed: " + "; ".join(failures))


def format_event_message(event: ListingEvent) -> str:
    listing = event.listing
    lines = [
        f"{event_emoji(event)} {event.human_label()} - {event.search_name}",
        listing.title or listing.address or "Untitled listing",
    ]

    if event.event_type == "price_change":
        lines.append(format_price_change(event))
    elif listing.price_text:
        lines.append(listing.price_text)

    details = []
    if listing.bedrooms is not None:
        details.append(f"{listing.bedrooms} bed")
    if listing.bathrooms is not None:
        details.append(f"{listing.bathrooms} bath")
    if listing.size_sqft:
        details.append(f"{listing.size_sqft} sq ft")
    if listing.agent:
        details.append(f"Agent: {listing.agent}")
    if details:
        lines.append(" | ".join(details))

    lines.extend(format_route_lines(listing))

    if listing.address and listing.address != listing.title:
        lines.append(listing.address)
    lines.append(listing.url)
    return "\n".join(lines)


def event_emoji(event: ListingEvent) -> str:
    if event.event_type == "price_change":
        return price_delta(event)[2]
    return {
        "new": "🆕",
        "reactivated": "🔁",
        "removed": "❌",
    }.get(event.event_type, "•")


def price_delta(event: ListingEvent) -> tuple[int | None, float | None, str]:
    """Return (absolute delta, percent delta, emoji) for a price change."""
    new_price = event.listing.price_pcm
    old_price = event.previous_price_pcm
    if not new_price or not old_price:
        return None, None, "💷"
    delta = new_price - old_price
    pct = (delta / old_price) * 100 if old_price else None
    emoji = "📉" if delta < 0 else "📈" if delta > 0 else "💷"
    return delta, pct, emoji


def format_price_change(event: ListingEvent) -> str:
    listing = event.listing
    previous = event.previous_price_text or (
        f"£{event.previous_price_pcm:,} pcm" if event.previous_price_pcm else "?"
    )
    current = listing.price_text or (
        f"£{listing.price_pcm:,} pcm" if listing.price_pcm else "?"
    )
    delta, pct, emoji = price_delta(event)
    if delta is None:
        return f"{previous} -> {current}"
    sign = "-" if delta < 0 else "+"
    pct_text = f", {pct:+.1f}%" if pct is not None else ""
    return f"{previous} -> {current} ({emoji} {sign}£{abs(delta):,}{pct_text})"


def format_digest(events: list[ListingEvent]) -> str:
    """One combined message summarising a poll's notifiable events."""
    if not events:
        return ""

    buckets: dict[str, list[ListingEvent]] = {}
    for event in events:
        buckets.setdefault(event.event_type, []).append(event)

    headline_parts = []
    for event_type, label in (
        ("new", "🆕 new"),
        ("reactivated", "🔁 returned"),
        ("price_change", "📉 price"),
        ("removed", "❌ removed"),
    ):
        count = len(buckets.get(event_type, []))
        if count:
            headline_parts.append(f"{count} {label}")
    search_names = sorted({event.search_name for event in events})
    title = " · ".join(search_names) if len(search_names) == 1 else "RentWatch"
    lines = [f"RentWatch update — {title}", " | ".join(headline_parts), ""]

    shown = 0
    for event in events:
        if shown >= 15:
            lines.append(f"...and {len(events) - shown} more")
            break
        listing = event.listing
        bits = [f"{event_emoji(event)} {listing.title or listing.address or 'Listing'}"]
        if event.event_type == "price_change":
            delta, pct, _ = price_delta(event)
            if delta is not None:
                sign = "-" if delta < 0 else "+"
                bits.append(f"{sign}£{abs(delta):,}")
        elif listing.price_text:
            bits.append(listing.price_text)
        commute = best_commute_summary(listing)
        if commute:
            bits.append(commute)
        lines.append(" — ".join(bits))
        lines.append(listing.url)
        shown += 1

    return "\n".join(line for line in lines if line is not None)


def best_commute_summary(listing: Listing) -> str:
    targets = listing.route_targets or []
    parts = []
    for target in targets[:2]:
        minutes = optional_int(target.get("transit_minutes"))
        if minutes is not None:
            name = str(target.get("name") or "T").split()[0]
            parts.append(f"{name} {minutes}m")
    return " / ".join(parts)


def listing_matches_route_filters(
    listing: Listing,
    route_filters: list[TelegramRouteFilterConfig],
) -> bool:
    if not route_filters:
        return True
    return any(
        route_filter_matches_listing(listing, route_filter)
        for route_filter in route_filters
    )


def route_filter_matches_listing(
    listing: Listing,
    route_filter: TelegramRouteFilterConfig,
) -> bool:
    route_target = find_matching_route_target(listing, route_filter)
    if route_target is None:
        return False

    if route_filter.max_transit_minutes is not None:
        transit_minutes = optional_int(route_target.get("transit_minutes"))
        if transit_minutes is None or transit_minutes > route_filter.max_transit_minutes:
            return False

    if route_filter.max_cycling_minutes is not None:
        cycling_minutes = optional_int(route_target.get("cycling_minutes"))
        if cycling_minutes is None or cycling_minutes > route_filter.max_cycling_minutes:
            return False

    return True


def find_matching_route_target(
    listing: Listing,
    route_filter: TelegramRouteFilterConfig,
) -> dict[str, object] | None:
    route_targets: list[dict[str, object]] = list(listing.route_targets)
    if not route_targets and (
        listing.transit_minutes is not None or listing.cycling_minutes is not None
    ):
        route_targets.append(
            {
                "name": "",
                "latitude": listing.route_target_latitude,
                "longitude": listing.route_target_longitude,
                "transit_minutes": listing.transit_minutes,
                "transit_distance_km": listing.transit_distance_km,
                "cycling_minutes": listing.cycling_minutes,
                "cycling_distance_km": listing.cycling_distance_km,
            }
        )

    return next(
        (
            target
            for target in route_targets
            if route_target_matches_filter(target, route_filter)
        ),
        None,
    )


def route_target_matches_filter(
    target: dict[str, object],
    route_filter: TelegramRouteFilterConfig,
) -> bool:
    target_name = str(target.get("name") or "").strip().lower()
    filter_name = route_filter.target_name.strip().lower()
    name_matches = bool(filter_name and target_name == filter_name)

    if (
        route_filter.target_latitude is not None
        and route_filter.target_longitude is not None
    ):
        try:
            target_latitude = float(target.get("latitude"))
            target_longitude = float(target.get("longitude"))
        except (TypeError, ValueError):
            return name_matches
        return (
            abs(target_latitude - route_filter.target_latitude) < 0.00001
            and abs(target_longitude - route_filter.target_longitude) < 0.00001
        )

    if filter_name:
        return name_matches
    return True


def format_route_lines(listing: Listing) -> list[str]:
    if listing.route_targets:
        lines = []
        for target in listing.route_targets:
            target_name = str(target.get("name") or "Target")
            route_details = [
                format_mode_route(
                    "Transit",
                    target.get("transit_minutes"),
                    target.get("transit_distance_km"),
                ),
                format_mode_route(
                    "Cycle",
                    target.get("cycling_minutes"),
                    target.get("cycling_distance_km"),
                ),
            ]
            available_details = [detail for detail in route_details if detail]
            if available_details:
                lines.append(f"{target_name}: " + " | ".join(available_details))
        if lines:
            return lines

    route_details = [
        format_mode_route(
            "Transit",
            listing.transit_minutes,
            listing.transit_distance_km,
        ),
        format_mode_route(
            "Cycle",
            listing.cycling_minutes,
            listing.cycling_distance_km,
        ),
    ]
    available_details = [detail for detail in route_details if detail]
    return [" | ".join(available_details)] if available_details else []


def format_mode_route(
    label: str,
    minutes: object,
    distance_km: object,
) -> str:
    minutes_value = optional_int(minutes)
    if minutes_value is None:
        return ""
    distance_value = optional_float(distance_km)
    distance = f", {distance_value:g} km" if distance_value is not None else ""
    return f"{label}: {minutes_value} min{distance}"


def optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
