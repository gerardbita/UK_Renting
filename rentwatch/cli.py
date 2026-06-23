from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sys
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from .config import (
    DEFAULT_CONFIG_PATH,
    AppConfig,
    SearchConfig,
    TelegramConfig,
    load_config,
    sample_config,
    save_config,
)
from .db import Store, listing_from_row
from .dedupe import assign_canonical_keys
from .models import Listing, ListingEvent
from .notifications import (
    TelegramNotifier,
    format_digest,
    format_event_message,
    listing_matches_route_filters,
)
from .progress import ProgressBar, compact_detail
from .rightmove_location import LocationLookupError, lookup_rightmove_locations
from .rightmove_url import RightmoveUrlOptions, build_rightmove_url
from .routing import RouteMetrics, RoutingError, TflRoutingClient, route_key
from .scrapers.rightmove import RightmoveScraper, ScraperError
from .db import utc_now


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except OSError:
            pass
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rentwatch",
        description="Monitor personal property searches and notify on changes.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to config JSON file. Defaults to ./config.json.",
    )
    subparsers = parser.add_subparsers(required=True)

    init_parser = subparsers.add_parser("init-config", help="Create a sample config file.")
    init_parser.add_argument("--force", action="store_true", help="Overwrite an existing file.")
    init_parser.set_defaults(func=cmd_init_config)

    add_parser = subparsers.add_parser("add", help="Add a pasted property search URL to the config.")
    add_parser.add_argument("name")
    add_parser.add_argument("url")
    add_parser.add_argument("--include", action="append", default=[])
    add_parser.add_argument("--exclude", action="append", default=[])
    add_parser.add_argument("--min-price-pcm", type=int)
    add_parser.add_argument("--max-price-pcm", type=int)
    add_parser.set_defaults(func=cmd_add)

    add_rightmove_parser = subparsers.add_parser(
        "add-rightmove",
        help="Add a Rightmove search using structured options instead of a pasted URL.",
    )
    add_rightmove_parser.add_argument("name")
    add_rightmove_arguments(add_rightmove_parser)
    add_rightmove_parser.add_argument("--include", action="append", default=[])
    add_rightmove_parser.add_argument("--exclude", action="append", default=[])
    add_rightmove_parser.set_defaults(func=cmd_add_rightmove)

    lookup_location_parser = subparsers.add_parser(
        "lookup-rightmove-location",
        help="Look up Rightmove location identifiers for a postcode, town, or area.",
    )
    lookup_location_parser.add_argument("query", help="Postcode, town, or area, e.g. W2 1SJ.")
    lookup_location_parser.add_argument("--limit", type=int, default=10)
    lookup_location_parser.add_argument("--include-streets", action="store_true")
    lookup_location_parser.set_defaults(func=cmd_lookup_rightmove_location)

    build_url_parser = subparsers.add_parser(
        "build-rightmove-url",
        help="Print a Rightmove URL from structured options.",
    )
    add_rightmove_arguments(build_url_parser)
    build_url_parser.set_defaults(func=cmd_build_rightmove_url)

    list_parser = subparsers.add_parser("list", help="List configured searches.")
    list_parser.set_defaults(func=cmd_list)

    run_parser = subparsers.add_parser("run", help="Run the monitor.")
    run_parser.add_argument("--once", action="store_true", help="Run one poll and exit.")
    run_parser.add_argument(
        "--prime",
        action="store_true",
        help="Save current results without sending notifications.",
    )
    run_parser.add_argument(
        "--no-notify",
        action="store_true",
        help="Do not send notifications during this run.",
    )
    run_parser.add_argument(
        "--max-pages",
        type=int,
        help="Limit Rightmove result pages per search. Useful while testing.",
    )
    run_parser.add_argument(
        "--allow-partial-write",
        action="store_true",
        help="Allow --max-pages runs to update the database. Off by default.",
    )
    run_parser.add_argument(
        "--search-changed",
        action="store_true",
        help=(
            "Use when changing radius, prices, or filters. Missing known listings "
            "become out_of_search and known reappearances do not notify as new."
        ),
    )
    run_parser.add_argument(
        "--skip-routes",
        action="store_true",
        help="Do not calculate public transport or cycling routes during this run.",
    )
    run_parser.add_argument(
        "--route-limit",
        type=int,
        help="Limit route calculations per run. Useful before backfilling all listings.",
    )
    run_parser.add_argument(
        "--refresh-routes",
        action="store_true",
        help="Ignore cached routes and calculate travel times again.",
    )
    run_parser.set_defaults(func=cmd_run)

    routes_parser = subparsers.add_parser(
        "routes",
        help="Backfill routes for listings already saved in the database.",
    )
    routes_parser.add_argument(
        "--route-limit",
        type=int,
        help="Limit route calculations. Useful for testing before a full backfill.",
    )
    routes_parser.add_argument(
        "--refresh-routes",
        action="store_true",
        help="Ignore cached routes and calculate travel times again.",
    )
    routes_parser.add_argument(
        "--include-removed",
        action="store_true",
        help="Also calculate routes for removed listings.",
    )
    routes_parser.set_defaults(func=cmd_routes)

    export_parser = subparsers.add_parser("export", help="Export known listings as CSV.")
    export_parser.add_argument("--output", type=Path, help="Write CSV to this path.")
    export_parser.set_defaults(func=cmd_export)

    telegram_parser = subparsers.add_parser(
        "test-telegram", help="Send a test Telegram message."
    )
    telegram_parser.set_defaults(func=cmd_test_telegram)
    return parser


def cmd_init_config(args: argparse.Namespace) -> int:
    if args.config.exists() and not args.force:
        print(f"Config already exists: {args.config}")
        print("Use --force to overwrite it.")
        return 2
    save_config(sample_config(), args.config)
    print(f"Created {args.config}")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    existing = next((search for search in config.searches if search.name == args.name), None)
    if existing is not None:
        if args.url not in existing.resolved_urls():
            existing.urls.append(args.url)
        save_config(config, args.config)
        print(f"Added URL to existing search {args.name!r} in {args.config}")
        return 0
    config.searches.append(
        SearchConfig(
            name=args.name,
            urls=[args.url],
            include_keywords=[item.lower() for item in args.include],
            exclude_keywords=[item.lower() for item in args.exclude],
            min_price_pcm=args.min_price_pcm,
            max_price_pcm=args.max_price_pcm,
        )
    )
    save_config(config, args.config)
    print(f"Added search {args.name!r} to {args.config}")
    return 0


def cmd_add_rightmove(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    if any(search.name == args.name for search in config.searches):
        print(f"A search named {args.name!r} already exists.", file=sys.stderr)
        return 2
    try:
        rightmove = resolve_rightmove_options(
            rightmove_options_from_args(args),
            timeout_seconds=config.http.timeout_seconds,
            user_agent=config.http.user_agent,
        )
    except LocationLookupError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    config.searches.append(
        SearchConfig(
            name=args.name,
            rightmove=rightmove,
            include_keywords=[item.lower() for item in args.include],
            exclude_keywords=[item.lower() for item in args.exclude],
            min_price_pcm=rightmove.min_price_pcm,
            max_price_pcm=rightmove.max_price_pcm,
        )
    )
    save_config(config, args.config)
    print(f"Added structured Rightmove search {args.name!r} to {args.config}")
    return 0


def cmd_build_rightmove_url(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    try:
        rightmove = resolve_rightmove_options(
            rightmove_options_from_args(args),
            timeout_seconds=config.http.timeout_seconds,
            user_agent=config.http.user_agent,
        )
    except LocationLookupError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(build_rightmove_url(rightmove))
    return 0


def cmd_lookup_rightmove_location(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    try:
        locations = lookup_rightmove_locations(
            args.query,
            limit=args.limit,
            include_streets=args.include_streets,
            timeout_seconds=config.http.timeout_seconds,
            user_agent=config.http.user_agent,
        )
    except LocationLookupError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if not locations:
        print(f"No Rightmove locations found for {args.query!r}.")
        return 1

    for index, location in enumerate(locations, start=1):
        print(
            f"{index}. {location.display_name} "
            f"({location.type}) -> {location.location_identifier}"
        )
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    if not config.searches:
        print("No searches configured.")
    for search in config.searches:
        filters = describe_filters(search)
        suffix = f" ({filters})" if filters else ""
        print(f"- {search.name}{suffix}")

    db_path = config.resolve_database_path(args.config)
    if db_path.exists():
        store = Store(db_path)
        try:
            summary = store.list_searches_summary()
        finally:
            store.close()
        if summary:
            print("\nDatabase summary:")
            for row in summary:
                print(f"- {row['search_name']}: {row['status']}={row['count']}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    if not config.searches:
        print(f"No searches configured in {args.config}.")
        print("Run `python3 -m rentwatch init-config` or `python3 -m rentwatch add ...`.")
        return 2

    scrapers = build_scrapers(config)

    store = Store(config.resolve_database_path(args.config))
    notifier = TelegramNotifier(
        config.notifications.telegram,
        timeout_seconds=config.http.timeout_seconds,
    )
    routing_client = TflRoutingClient(
        timeout_seconds=config.http.timeout_seconds,
        user_agent=config.http.user_agent,
    )

    try:
        while True:
            run_once(
                config,
                store,
                scrapers,
                notifier,
                notify=not args.no_notify and not args.prime,
                show_events=not args.prime,
                max_pages=args.max_pages,
                calculate_routes=not args.skip_routes,
                route_limit=args.route_limit,
                refresh_routes=args.refresh_routes,
                routing_client=routing_client,
                record_results=args.max_pages is None or args.allow_partial_write,
                search_changed=args.search_changed,
            )
            if args.once:
                return 0
            delay = random.randint(
                config.polling.delay_min_seconds,
                config.polling.delay_max_seconds,
            )
            print(f"Next poll in {delay} seconds.")
            time.sleep(delay)
    finally:
        store.close()


def cmd_routes(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    if not config.routing.enabled:
        print("Routing is disabled in config.json.")
        return 2
    if not config.routing.targets:
        print("Routing is enabled but no route targets are configured.", file=sys.stderr)
        return 2

    store = Store(config.resolve_database_path(args.config))
    routing_client = TflRoutingClient(
        timeout_seconds=config.http.timeout_seconds,
        user_agent=config.http.user_agent,
    )
    try:
        listings = []
        synced = 0
        for row in store.iter_listings():
            if not args.include_removed and row["status"] != "active":
                continue
            listing = listing_from_row(row)
            if listing.latitude is None or listing.longitude is None:
                continue
            if sync_listing_route_targets(listing, config):
                store.update_listing_routes(listing)
                synced += 1
            if not args.refresh_routes and listing_has_complete_targets(
                listing, config
            ):
                continue
            listing.route_updated_at = ""
            listings.append(listing)

        if not listings:
            if synced:
                print(f"Synced route target labels for {synced} listing(s).")
            print("No listings need route backfill.")
            return 0

        enrich_listings_with_routes(
            config,
            store,
            listings,
            routing_client=routing_client,
            route_limit=args.route_limit,
            refresh_routes=args.refresh_routes,
        )

        saved = 0
        for listing in listings:
            if listing.route_updated_at:
                store.update_listing_routes(listing)
                saved += 1
        if synced:
            print(f"Synced route target labels for {synced} listing(s).")
        print(f"Saved route data for {saved} listing(s).")
        return 0
    finally:
        store.close()


def cmd_export(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    store = Store(config.resolve_database_path(args.config))
    try:
        rows = list(store.iter_listings())
    finally:
        store.close()

    fieldnames = [
        "search_name",
        "status",
        "price_pcm",
        "price_text",
        "bedrooms",
        "latitude",
        "longitude",
        "transit_minutes",
        "transit_distance_km",
        "cycling_minutes",
        "cycling_distance_km",
        "route_target_latitude",
        "route_target_longitude",
        "address",
        "agent",
        "title",
        "url",
        "search_first_seen_at",
        "search_last_seen_at",
    ]
    output_handle = args.output.open("w", newline="", encoding="utf-8") if args.output else sys.stdout
    try:
        writer = csv.DictWriter(output_handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row[field] for field in fieldnames})
    finally:
        if args.output:
            output_handle.close()
    if args.output:
        print(f"Exported {len(rows)} listings to {args.output}")
    return 0


def cmd_test_telegram(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    notifier = TelegramNotifier(
        config.notifications.telegram,
        timeout_seconds=config.http.timeout_seconds,
    )
    if not notifier.enabled():
        print(
            "Telegram is not enabled or is missing bot_token/chat_id.",
            file=sys.stderr,
        )
        return 2
    notifier.send("RentWatch Telegram test message.")
    recipients = len(config.notifications.telegram.recipient_chat_ids())
    print(f"Sent Telegram test message to {recipients} recipient(s).")
    return 0


class ScrapeProgress:
    def __init__(self, source: str):
        self.source = source
        self.bar: ProgressBar | None = None

    def __call__(self, event: dict[str, object]) -> None:
        total_pages = optional_int(event.get("total_pages"))
        current_page = optional_int(event.get("current_page")) or 0
        if self.bar is None:
            self.bar = ProgressBar(
                f"{self.source.title()} scrape",
                total=total_pages,
                unit="pages",
            )

        detail = self.detail(event)
        if event.get("done"):
            self.bar.current = current_page
            self.bar.finish(detail=detail)
            return
        self.bar.update(current_page, detail=detail)

    def finish_failed(self) -> None:
        if self.bar is not None:
            self.bar.finish(detail="failed; keeping previous data for missing pages")

    @staticmethod
    def detail(event: dict[str, object]) -> str:
        current_listings = optional_int(event.get("current_listings")) or 0
        total_listings = optional_int(event.get("total_listings"))
        if total_listings:
            parts = [f"{current_listings:,}/{total_listings:,} headline listings"]
        else:
            parts = [f"{current_listings:,} listings"]
        if event.get("stopped_early"):
            parts.append("stopped after empty result pages")
        return " | ".join(parts)


def optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def run_once(
    config: AppConfig,
    store: Store,
    scrapers: dict[str, object],
    notifier: TelegramNotifier,
    *,
    notify: bool,
    show_events: bool = True,
    max_pages: int | None,
    calculate_routes: bool = True,
    route_limit: int | None = None,
    refresh_routes: bool = False,
    routing_client: TflRoutingClient | None = None,
    record_results: bool = True,
    search_changed: bool = False,
) -> None:
    for search in config.searches:
        print(f"Checking {search.name}...")
        scraped_by_key: dict[str, Listing] = {}
        scrape_had_failures = False
        urls = resolve_search_urls(search, config)
        if not urls:
            print(f"Skipped {search.name}: no portal URLs.")
            continue

        for url in urls:
            source = source_for_url(url)
            scraper = scrapers.get(source)
            if scraper is None:
                print(
                    f"Skipped {search.name}: unsupported portal URL "
                    f"(only Rightmove is supported): {url}",
                    file=sys.stderr,
                )
                continue
            progress = ScrapeProgress(source)
            try:
                portal_listings = scraper.scrape(
                    url,
                    max_pages=max_pages,
                    progress=progress,
                )
            except (ScraperError, LocationLookupError, ValueError) as exc:
                progress.finish_failed()
                scrape_had_failures = True
                print(f"Failed {search.name} ({source}): {exc}", file=sys.stderr)
                continue
            scraped_by_key.update(
                {listing.listing_key: listing for listing in portal_listings}
            )

        if not scraped_by_key:
            print(f"{search.name}: no listings scraped.")
            continue

        # Sanity guard: a sudden collapse in scraped volume on a full run almost
        # always means a markup change or a soft block, not that the market
        # emptied out. Treat it as a partial scrape so removed-detection does not
        # cascade thousands of false "removed" events.
        previously_active = store.active_listing_count(search.name)
        scraped_count = len(scraped_by_key)
        if (
            max_pages is None
            and not scrape_had_failures
            and previously_active >= 30
            and scraped_count < 0.4 * previously_active
        ):
            scrape_had_failures = True
            print(
                f"Sanity guard: only scraped {scraped_count} listings vs "
                f"{previously_active} previously active for {search.name}; "
                "treating as a partial scrape and skipping removed-listing detection.",
                file=sys.stderr,
            )

        fingerprint = search_config_fingerprint(search, urls)
        stored_fingerprint = store.get_search_fingerprint(search.name)
        automatic_search_changed = (
            stored_fingerprint is not None and stored_fingerprint != fingerprint
        )
        effective_search_changed = search_changed or automatic_search_changed
        if automatic_search_changed and not search_changed:
            print(
                "Search definition changed since the last successful full run; "
                "using search changed mode."
            )

        scraped = list(scraped_by_key.values())
        existing_listings = store.iter_listing_models()
        assign_canonical_keys(scraped, existing_listings)
        preserve_existing_route_data(scraped, existing_listings)
        for listing in scraped:
            sync_listing_route_targets(listing, config)

        listings = apply_filters(search, scraped)
        if calculate_routes and record_results:
            enrich_listings_with_routes(
                config,
                store,
                listings,
                routing_client=routing_client,
                route_limit=route_limit,
                refresh_routes=refresh_routes,
            )
        elif calculate_routes and not record_results:
            print("Limited page run: skipped route calculation.")
        if not record_results:
            print("Limited page run: read-only; skipped database writes.")
            print(f"{search.name}: {len(listings)} matching listings, 0 changes recorded.")
            continue
        telegram_filter_config = (
            config.notifications.telegram
            if notify and notifier.enabled()
            else None
        )
        events = filter_notifiable_events(
            search,
            store.record_search_results(
                search.name,
                listings,
                mark_removed=max_pages is None and not scrape_had_failures,
                missing_status="out_of_search" if effective_search_changed else "removed",
                suppress_known_new_events=effective_search_changed,
            ),
            telegram_config=telegram_filter_config,
        )
        if effective_search_changed:
            print("Search changed mode: missing listings marked out_of_search.")
        if scrape_had_failures:
            print("Partial scrape: skipped removed-listing detection.")
        elif max_pages is not None:
            print("Limited page run: skipped removed-listing detection.")
        else:
            store.set_search_fingerprint(search.name, fingerprint)
        change_label = "notifiable changes" if notify else "changes recorded"
        print(
            f"{search.name}: {len(listings)} matching listings, "
            f"{len(events)} {change_label}."
        )
        if show_events:
            for event in events:
                print_event(event)

        if not (notify and notifier.enabled()) or not events:
            continue

        if config.notifications.telegram.digest:
            digest = format_digest(events)
            notifier.send(digest)
            for event in events:
                store.mark_notified(event, digest)
        else:
            for event in events:
                message = format_event_message(event)
                notifier.send(message)
                store.mark_notified(event, message)


def search_config_fingerprint(search: SearchConfig, urls: list[str]) -> str:
    payload = {
        "urls": sorted(urls),
        "include_keywords": sorted(search.include_keywords),
        "exclude_keywords": sorted(search.exclude_keywords),
        "min_price_pcm": search.min_price_pcm,
        "max_price_pcm": search.max_price_pcm,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def preserve_existing_route_data(
    scraped: list[Listing], existing_listings: list[Listing]
) -> None:
    existing_by_key = {
        listing.listing_key: listing
        for listing in existing_listings
        if listing.route_updated_at or listing.route_targets
    }
    for listing in scraped:
        existing = existing_by_key.get(listing.listing_key)
        if existing is None:
            continue
        listing.transit_minutes = existing.transit_minutes
        listing.transit_distance_km = existing.transit_distance_km
        listing.cycling_minutes = existing.cycling_minutes
        listing.cycling_distance_km = existing.cycling_distance_km
        listing.route_target_latitude = existing.route_target_latitude
        listing.route_target_longitude = existing.route_target_longitude
        listing.route_targets = existing.route_targets
        listing.route_updated_at = existing.route_updated_at


def enrich_listings_with_routes(
    config: AppConfig,
    store: Store,
    listings: list[Listing],
    *,
    routing_client: TflRoutingClient | None,
    route_limit: int | None,
    refresh_routes: bool,
) -> None:
    routing = config.routing
    if not routing.enabled:
        return
    targets = routing.targets
    if not targets:
        print("Routing is enabled but target coordinates are missing.", file=sys.stderr)
        return
    if routing_client is None:
        return

    candidates = [
        listing
        for listing in listings
        if listing.latitude is not None and listing.longitude is not None
    ]
    if route_limit is not None:
        candidates = candidates[:route_limit]

    if not candidates:
        return

    route_date = next_weekday_date(routing.departure_day)
    route_time = normalize_route_time(routing.departure_time)
    cache_profile = f"{routing.departure_day.lower()}-{route_time}"
    route_progress = ProgressBar(
        "Routes",
        total=len(candidates),
        unit="listings",
    )
    print(
        f"Calculating routes for {len(candidates)} listing(s) "
        f"to {len(targets)} target(s) "
        f"for {routing.departure_day} {routing.departure_time}..."
    )
    updated_count = 0
    skipped_count = 0
    network_requests = 0
    route_failures: list[str] = []

    def mark_network_request() -> None:
        nonlocal network_requests
        network_requests += 1

    for candidate_index, listing in enumerate(candidates, start=1):
        if not refresh_routes and listing_has_complete_targets(listing, config):
            skipped_count += 1
            route_progress.update(
                candidate_index,
                detail=compact_detail(
                    f"cached: {listing.address or listing.title or listing.url}"
                ),
            )
            continue

        updated = False
        route_targets = []
        network_requests_before_listing = network_requests
        for index, target in enumerate(targets):
            target_result = {
                "name": target.name,
                "latitude": target.latitude,
                "longitude": target.longitude,
                "transit_minutes": None,
                "transit_distance_km": None,
                "cycling_minutes": None,
                "cycling_distance_km": None,
            }
            if routing.public_transport:
                metrics = get_or_fetch_route(
                    store,
                    routing_client,
                    listing,
                    mode="public_transport",
                    destination_latitude=target.latitude,
                    destination_longitude=target.longitude,
                    tfl_modes=routing.tfl_modes,
                    cache_hours=routing.cache_hours,
                    cache_profile=cache_profile,
                    route_date=route_date,
                    route_time=route_time,
                    refresh_routes=refresh_routes,
                    on_network_request=mark_network_request,
                    on_error=route_failures.append,
                )
                if metrics:
                    target_result["transit_minutes"] = metrics.duration_minutes
                    target_result["transit_distance_km"] = metrics.distance_km
                    if index == 0:
                        listing.transit_minutes = metrics.duration_minutes
                        listing.transit_distance_km = metrics.distance_km
                    updated = True

            if routing.cycling:
                metrics = get_or_fetch_route(
                    store,
                    routing_client,
                    listing,
                    mode="cycling",
                    destination_latitude=target.latitude,
                    destination_longitude=target.longitude,
                    tfl_modes=routing.tfl_modes,
                    cache_hours=routing.cache_hours,
                    cache_profile=cache_profile,
                    route_date=route_date,
                    route_time=route_time,
                    refresh_routes=refresh_routes,
                    on_network_request=mark_network_request,
                    on_error=route_failures.append,
                )
                if metrics:
                    target_result["cycling_minutes"] = metrics.duration_minutes
                    target_result["cycling_distance_km"] = metrics.distance_km
                    if index == 0:
                        listing.cycling_minutes = metrics.duration_minutes
                        listing.cycling_distance_km = metrics.distance_km
                    updated = True

            route_targets.append(target_result)

        if updated:
            first_target = targets[0]
            listing.route_target_latitude = first_target.latitude
            listing.route_target_longitude = first_target.longitude
            listing.route_targets = route_targets
            listing.route_updated_at = utc_now()
            updated_count += 1

        route_progress.update(
            candidate_index,
            detail=compact_detail(listing.address or listing.title or listing.url),
        )

        if (
            network_requests > network_requests_before_listing
            and routing.request_delay_seconds > 0
        ):
            time.sleep(routing.request_delay_seconds)
    route_progress.finish(
        detail=(
            f"updated {updated_count:,}; cached {skipped_count:,}; "
            f"TfL requests {network_requests:,}"
        )
    )
    for failure in route_failures:
        print(failure, file=sys.stderr)


def listing_has_complete_targets(listing: Listing, config: AppConfig) -> bool:
    if not listing.route_targets:
        return False

    for target in config.routing.targets:
        match = next(
            (
                item
                for item in listing.route_targets
                if route_target_matches(item, target.latitude, target.longitude)
            ),
            None,
        )
        if match is None:
            return False
        if config.routing.public_transport and match.get("transit_minutes") is None:
            return False
        if config.routing.cycling and match.get("cycling_minutes") is None:
            return False
    return True


def sync_listing_route_targets(listing: Listing, config: AppConfig) -> bool:
    if not listing.route_targets:
        return False

    normalized = []
    for target in config.routing.targets:
        match = find_route_target(
            listing.route_targets,
            target.latitude,
            target.longitude,
        )
        if match is None:
            return False
        normalized.append(
            {
                "name": target.name,
                "latitude": target.latitude,
                "longitude": target.longitude,
                "transit_minutes": match.get("transit_minutes"),
                "transit_distance_km": match.get("transit_distance_km"),
                "cycling_minutes": match.get("cycling_minutes"),
                "cycling_distance_km": match.get("cycling_distance_km"),
            }
        )

    if listing.route_targets == normalized:
        return False
    listing.route_targets = normalized
    return True


def find_route_target(
    route_targets: list[dict[str, object]], latitude: float, longitude: float
) -> dict[str, object] | None:
    return next(
        (
            item
            for item in route_targets
            if route_target_matches(item, latitude, longitude)
        ),
        None,
    )


def route_target_matches(
    item: dict[str, object], latitude: float, longitude: float
) -> bool:
    try:
        item_latitude = float(item.get("latitude"))
        item_longitude = float(item.get("longitude"))
    except (TypeError, ValueError):
        return False
    return (
        abs(item_latitude - latitude) < 0.00001
        and abs(item_longitude - longitude) < 0.00001
    )


def get_or_fetch_route(
    store: Store,
    routing_client: TflRoutingClient,
    listing: Listing,
    *,
    mode: str,
    destination_latitude: float,
    destination_longitude: float,
    tfl_modes: str,
    cache_hours: float | None,
    cache_profile: str,
    route_date: str,
    route_time: str,
    refresh_routes: bool,
    on_network_request: Callable[[], None] | None = None,
    on_error: Callable[[str], None] | None = None,
) -> RouteMetrics | None:
    if listing.latitude is None or listing.longitude is None:
        return None

    key = route_key(
        "tfl",
        mode,
        listing.latitude,
        listing.longitude,
        destination_latitude,
        destination_longitude,
        profile=cache_profile,
    )
    cached = store.get_cached_route(key)
    if (
        not refresh_routes
        and cached is not None
        and cached_route_is_fresh(cached["fetched_at"], cache_hours)
    ):
        return RouteMetrics(
            mode=mode,
            provider="tfl",
            duration_minutes=cached["duration_minutes"],
            distance_km=cached["distance_km"],
            summary=cached["summary"] or "",
        )

    try:
        if on_network_request is not None:
            on_network_request()
        if mode == "public_transport":
            metrics = routing_client.public_transport(
                listing.latitude,
                listing.longitude,
                destination_latitude,
                destination_longitude,
                modes=tfl_modes,
                date=route_date,
                time=route_time,
            )
        elif mode == "cycling":
            metrics = routing_client.cycling(
                listing.latitude,
                listing.longitude,
                destination_latitude,
                destination_longitude,
                date=route_date,
                time=route_time,
            )
        else:
            return None
    except RoutingError as exc:
        message = f"Route failed for {listing.address or listing.url}: {exc}"
        if on_error is not None:
            on_error(message)
        else:
            print(message, file=sys.stderr)
        return None

    store.save_cached_route(
        route_key=key,
        provider=metrics.provider,
        mode=metrics.mode,
        origin_latitude=listing.latitude,
        origin_longitude=listing.longitude,
        destination_latitude=destination_latitude,
        destination_longitude=destination_longitude,
        duration_minutes=metrics.duration_minutes,
        distance_km=metrics.distance_km,
        summary=metrics.summary,
    )
    return metrics


def cached_route_is_fresh(fetched_at: str, cache_hours: float | None) -> bool:
    if cache_hours is None or cache_hours <= 0:
        return True
    try:
        fetched = datetime.fromisoformat(fetched_at)
    except ValueError:
        return False
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - fetched <= timedelta(hours=cache_hours)


def next_weekday_date(day_name: str) -> str:
    weekday_by_name = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }
    target = weekday_by_name.get(day_name.strip().lower())
    if target is None:
        raise ValueError(f"Unknown routing departure day: {day_name!r}")
    today = date.today()
    days_ahead = (target - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return (today + timedelta(days=days_ahead)).strftime("%Y%m%d")


def normalize_route_time(value: str) -> str:
    cleaned = value.strip().replace(":", "")
    if len(cleaned) != 4 or not cleaned.isdigit():
        raise ValueError(f"Routing departure time must be HH:MM or HHMM, got {value!r}")
    return cleaned


def apply_filters(search: SearchConfig, listings: list[Listing]) -> list[Listing]:
    filtered: list[Listing] = []
    for listing in listings:
        if search.min_price_pcm is not None and (
            listing.price_pcm is None or listing.price_pcm < search.min_price_pcm
        ):
            continue
        if search.max_price_pcm is not None and (
            listing.price_pcm is None or listing.price_pcm > search.max_price_pcm
        ):
            continue
        text = listing.searchable_text
        if any(keyword not in text for keyword in search.include_keywords):
            continue
        if any(keyword in text for keyword in search.exclude_keywords):
            continue
        filtered.append(listing)
    return filtered


def filter_notifiable_events(
    search: SearchConfig,
    events: list[ListingEvent],
    *,
    telegram_config: TelegramConfig | None = None,
) -> list[ListingEvent]:
    allowed: list[ListingEvent] = []
    for event in events:
        event_enabled = (
            (event.event_type in {"new", "reactivated"} and search.notify_new)
            or (event.event_type == "price_change" and search.notify_price_changes)
            or (event.event_type == "removed" and search.notify_removed)
        )
        if not event_enabled:
            continue
        if (
            telegram_config is not None
            and telegram_config.route_filters
            and not listing_matches_route_filters(
                event.listing,
                telegram_config.route_filters,
            )
        ):
            continue
        allowed.append(event)
    return allowed


def print_event(event: ListingEvent) -> None:
    listing = event.listing
    price = f" - {listing.price_text}" if listing.price_text else ""
    print(f"  {event.human_label()}: {listing.address or listing.title}{price}")
    print(f"    {listing.url}")


def describe_filters(search: SearchConfig) -> str:
    parts = []
    urls = search.resolved_urls()
    if len(urls) > 1:
        parts.append(f"{len(urls)} portal URLs")
    if search.min_price_pcm is not None:
        parts.append(f"min GBP {search.min_price_pcm} pcm")
    if search.max_price_pcm is not None:
        parts.append(f"max GBP {search.max_price_pcm} pcm")
    if search.include_keywords:
        parts.append("include: " + ", ".join(search.include_keywords))
    if search.exclude_keywords:
        parts.append("exclude: " + ", ".join(search.exclude_keywords))
    if search.rightmove is not None and search.rightmove.must_have:
        parts.append("must have: " + ", ".join(search.rightmove.must_have))
    if search.rightmove is not None and search.rightmove.furnish_types:
        parts.append("furnishing: " + ", ".join(search.rightmove.furnish_types))
    return "; ".join(parts)


def add_rightmove_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--search-location", required=True, help="Postcode or place, e.g. W2 1SJ.")
    parser.add_argument(
        "--location-identifier",
        default="",
        help="Rightmove location identifier, e.g. POSTCODE^918640.",
    )
    parser.add_argument("--radius", type=float, default=5.0)
    parser.add_argument("--min-price-pcm", type=int)
    parser.add_argument("--max-price-pcm", type=int)
    parser.add_argument("--min-bedrooms", type=int)
    parser.add_argument("--max-bedrooms", type=int)
    parser.add_argument("--property-types", nargs="*", default=[])
    parser.add_argument("--dont-show", nargs="*", default=[])
    parser.add_argument("--must-have", nargs="*", default=[])
    parser.add_argument("--furnish-types", nargs="*", default=[])
    parser.add_argument("--include-let-agreed", action="store_true")
    parser.add_argument(
        "--no-location-lookup",
        action="store_true",
        help="Do not look up a missing Rightmove location identifier automatically.",
    )
    parser.add_argument("--sort-type", type=int, default=6)


def rightmove_options_from_args(args: argparse.Namespace) -> RightmoveUrlOptions:
    return RightmoveUrlOptions(
        search_location=args.search_location,
        location_identifier=args.location_identifier,
        radius=args.radius,
        min_price_pcm=args.min_price_pcm,
        max_price_pcm=args.max_price_pcm,
        min_bedrooms=args.min_bedrooms,
        max_bedrooms=args.max_bedrooms,
        property_types=args.property_types,
        dont_show=args.dont_show,
        must_have=args.must_have,
        furnish_types=args.furnish_types,
        include_let_agreed=args.include_let_agreed,
        lookup_location_identifier=not args.no_location_lookup,
        sort_type=args.sort_type,
    )


def resolve_search_url(search: SearchConfig, config: AppConfig) -> str:
    urls = resolve_search_urls(search, config)
    if urls:
        return urls[0]
    raise ValueError(f"Search {search.name!r} has neither url nor rightmove config.")


def resolve_search_urls(search: SearchConfig, config: AppConfig) -> list[str]:
    if search.rightmove is None:
        return search.resolved_urls()

    rightmove_url = build_rightmove_url(
        resolve_rightmove_options(
            search.rightmove,
            timeout_seconds=config.http.timeout_seconds,
            user_agent=config.http.user_agent,
        )
    )
    urls = []
    if search.url:
        urls.append(search.url)
    urls.extend(search.urls)
    urls.append(rightmove_url)
    return list(dict.fromkeys(urls))


def build_scrapers(config: AppConfig) -> dict[str, object]:
    kwargs = {
        "timeout_seconds": config.http.timeout_seconds,
        "user_agent": config.http.user_agent,
        "page_delay_seconds": config.polling.page_delay_seconds,
    }
    return {"rightmove": RightmoveScraper(**kwargs)}


def source_for_url(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "rightmove.co.uk" in host:
        return "rightmove"
    return ""


def resolve_rightmove_options(
    options: RightmoveUrlOptions,
    *,
    timeout_seconds: int,
    user_agent: str,
) -> RightmoveUrlOptions:
    if options.location_identifier or not options.lookup_location_identifier:
        return options

    locations = lookup_rightmove_locations(
        options.search_location,
        limit=1,
        timeout_seconds=timeout_seconds,
        user_agent=user_agent,
    )
    if not locations:
        raise LocationLookupError(
            f"No Rightmove location identifier found for {options.search_location!r}."
        )

    return replace(options, location_identifier=locations[0].location_identifier)
