from pathlib import Path

from rentwatch.db import Store
from rentwatch.models import Listing


def test_store_detects_new_price_change_and_removed(tmp_path: Path):
    store = Store(tmp_path / "rentwatch.sqlite3")
    try:
        listing = Listing(
            source="rightmove",
            property_id="1",
            url="https://example.test/1",
            address="One Street",
            price_text="£1,000 pcm",
            price_pcm=1000,
            latitude=51.5,
            longitude=-0.1,
        )
        events = store.record_search_results("test", [listing])
        assert [event.event_type for event in events] == ["new"]

        changed = Listing(
            source="rightmove",
            property_id="1",
            url="https://example.test/1",
            address="One Street",
            price_text="£950 pcm",
            price_pcm=950,
            latitude=51.5,
            longitude=-0.1,
        )
        events = store.record_search_results("test", [changed])
        assert [event.event_type for event in events] == ["price_change"]
        assert events[0].previous_price_pcm == 1000
        row = next(iter(store.iter_listings()))
        assert row["latitude"] == 51.5
        assert row["longitude"] == -0.1

        events = store.record_search_results("test", [])
        assert [event.event_type for event in events] == ["removed"]
    finally:
        store.close()
