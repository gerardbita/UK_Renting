from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "rentwatch.sqlite3"
CONFIG_PATH = ROOT / "config.json"
OUTPUT_PATH = ROOT / "docs" / "data" / "listings.json"
WEB_OUTPUT_PATH = ROOT / "web" / "public" / "data" / "listings.json"


FIELDS = [
    "canonical_key",
    "search_name",
    "status",
    "source",
    "source_count",
    "source_names",
    "sources",
    "price_pcm",
    "price_text",
    "bedrooms",
    "has_garden",
    "has_parking",
    "latitude",
    "longitude",
    "transit_minutes",
    "transit_distance_km",
    "cycling_minutes",
    "cycling_distance_km",
    "route_target_latitude",
    "route_target_longitude",
    "route_targets",
    "address",
    "agent",
    "summary",
    "title",
    "url",
    "search_first_seen_at",
    "search_last_seen_at",
]


def main() -> int:
    if not DB_PATH.exists():
        raise SystemExit(f"Missing database: {DB_PATH}")

    config = load_config()
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    ensure_site_columns(con)
    rows = con.execute(
        """
        SELECT
            sl.search_name,
            sl.status,
            sl.first_seen_at AS search_first_seen_at,
            sl.last_seen_at AS search_last_seen_at,
            l.price_pcm,
            l.price_text,
            l.bedrooms,
            l.summary,
            l.latitude,
            l.longitude,
            l.transit_minutes,
            l.transit_distance_km,
            l.cycling_minutes,
            l.cycling_distance_km,
            l.route_target_latitude,
            l.route_target_longitude,
            l.route_targets_json,
            l.listing_key,
            l.source,
            l.property_id,
            l.canonical_key,
            l.raw_json,
            l.address,
            l.agent,
            l.title,
            l.url
        FROM search_listings sl
        JOIN listings l ON l.listing_key = sl.listing_key
        ORDER BY
            CASE sl.status WHEN 'active' THEN 0 ELSE 1 END,
            l.transit_minutes IS NULL,
            l.transit_minutes,
            l.price_pcm,
            l.address
        """
    ).fetchall()
    con.close()

    grouped = {}
    for row in rows:
        canonical_key = row["canonical_key"] or row["listing_key"]
        group_key = (row["search_name"], canonical_key)
        grouped.setdefault(group_key, []).append(row)

    listings = []
    for (_, canonical_key), group in grouped.items():
        primary = choose_primary_row(group)
        listing = {field: primary[field] for field in FIELDS if field in primary.keys()}
        listing["canonical_key"] = canonical_key
        listing["status"] = "active" if any(row["status"] == "active" for row in group) else "removed"
        listing["search_first_seen_at"] = min(row["search_first_seen_at"] for row in group)
        listing["search_last_seen_at"] = max(row["search_last_seen_at"] for row in group)
        listing["route_targets"] = json.loads(primary["route_targets_json"] or "[]")
        listing["has_garden"] = any(has_any(row, ["garden", "patio", "terrace", "outdoor space"]) for row in group)
        listing["has_parking"] = any(has_any(row, ["parking", "car park", "off street", "off-street", "garage"]) for row in group)
        listing["sources"] = [source_payload(row) for row in sorted(group, key=source_sort_key)]
        listing["source_count"] = len(listing["sources"])
        listing["source_names"] = [source["source"] for source in listing["sources"]]
        listing["source"] = listing["sources"][0]["source"] if listing["sources"] else primary["source"]
        best_price = best_price_row(group)
        if best_price is not None:
            listing["price_pcm"] = best_price["price_pcm"]
            listing["price_text"] = best_price["price_text"]
        listings.append(listing)

    listings.sort(
        key=lambda listing: (
            0 if listing["status"] == "active" else 1,
            listing.get("transit_minutes") is None,
            listing.get("transit_minutes") or 9999,
            listing.get("price_pcm") or 999999,
            listing.get("address") or "",
        )
    )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "routing": safe_routing_config(config.get("routing", {})),
        "listings": listings,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    output_json = json.dumps(payload, indent=2)
    OUTPUT_PATH.write_text(output_json, encoding="utf-8")
    if WEB_OUTPUT_PATH.parent.parent.exists():
        WEB_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        WEB_OUTPUT_PATH.write_text(output_json, encoding="utf-8")
    print(f"Wrote {len(listings)} listings to {OUTPUT_PATH}")
    return 0


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    # Do not export notification credentials or any other local secrets.
    return {"routing": data.get("routing", {})}


def ensure_site_columns(con: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in con.execute("PRAGMA table_info(listings)").fetchall()
    }
    if "route_targets_json" not in columns:
        con.execute("ALTER TABLE listings ADD COLUMN route_targets_json TEXT")
        con.commit()
    if "canonical_key" not in columns:
        con.execute("ALTER TABLE listings ADD COLUMN canonical_key TEXT")
        con.commit()


def choose_primary_row(rows: list[sqlite3.Row]) -> sqlite3.Row:
    return sorted(rows, key=primary_sort_key)[0]


def primary_sort_key(row: sqlite3.Row) -> tuple:
    route_targets = json.loads(row["route_targets_json"] or "[]")
    route_count = sum(
        1
        for route in route_targets
        if route.get("transit_minutes") is not None or route.get("cycling_minutes") is not None
    )
    return (
        0 if row["status"] == "active" else 1,
        -route_count,
        0 if row["latitude"] is not None and row["longitude"] is not None else 1,
        0 if row["price_pcm"] is not None else 1,
        source_sort_index(row["source"]),
        row["listing_key"],
    )


def best_price_row(rows: list[sqlite3.Row]) -> sqlite3.Row | None:
    candidates = [
        row
        for row in rows
        if row["status"] == "active" and row["price_pcm"] is not None
    ]
    if not candidates:
        candidates = [row for row in rows if row["price_pcm"] is not None]
    return min(candidates, key=lambda row: row["price_pcm"]) if candidates else None


def source_payload(row: sqlite3.Row) -> dict:
    return {
        "source": row["source"],
        "listing_key": row["listing_key"],
        "property_id": row["property_id"],
        "url": row["url"],
        "status": row["status"],
        "price_text": row["price_text"],
        "price_pcm": row["price_pcm"],
        "agent": row["agent"],
        "title": row["title"],
        "address": row["address"],
        "search_first_seen_at": row["search_first_seen_at"],
        "search_last_seen_at": row["search_last_seen_at"],
    }


def source_sort_key(row: sqlite3.Row) -> tuple:
    return (source_sort_index(row["source"]), row["listing_key"])


def source_sort_index(source: str) -> int:
    order = {"rightmove": 0, "zoopla": 1}
    return order.get(source, 99)


def safe_routing_config(routing: dict) -> dict:
    data = {
        "enabled": bool(routing.get("enabled", False)),
        "departure_day": routing.get("departure_day"),
        "departure_time": routing.get("departure_time"),
        "targets": routing.get("targets", []),
    }
    if not data["targets"]:
        data.update(
            {
                "target_name": routing.get("target_name") or "Target",
                "target_latitude": routing.get("target_latitude"),
                "target_longitude": routing.get("target_longitude"),
            }
        )
    return data


def has_any(row: sqlite3.Row, needles: list[str]) -> bool:
    text = " ".join(
        str(row[field] or "")
        for field in ("title", "address", "summary")
        if field in row.keys()
    ).lower()
    return any(needle in text for needle in needles)


if __name__ == "__main__":
    raise SystemExit(main())
