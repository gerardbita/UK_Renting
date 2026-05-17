from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .models import Listing, ListingEvent


SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    listing_key TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    property_id TEXT NOT NULL,
    url TEXT NOT NULL,
    address TEXT,
    price_text TEXT,
    price_pcm INTEGER,
    bedrooms INTEGER,
    latitude REAL,
    longitude REAL,
    transit_minutes INTEGER,
    transit_distance_km REAL,
    cycling_minutes INTEGER,
    cycling_distance_km REAL,
    route_target_latitude REAL,
    route_target_longitude REAL,
    route_targets_json TEXT,
    route_updated_at TEXT,
    canonical_key TEXT,
    agent TEXT,
    summary TEXT,
    title TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    last_changed_at TEXT NOT NULL,
    raw_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS search_listings (
    search_name TEXT NOT NULL,
    listing_key TEXT NOT NULL,
    status TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    last_snapshot_json TEXT NOT NULL,
    last_price_text TEXT,
    last_price_pcm INTEGER,
    notified_new_at TEXT,
    notified_price_at TEXT,
    notified_removed_at TEXT,
    PRIMARY KEY (search_name, listing_key),
    FOREIGN KEY (listing_key) REFERENCES listings(listing_key)
);

CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    search_name TEXT NOT NULL,
    listing_key TEXT NOT NULL,
    seen_at TEXT NOT NULL,
    price_text TEXT,
    price_pcm INTEGER
);

CREATE TABLE IF NOT EXISTS notification_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    search_name TEXT NOT NULL,
    listing_key TEXT NOT NULL,
    event_type TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    message TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS route_cache (
    route_key TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    mode TEXT NOT NULL,
    origin_latitude REAL NOT NULL,
    origin_longitude REAL NOT NULL,
    destination_latitude REAL NOT NULL,
    destination_longitude REAL NOT NULL,
    duration_minutes INTEGER NOT NULL,
    distance_km REAL,
    summary TEXT,
    fetched_at TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.init_schema()

    def close(self) -> None:
        self.connection.close()

    def init_schema(self) -> None:
        self.connection.executescript(SCHEMA)
        self._ensure_listing_columns()
        self.connection.commit()

    def record_search_results(
        self, search_name: str, listings: Iterable[Listing]
    ) -> list[ListingEvent]:
        now = utc_now()
        listings_by_key = {listing.listing_key: listing for listing in listings}
        existing = self._search_rows(search_name)
        events: list[ListingEvent] = []

        with self.connection:
            for listing in listings_by_key.values():
                self._upsert_listing(listing, now)
                row = existing.get(listing.listing_key)
                snapshot_json = json.dumps(listing.snapshot(), sort_keys=True)

                if row is None:
                    self.connection.execute(
                        """
                        INSERT INTO search_listings (
                            search_name, listing_key, status, first_seen_at, last_seen_at,
                            last_snapshot_json, last_price_text, last_price_pcm
                        ) VALUES (?, ?, 'active', ?, ?, ?, ?, ?)
                        """,
                        (
                            search_name,
                            listing.listing_key,
                            now,
                            now,
                            snapshot_json,
                            listing.price_text,
                            listing.price_pcm,
                        ),
                    )
                    self._insert_price_history(search_name, listing, now)
                    events.append(ListingEvent("new", search_name, listing))
                    continue

                if row["status"] == "removed":
                    events.append(ListingEvent("reactivated", search_name, listing))

                if self._price_changed(row, listing):
                    self._insert_price_history(search_name, listing, now)
                    events.append(
                        ListingEvent(
                            "price_change",
                            search_name,
                            listing,
                            previous_price_text=row["last_price_text"],
                            previous_price_pcm=row["last_price_pcm"],
                        )
                    )

                self.connection.execute(
                    """
                    UPDATE search_listings
                    SET status = 'active',
                        last_seen_at = ?,
                        last_snapshot_json = ?,
                        last_price_text = ?,
                        last_price_pcm = ?
                    WHERE search_name = ? AND listing_key = ?
                    """,
                    (
                        now,
                        snapshot_json,
                        listing.price_text,
                        listing.price_pcm,
                        search_name,
                        listing.listing_key,
                    ),
                )

            active_keys = {
                key for key, row in existing.items() if row["status"] == "active"
            }
            removed_keys = active_keys - set(listings_by_key)
            for listing_key in removed_keys:
                row = self._listing_row(listing_key)
                if row is None:
                    continue
                listing = listing_from_row(row)
                self.connection.execute(
                    """
                    UPDATE search_listings
                    SET status = 'removed', last_seen_at = ?
                    WHERE search_name = ? AND listing_key = ?
                    """,
                    (now, search_name, listing_key),
                )
                events.append(ListingEvent("removed", search_name, listing))

        return events

    def mark_notified(self, event: ListingEvent, message: str) -> None:
        now = utc_now()
        column_by_event = {
            "new": "notified_new_at",
            "price_change": "notified_price_at",
            "reactivated": "notified_new_at",
            "removed": "notified_removed_at",
        }
        column = column_by_event.get(event.event_type)
        with self.connection:
            if column:
                self.connection.execute(
                    f"""
                    UPDATE search_listings
                    SET {column} = ?
                    WHERE search_name = ? AND listing_key = ?
                    """,
                    (now, event.search_name, event.listing.listing_key),
                )
            self.connection.execute(
                """
                INSERT INTO notification_log (
                    search_name, listing_key, event_type, sent_at, message
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event.search_name,
                    event.listing.listing_key,
                    event.event_type,
                    now,
                    message,
                ),
            )

    def iter_listings(self) -> Iterable[sqlite3.Row]:
        return self.connection.execute(
            """
            SELECT
                sl.search_name,
                sl.status,
                sl.first_seen_at AS search_first_seen_at,
                sl.last_seen_at AS search_last_seen_at,
                l.*
            FROM search_listings sl
            JOIN listings l ON l.listing_key = sl.listing_key
            ORDER BY sl.search_name, sl.status, l.price_pcm, l.address
            """
        )

    def iter_listing_models(self) -> list[Listing]:
        rows = self.connection.execute(
            """
            SELECT *
            FROM listings
            ORDER BY last_seen_at DESC, listing_key
            """
        ).fetchall()
        return [listing_from_row(row) for row in rows]

    def update_listing_routes(self, listing: Listing) -> None:
        with self.connection:
            self.connection.execute(
                """
                UPDATE listings
                SET transit_minutes = ?,
                    transit_distance_km = ?,
                    cycling_minutes = ?,
                    cycling_distance_km = ?,
                    route_target_latitude = ?,
                    route_target_longitude = ?,
                    route_targets_json = ?,
                    route_updated_at = ?
                WHERE listing_key = ?
                """,
                (
                    listing.transit_minutes,
                    listing.transit_distance_km,
                    listing.cycling_minutes,
                    listing.cycling_distance_km,
                    listing.route_target_latitude,
                    listing.route_target_longitude,
                    json.dumps(listing.route_targets or [], sort_keys=True),
                    listing.route_updated_at,
                    listing.listing_key,
                ),
            )

    def list_searches_summary(self) -> list[sqlite3.Row]:
        return list(
            self.connection.execute(
                """
                SELECT search_name, status, COUNT(*) AS count
                FROM search_listings
                GROUP BY search_name, status
                ORDER BY search_name, status
                """
            )
        )

    def get_cached_route(self, route_key: str) -> sqlite3.Row | None:
        return self.connection.execute(
            "SELECT * FROM route_cache WHERE route_key = ?",
            (route_key,),
        ).fetchone()

    def save_cached_route(
        self,
        *,
        route_key: str,
        provider: str,
        mode: str,
        origin_latitude: float,
        origin_longitude: float,
        destination_latitude: float,
        destination_longitude: float,
        duration_minutes: int,
        distance_km: float | None,
        summary: str,
    ) -> None:
        with self.connection:
            self.connection.execute(
                """
                INSERT OR REPLACE INTO route_cache (
                    route_key, provider, mode, origin_latitude, origin_longitude,
                    destination_latitude, destination_longitude, duration_minutes,
                    distance_km, summary, fetched_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    route_key,
                    provider,
                    mode,
                    origin_latitude,
                    origin_longitude,
                    destination_latitude,
                    destination_longitude,
                    duration_minutes,
                    distance_km,
                    summary,
                    utc_now(),
                ),
            )

    def _search_rows(self, search_name: str) -> dict[str, sqlite3.Row]:
        rows = self.connection.execute(
            "SELECT * FROM search_listings WHERE search_name = ?",
            (search_name,),
        ).fetchall()
        return {row["listing_key"]: row for row in rows}

    def _listing_row(self, listing_key: str) -> sqlite3.Row | None:
        return self.connection.execute(
            "SELECT * FROM listings WHERE listing_key = ?",
            (listing_key,),
        ).fetchone()

    def _upsert_listing(self, listing: Listing, now: str) -> None:
        current = self._listing_row(listing.listing_key)
        snapshot_json = json.dumps(listing.snapshot(), sort_keys=True)
        raw_json = json.dumps(listing.raw or {}, sort_keys=True)

        if current is None:
            self.connection.execute(
                """
                INSERT INTO listings (
                    listing_key, source, property_id, url, address, price_text,
                    price_pcm, bedrooms, latitude, longitude, agent, summary,
                    transit_minutes, transit_distance_km, cycling_minutes,
                    cycling_distance_km, route_target_latitude,
                    route_target_longitude, route_targets_json, route_updated_at,
                    canonical_key, title, first_seen_at, last_seen_at,
                    last_changed_at, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    listing.listing_key,
                    listing.source,
                    listing.property_id,
                    listing.url,
                    listing.address,
                    listing.price_text,
                    listing.price_pcm,
                    listing.bedrooms,
                    listing.latitude,
                    listing.longitude,
                    listing.agent,
                    listing.summary,
                    listing.transit_minutes,
                    listing.transit_distance_km,
                    listing.cycling_minutes,
                    listing.cycling_distance_km,
                    listing.route_target_latitude,
                    listing.route_target_longitude,
                    json.dumps(listing.route_targets or [], sort_keys=True),
                    listing.route_updated_at,
                    listing.canonical_key,
                    listing.title,
                    now,
                    now,
                    now,
                    raw_json,
                ),
            )
            return

        route_values = route_values_for_update(listing, current)
        current_snapshot = json.dumps(
            listing_from_row(current).snapshot(), sort_keys=True
        )
        changed_at = now if current_snapshot != snapshot_json else current["last_changed_at"]
        self.connection.execute(
            """
            UPDATE listings
            SET url = ?,
                address = ?,
                price_text = ?,
                price_pcm = ?,
                bedrooms = ?,
                latitude = ?,
                longitude = ?,
                agent = ?,
                summary = ?,
                transit_minutes = ?,
                transit_distance_km = ?,
                cycling_minutes = ?,
                cycling_distance_km = ?,
                route_target_latitude = ?,
                route_target_longitude = ?,
                route_targets_json = ?,
                route_updated_at = ?,
                canonical_key = ?,
                title = ?,
                last_seen_at = ?,
                last_changed_at = ?,
                raw_json = ?
            WHERE listing_key = ?
            """,
            (
                listing.url,
                listing.address,
                listing.price_text,
                listing.price_pcm,
                listing.bedrooms,
                listing.latitude,
                listing.longitude,
                listing.agent,
                listing.summary,
                route_values["transit_minutes"],
                route_values["transit_distance_km"],
                route_values["cycling_minutes"],
                route_values["cycling_distance_km"],
                route_values["route_target_latitude"],
                route_values["route_target_longitude"],
                route_values["route_targets_json"],
                route_values["route_updated_at"],
                listing.canonical_key,
                listing.title,
                now,
                changed_at,
                raw_json,
                listing.listing_key,
            ),
        )

    def _insert_price_history(
        self, search_name: str, listing: Listing, seen_at: str
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO price_history (
                search_name, listing_key, seen_at, price_text, price_pcm
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                search_name,
                listing.listing_key,
                seen_at,
                listing.price_text,
                listing.price_pcm,
            ),
        )

    @staticmethod
    def _price_changed(row: sqlite3.Row, listing: Listing) -> bool:
        return (
            (row["last_price_text"] or "") != (listing.price_text or "")
            or row["last_price_pcm"] != listing.price_pcm
        )

    def _ensure_listing_columns(self) -> None:
        existing = {
            row["name"]
            for row in self.connection.execute("PRAGMA table_info(listings)").fetchall()
        }
        if "latitude" not in existing:
            self.connection.execute("ALTER TABLE listings ADD COLUMN latitude REAL")
        if "longitude" not in existing:
            self.connection.execute("ALTER TABLE listings ADD COLUMN longitude REAL")
        for column, column_type in [
            ("transit_minutes", "INTEGER"),
            ("transit_distance_km", "REAL"),
            ("cycling_minutes", "INTEGER"),
            ("cycling_distance_km", "REAL"),
            ("route_target_latitude", "REAL"),
            ("route_target_longitude", "REAL"),
            ("route_targets_json", "TEXT"),
            ("route_updated_at", "TEXT"),
            ("canonical_key", "TEXT"),
        ]:
            if column not in existing:
                self.connection.execute(
                    f"ALTER TABLE listings ADD COLUMN {column} {column_type}"
                )


def listing_from_row(row: sqlite3.Row) -> Listing:
    return Listing(
        source=row["source"],
        property_id=row["property_id"],
        url=row["url"],
        address=row["address"] or "",
        price_text=row["price_text"] or "",
        price_pcm=row["price_pcm"],
        bedrooms=row["bedrooms"],
        latitude=row["latitude"],
        longitude=row["longitude"],
        transit_minutes=row["transit_minutes"],
        transit_distance_km=row["transit_distance_km"],
        cycling_minutes=row["cycling_minutes"],
        cycling_distance_km=row["cycling_distance_km"],
        route_target_latitude=row["route_target_latitude"],
        route_target_longitude=row["route_target_longitude"],
        route_targets=json.loads(row["route_targets_json"] or "[]"),
        route_updated_at=row["route_updated_at"] or "",
        canonical_key=row["canonical_key"] or "",
        agent=row["agent"] or "",
        summary=row["summary"] or "",
        title=row["title"] or "",
        raw=json.loads(row["raw_json"] or "{}"),
    )


def route_values_for_update(
    listing: Listing, current: sqlite3.Row
) -> dict[str, int | float | str | None]:
    if listing.route_updated_at:
        return {
            "transit_minutes": listing.transit_minutes,
            "transit_distance_km": listing.transit_distance_km,
            "cycling_minutes": listing.cycling_minutes,
            "cycling_distance_km": listing.cycling_distance_km,
            "route_target_latitude": listing.route_target_latitude,
            "route_target_longitude": listing.route_target_longitude,
            "route_targets_json": json.dumps(listing.route_targets or [], sort_keys=True),
            "route_updated_at": listing.route_updated_at,
        }

    return {
        "transit_minutes": current["transit_minutes"],
        "transit_distance_km": current["transit_distance_km"],
        "cycling_minutes": current["cycling_minutes"],
        "cycling_distance_km": current["cycling_distance_km"],
        "route_target_latitude": current["route_target_latitude"],
        "route_target_longitude": current["route_target_longitude"],
        "route_targets_json": current["route_targets_json"],
        "route_updated_at": current["route_updated_at"],
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
