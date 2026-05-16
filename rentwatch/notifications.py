from __future__ import annotations

from dataclasses import dataclass

import requests

from .config import TelegramConfig
from .models import ListingEvent


class NotificationError(RuntimeError):
    pass


@dataclass(slots=True)
class TelegramNotifier:
    config: TelegramConfig
    timeout_seconds: int = 15

    def enabled(self) -> bool:
        return bool(self.config.enabled and self.config.bot_token and self.config.chat_id)

    def send(self, message: str) -> None:
        if not self.enabled():
            return
        url = f"https://api.telegram.org/bot{self.config.bot_token}/sendMessage"
        response = requests.post(
            url,
            json={
                "chat_id": self.config.chat_id,
                "text": message,
                "disable_web_page_preview": False,
            },
            timeout=self.timeout_seconds,
        )
        if response.status_code >= 400:
            raise NotificationError(
                f"Telegram returned HTTP {response.status_code}: {response.text[:200]}"
            )


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

    route_details = []
    if listing.transit_minutes is not None:
        distance = (
            f", {listing.transit_distance_km:g} km"
            if listing.transit_distance_km is not None
            else ""
        )
        route_details.append(f"Transit: {listing.transit_minutes} min{distance}")
    if listing.cycling_minutes is not None:
        distance = (
            f", {listing.cycling_distance_km:g} km"
            if listing.cycling_distance_km is not None
            else ""
        )
        route_details.append(f"Cycle: {listing.cycling_minutes} min{distance}")
    if route_details:
        lines.append(" | ".join(route_details))

    if listing.address and listing.address != listing.title:
        lines.append(listing.address)
    lines.append(listing.url)
    return "\n".join(lines)
