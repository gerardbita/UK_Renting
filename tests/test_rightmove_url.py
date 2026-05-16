from urllib.parse import parse_qs, urlparse

from rentwatch.config import SearchConfig
from rentwatch.rightmove_url import RightmoveUrlOptions, build_rightmove_url


def test_build_rightmove_url_from_structured_options():
    url = build_rightmove_url(
        RightmoveUrlOptions(
            search_location="W2 1SJ",
            location_identifier="POSTCODE^918640",
            radius=5.0,
            min_price_pcm=1000,
            max_price_pcm=2250,
            min_bedrooms=1,
            property_types=["detached", "semi-detached", "terraced", "flat", "bungalow"],
            dont_show=["houseShare", "retirement", "student"],
            must_have=["garden"],
            furnish_types=["unfurnished", "partFurnished"],
        )
    )

    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    assert parsed.path == "/property-to-rent/find.html"
    assert params["searchLocation"] == ["W2 1SJ"]
    assert params["locationIdentifier"] == ["POSTCODE^918640"]
    assert params["radius"] == ["5"]
    assert params["minPrice"] == ["1000"]
    assert params["maxPrice"] == ["2250"]
    assert params["mustHave"] == ["garden"]
    assert params["furnishTypes"] == ["unfurnished,partFurnished"]
    assert "_includeLetAgreed" not in params


def test_search_config_resolves_structured_rightmove_url():
    search = SearchConfig(
        name="test",
        rightmove=RightmoveUrlOptions(search_location="W2 1SJ"),
    )

    assert "searchLocation=W2+1SJ" in search.resolved_url()
