from unittest.mock import Mock, patch

from rentwatch.config import TelegramConfig
from rentwatch.models import Listing, ListingEvent
from rentwatch.notifications import TelegramNotifier, format_event_message


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
                "name": "Paddington target",
                "transit_minutes": 26,
                "transit_distance_km": 2.67,
                "cycling_minutes": 9,
                "cycling_distance_km": 2.68,
            },
            {
                "name": "Hammersmith target",
                "transit_minutes": 24,
                "transit_distance_km": 3.41,
                "cycling_minutes": 11,
                "cycling_distance_km": 3.29,
            },
        ],
    )
    event = ListingEvent("new", "Noemie work and Gerard work", listing)

    message = format_event_message(event)

    assert "Paddington target: Transit: 26 min, 2.67 km | Cycle: 9 min, 2.68 km" in message
    assert "Hammersmith target: Transit: 24 min, 3.41 km | Cycle: 11 min, 3.29 km" in message


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
