from __future__ import annotations

import json
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rentwatch.scoring import (  # noqa: E402
    ScoreInput,
    balanced_score,
    best_commute_minutes,
    price_percentiles,
)

DB_PATH = ROOT / "rentwatch.sqlite3"
CONFIG_PATH = ROOT / "config.json"
OUTPUT_PATH = ROOT / "docs" / "data" / "listings.json"
WEB_OUTPUT_PATH = ROOT / "web" / "public" / "data" / "listings.json"

# Listings shown on the dashboard. Removed listings stay in the DB but are not
# shipped to the browser (they only inflate the payload and git history).
EXPORTED_STATUSES = ("active", "out_of_search")

MAX_GALLERY_IMAGES = 8
MAX_PRICE_HISTORY_POINTS = 16


def main() -> int:
    if not DB_PATH.exists():
        raise SystemExit(f"Missing database: {DB_PATH}")

    config = load_config()
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    ensure_site_columns(con)

    counts = status_counts(con)
    rows = con.execute(
        f"""
        SELECT
            sl.search_name,
            sl.status,
            sl.first_seen_at AS search_first_seen_at,
            sl.last_seen_at AS search_last_seen_at,
            l.*
        FROM search_listings sl
        JOIN listings l ON l.listing_key = sl.listing_key
        WHERE sl.status IN ({",".join("?" * len(EXPORTED_STATUSES))})
        ORDER BY l.price_pcm, l.address
        """,
        EXPORTED_STATUSES,
    ).fetchall()

    grouped: dict[tuple, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        canonical_key = row["canonical_key"] or row["listing_key"]
        grouped[(row["search_name"], canonical_key)].append(row)

    price_history = load_price_history(con, [row["listing_key"] for row in rows])
    con.close()

    listings = [
        build_listing(canonical_key, group, price_history)
        for (_, canonical_key), group in grouped.items()
    ]

    # Score against the live market: percentile rank within the active set.
    active_prices = [
        listing["price_pcm"]
        for listing in listings
        if listing["status"] == "active" and listing.get("price_pcm")
    ]
    percentiles = price_percentiles(active_prices)
    for listing in listings:
        apply_score(listing, percentiles)

    listings.sort(key=sort_key)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "routing": safe_routing_config(config.get("routing", {})),
        "meta": build_meta(listings, counts),
        "listings": [slim(listing) for listing in listings],
    }

    output_json = json.dumps(payload, separators=(",", ":"))
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(output_json, encoding="utf-8")
    if WEB_OUTPUT_PATH.parent.parent.exists():
        WEB_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        WEB_OUTPUT_PATH.write_text(output_json, encoding="utf-8")

    size_kb = len(output_json.encode("utf-8")) / 1024
    print(
        f"Wrote {len(listings)} listings "
        f"({counts.get('active', 0)} active, {counts.get('out_of_search', 0)} out-of-search; "
        f"{counts.get('removed', 0)} removed not exported) to {OUTPUT_PATH} [{size_kb:,.0f} KB]"
    )
    return 0


def build_listing(
    canonical_key: str,
    group: list[sqlite3.Row],
    price_history: dict[str, list[dict]],
) -> dict:
    primary = choose_primary_row(group)
    status = grouped_status(group)

    images = json_list(primary["image_urls"] if "image_urls" in primary.keys() else None)
    if not images:
        images = json_list(primary["image_urls_json"]) if "image_urls_json" in primary.keys() else []
    main_image = (primary["main_image"] if "main_image" in primary.keys() else "") or (
        images[0] if images else ""
    )

    listing = {
        "canonical_key": canonical_key,
        "search_name": primary["search_name"],
        "status": status,
        "price_pcm": primary["price_pcm"],
        "price_text": primary["price_text"],
        "bedrooms": primary["bedrooms"],
        "bathrooms": col(primary, "bathrooms"),
        "size_sqft": col(primary, "size_sqft"),
        "property_subtype": col(primary, "property_subtype") or "",
        "latitude": primary["latitude"],
        "longitude": primary["longitude"],
        "transit_minutes": primary["transit_minutes"],
        "transit_distance_km": round2(primary["transit_distance_km"]),
        "cycling_minutes": primary["cycling_minutes"],
        "cycling_distance_km": round2(primary["cycling_distance_km"]),
        "route_targets": json_list(primary["route_targets_json"]),
        "address": primary["address"],
        "agent": primary["agent"],
        "summary": primary["summary"],
        "title": primary["title"],
        "url": primary["url"],
        "main_image": main_image,
        "images": images[:MAX_GALLERY_IMAGES],
        "key_features": json_list(col(primary, "key_features_json"))[:6],
        "let_agreed": bool(col(primary, "let_agreed")),
        "first_listed_date": col(primary, "first_listed_date") or "",
        "added_or_reduced": col(primary, "added_or_reduced") or "",
        "update_reason": col(primary, "update_reason") or "",
        "available_date": col(primary, "available_date") or "",
        "epc_rating": col(primary, "epc_rating") or "",
        "deposit_pcm": col(primary, "deposit_pcm"),
        "council_tax_band": col(primary, "council_tax_band") or "",
        "search_first_seen_at": min(row["search_first_seen_at"] for row in group),
        "search_last_seen_at": max(row["search_last_seen_at"] for row in group),
    }
    listing["freshness"] = freshness_label(listing)
    listing["has_garden"] = any(
        has_any(row, ["garden", "patio", "terrace", "outdoor space"]) for row in group
    )
    listing["has_parking"] = any(
        has_any(row, ["parking", "car park", "off street", "off-street", "garage"])
        for row in group
    )
    listing["sources"] = [source_payload(row) for row in sorted(group, key=source_sort_key)]
    listing["source_count"] = len(listing["sources"])
    listing["source_names"] = [source["source"] for source in listing["sources"]]
    listing["source"] = listing["sources"][0]["source"] if listing["sources"] else primary["source"]

    best_price = best_price_row(group)
    if best_price is not None:
        listing["price_pcm"] = best_price["price_pcm"]
        listing["price_text"] = best_price["price_text"]

    if status == "active":
        history = merge_price_history(group, price_history)
        if len(history) > 1:
            listing["price_history"] = history

    return listing


def apply_score(listing: dict, percentiles: dict[int, float]) -> None:
    routes = listing.get("route_targets") or []
    if routes:
        commutes = [
            best_commute_minutes(route.get("transit_minutes"), route.get("cycling_minutes"))
            for route in routes
        ]
    else:
        commutes = [
            best_commute_minutes(listing.get("transit_minutes"), listing.get("cycling_minutes"))
        ]
    result = balanced_score(
        ScoreInput(
            commutes=commutes,
            price_pcm=listing.get("price_pcm"),
            price_percentile=percentiles.get(listing.get("price_pcm")),
            let_agreed=listing.get("let_agreed", False),
            size_sqft=listing.get("size_sqft"),
            has_garden=listing.get("has_garden", False),
            has_parking=listing.get("has_parking", False),
            fresh=listing.get("freshness") in {"new", "reduced"},
        )
    )
    listing["score"] = result.score
    listing["score_breakdown"] = {k: v for k, v in result.breakdown.items() if v}


def build_meta(listings: list[dict], counts: dict[str, int]) -> dict:
    active = [item for item in listings if item["status"] == "active"]
    prices = sorted(item["price_pcm"] for item in active if item.get("price_pcm"))
    scores = [item["score"] for item in active if item.get("score") is not None]
    return {
        "counts": {
            "active": counts.get("active", 0),
            "out_of_search": counts.get("out_of_search", 0),
            "removed": counts.get("removed", 0),
            "total": sum(counts.values()),
            "exported": len(listings),
            "with_photos": sum(1 for item in listings if item.get("main_image")),
        },
        "price": {
            "min": prices[0] if prices else None,
            "median": prices[len(prices) // 2] if prices else None,
            "max": prices[-1] if prices else None,
        },
        "freshness": {
            "new": sum(1 for item in active if item.get("freshness") == "new"),
            "reduced": sum(1 for item in active if item.get("freshness") == "reduced"),
        },
        "best_score": max(scores) if scores else None,
    }


def freshness_label(listing: dict) -> str | None:
    reason = (listing.get("update_reason") or "").lower()
    blurb = (listing.get("added_or_reduced") or "").lower()
    if "reduced" in reason or "reduced" in blurb:
        return "reduced"
    if reason in {"new", "new_price"} or "added today" in blurb or "new today" in blurb:
        return "new"
    return None


def load_price_history(con: sqlite3.Connection, listing_keys: list[str]) -> dict[str, list[dict]]:
    if not listing_keys:
        return {}
    history: dict[str, list[dict]] = defaultdict(list)
    unique_keys = list(dict.fromkeys(listing_keys))
    chunk = 400
    for start in range(0, len(unique_keys), chunk):
        batch = unique_keys[start : start + chunk]
        placeholders = ",".join("?" * len(batch))
        for row in con.execute(
            f"""
            SELECT listing_key, seen_at, price_pcm
            FROM price_history
            WHERE listing_key IN ({placeholders}) AND price_pcm IS NOT NULL
            ORDER BY seen_at
            """,
            batch,
        ):
            history[row["listing_key"]].append({"t": row["seen_at"], "p": row["price_pcm"]})
    return history


def merge_price_history(group: list[sqlite3.Row], history: dict[str, list[dict]]) -> list[dict]:
    points: list[dict] = []
    for row in group:
        points.extend(history.get(row["listing_key"], []))
    points.sort(key=lambda point: point["t"])
    # Collapse consecutive identical prices into change points only.
    collapsed: list[dict] = []
    for point in points:
        if not collapsed or collapsed[-1]["p"] != point["p"]:
            collapsed.append(point)
    return collapsed[-MAX_PRICE_HISTORY_POINTS:]


def slim(listing: dict) -> dict:
    """Drop empty values to keep the payload (and git history) small."""
    out = {}
    for key, value in listing.items():
        if value in (None, "", [], {}):
            continue
        out[key] = value
    return out


def status_counts(con: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for row in con.execute(
        "SELECT status, COUNT(*) AS n FROM search_listings GROUP BY status"
    ):
        counts[row["status"]] += row["n"]
    return dict(counts)


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    # Never export notification credentials or any other local secrets.
    return {"routing": data.get("routing", {})}


def ensure_site_columns(con: sqlite3.Connection) -> None:
    existing = {row["name"] for row in con.execute("PRAGMA table_info(listings)").fetchall()}
    wanted = {
        "route_targets_json": "TEXT",
        "canonical_key": "TEXT",
        "image_urls_json": "TEXT",
        "main_image": "TEXT",
        "bathrooms": "INTEGER",
        "property_subtype": "TEXT",
        "size_sqft": "INTEGER",
        "let_agreed": "INTEGER",
        "first_listed_date": "TEXT",
        "added_or_reduced": "TEXT",
        "update_reason": "TEXT",
        "available_date": "TEXT",
        "key_features_json": "TEXT",
        "epc_rating": "TEXT",
        "deposit_pcm": "INTEGER",
        "council_tax_band": "TEXT",
    }
    changed = False
    for column, column_type in wanted.items():
        if column not in existing:
            con.execute(f"ALTER TABLE listings ADD COLUMN {column} {column_type}")
            changed = True
    if changed:
        con.commit()


def choose_primary_row(rows: list[sqlite3.Row]) -> sqlite3.Row:
    return sorted(rows, key=primary_sort_key)[0]


def grouped_status(rows: list[sqlite3.Row]) -> str:
    statuses = {row["status"] for row in rows}
    if "active" in statuses:
        return "active"
    if "out_of_search" in statuses:
        return "out_of_search"
    return "removed"


def primary_sort_key(row: sqlite3.Row) -> tuple:
    route_targets = json_list(row["route_targets_json"])
    route_count = sum(
        1
        for route in route_targets
        if route.get("transit_minutes") is not None or route.get("cycling_minutes") is not None
    )
    has_photo = 0 if (col(row, "main_image") or json_list(col(row, "image_urls_json"))) else 1
    return (
        status_sort_index(row["status"]),
        has_photo,
        -route_count,
        0 if row["latitude"] is not None and row["longitude"] is not None else 1,
        0 if row["price_pcm"] is not None else 1,
        source_sort_index(row["source"]),
        row["listing_key"],
    )


def best_price_row(rows: list[sqlite3.Row]) -> sqlite3.Row | None:
    candidates = [r for r in rows if r["status"] == "active" and r["price_pcm"] is not None]
    if not candidates:
        candidates = [r for r in rows if r["price_pcm"] is not None]
    return min(candidates, key=lambda r: r["price_pcm"]) if candidates else None


def source_payload(row: sqlite3.Row) -> dict:
    return {
        "source": row["source"],
        "url": row["url"],
        "status": row["status"],
        "price_text": row["price_text"],
        "price_pcm": row["price_pcm"],
        "agent": row["agent"],
    }


def source_sort_key(row: sqlite3.Row) -> tuple:
    return (source_sort_index(row["source"]), row["listing_key"])


def status_sort_index(status: str) -> int:
    return {"active": 0, "out_of_search": 1, "removed": 2}.get(status, 99)


def source_sort_index(source: str) -> int:
    return {"rightmove": 0}.get(source, 99)


def sort_key(listing: dict) -> tuple:
    return (
        status_sort_index(listing["status"]),
        -(listing.get("score") or 0),
        listing.get("price_pcm") or 999999,
        listing.get("address") or "",
    )


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
    features = " ".join(json_list(col(row, "key_features_json"))).lower()
    text = f"{text} {features}"
    return any(needle in text for needle in needles)


def col(row: sqlite3.Row, name: str):
    return row[name] if name in row.keys() else None


def json_list(value) -> list:
    if not value:
        return []
    try:
        data = json.loads(value)
    except (TypeError, ValueError):
        return []
    return data if isinstance(data, list) else []


def round2(value):
    return round(value, 2) if isinstance(value, (int, float)) else value


if __name__ == "__main__":
    raise SystemExit(main())
