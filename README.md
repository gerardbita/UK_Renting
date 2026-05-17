# RentWatch

RentWatch is a personal property search monitor. It is inspired by the small
RightMoveScraper script, but stores state in SQLite, supports Rightmove and
Zoopla search URLs, tracks price changes, filters results, deduplicates matching
homes across portals, and sends Telegram notifications safely using POST
requests.

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

Or add a pasted search URL directly:

```bash
python3 -m rentwatch add "Camden 1-bed" "https://www.rightmove.co.uk/property-to-rent/find.html?..."
```

You can add a Zoopla URL under the same search name. RentWatch will keep one
combined search and merge duplicate homes when the signals are strong enough:

```bash
python3 -m rentwatch add "Camden 1-bed" "https://www.zoopla.co.uk/to-rent/property/..."
```

Searches can contain one URL or multiple portal URLs:

```json
{
  "name": "W2 garden unfurnished",
  "urls": [
    "https://www.rightmove.co.uk/property-to-rent/find.html?...",
    "https://www.zoopla.co.uk/to-rent/property/..."
  ],
  "include_keywords": [],
  "exclude_keywords": ["student", "short let"],
  "min_price_pcm": 1000,
  "max_price_pcm": 2500,
  "notify_new": true,
  "notify_price_changes": true,
  "notify_removed": false
}
```

Zoopla blocks normal Python HTTP requests more aggressively than Rightmove. If a
Zoopla run reports a browser verification page, run this once and complete the
verification in the Chrome window that opens:

```bash
python3 -m rentwatch auth-zoopla
```

The verification profile is stored locally under `.rentwatch-browser/` and is
ignored by git.

When `config.json` contains a Zoopla URL, `python3 -m rentwatch run` checks
Zoopla access before the normal scraping loop. This makes Zoopla verification
fail fast, before Rightmove scraping, routing, or Telegram notification work
starts. You can bypass that startup check while debugging with:

```bash
python3 -m rentwatch run --skip-zoopla-preflight
```

Optional routing can calculate TfL public-transport and cycling time to a
specific target. To calculate routes to more than one place, add `targets`:

```json
{
  "routing": {
    "enabled": true,
    "public_transport": true,
    "cycling": true,
    "tfl_modes": "tube,bus,overground,elizabeth-line,dlr,national-rail",
    "request_delay_seconds": 0.2,
    "cache_hours": null,
    "departure_day": "wednesday",
    "departure_time": "08:00",
    "targets": [
      {
        "name": "Paddington target",
        "latitude": 51.5209823,
        "longitude": -0.1770073
      },
      {
        "name": "Hammersmith target",
        "latitude": 51.4928449,
        "longitude": -0.2198001
      }
    ]
  }
}
```

`cache_hours: null` means routes are calculated once and reused. Use
`python3 -m rentwatch run --once --no-notify --refresh-routes` if you
intentionally want to recalculate them.

## React dashboard

The GitHub Pages site is a React/Vite dashboard in `web/`. It reads the
exported JSON from `web/public/data/listings.json`; `scripts/export_site_data.py`
also writes that file after updating `docs/data/listings.json`.

```bash
python3 -m rentwatch run --once --no-notify
python3 scripts/export_site_data.py
cd web
npm install
npm run dev
```

For GitHub Pages, the workflow builds the app with `/UK_Renting/` as the base
path and deploys `web/dist`.

If you already have listings in `rentwatch.sqlite3` and only need to fill new
route targets, use the database-only route backfill. This avoids fetching
Rightmove before calculating TfL routes:

```bash
python3 -m rentwatch routes
python3 scripts/export_site_data.py
```

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
- latitude and longitude, when the portal includes map coordinates
- TfL public-transport time/distance to your configured target
- TfL cycling time/distance to your configured target
- source links for matching Rightmove/Zoopla listings shown as one home
- first and last seen timestamps
- price history

The SQLite database defaults to `rentwatch.sqlite3`.
