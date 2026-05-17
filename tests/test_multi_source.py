from rentwatch.config import SearchConfig
from rentwatch.dedupe import assign_canonical_keys, match_score
from rentwatch.models import Listing
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
