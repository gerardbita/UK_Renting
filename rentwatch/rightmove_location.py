from __future__ import annotations

from dataclasses import dataclass

import requests


RIGHTMOVE_LOCATION_HOST = "https://los.rightmove.co.uk"


class LocationLookupError(RuntimeError):
    pass


@dataclass(slots=True)
class LocationSuggestion:
    id: str
    type: str
    display_name: str

    @property
    def location_identifier(self) -> str:
        return f"{self.type}^{self.id}"


def lookup_rightmove_locations(
    query: str,
    *,
    limit: int = 10,
    include_streets: bool = False,
    timeout_seconds: int = 20,
    user_agent: str = "RentWatch/0.1 personal property monitor",
) -> list[LocationSuggestion]:
    params = {"query": query, "limit": str(limit)}
    if not include_streets:
        params["exclude"] = "STREET"

    try:
        response = requests.get(
            f"{RIGHTMOVE_LOCATION_HOST}/typeahead",
            params=params,
            headers={"User-Agent": user_agent, "Accept": "application/json"},
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        raise LocationLookupError(f"Rightmove location lookup failed: {exc}") from exc
    except ValueError as exc:
        raise LocationLookupError("Rightmove location lookup returned invalid JSON.") from exc

    return [
        LocationSuggestion(
            id=str(item["id"]),
            type=str(item["type"]),
            display_name=str(item["displayName"]),
        )
        for item in payload.get("matches", [])
        if item.get("id") and item.get("type") and item.get("displayName")
    ]
