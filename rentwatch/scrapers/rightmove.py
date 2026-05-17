from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup, Tag

from rentwatch.models import Listing
from rentwatch.scrapers.base import ScraperError


RIGHTMOVE_BASE_URL = "https://www.rightmove.co.uk"
RESULTS_PER_PAGE = 24


class RightmoveScraper:
    source = "rightmove"

    def __init__(
        self,
        *,
        timeout_seconds: int = 20,
        user_agent: str,
        page_delay_seconds: float = 1.0,
        session: requests.Session | None = None,
    ):
        self.timeout_seconds = timeout_seconds
        self.page_delay_seconds = page_delay_seconds
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-GB,en;q=0.9",
            }
        )

    def scrape(
        self,
        url: str,
        max_pages: int | None = None,
        progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> list[Listing]:
        first_html = self._get(url)
        first_page = parse_results_html(first_html, page_url=url)
        pages = page_count(first_page.total_count, len(first_page.listings))
        if max_pages is not None:
            pages = min(pages, max_pages)

        listings_by_key = {listing.listing_key: listing for listing in first_page.listings}
        report_scrape_progress(
            progress,
            source=self.source,
            current_page=1 if pages else 0,
            total_pages=pages,
            current_listings=len(listings_by_key),
            total_listings=first_page.total_count,
        )
        empty_pages = 0
        last_page = 1 if pages else 0
        for page_number in range(1, pages):
            if self.page_delay_seconds > 0:
                time.sleep(self.page_delay_seconds)
            page_url = with_result_index(url, page_number * RESULTS_PER_PAGE)
            page = parse_results_html(self._get(page_url), page_url=page_url)
            last_page = page_number + 1
            if not page.listings:
                empty_pages += 1
            else:
                empty_pages = 0
            listings_by_key.update(
                {listing.listing_key: listing for listing in page.listings}
            )
            report_scrape_progress(
                progress,
                source=self.source,
                current_page=last_page,
                total_pages=pages,
                current_listings=len(listings_by_key),
                total_listings=first_page.total_count,
            )
            if empty_pages >= 2:
                report_scrape_progress(
                    progress,
                    source=self.source,
                    current_page=last_page,
                    total_pages=pages,
                    current_listings=len(listings_by_key),
                    total_listings=first_page.total_count,
                    done=True,
                    stopped_early=True,
                )
                return list(listings_by_key.values())
        report_scrape_progress(
            progress,
            source=self.source,
            current_page=last_page,
            total_pages=pages,
            current_listings=len(listings_by_key),
            total_listings=first_page.total_count,
            done=True,
        )
        return list(listings_by_key.values())

    def _get(self, url: str) -> str:
        try:
            response = self.session.get(url, timeout=self.timeout_seconds)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ScraperError(f"Failed to fetch Rightmove page: {exc}") from exc
        return response.text


class ParsedPage:
    def __init__(self, listings: list[Listing], total_count: int | None):
        self.listings = listings
        self.total_count = total_count


def report_scrape_progress(
    progress: Callable[[dict[str, Any]], None] | None,
    **event: Any,
) -> None:
    if progress is not None:
        progress(event)


def parse_results_html(html: str, *, page_url: str = RIGHTMOVE_BASE_URL) -> ParsedPage:
    soup = BeautifulSoup(html, "html.parser")
    search_results = extract_next_data_search_results(soup)
    total_count = parse_total_count(soup, search_results=search_results)
    property_data_by_id = extract_property_data_by_id(search_results)
    listings: dict[str, Listing] = {}

    for card, link in iter_listing_cards(soup):
        listing = listing_from_card(
            card,
            link,
            page_url=page_url,
            property_data_by_id=property_data_by_id,
        )
        if listing is not None:
            listings.setdefault(listing.listing_key, listing)

    return ParsedPage(list(listings.values()), total_count)


def iter_listing_cards(soup: BeautifulSoup) -> list[tuple[Tag, Tag]]:
    links = soup.select("a.propertyCard-link[href]")
    if not links:
        links = soup.select("a[data-test='property-card-link'][href]")
    if not links:
        links = soup.select("a[href*='/properties/']")

    cards: list[tuple[Tag, Tag]] = []
    for link in links:
        card = link.find_parent(_is_listing_container)
        if card is None:
            card = link.parent if isinstance(link.parent, Tag) else link
        cards.append((card, link))
    return cards


def listing_from_card(
    card: Tag,
    link: Tag,
    *,
    page_url: str,
    property_data_by_id: dict[str, dict[str, Any]] | None = None,
) -> Listing | None:
    href = link.get("href")
    if not href:
        return None
    url = urljoin(RIGHTMOVE_BASE_URL, str(href))
    property_id = extract_property_id(url, card)
    property_data = (property_data_by_id or {}).get(property_id, {})
    latitude, longitude = extract_coordinates(property_data)

    price_text = extract_price_text(card)
    address = compact_text(
        first_text(
            card,
            [
                "address.propertyCard-address",
                ".propertyCard-address",
                "[data-testid='property-address'] address",
                "[data-testid='property-address']",
                "[data-test='propertyCard-address']",
                "address",
            ],
        )
    )
    property_type = compact_text(
        first_text(
            card,
            [
                "[class*='PropertyInformation_propertyType']",
            ],
        )
    )
    title = compact_text(
        first_text(
            card,
            [
                ".propertyCard-title",
                "[data-test='propertyCard-title']",
                "[data-testid='property-title']",
                "h2",
            ],
        )
    )
    bedrooms = extract_bedrooms(card, " ".join([title, summary_text(card), address]))
    if not title and bedrooms is not None and property_type:
        title = f"{bedrooms} bed {property_type}"
    summary = compact_text(
        first_text(
            card,
            [
                ".propertyCard-description",
                "[data-test='propertyCard-description']",
                "[data-testid='property-description']",
                ".propertyCard-summary",
            ],
        )
    )
    agent = extract_agent(card)

    raw = {
        "page_url": page_url,
        "card_text": compact_text(card.get_text(" ", strip=True)),
        "has_embedded_property_data": bool(property_data),
    }
    return Listing(
        source="rightmove",
        property_id=property_id,
        url=url,
        address=address,
        price_text=price_text,
        price_pcm=parse_price_pcm(price_text),
        bedrooms=bedrooms,
        latitude=latitude,
        longitude=longitude,
        agent=agent,
        summary=summary,
        title=title,
        raw=raw,
    )


def parse_total_count(
    soup: BeautifulSoup, *, search_results: dict[str, Any] | None = None
) -> int | None:
    if search_results:
        for key in ["resultCount", "total"]:
            value = search_results.get(key)
            if value is not None:
                return int(str(value).replace(",", ""))

    text = first_text(
        soup,
        [
            ".searchHeader-resultCount",
            "[data-test='searchHeader-resultCount']",
            "[data-testid='result-count']",
        ],
    )
    if not text:
        html = str(soup)
        for pattern in [
            r'"resultCount"\s*:\s*"([0-9][0-9,]*)"',
            r'"resultCount"\s*:\s*([0-9][0-9,]*)',
        ]:
            match = re.search(pattern, html)
            if match:
                return int(match.group(1).replace(",", ""))
        return None
    match = re.search(r"([0-9][0-9,]*)", text)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def extract_next_data_search_results(soup: BeautifulSoup) -> dict[str, Any]:
    script = soup.find("script", id="__NEXT_DATA__")
    if script is None or not script.string:
        return {}
    try:
        data = json.loads(script.string)
    except json.JSONDecodeError:
        return {}
    search_results = (
        data.get("props", {})
        .get("pageProps", {})
        .get("searchResults", {})
    )
    return search_results if isinstance(search_results, dict) else {}


def extract_property_data_by_id(
    search_results: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    properties = search_results.get("properties", [])
    if not isinstance(properties, list):
        return {}

    data_by_id: dict[str, dict[str, Any]] = {}
    for item in properties:
        if isinstance(item, dict) and item.get("id") is not None:
            data_by_id[str(item["id"])] = item
    return data_by_id


def extract_coordinates(property_data: dict[str, Any]) -> tuple[float | None, float | None]:
    location = property_data.get("location", {})
    if not isinstance(location, dict):
        return None, None
    return _optional_float(location.get("latitude")), _optional_float(
        location.get("longitude")
    )


def page_count(total_count: int | None, listings_on_first_page: int) -> int:
    if total_count is None:
        return 1 if listings_on_first_page else 0
    if total_count <= 0:
        return 0
    return math.ceil(total_count / RESULTS_PER_PAGE)


def with_result_index(url: str, index: int) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["index"] = str(index)
    return urlunparse(parsed._replace(query=urlencode(query)))


def extract_property_id(url: str, card: Tag | None = None) -> str:
    for pattern in [
        r"/properties/(\d+)",
        r"property-(\d+)",
        r"prop(?:erty)?Id=(\d+)",
    ]:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    if card is not None:
        for attribute in ["data-property-id", "data-test-property-id", "id"]:
            value = card.get(attribute)
            if value:
                match = re.search(r"(\d+)", str(value))
                if match:
                    return match.group(1)

    normalized = url.split("#", 1)[0]
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


def parse_price_pcm(price_text: str) -> int | None:
    text = price_text.lower()
    match = re.search(r"£\s*([0-9,]+(?:\.\d+)?)", text)
    if not match:
        return None

    amount = float(match.group(1).replace(",", ""))
    if any(token in text for token in ["pw", "per week", "weekly", "pppw"]):
        amount = amount * 52 / 12
    return round(amount)


def parse_bedrooms(text: str) -> int | None:
    match = re.search(r"\b([0-9]+)\s*(?:beds?|bedrooms?)\b", text.lower())
    if not match:
        return None
    return int(match.group(1))


def extract_price_text(card: Tag) -> str:
    for selector in [
        ".propertyCard-priceValue",
        "[class*='PropertyPrice_price__']",
        "[data-test='propertyCard-price']",
        "[data-testid='property-price']",
    ]:
        node = card.select_one(selector)
        if node is None:
            continue
        text = compact_text(node.get_text(" ", strip=True))
        match = re.search(
            r"£\s*[0-9,]+(?:\.\d+)?\s*(?:pcm|pw|per month|per week|pppw)?",
            text,
            flags=re.I,
        )
        if match:
            return compact_text(match.group(0))
        if text:
            return text
    return ""


def extract_bedrooms(card: Tag, fallback_text: str) -> int | None:
    text = first_text(
        card,
        [
            "[class*='PropertyInformation_bedroomsCount']",
            "[data-testid='property-bedrooms']",
        ],
    )
    if text and text.strip().isdigit():
        return int(text.strip())

    for node in card.select("[aria-label]"):
        aria_label = str(node.get("aria-label", ""))
        if "bed" not in " ".join(node.parent.get("class", [])).lower():
            continue
        match = re.search(r"\b([0-9]+)\b", aria_label)
        if match:
            return int(match.group(1))

    return parse_bedrooms(fallback_text)


def extract_agent(card: Tag) -> str:
    title = first_attribute(
        card,
        [
            "[data-testid^='property-branch-logo'][title]",
            ".propertyCard-branchLogo[title]",
        ],
        "title",
    )
    if title:
        return compact_text(title)

    return compact_text(
        first_text(
            card,
            [
                ".propertyCard-branchSummary",
                "[data-test='propertyCard-branchSummary']",
                "[data-testid='marketed-by-text']",
                ".propertyCard-agent",
            ],
        )
    )


def summary_text(card: Tag) -> str:
    return first_text(
        card,
        [
            ".propertyCard-description",
            "[data-test='propertyCard-description']",
            "[data-testid='property-description']",
            ".propertyCard-summary",
        ],
    )


def first_text(root: Tag | BeautifulSoup, selectors: list[str]) -> str:
    for selector in selectors:
        node = root.select_one(selector)
        if node is not None:
            text = node.get_text(" ", strip=True)
            if text:
                return text
    return ""


def first_attribute(root: Tag | BeautifulSoup, selectors: list[str], attribute: str) -> str:
    for selector in selectors:
        node = root.select_one(selector)
        if node is not None:
            value = node.get(attribute)
            if value:
                return str(value)
    return ""


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def compact_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _is_listing_container(tag: Tag) -> bool:
    if tag.name not in {"div", "article", "li"}:
        return False
    class_text = " ".join(tag.get("class", []))
    test_id = str(tag.get("data-testid", ""))
    return (
        bool(re.fullmatch(r"propertyCard-\d+", test_id))
        or "l-searchResult" in class_text
        or "propertyCard-details" in class_text
        or "PropertyCard_propertyCardContainer__" in class_text
    )
