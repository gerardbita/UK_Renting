from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup, Tag

from rentwatch.models import Listing
from rentwatch.scrapers.base import ScraperError
from rentwatch.scrapers.rightmove import compact_text, parse_bedrooms, parse_price_pcm


ZOOPLA_BASE_URL = "https://www.zoopla.co.uk"
RESULTS_PER_PAGE = 25


class ZooplaScraper:
    source = "zoopla"

    def __init__(
        self,
        *,
        timeout_seconds: int = 20,
        user_agent: str,
        page_delay_seconds: float = 1.0,
        session: requests.Session | None = None,
        browser_fallback: bool = True,
        browser_profile_dir: Path | None = None,
    ):
        self.timeout_seconds = timeout_seconds
        self.page_delay_seconds = page_delay_seconds
        self.browser_fallback = browser_fallback
        self.browser_profile_dir = browser_profile_dir or Path(".rentwatch-browser") / "zoopla"
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
        first_html = self._get_http(url)
        if first_html is None:
            if not self.browser_fallback:
                raise ScraperError(
                    "Zoopla blocked the HTTP request and browser fallback is disabled."
                )
            with zoopla_browser_fetcher(
                self.timeout_seconds,
                profile_dir=self.browser_profile_dir,
            ) as fetch:
                first_html = fetch(url)
                return self._scrape_pages(
                    url,
                    first_html,
                    fetch,
                    max_pages=max_pages,
                    progress=progress,
                )

        return self._scrape_pages(
            url,
            first_html,
            self._get_http_required,
            max_pages=max_pages,
            progress=progress,
        )

    def check_access(self, url: str) -> int:
        first_html = self._get_http(url)
        if first_html is None:
            if not self.browser_fallback:
                raise ScraperError(
                    "Zoopla blocked the HTTP request and browser fallback is disabled."
                )
            with zoopla_browser_fetcher(
                self.timeout_seconds,
                profile_dir=self.browser_profile_dir,
            ) as fetch:
                first_html = fetch(url)

        page = parse_results_html(first_html, page_url=url)
        return len(page.listings)

    def _scrape_pages(
        self,
        url: str,
        first_html: str,
        fetch: Any,
        *,
        max_pages: int | None,
        progress: Callable[[dict[str, Any]], None] | None,
    ) -> list[Listing]:
        first_page = parse_results_html(first_html, page_url=url)
        pages = first_page.page_count or (1 if first_page.listings else 0)
        if max_pages is not None:
            pages = min(pages, max_pages)

        listings_by_key = {listing.listing_key: listing for listing in first_page.listings}
        report_scrape_progress(
            progress,
            source=self.source,
            current_page=1 if pages else 0,
            total_pages=pages,
            current_listings=len(listings_by_key),
            total_listings=None,
        )
        last_page = 1 if pages else 0
        for page_number in range(2, pages + 1):
            if self.page_delay_seconds > 0:
                time.sleep(self.page_delay_seconds)
            page_url = with_page(url, page_number)
            page = parse_results_html(fetch(page_url), page_url=page_url)
            last_page = page_number
            listings_by_key.update(
                {listing.listing_key: listing for listing in page.listings}
            )
            report_scrape_progress(
                progress,
                source=self.source,
                current_page=last_page,
                total_pages=pages,
                current_listings=len(listings_by_key),
                total_listings=None,
            )
        report_scrape_progress(
            progress,
            source=self.source,
            current_page=last_page,
            total_pages=pages,
            current_listings=len(listings_by_key),
            total_listings=None,
            done=True,
        )
        return list(listings_by_key.values())

    def _get_http_required(self, url: str) -> str:
        html = self._get_http(url)
        if html is None:
            raise ScraperError(
                "Zoopla blocked the HTTP request. Retry with browser fallback enabled."
            )
        return html

    def _get_http(self, url: str) -> str | None:
        try:
            response = self.session.get(url, timeout=self.timeout_seconds)
        except requests.RequestException as exc:
            raise ScraperError(f"Failed to fetch Zoopla page: {exc}") from exc
        if response.status_code in {403, 429} or is_cloudflare_challenge(response.text):
            return None
        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ScraperError(f"Failed to fetch Zoopla page: {exc}") from exc
        return response.text


class ParsedPage:
    def __init__(self, listings: list[Listing], page_count: int | None = None):
        self.listings = listings
        self.page_count = page_count


def report_scrape_progress(
    progress: Callable[[dict[str, Any]], None] | None,
    **event: Any,
) -> None:
    if progress is not None:
        progress(event)


def parse_results_html(html: str, *, page_url: str = ZOOPLA_BASE_URL) -> ParsedPage:
    if is_cloudflare_challenge(html):
        raise ScraperError("Zoopla returned a Cloudflare browser challenge.")

    soup = BeautifulSoup(html, "html.parser")
    listings: dict[str, Listing] = {}
    data = extract_next_data(soup)
    for item in iter_listing_payloads(data):
        listing = listing_from_payload(item, page_url=page_url)
        if listing is not None:
            listings.setdefault(listing.listing_key, listing)

    if not listings:
        for card, link in iter_listing_cards(soup):
            listing = listing_from_card(card, link, page_url=page_url)
            if listing is not None:
                listings.setdefault(listing.listing_key, listing)

    return ParsedPage(list(listings.values()), page_count=parse_page_count(soup, data))


def is_cloudflare_challenge(html: str) -> bool:
    lower = html.lower()
    return (
        ("just a moment" in lower and "cloudflare" in lower)
        or "challenges.cloudflare.com" in lower
        or "performing security verification" in lower
    )


@contextmanager
def zoopla_browser_fetcher(timeout_seconds: int, *, profile_dir: Path) -> Iterable[Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ScraperError(
            "Zoopla blocked direct HTTP. Install Playwright in this venv to use "
            "the browser fallback: python3 -m pip install playwright"
        ) from exc

    playwright = sync_playwright().start()
    context = None
    try:
        profile_dir.mkdir(parents=True, exist_ok=True)
        context = playwright.chromium.launch_persistent_context(
            str(profile_dir),
            channel="chrome",
            headless=False,
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(timeout_seconds * 1000)

        def fetch(url: str) -> str:
            response = page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=timeout_seconds * 1000,
            )
            if response is not None and response.status >= 400:
                # Zoopla often clears a 403 challenge in a headed browser after JS runs.
                page.wait_for_timeout(12000)
            else:
                page.wait_for_timeout(6000)
            html = page.content()
            if is_cloudflare_challenge(html):
                raise ScraperError(
                    "Zoopla is still showing a browser verification page. "
                    "Run `python3 -m rentwatch auth-zoopla`, complete the "
                    "verification in the opened Chrome window, then retry."
                )
            return html

        yield fetch
    finally:
        if context is not None:
            context.close()
        playwright.stop()


def open_zoopla_browser_profile(
    url: str,
    *,
    profile_dir: Path,
    timeout_seconds: int,
) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ScraperError(
            "Playwright is required for Zoopla browser authentication. "
            "Install it with: python3 -m pip install playwright"
        ) from exc

    profile_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(profile_dir),
            channel="chrome",
            headless=False,
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(timeout_seconds * 1000)
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_seconds * 1000)
            print("Chrome is open with the RentWatch Zoopla profile.")
            print("Complete any Zoopla verification, then press Enter here.")
            input()
        finally:
            context.close()


def extract_next_data(soup: BeautifulSoup) -> dict[str, Any]:
    script = soup.find("script", id="__NEXT_DATA__")
    if script is None or not script.string:
        return {}
    try:
        data = json.loads(script.string)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def iter_listing_payloads(data: Any) -> Iterable[dict[str, Any]]:
    seen: set[int] = set()
    for item in walk_dicts(data):
        if id(item) in seen:
            continue
        seen.add(id(item))
        if looks_like_listing(item):
            yield item


def walk_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_dicts(child)


def looks_like_listing(item: dict[str, Any]) -> bool:
    text_values = " ".join(str(value) for value in item.values() if isinstance(value, str))
    has_url = "/to-rent/details/" in text_values or "/property/" in text_values
    has_id = any(key in item for key in ["listingId", "listing_id", "listingIdV2", "propertyId"])
    has_price = any(key in item for key in ["price", "pricing", "rentalPrices", "priceTitle"])
    return (has_url or has_id) and has_price


def listing_from_payload(item: dict[str, Any], *, page_url: str) -> Listing | None:
    url = first_url(item)
    property_id = first_string(
        item,
        ["listingId", "listing_id", "listingIdV2", "propertyId", "id"],
    )
    if not property_id and url:
        property_id = extract_property_id(url)
    if not property_id:
        return None

    if not url:
        url = f"{ZOOPLA_BASE_URL}/to-rent/details/{property_id}/"
    url = urljoin(ZOOPLA_BASE_URL, url)
    price_text = first_price_text(item)
    latitude, longitude = extract_coordinates(item)
    address = first_address(item)
    title = first_string(item, ["title", "propertyTitle", "propertyType"]) or address
    summary = first_string(item, ["description", "shortDescription", "summary"])
    agent = first_agent(item)
    image_urls = extract_image_urls(item)

    return Listing(
        source="zoopla",
        property_id=str(property_id),
        url=url,
        address=address,
        price_text=price_text,
        price_pcm=parse_price_pcm(price_text),
        bedrooms=first_int(item, ["numBedrooms", "bedrooms", "beds", "bedroomCount"]),
        latitude=latitude,
        longitude=longitude,
        agent=agent,
        summary=summary,
        title=title,
        raw={
            "page_url": page_url,
            "image_urls": image_urls,
            "has_embedded_property_data": True,
        },
    )


def iter_listing_cards(soup: BeautifulSoup) -> list[tuple[Tag, Tag]]:
    links = soup.select("a[href*='/to-rent/details/']")
    cards = []
    for link in links:
        card = link.find_parent(["article", "li", "div"]) or link
        cards.append((card, link))
    return cards


def listing_from_card(card: Tag, link: Tag, *, page_url: str) -> Listing | None:
    href = link.get("href")
    if not href:
        return None
    url = urljoin(ZOOPLA_BASE_URL, str(href))
    property_id = extract_property_id(url)
    text = compact_text(card.get_text(" ", strip=True))
    price_match = re.search(r"£\s*[0-9,]+(?:\.\d+)?\s*(?:pcm|pw|per month|per week)?", text, re.I)
    price_text = compact_text(price_match.group(0)) if price_match else ""
    title = compact_text(link.get_text(" ", strip=True)) or text[:120]
    return Listing(
        source="zoopla",
        property_id=property_id,
        url=url,
        address=title,
        price_text=price_text,
        price_pcm=parse_price_pcm(price_text),
        bedrooms=parse_bedrooms(text),
        title=title,
        summary=text[:500],
        raw={"page_url": page_url, "card_text": text},
    )


def parse_page_count(soup: BeautifulSoup, data: dict[str, Any]) -> int | None:
    for item in walk_dicts(data):
        total = first_int(item, ["totalResults", "resultCount", "total"])
        if total:
            return max(1, (total + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE)
    text = soup.get_text(" ", strip=True)
    match = re.search(r"([0-9][0-9,]*)\s+results", text, re.I)
    if not match:
        return None
    total = int(match.group(1).replace(",", ""))
    return max(1, (total + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE)


def with_page(url: str, page: int) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["pn"] = str(page)
    return urlunparse(parsed._replace(query=urlencode(query)))


def first_url(item: dict[str, Any]) -> str:
    for key in ["detailsUrl", "detailUrl", "listingUrl", "listing_url", "url", "propertyUrl"]:
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def first_price_text(item: dict[str, Any]) -> str:
    for key in ["priceTitle", "priceLabel", "displayPrice"]:
        value = item.get(key)
        if isinstance(value, str) and value:
            return compact_text(value)
    price = item.get("price")
    if isinstance(price, str):
        return compact_text(price)
    if isinstance(price, dict):
        text = first_string(price, ["label", "display", "title", "priceTitle"])
        if text:
            return text
        amount = first_int(price, ["amount", "value", "pcm"])
        if amount:
            return f"£{amount:,} pcm"
    rental = item.get("rentalPrices")
    if isinstance(rental, dict):
        amount = first_int(rental, ["perMonth", "monthly", "pcm"])
        if amount:
            return f"£{amount:,} pcm"
    return ""


def first_address(item: dict[str, Any]) -> str:
    value = item.get("address")
    if isinstance(value, str):
        return compact_text(value)
    if isinstance(value, dict):
        parts = [
            first_string(value, ["addressLine1", "addressLine2", "street"]),
            first_string(value, ["town", "city"]),
            first_string(value, ["postcode", "outcode"]),
        ]
        return compact_text(", ".join(part for part in parts if part))
    return first_string(item, ["displayAddress", "addressLabel", "location"]) or ""


def first_agent(item: dict[str, Any]) -> str:
    for key in ["agent", "branch"]:
        value = item.get(key)
        if isinstance(value, dict):
            text = first_string(value, ["name", "branchName"])
            if text:
                return text
        if isinstance(value, str):
            return compact_text(value)
    return first_string(item, ["agentName", "branchName"]) or ""


def extract_coordinates(item: dict[str, Any]) -> tuple[float | None, float | None]:
    latitude = first_float(item, ["latitude", "lat"])
    longitude = first_float(item, ["longitude", "lng", "lon"])
    if latitude is not None and longitude is not None:
        return latitude, longitude

    location = item.get("location")
    if isinstance(location, dict):
        return (
            first_float(location, ["latitude", "lat"]),
            first_float(location, ["longitude", "lng", "lon"]),
        )
    return None, None


def extract_image_urls(item: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for value in walk_values(item):
        if not isinstance(value, str):
            continue
        if not re.search(r"\.(?:jpg|jpeg|png|webp)(?:\?|$)", value, re.I):
            continue
        url = urljoin(ZOOPLA_BASE_URL, value)
        if url not in urls:
            urls.append(url)
    return urls[:12]


def walk_values(value: Any) -> Iterable[Any]:
    if isinstance(value, dict):
        for child in value.values():
            yield from walk_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_values(child)
    else:
        yield value


def extract_property_id(url: str) -> str:
    for pattern in [r"/details/(\d+)", r"listing[_-]?id=(\d+)", r"/(\d+)/?$"]:
        match = re.search(pattern, url, re.I)
        if match:
            return match.group(1)
    return hashlib.sha1(url.split("#", 1)[0].encode("utf-8")).hexdigest()[:16]


def first_string(item: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value:
            return compact_text(value)
        if value is not None and not isinstance(value, (dict, list)):
            return compact_text(str(value))
    return ""


def first_int(item: dict[str, Any], keys: list[str]) -> int | None:
    for key in keys:
        value = item.get(key)
        if value is None or value == "":
            continue
        try:
            return int(float(str(value).replace(",", "")))
        except ValueError:
            continue
    return None


def first_float(item: dict[str, Any], keys: list[str]) -> float | None:
    for key in keys:
        value = item.get(key)
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None
