from __future__ import annotations

import argparse
import csv
import random
import sys
import time
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .config import (
    DEFAULT_CONFIG_PATH,
    AppConfig,
    SearchConfig,
    load_config,
    sample_config,
    save_config,
)
from .db import Store
from .models import Listing, ListingEvent
from .notifications import TelegramNotifier, format_event_message
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

    add_parser = subparsers.add_parser("add", help="Add a Rightmove search to the config.")
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
    if any(search.name == args.name for search in config.searches):
        print(f"A search named {args.name!r} already exists.", file=sys.stderr)
        return 2
    config.searches.append(
        SearchConfig(
            name=args.name,
            url=args.url,
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

    store = Store(config.resolve_database_path(args.config))
    notifier = TelegramNotifier(
        config.notifications.telegram,
        timeout_seconds=config.http.timeout_seconds,
    )
    scraper = RightmoveScraper(
        timeout_seconds=config.http.timeout_seconds,
        user_agent=config.http.user_agent,
        page_delay_seconds=config.polling.page_delay_seconds,
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
                scraper,
                notifier,
                notify=not args.no_notify and not args.prime,
                show_events=not args.prime,
                max_pages=args.max_pages,
                calculate_routes=not args.skip_routes,
                route_limit=args.route_limit,
                refresh_routes=args.refresh_routes,
                routing_client=routing_client,
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
        print("Telegram is not enabled or is missing bot_token/chat_id.", file=sys.stderr)
        return 2
    notifier.send("RentWatch Telegram test message.")
    print("Sent Telegram test message.")
    return 0


def run_once(
    config: AppConfig,
    store: Store,
    scraper: RightmoveScraper,
    notifier: TelegramNotifier,
    *,
    notify: bool,
    show_events: bool = True,
    max_pages: int | None,
    calculate_routes: bool = True,
    route_limit: int | None = None,
    refresh_routes: bool = False,
    routing_client: TflRoutingClient | None = None,
) -> None:
    for search in config.searches:
        print(f"Checking {search.name}...")
        try:
            url = resolve_search_url(search, config)
            scraped = scraper.scrape(url, max_pages=max_pages)
        except (ScraperError, LocationLookupError, ValueError) as exc:
            print(f"Failed {search.name}: {exc}", file=sys.stderr)
            continue

        listings = apply_filters(search, scraped)
        if calculate_routes:
            enrich_listings_with_routes(
                config,
                store,
                listings,
                routing_client=routing_client,
                route_limit=route_limit,
                refresh_routes=refresh_routes,
            )
        events = filter_notifiable_events(search, store.record_search_results(search.name, listings))
        change_label = "notifiable changes" if notify else "changes recorded"
        print(
            f"{search.name}: {len(listings)} matching listings, "
            f"{len(events)} {change_label}."
        )
        for event in events:
            message = format_event_message(event)
            if show_events:
                print_event(event)
            if notify and notifier.enabled():
                notifier.send(message)
                store.mark_notified(event, message)


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
    print(
        f"Calculating routes for {len(candidates)} listing(s) "
        f"to {len(targets)} target(s) "
        f"for {routing.departure_day} {routing.departure_time}..."
    )
    for listing in candidates:
        updated = False
        route_targets = []
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
            target_profile = f"{cache_profile}-{target.latitude:.5f}-{target.longitude:.5f}"

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
                    cache_profile=target_profile,
                    route_date=route_date,
                    route_time=route_time,
                    refresh_routes=refresh_routes,
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
                    cache_profile=target_profile,
                    route_date=route_date,
                    route_time=route_time,
                    refresh_routes=refresh_routes,
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

        if routing.request_delay_seconds > 0:
            time.sleep(routing.request_delay_seconds)


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
        print(f"Route failed for {listing.address or listing.url}: {exc}", file=sys.stderr)
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
    search: SearchConfig, events: list[ListingEvent]
) -> list[ListingEvent]:
    allowed: list[ListingEvent] = []
    for event in events:
        if event.event_type in {"new", "reactivated"} and search.notify_new:
            allowed.append(event)
        elif event.event_type == "price_change" and search.notify_price_changes:
            allowed.append(event)
        elif event.event_type == "removed" and search.notify_removed:
            allowed.append(event)
    return allowed


def print_event(event: ListingEvent) -> None:
    listing = event.listing
    price = f" - {listing.price_text}" if listing.price_text else ""
    print(f"  {event.human_label()}: {listing.address or listing.title}{price}")
    print(f"    {listing.url}")


def describe_filters(search: SearchConfig) -> str:
    parts = []
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
    if search.url:
        return search.url
    if search.rightmove is None:
        raise ValueError(f"Search {search.name!r} has neither url nor rightmove config.")

    return build_rightmove_url(
        resolve_rightmove_options(
            search.rightmove,
            timeout_seconds=config.http.timeout_seconds,
            user_agent=config.http.user_agent,
        )
    )


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
