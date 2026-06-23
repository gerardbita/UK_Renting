from unittest.mock import Mock, patch

from rentwatch.config import TelegramConfig, TelegramRouteFilterConfig
from rentwatch.models import Listing, ListingEvent
from rentwatch.notifications import (
    TelegramNotifier,
    format_event_message,
    listing_matches_route_filters,
)


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
