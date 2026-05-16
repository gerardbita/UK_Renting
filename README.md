# RentWatch

RentWatch is a personal property search monitor. It is inspired by the small
RightMoveScraper script, but stores state in SQLite, supports multiple searches,
tracks price changes, filters results, and sends Telegram notifications safely
using POST requests.

Use it at low frequency for personal monitoring. Check the website's terms before
running it, and do not use it for high-volume or commercial scraping.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
```

## Configure

Create a starter config:

```bash
python3 -m rentwatch init-config
```

Or add a search directly:

```bash
python3 -m rentwatch add "Camden 1-bed" "https://www.rightmove.co.uk/property-to-rent/find.html?..."
```

Searches are normally pasted Rightmove result URLs:

```json
{
  "name": "W2 garden unfurnished",
  "url": "https://www.rightmove.co.uk/property-to-rent/find.html?...",
  "include_keywords": [],
  "exclude_keywords": ["student", "short let"],
  "min_price_pcm": 1000,
  "max_price_pcm": 2250,
  "notify_new": true,
  "notify_price_changes": true,
  "notify_removed": false
}
```

Optional routing can calculate TfL public-transport and cycling time to a
specific target:

```json
{
  "routing": {
    "enabled": true,
    "target_name": "London target",
    "target_latitude": 51.5209823,
    "target_longitude": -0.1770073,
    "public_transport": true,
    "cycling": true,
    "cache_hours": null,
    "departure_day": "wednesday",
    "departure_time": "13:00"
  }
}
```

`cache_hours: null` means routes are calculated once and reused. Use
`python3 -m rentwatch run --once --no-notify --refresh-routes` if you
intentionally want to recalculate them.

Edit `config.json` to add Telegram credentials:

```json
{
  "notifications": {
    "telegram": {
      "enabled": true,
      "bot_token": "123456:abc",
      "chat_id": "123456789"
    }
  }
}
```

## Run

Prime the database first so the current listings are saved without sending a
large initial batch of notifications:

```bash
python3 -m rentwatch run --once --prime
```

Then run a single check:

```bash
python3 -m rentwatch run --once
```

Run continuously:

```bash
python3 -m rentwatch run
```

By default it waits a random 30-60 minutes between checks.

## Useful Commands

```bash
python3 -m rentwatch list
python3 -m rentwatch export --output listings.csv
python3 -m rentwatch test-telegram
```

## What It Tracks

- new listings
- returned listings
- removed listings, if enabled per search
- price changes
- latitude and longitude, when Rightmove includes map coordinates
- TfL public-transport time/distance to your configured target
- TfL cycling time/distance to your configured target
- first and last seen timestamps
- price history

The SQLite database defaults to `rentwatch.sqlite3`.
