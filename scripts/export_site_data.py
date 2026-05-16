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
    "search_name",
    "status",
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

    listings = []
    for row in rows:
        listing = {field: row[field] for field in FIELDS if field in row.keys()}
        listing["route_targets"] = json.loads(row["route_targets_json"] or "[]")
        listing["has_garden"] = has_any(row, ["garden", "patio", "terrace", "outdoor space"])
        listing["has_parking"] = has_any(row, ["parking", "car park", "off street", "off-street", "garage"])
        listings.append(listing)
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


def safe_routing_config(routing: dict) -> dict:
    return {
        "enabled": bool(routing.get("enabled", False)),
        "target_name": routing.get("target_name") or "Target",
        "target_latitude": routing.get("target_latitude"),
        "target_longitude": routing.get("target_longitude"),
        "departure_day": routing.get("departure_day"),
        "departure_time": routing.get("departure_time"),
        "targets": routing.get("targets", []),
    }


def has_any(row: sqlite3.Row, needles: list[str]) -> bool:
    text = " ".join(
        str(row[field] or "")
        for field in ("title", "address", "summary")
        if field in row.keys()
    ).lower()
    return any(needle in text for needle in needles)


if __name__ == "__main__":
    raise SystemExit(main())
