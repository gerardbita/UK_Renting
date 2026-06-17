#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CONFIG_PATH="${CONFIG_PATH:-$ROOT/config.json}"
SEARCH_NAME="${SEARCH_NAME:-Noemie work and Gerard work}"
PRICE_BANDS="${PRICE_BANDS:-1000:1600,1601:1750,1751:1900,1901:2050,2051:2200}"
SEARCH_RADIUS="${SEARCH_RADIUS:-6}"
COMMIT_MESSAGE="${COMMIT_MESSAGE:-Update split price search data}"
PYTHON_BIN="${PYTHON_BIN:-}"
DRY_RUN="${DRY_RUN:-0}"
SEND_NOTIFICATIONS="${SEND_NOTIFICATIONS:-0}"
AUTH_ZOOPLA="${AUTH_ZOOPLA:-0}"
SKIP_ROUTES="${SKIP_ROUTES:-0}"
RUN_ZOOPLA="${RUN_ZOOPLA:-0}"
SEARCH_CHANGED="${SEARCH_CHANGED:-0}"

if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    PYTHON_BIN="$ROOT/.venv/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi

if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "Missing config file: $CONFIG_PATH" >&2
  exit 2
fi

"$PYTHON_BIN" - "$CONFIG_PATH" "$SEARCH_NAME" "$PRICE_BANDS" "$SEARCH_RADIUS" <<'PY'
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


config_path = Path(sys.argv[1])
search_name = sys.argv[2]
price_bands = [
    tuple(int(part) for part in band.split(":", 1))
    for band in sys.argv[3].split(",")
    if band.strip()
]
search_radius = sys.argv[4].strip()


def first_url(urls: list[str], host_part: str) -> str:
    return next((url for url in urls if host_part in urlparse(url).netloc.lower()), "")


def with_query_values(url: str, values: dict[str, int | str]) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    for key, value in values.items():
        query[key] = str(value)
    return urlunparse(parsed._replace(query=urlencode(query)))


def radius_query_values(radius: str) -> tuple[dict[str, str], dict[str, str]]:
    if not radius:
        return {}, {}
    value = float(radius)
    rightmove_radius = f"{value:.1f}"
    zoopla_radius = f"{value:g}"
    return {"radius": rightmove_radius}, {"radius": zoopla_radius}


def normalize_search_names(db_path: Path, target_name: str) -> None:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT * FROM search_listings WHERE search_name LIKE ?",
            (target_name + "%",),
        ).fetchall()
        by_listing = {}
        for row in rows:
            by_listing.setdefault(row["listing_key"], []).append(row)

        for listing_key, listing_rows in by_listing.items():
            chosen = sorted(listing_rows, key=lambda row: row["last_seen_at"] or "")[-1]
            first_seen = min(row["first_seen_at"] for row in listing_rows if row["first_seen_at"])
            last_seen = max(row["last_seen_at"] for row in listing_rows if row["last_seen_at"])
            status = "active" if any(row["status"] == "active" for row in listing_rows) else chosen["status"]
            con.execute(
                """
                INSERT INTO search_listings (
                    search_name, listing_key, status, first_seen_at, last_seen_at,
                    last_snapshot_json, last_price_text, last_price_pcm,
                    notified_new_at, notified_price_at, notified_removed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(search_name, listing_key) DO UPDATE SET
                    status = excluded.status,
                    first_seen_at = MIN(search_listings.first_seen_at, excluded.first_seen_at),
                    last_seen_at = MAX(search_listings.last_seen_at, excluded.last_seen_at),
                    last_snapshot_json = excluded.last_snapshot_json,
                    last_price_text = excluded.last_price_text,
                    last_price_pcm = excluded.last_price_pcm,
                    notified_new_at = COALESCE(search_listings.notified_new_at, excluded.notified_new_at),
                    notified_price_at = COALESCE(search_listings.notified_price_at, excluded.notified_price_at),
                    notified_removed_at = COALESCE(search_listings.notified_removed_at, excluded.notified_removed_at)
                """,
                (
                    target_name,
                    listing_key,
                    status,
                    first_seen,
                    last_seen,
                    chosen["last_snapshot_json"],
                    chosen["last_price_text"],
                    chosen["last_price_pcm"],
                    chosen["notified_new_at"],
                    chosen["notified_price_at"],
                    chosen["notified_removed_at"],
                ),
            )

        con.execute(
            "DELETE FROM search_listings WHERE search_name LIKE ? AND search_name <> ?",
            (target_name + "%", target_name),
        )
        con.execute(
            "UPDATE price_history SET search_name = ? WHERE search_name LIKE ?",
            (target_name, target_name + "%"),
        )
        con.execute(
            "UPDATE notification_log SET search_name = ? WHERE search_name LIKE ?",
            (target_name, target_name + "%"),
        )
        con.commit()
    finally:
        con.close()

data = json.loads(config_path.read_text(encoding="utf-8"))
searches = data.get("searches") or []
if not searches:
    raise SystemExit("config.json has no searches to split.")

matching_searches = [
    search for search in searches if str(search.get("name", "")).startswith(search_name)
]
source_search = matching_searches[0] if matching_searches else searches[0]
source_urls = []
if source_search.get("url"):
    source_urls.append(source_search["url"])
source_urls.extend(source_search.get("urls") or [])

rightmove_base = first_url(source_urls, "rightmove.co.uk")
zoopla_base = first_url(source_urls, "zoopla.co.uk")
if not rightmove_base and not zoopla_base:
    raise SystemExit("Could not find a Rightmove or Zoopla URL in config.json.")

split_urls = []
rightmove_radius, zoopla_radius = radius_query_values(search_radius)
for low, high in price_bands:
    if rightmove_base:
        split_urls.append(
            with_query_values(
                rightmove_base,
                {"minPrice": low, "maxPrice": high, "index": 0, **rightmove_radius},
            )
        )
    if zoopla_base:
        split_urls.append(
            with_query_values(
                zoopla_base,
                {"price_min": low, "price_max": high, **zoopla_radius},
            )
        )

new_search = {
    "name": search_name,
    "include_keywords": list(source_search.get("include_keywords") or []),
    "exclude_keywords": list(source_search.get("exclude_keywords") or []),
    "min_price_pcm": min(low for low, _ in price_bands),
    "max_price_pcm": max(high for _, high in price_bands),
    "notify_new": bool(source_search.get("notify_new", True)),
    "notify_price_changes": bool(source_search.get("notify_price_changes", True)),
    "notify_removed": bool(source_search.get("notify_removed", False)),
    "urls": split_urls,
}

remaining = [
    search
    for search in searches
    if not str(search.get("name", "")).startswith(search_name)
]
data["searches"] = [new_search, *remaining]
config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

db_path = Path(data.get("database") or "rentwatch.sqlite3")
if not db_path.is_absolute():
    db_path = config_path.resolve().parent / db_path
if db_path.exists():
    normalize_search_names(db_path, search_name)

print(f"Configured {len(price_bands)} price bands under search name: {search_name}")
print(f"Generated {len(split_urls)} portal URL(s):")
for url in split_urls:
    host = urlparse(url).netloc
    query = dict(parse_qsl(urlparse(url).query, keep_blank_values=True))
    low = query.get("minPrice") or query.get("price_min")
    high = query.get("maxPrice") or query.get("price_max")
    radius = query.get("radius") or "unchanged"
    print(f"- {host}: GBP {low}-{high}; radius {radius} miles")
PY

echo
"$PYTHON_BIN" -m rentwatch --config "$CONFIG_PATH" list

if [[ "$DRY_RUN" == "1" ]]; then
  echo
  echo "DRY_RUN=1 set; stopping before scraping/export/git."
  exit 0
fi

if [[ "$AUTH_ZOOPLA" == "1" ]]; then
  "$PYTHON_BIN" -m rentwatch --config "$CONFIG_PATH" auth-zoopla
fi

run_args=(run --once --prime)
if [[ "$SEND_NOTIFICATIONS" == "1" ]]; then
  run_args=(run --once)
fi
if [[ "$SKIP_ROUTES" == "1" ]]; then
  run_args+=(--skip-routes)
fi
if [[ "$SEARCH_CHANGED" == "1" ]]; then
  run_args+=(--search-changed)
fi
case "$RUN_ZOOPLA" in
  0|false|no)
    run_args+=(--skip-zoopla)
    ;;
  only)
    run_args+=(--only-zoopla)
    ;;
  1|true|yes)
    ;;
  *)
    echo "RUN_ZOOPLA must be 1, 0, or only. Got: $RUN_ZOOPLA" >&2
    exit 2
    ;;
esac

"$PYTHON_BIN" -m rentwatch --config "$CONFIG_PATH" "${run_args[@]}"
"$PYTHON_BIN" scripts/export_site_data.py

git add docs/data/listings.json web/public/data/listings.json

if git diff --cached --quiet; then
  echo "No website data changes to commit."
  exit 0
fi

git commit -m "$COMMIT_MESSAGE"
git push origin "$(git branch --show-current)"
