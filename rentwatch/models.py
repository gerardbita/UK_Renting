from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Listing:
    source: str
    property_id: str
    url: str
    address: str = ""
    price_text: str = ""
    price_pcm: int | None = None
    bedrooms: int | None = None
    latitude: float | None = None
    longitude: float | None = None
    transit_minutes: int | None = None
    transit_distance_km: float | None = None
    cycling_minutes: int | None = None
    cycling_distance_km: float | None = None
    route_target_latitude: float | None = None
    route_target_longitude: float | None = None
    route_targets: list[dict[str, Any]] = field(default_factory=list)
    route_updated_at: str = ""
    agent: str = ""
    summary: str = ""
    title: str = ""
    canonical_key: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def listing_key(self) -> str:
        return f"{self.source}:{self.property_id}"

    @property
    def searchable_text(self) -> str:
        return " ".join(
            part
            for part in [
                self.address,
                self.price_text,
                self.agent,
                self.summary,
                self.title,
            ]
            if part
        ).lower()

    def snapshot(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "property_id": self.property_id,
            "url": self.url,
            "address": self.address,
            "price_text": self.price_text,
            "price_pcm": self.price_pcm,
            "bedrooms": self.bedrooms,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "agent": self.agent,
            "summary": self.summary,
            "title": self.title,
            "canonical_key": self.canonical_key,
        }


@dataclass(slots=True)
class ListingEvent:
    event_type: str
    search_name: str
    listing: Listing
    previous_price_text: str | None = None
    previous_price_pcm: int | None = None

    def human_label(self) -> str:
        labels = {
            "new": "New listing",
            "price_change": "Price change",
            "reactivated": "Listing returned",
            "removed": "Listing removed",
        }
        return labels.get(self.event_type, self.event_type.replace("_", " ").title())
