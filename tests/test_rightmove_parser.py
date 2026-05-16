from pathlib import Path

from rentwatch.scrapers.rightmove import (
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


def test_weekly_rent_is_normalized_to_pcm():
    assert parse_price_pcm("£450 pw") == 1950


def test_with_result_index_replaces_existing_index():
    url = with_result_index("https://www.rightmove.co.uk/find.html?a=1&index=24", 48)
    assert url == "https://www.rightmove.co.uk/find.html?a=1&index=48"
