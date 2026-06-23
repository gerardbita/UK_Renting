from pathlib import Path

import requests

from rentwatch.scrapers.rightmove import (
    RightmoveScraper,
    parse_price_pcm,
    parse_results_html,
    with_result_index,
)


FIXTURE = Path(__file__).parent / "fixtures" / "rightmove_search.html"


def test_parse_results_deduplicates_and_extracts_fields():
    page = parse_results_html(FIXTURE.read_text(), page_url="https://example.test/search")

    assert page.total_count == 2
    assert len(page.listings) == 2

    first = page.listings[0]
    assert first.property_id == "123456789"
    assert first.price_pcm == 1750
    assert first.bedrooms == 1
    assert first.latitude == 51.5412
    assert first.longitude == -0.1421
    assert first.address == "Example Road, Camden, London"
    assert first.agent == "Marketed by Example Estates"


def test_parse_extracts_rich_detail_from_next_data():
    page = parse_results_html(FIXTURE.read_text(), page_url="https://example.test/search")
    by_id = {listing.property_id: listing for listing in page.listings}

    rich = by_id["123456789"]
    assert rich.image_urls == [
        "https://media.rightmove.co.uk/photo_max_1.jpeg",
        "https://media.rightmove.co.uk/photo_max_2.jpeg",
    ]
    assert rich.main_image == "https://media.rightmove.co.uk/photo_max_1.jpeg"
    assert rich.raw["image_urls"] == rich.image_urls  # powers cross-portal dedupe
    assert rich.bathrooms == 1
    assert rich.property_subtype == "Apartment"
    assert rich.size_sqft == 650
    assert rich.first_listed_date == "2026-05-01T10:00:00Z"
    assert rich.added_or_reduced == "Reduced on 10/05/2026"
    assert rich.update_reason == "price_reduced"
    assert rich.available_date == "2026-06-01"
    assert rich.key_features == ["Balcony", "Modern kitchen"]
    assert rich.let_agreed is False

    assert by_id["987654321"].let_agreed is True  # displayStatus "Let Agreed"


def test_weekly_rent_is_normalized_to_pcm():
    assert parse_price_pcm("£450 pw") == 1950


def test_with_result_index_replaces_existing_index():
    url = with_result_index("https://www.rightmove.co.uk/find.html?a=1&index=24", 48)
    assert url == "https://www.rightmove.co.uk/find.html?a=1&index=48"


def test_rightmove_fetch_retries_transient_timeout():
    class FakeResponse:
        text = FIXTURE.read_text()

        def raise_for_status(self):
            return None

    class FlakySession:
        def __init__(self):
            self.headers = {}
            self.calls = 0

        def get(self, url, timeout):
            self.calls += 1
            if self.calls == 1:
                raise requests.Timeout("temporary timeout")
            return FakeResponse()

    session = FlakySession()
    scraper = RightmoveScraper(
        timeout_seconds=1,
        user_agent="test",
        retry_attempts=2,
        retry_delay_seconds=0,
        session=session,
    )

    listings = scraper.scrape("https://www.rightmove.co.uk/property-to-rent/find.html")

    assert session.calls == 2
    assert len(listings) == 2
