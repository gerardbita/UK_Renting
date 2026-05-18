from argparse import Namespace

from rentwatch.cli import (
    enabled_sources_from_args,
    enrich_listings_with_routes,
    filter_urls_by_source,
    preserve_existing_route_data,
    preflight_zoopla_access,
    run_once,
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
from rentwatch.scrapers.zoopla import parse_results_html, with_page


def test_search_config_accepts_multiple_urls():
    search = SearchConfig.from_dict(
        {
            "name": "work commute",
            "urls": [
                "https://www.rightmove.co.uk/property-to-rent/find.html?index=0",
                "https://www.zoopla.co.uk/to-rent/property/london/w2/",
            ],
        }
    )

    assert search.resolved_urls() == [
        "https://www.rightmove.co.uk/property-to-rent/find.html?index=0",
        "https://www.zoopla.co.uk/to-rent/property/london/w2/",
    ]


def test_cross_source_match_uses_coordinates_beds_rent_and_address():
    rightmove = Listing(
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
    zoopla = Listing(
        source="zoopla",
        property_id="456",
        url="https://www.zoopla.co.uk/to-rent/details/456/",
        address="Palace Gardens Terrace, W8",
        price_text="£1,925 pcm",
        price_pcm=1925,
        bedrooms=1,
        latitude=51.50805,
        longitude=-0.19304,
    )

    score, reasons = match_score(zoopla, rightmove)
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
            source="zoopla",
            property_id="456",
            url="https://www.zoopla.co.uk/to-rent/details/456/",
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


def test_zoopla_card_parser_extracts_listing_fields():
    html = """
    <html><body>
      <article>
        <a href="/to-rent/details/987654/">Pavilion Court, Stafford Road, London NW6</a>
        <span>£2,200 pcm</span>
        <span>2 beds</span>
        <p>A newly refurbished flat close to transport.</p>
      </article>
    </body></html>
    """

    page = parse_results_html(html, page_url="https://www.zoopla.co.uk/to-rent/")

    assert len(page.listings) == 1
    assert page.listings[0].listing_key == "zoopla:987654"
    assert page.listings[0].price_pcm == 2200
    assert page.listings[0].bedrooms == 2
    assert page.listings[0].url == "https://www.zoopla.co.uk/to-rent/details/987654/"


def test_zoopla_page_number_uses_pn_query_param():
    assert (
        with_page("https://www.zoopla.co.uk/to-rent/property/london/w2/?q=W2", 3)
        == "https://www.zoopla.co.uk/to-rent/property/london/w2/?q=W2&pn=3"
    )


def test_zoopla_preflight_runs_before_scraping():
    calls = []

    class FakeZooplaScraper:
        def check_access(self, url):
            calls.append(url)
            return 25

    config = AppConfig(
        searches=[
            SearchConfig(
                name="combined",
                urls=[
                    "https://www.rightmove.co.uk/property-to-rent/find.html",
                    "https://www.zoopla.co.uk/to-rent/property/london/w2/",
                ],
            )
        ]
    )

    assert preflight_zoopla_access(config, {"zoopla": FakeZooplaScraper()})
    assert calls == ["https://www.zoopla.co.uk/to-rent/property/london/w2/"]


def test_skip_zoopla_sources_filters_urls_and_preflight():
    urls = [
        "https://www.rightmove.co.uk/property-to-rent/find.html",
        "https://www.zoopla.co.uk/to-rent/property/london/w2/",
    ]
    sources = enabled_sources_from_args(
        Namespace(skip_zoopla=True, only_zoopla=False)
    )

    assert sources == {"rightmove"}
    assert filter_urls_by_source(urls, sources) == [urls[0]]

    config = AppConfig(searches=[SearchConfig(name="combined", urls=urls)])
    assert preflight_zoopla_access(config, {}, enabled_sources=sources)


def test_only_zoopla_sources_filters_urls():
    urls = [
        "https://www.rightmove.co.uk/property-to-rent/find.html",
        "https://www.zoopla.co.uk/to-rent/property/london/w2/",
    ]
    sources = enabled_sources_from_args(
        Namespace(skip_zoopla=False, only_zoopla=True)
    )

    assert sources == {"zoopla"}
    assert filter_urls_by_source(urls, sources) == [urls[1]]


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
