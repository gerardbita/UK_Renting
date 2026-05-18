from __future__ import annotations

from dataclasses import dataclass

import requests

from .config import TelegramConfig
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
        f"{event.human_label()} - {event.search_name}",
        listing.title or listing.address or "Untitled listing",
    ]

    if listing.price_text:
        if event.event_type == "price_change" and event.previous_price_text:
            lines.append(f"{event.previous_price_text} -> {listing.price_text}")
        else:
            lines.append(listing.price_text)

    details = []
    if listing.bedrooms is not None:
        details.append(f"{listing.bedrooms} bed")
    if listing.agent:
        details.append(f"Agent: {listing.agent}")
    if details:
        lines.append(" | ".join(details))

    lines.extend(format_route_lines(listing))

    if listing.address and listing.address != listing.title:
        lines.append(listing.address)
    lines.append(listing.url)
    return "\n".join(lines)


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
