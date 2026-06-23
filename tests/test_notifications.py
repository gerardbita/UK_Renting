from unittest.mock import Mock, patch

from rentwatch.config import TelegramConfig, TelegramRouteFilterConfig
from rentwatch.models import Listing, ListingEvent
from rentwatch.notifications import (
    TelegramNotifier,
    format_digest,
    format_event_message,
    listing_matches_route_filters,
)


def _listing(**kwargs):
    base = dict(
        source="rightmove",
        property_id="1",
        url="https://www.rightmove.co.uk/properties/1",
    )
    base.update(kwargs)
    return Listing(**base)


def test_telegram_message_includes_all_route_targets():
    listing = Listing(
        source="rightmove",
        property_id="123",
        url="https://www.rightmove.co.uk/properties/123",
        title="Palace Gardens Terrace",
        address="Palace Gardens Terrace, W8",
        price_text="£1,900 pcm",
        bedrooms=1,
        agent="Example Agent",
        route_targets=[
            {
                "name": "Noémie's work",
                "latitude": 51.5209823,
                "longitude": -0.1770073,
                "transit_minutes": 26,
                "transit_distance_km": 2.67,
                "cycling_minutes": 9,
                "cycling_distance_km": 2.68,
            },
            {
                "name": "Gerard's work",
                "latitude": 51.4928449,
                "longitude": -0.2198001,
                "transit_minutes": 24,
                "transit_distance_km": 3.41,
                "cycling_minutes": 11,
                "cycling_distance_km": 3.29,
            },
        ],
    )
    event = ListingEvent("new", "Noemie work and Gerard work", listing)

    message = format_event_message(event)

    assert "Noémie's work: Transit: 26 min, 2.67 km | Cycle: 9 min, 2.68 km" in message
    assert "Gerard's work: Transit: 24 min, 3.41 km | Cycle: 11 min, 3.29 km" in message


def test_telegram_message_falls_back_to_single_target_routes():
    listing = Listing(
        source="rightmove",
        property_id="123",
        url="https://www.rightmove.co.uk/properties/123",
        title="Palace Gardens Terrace",
        transit_minutes=26,
        transit_distance_km=2.67,
        cycling_minutes=9,
        cycling_distance_km=2.68,
    )
    event = ListingEvent("new", "Noemie work and Gerard work", listing)

    message = format_event_message(event)

    assert "Transit: 26 min, 2.67 km | Cycle: 9 min, 2.68 km" in message


def test_price_change_message_shows_delta_and_percent():
    listing = _listing(title="Flat A", price_text="£1,800 pcm", price_pcm=1800)
    event = ListingEvent(
        "price_change",
        "Search",
        listing,
        previous_price_text="£2,000 pcm",
        previous_price_pcm=2000,
    )

    message = format_event_message(event)

    assert "📉" in message
    assert "£2,000 pcm -> £1,800 pcm" in message
    assert "-£200" in message
    assert "-10.0%" in message


def test_digest_summarises_multiple_events():
    new_listing = _listing(property_id="1", title="New Flat", price_text="£1,500 pcm", price_pcm=1500)
    drop_listing = _listing(property_id="2", title="Cheaper Flat", price_text="£1,700 pcm", price_pcm=1700)
    events = [
        ListingEvent("new", "Search", new_listing),
        ListingEvent(
            "price_change",
            "Search",
            drop_listing,
            previous_price_pcm=1900,
            previous_price_text="£1,900 pcm",
        ),
    ]

    digest = format_digest(events)

    assert "1 🆕 new" in digest
    assert "1 📉 price" in digest
    assert "New Flat" in digest
    assert "Cheaper Flat" in digest
    assert "-£200" in digest


def test_telegram_notifier_sends_to_all_recipients():
    config = TelegramConfig(
        enabled=True,
        bot_token="token",
        chat_id="111",
        chat_ids=["222", "111"],
    )
    notifier = TelegramNotifier(config)

    with patch("rentwatch.notifications.requests.post") as post:
        post.return_value = Mock(status_code=200, text="ok")
        notifier.send("hello")

    sent_chat_ids = [call.kwargs["json"]["chat_id"] for call in post.call_args_list]
    assert sent_chat_ids == ["111", "222"]


def test_listing_matches_telegram_route_filter_when_inside_limits():
    listing = Listing(
        source="rightmove",
        property_id="123",
        url="https://www.rightmove.co.uk/properties/123",
        route_targets=[
            {
                "name": "Noémie's work",
                "latitude": 51.5209823,
                "longitude": -0.1770073,
                "transit_minutes": 35,
                "cycling_minutes": 25,
            }
        ],
    )
    route_filter = TelegramRouteFilterConfig(
        target_name="Noémie's work",
        target_latitude=51.5209823,
        target_longitude=-0.1770073,
        max_transit_minutes=35,
        max_cycling_minutes=25,
    )

    assert listing_matches_route_filters(listing, [route_filter])


def test_listing_fails_telegram_route_filter_when_transport_is_too_slow():
    listing = Listing(
        source="rightmove",
        property_id="123",
        url="https://www.rightmove.co.uk/properties/123",
        route_targets=[
            {
                "name": "Noémie's work",
                "latitude": 51.5209823,
                "longitude": -0.1770073,
                "transit_minutes": 36,
                "cycling_minutes": 25,
            }
        ],
    )
    route_filter = TelegramRouteFilterConfig(
        target_name="Noémie's work",
        target_latitude=51.5209823,
        target_longitude=-0.1770073,
        max_transit_minutes=35,
        max_cycling_minutes=25,
    )

    assert not listing_matches_route_filters(listing, [route_filter])


def test_listing_fails_telegram_route_filter_when_cycle_is_too_slow():
    listing = Listing(
        source="rightmove",
        property_id="123",
        url="https://www.rightmove.co.uk/properties/123",
        route_targets=[
            {
                "name": "Noémie's work",
                "latitude": 51.5209823,
                "longitude": -0.1770073,
                "transit_minutes": 35,
                "cycling_minutes": 26,
            }
        ],
    )
    route_filter = TelegramRouteFilterConfig(
        target_name="Noémie's work",
        target_latitude=51.5209823,
        target_longitude=-0.1770073,
        max_transit_minutes=35,
        max_cycling_minutes=25,
    )

    assert not listing_matches_route_filters(listing, [route_filter])
