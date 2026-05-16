from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode


RIGHTMOVE_RENT_URL = "https://www.rightmove.co.uk/property-to-rent/find.html"


@dataclass(slots=True)
class RightmoveUrlOptions:
    search_location: str
    location_identifier: str = ""
    radius: float | None = None
    min_price_pcm: int | None = None
    max_price_pcm: int | None = None
    min_bedrooms: int | None = None
    max_bedrooms: int | None = None
    property_types: list[str] = field(default_factory=list)
    dont_show: list[str] = field(default_factory=list)
    must_have: list[str] = field(default_factory=list)
    furnish_types: list[str] = field(default_factory=list)
    include_let_agreed: bool = False
    lookup_location_identifier: bool = True
    sort_type: int = 6

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RightmoveUrlOptions":
        return cls(
            search_location=str(data["search_location"]),
            location_identifier=str(data.get("location_identifier", "")),
            radius=_optional_float(data.get("radius")),
            min_price_pcm=_optional_int(data.get("min_price_pcm")),
            max_price_pcm=_optional_int(data.get("max_price_pcm")),
            min_bedrooms=_optional_int(data.get("min_bedrooms")),
            max_bedrooms=_optional_int(data.get("max_bedrooms")),
            property_types=[str(item) for item in data.get("property_types", [])],
            dont_show=[str(item) for item in data.get("dont_show", [])],
            must_have=[str(item) for item in data.get("must_have", [])],
            furnish_types=[str(item) for item in data.get("furnish_types", [])],
            include_let_agreed=bool(data.get("include_let_agreed", False)),
            lookup_location_identifier=bool(data.get("lookup_location_identifier", True)),
            sort_type=int(data.get("sort_type", 6)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "search_location": self.search_location,
            "location_identifier": self.location_identifier,
            "radius": self.radius,
            "min_price_pcm": self.min_price_pcm,
            "max_price_pcm": self.max_price_pcm,
            "min_bedrooms": self.min_bedrooms,
            "max_bedrooms": self.max_bedrooms,
            "property_types": self.property_types,
            "dont_show": self.dont_show,
            "must_have": self.must_have,
            "furnish_types": self.furnish_types,
            "include_let_agreed": self.include_let_agreed,
            "lookup_location_identifier": self.lookup_location_identifier,
            "sort_type": self.sort_type,
        }


def build_rightmove_url(options: RightmoveUrlOptions) -> str:
    params: list[tuple[str, str]] = [
        ("searchLocation", options.search_location),
        ("rent", "To rent"),
        ("index", "0"),
        ("sortType", str(options.sort_type)),
        ("channel", "RENT"),
        ("transactionType", "LETTING"),
    ]

    if options.location_identifier:
        params.extend(
            [
                ("useLocationIdentifier", "true"),
                ("locationIdentifier", options.location_identifier),
                ("displayLocationIdentifier", "undefined"),
            ]
        )
    if options.radius is not None:
        params.append(("radius", _format_float(options.radius)))
    if options.include_let_agreed:
        params.append(("_includeLetAgreed", "on"))
    if options.min_price_pcm is not None:
        params.append(("minPrice", str(options.min_price_pcm)))
    if options.max_price_pcm is not None:
        params.append(("maxPrice", str(options.max_price_pcm)))
    if options.min_bedrooms is not None:
        params.append(("minBedrooms", str(options.min_bedrooms)))
    if options.max_bedrooms is not None:
        params.append(("maxBedrooms", str(options.max_bedrooms)))
    if options.property_types:
        params.append(("propertyTypes", ",".join(options.property_types)))
    if options.dont_show:
        params.append(("dontShow", ",".join(options.dont_show)))
    if options.must_have:
        params.append(("mustHave", ",".join(options.must_have)))
    if options.furnish_types:
        params.append(("furnishTypes", ",".join(options.furnish_types)))

    return f"{RIGHTMOVE_RENT_URL}?{urlencode(params)}"


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _format_float(value: float) -> str:
    return str(int(value)) if value.is_integer() else str(value)
