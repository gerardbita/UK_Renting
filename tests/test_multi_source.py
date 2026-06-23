from rentwatch.cli import (
    enrich_listings_with_routes,
    preserve_existing_route_data,
    run_once,
    search_config_fingerprint,
)
from rentwatch.config import (
    AppConfig,
    RouteTargetConfig,
    RoutingConfig,
    SearchConfig,
    TelegramConfig,
)
from rentwatch.db import Store
from rentwatch.dedupe import assign_canonical_keys, match_score
from rentwatch.models import Listing
from rentwatch.notifications import TelegramNotifier
from rentwatch.scrapers.base import ScraperError


def test_search_config_accepts_multiple_urls():
    search = SearchConfig.from_dict(
        {
            "name": "work commute",
            "urls": [
                "https://www.rightmove.co.uk/property-to-rent/find.html?index=0",
                "https://www.rightmove.co.uk/property-to-rent/find.html?index=24",
            ],
        }
    )

    assert search.resolved_urls() == [
        "https://www.rightmove.co.uk/property-to-rent/find.html?index=0",
        "https://www.rightmove.co.uk/property-to-rent/find.html?index=24",
    ]


def test_cross_source_match_uses_coordinates_beds_rent_and_address():
    # The dedupe engine is source-agnostic; it merges the same home seen via two
    # different feeds when the signals line up.
    primary = Listing(
        source="rightmove",
        property_id="123",
        url="https://www.rightmove.co.uk/properties/123",
        address="Palace Gardens Terrace, London W8",
        price_text="£1,900 pcm",
        price_pcm=1900,
        bedrooms=1,
        latitude=51.508,
        longitude=-0.193,
    )
    other = Listing(
        source="onthemarket",
        property_id="456",
        url="https://www.onthemarket.com/details/456/",
        address="Palace Gardens Terrace, W8",
        price_text="£1,925 pcm",
        price_pcm=1925,
        bedrooms=1,
        latitude=51.50805,
        longitude=-0.19304,
    )

    score, reasons = match_score(other, primary)
    assert score >= 80
    assert "same bedrooms" in reasons


def test_assign_canonical_keys_reuses_existing_cross_source_property():
    existing = Listing(
        source="rightmove",
        property_id="123",
        url="https://www.rightmove.co.uk/properties/123",
        address="Palace Gardens Terrace, London W8",
        price_text="£1,900 pcm",
        price_pcm=1900,
        bedrooms=1,
        latitude=51.508,
        longitude=-0.193,
        canonical_key="property:rightmove:123",
    )
    scraped = [
        Listing(
            source="onthemarket",
            property_id="456",
            url="https://www.onthemarket.com/details/456/",
            address="Palace Gardens Terrace, W8",
            price_text="£1,925 pcm",
            price_pcm=1925,
            bedrooms=1,
            latitude=51.50805,
            longitude=-0.19304,
        )
    ]

    assign_canonical_keys(scraped, [existing])

    assert scraped[0].canonical_key == "property:rightmove:123"


def test_limited_page_run_can_be_read_only(tmp_path):
    class FakeRightmoveScraper:
        def scrape(self, url, max_pages=None, progress=None):
            return [
                Listing(
                    source="rightmove",
                    property_id="1",
                    url="https://www.rightmove.co.uk/properties/1",
                    address="One Street",
                    price_text="£1,000 pcm",
                    price_pcm=1000,
                )
            ]

    config = AppConfig(
        searches=[
            SearchConfig(
                name="combined",
                urls=["https://www.rightmove.co.uk/property-to-rent/find.html"],
            )
        ]
    )
    store = Store(tmp_path / "rentwatch.sqlite3")
    try:
        run_once(
            config,
            store,
            {"rightmove": FakeRightmoveScraper()},
            TelegramNotifier(TelegramConfig()),
            notify=False,
            show_events=False,
            max_pages=1,
            calculate_routes=False,
            record_results=False,
        )

        assert list(store.iter_listings()) == []
    finally:
        store.close()


def test_partial_scrape_failure_does_not_mark_missing_listings_removed(tmp_path):
    class PartlyFailingRightmoveScraper:
        def scrape(self, url, max_pages=None, progress=None):
            if "fail=true" in url:
                raise ScraperError("timeout")
            return [
                Listing(
                    source="rightmove",
                    property_id="1",
                    url="https://www.rightmove.co.uk/properties/1",
                    address="One Street",
                    price_text="£1,000 pcm",
                    price_pcm=1000,
                )
            ]

    listing_one = Listing(
        source="rightmove",
        property_id="1",
        url="https://www.rightmove.co.uk/properties/1",
        price_pcm=1000,
    )
    listing_two = Listing(
        source="rightmove",
        property_id="2",
        url="https://www.rightmove.co.uk/properties/2",
        price_pcm=1500,
    )
    config = AppConfig(
        searches=[
            SearchConfig(
                name="combined",
                urls=[
                    "https://www.rightmove.co.uk/property-to-rent/find.html",
                    "https://www.rightmove.co.uk/property-to-rent/find.html?fail=true",
                ],
            )
        ]
    )
    store = Store(tmp_path / "rentwatch.sqlite3")
    try:
        store.record_search_results("combined", [listing_one, listing_two])

        run_once(
            config,
            store,
            {"rightmove": PartlyFailingRightmoveScraper()},
            TelegramNotifier(TelegramConfig()),
            notify=False,
            show_events=False,
            max_pages=None,
            calculate_routes=False,
            record_results=True,
        )

        statuses = {
            row["listing_key"]: row["status"]
            for row in store.iter_listings()
        }
        assert statuses["rightmove:1"] == "active"
        assert statuses["rightmove:2"] == "active"
    finally:
        store.close()


def test_changed_search_fingerprint_uses_search_changed_mode(tmp_path):
    class FakeRightmoveScraper:
        def scrape(self, url, max_pages=None, progress=None):
            return [
                Listing(
                    source="rightmove",
                    property_id="1",
                    url="https://www.rightmove.co.uk/properties/1",
                    price_text="£1,000 pcm",
                    price_pcm=1000,
                )
            ]

    previous_search = SearchConfig(
        name="combined",
        urls=["https://www.rightmove.co.uk/property-to-rent/find.html?radius=10"],
    )
    current_search = SearchConfig(
        name="combined",
        urls=["https://www.rightmove.co.uk/property-to-rent/find.html?radius=5"],
    )
    config = AppConfig(searches=[current_search])
    store = Store(tmp_path / "rentwatch.sqlite3")
    try:
        store.record_search_results(
            "combined",
            [
                Listing(
                    source="rightmove",
                    property_id="1",
                    url="https://www.rightmove.co.uk/properties/1",
                    price_pcm=1000,
                ),
                Listing(
                    source="rightmove",
                    property_id="2",
                    url="https://www.rightmove.co.uk/properties/2",
                    price_pcm=1500,
                ),
            ],
        )
        store.set_search_fingerprint(
            "combined",
            search_config_fingerprint(previous_search, previous_search.resolved_urls()),
        )

        run_once(
            config,
            store,
            {"rightmove": FakeRightmoveScraper()},
            TelegramNotifier(TelegramConfig()),
            notify=False,
            show_events=False,
            max_pages=None,
            calculate_routes=False,
            record_results=True,
        )

        statuses = {row["listing_key"]: row["status"] for row in store.iter_listings()}
        assert statuses["rightmove:1"] == "active"
        assert statuses["rightmove:2"] == "out_of_search"
        assert store.get_search_fingerprint("combined") == search_config_fingerprint(
            current_search, current_search.resolved_urls()
        )
    finally:
        store.close()


def test_search_fingerprint_ignores_notification_settings():
    urls = ["https://www.rightmove.co.uk/property-to-rent/find.html?radius=5"]
    first = SearchConfig(name="combined", urls=urls, notify_removed=False)
    second = SearchConfig(name="combined", urls=urls, notify_removed=True)

    assert search_config_fingerprint(first, urls) == search_config_fingerprint(second, urls)


def test_preserves_existing_route_data_for_scraped_listing():
    scraped = [
        Listing(
            source="rightmove",
            property_id="1",
            url="https://www.rightmove.co.uk/properties/1",
        )
    ]
    existing = [
        Listing(
            source="rightmove",
            property_id="1",
            url="https://www.rightmove.co.uk/properties/1",
            route_targets=[
                {
                    "name": "Work",
                    "latitude": 51.5,
                    "longitude": -0.1,
                    "transit_minutes": 20,
                    "transit_distance_km": 4.2,
                    "cycling_minutes": 12,
                    "cycling_distance_km": 3.1,
                }
            ],
            route_updated_at="2026-05-18T12:00:00+00:00",
        )
    ]

    preserve_existing_route_data(scraped, existing)

    assert scraped[0].route_targets == existing[0].route_targets
    assert scraped[0].route_updated_at == existing[0].route_updated_at


def test_complete_route_targets_skip_tfl_calls(tmp_path):
    class ExplodingRoutingClient:
        def public_transport(self, *args, **kwargs):
            raise AssertionError("routing client should not be called")

        def cycling(self, *args, **kwargs):
            raise AssertionError("routing client should not be called")

    listing = Listing(
        source="rightmove",
        property_id="1",
        url="https://www.rightmove.co.uk/properties/1",
        latitude=51.51,
        longitude=-0.12,
        route_targets=[
            {
                "name": "Work",
                "latitude": 51.5,
                "longitude": -0.1,
                "transit_minutes": 20,
                "transit_distance_km": 4.2,
                "cycling_minutes": 12,
                "cycling_distance_km": 3.1,
            }
        ],
        route_updated_at="2026-05-18T12:00:00+00:00",
    )
    config = AppConfig(
        routing=RoutingConfig(
            enabled=True,
            targets=[RouteTargetConfig(name="Work", latitude=51.5, longitude=-0.1)],
        )
    )
    store = Store(tmp_path / "rentwatch.sqlite3")
    try:
        enrich_listings_with_routes(
            config,
            store,
            [listing],
            routing_client=ExplodingRoutingClient(),
            route_limit=None,
            refresh_routes=False,
        )
    finally:
        store.close()
