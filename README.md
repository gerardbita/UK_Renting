# RentWatch

RentWatch is a personal London rental monitor. It scrapes Rightmove search URLs,
stores state in SQLite, tracks price changes, captures listing photos and detail,
deduplicates matching homes, scores each listing against **two** commute
destinations, and sends Telegram alerts. A dark, data-dense React dashboard is
published to GitHub Pages.

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

Or add a pasted Rightmove search URL directly:

```bash
python3 -m rentwatch add "Camden 1-bed" "https://www.rightmove.co.uk/property-to-rent/find.html?..."
```

A search can hold one URL or several (e.g. price bands — see below):

```json
{
  "name": "W2 garden unfurnished",
  "urls": [
    "https://www.rightmove.co.uk/property-to-rent/find.html?..."
  ],
  "include_keywords": [],
  "exclude_keywords": ["student", "short let"],
  "min_price_pcm": 1000,
  "max_price_pcm": 2200,
  "notify_new": true,
  "notify_price_changes": true,
  "notify_removed": false
}
```

### Secrets via environment variables

Any string in `config.json` may reference an environment variable with
`${VAR}` syntax, so secrets never need to live in the file:

```json
{
  "notifications": {
    "telegram": {
      "enabled": true,
      "bot_token": "${TELEGRAM_BOT_TOKEN}",
      "chat_id": "${TELEGRAM_CHAT_ID}",
      "chat_ids": [],
      "digest": false
    }
  }
}
```

```bash
export TELEGRAM_BOT_TOKEN="123456:abc"
export TELEGRAM_CHAT_ID="123456789"
```

Unknown variables are left untouched. `chat_id` is the main recipient; add extra
recipients to `chat_ids`. Set `"digest": true` to receive **one** combined message
per poll ("🆕 4 new · 📉 2 price drops" plus the top items) instead of one message
per change.

### Routing to two destinations

Optional routing calculates TfL public-transport and cycling time to each target:

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
      { "name": "Noémie's work", "latitude": 51.5209823, "longitude": -0.1770073 },
      { "name": "Gerard's work", "latitude": 51.4928449, "longitude": -0.2198001 }
    ]
  }
}
```

`cache_hours: null` calculates routes once and reuses them. Force a recalculation
with `python3 -m rentwatch run --once --no-notify --refresh-routes`.

Telegram alerts can be limited by commute time (this only filters what is *sent*;
the dashboard still stores and shows everything):

```json
{
  "notifications": {
    "telegram": {
      "route_filters": [
        {
          "target_name": "Noémie's work",
          "target_latitude": 51.5209823,
          "target_longitude": -0.1770073,
          "max_transit_minutes": 35,
          "max_cycling_minutes": 25
        }
      ]
    }
  }
}
```

## Run

Prime the database first so current listings are saved without a large initial
notification batch:

```bash
python3 -m rentwatch run --once --prime
```

Then a single check:

```bash
python3 -m rentwatch run --once
```

Limited page checks are read-only by default, so this is safe for testing:

```bash
python3 -m rentwatch run --once --max-pages 1 --skip-routes
```

Use `--allow-partial-write` only if you intentionally want a limited-page run to
update the database. Run continuously (random 30–60 min between checks) with
`python3 -m rentwatch run`.

### Sanity guard

On a full run, if RentWatch scrapes far fewer listings than it had active for a
search (a sign of a markup change or a soft block), it treats the run as partial
and **skips removed-listing detection** so a glitch can't cascade thousands of
false "removed" events.

## What it captures

Straight from each Rightmove search result (no extra requests):

- listing **photos** (gallery + thumbnail)
- price, bedrooms, **bathrooms**, **floor area** (when present), property subtype
- **available-from date**, **key features**
- **freshness** — "new" / "reduced" — and **let-agreed** status
- map coordinates, agent, summary
- TfL public-transport and cycling time to each configured target
- first/last seen timestamps and full price history

EPC rating, deposit, and council-tax band require Rightmove's per-listing detail
pages, which are now JavaScript-rendered and frequently show "Ask agent". The
database columns and `Store.update_listing_details` hook are in place for a future
clean source, but a fragile per-listing detail crawler is deliberately **not**
shipped. The dashboard shows these fields when present and "—" otherwise.

## Balanced score

Each listing gets a 0–100 score ([rentwatch/scoring.py](rentwatch/scoring.py),
mirrored in [web/src/lib/scoring.js](web/src/lib/scoring.js)) that penalises the
**worse** of the two commutes (both people must get to work), commute imbalance,
rent percentile within the live market, let-agreed status, and missing routes; and
rewards floor area, garden/parking, and freshly-listed homes. The dashboard's
"Commute priority" sliders re-weight the two targets and re-rank instantly.

## Dashboard

A React/Vite dashboard in `web/` reads the exported JSON. It has a dark
command-center layout: a clustered commute map, a virtualized power-table, a photo
**gallery** view, a live stats panel (commute-balance scatter, rent histogram,
shortlist), a working **Compare** modal, a listing **detail** slide-over (photos,
price-history sparkline, commute breakdown, "why this score"), saved searches, and
shareable URL filter state.

```bash
python3 -m rentwatch run --once --no-notify
python3 scripts/export_site_data.py
cd web
npm install
npm run dev
```

The exporter ships only **active + out-of-search** listings (slim, nulls dropped,
totals in `meta.counts`) — far smaller than shipping every removed listing. The
build-artifact copy `web/public/data/listings.json` is git-ignored; only
`docs/data/listings.json` is committed, and the GitHub Pages workflow rebuilds the
rest with `/UK_Renting/` as the base path.

## Split-price search

To avoid Rightmove's ~1,000-result pagination cap, the split-price script rewrites
`config.json` into five price bands under one search name, runs the monitor once,
exports the website JSON, commits `docs/data/listings.json`, and pushes:

```bash
scripts/update_split_price_search.sh
```

Default bands: `1000-1600`, `1601-1750`, `1751-1900`, `1901-2050`, `2051-2200`.
Override them or the radius:

```bash
SEARCH_RADIUS=6 PRICE_BANDS="1000:1600,1601:1750,1751:1900,1901:2050,2051:2200" scripts/update_split_price_search.sh
```

`DRY_RUN=1` stops before scraping. To run live (send Telegram + publish after every
pass on the configured polling delay):

```bash
scripts/live_notify_and_publish.sh
```

After each successful full run, RentWatch stores a fingerprint of the active search
definition. If URLs, price limits, or keywords change later, the next full run uses
search-changed mode automatically: missing known listings become `out_of_search`
instead of `removed`, and known reappearances are not sent as new-listing alerts.

If you already have listings and only need to fill new route targets:

```bash
python3 -m rentwatch routes
python3 scripts/export_site_data.py
```

## Useful commands

```bash
python3 -m rentwatch list
python3 -m rentwatch export --output listings.csv
python3 -m rentwatch test-telegram
```

The SQLite database defaults to `rentwatch.sqlite3`.
