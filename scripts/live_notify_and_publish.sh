#!/usr/bin/env bash
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CONFIG_PATH="${CONFIG_PATH:-$ROOT/config.json}"
PYTHON_BIN="${PYTHON_BIN:-}"
RUN_ZOOPLA="${RUN_ZOOPLA:-0}"
SKIP_ROUTES="${SKIP_ROUTES:-0}"
SEARCH_CHANGED="${SEARCH_CHANGED:-0}"
SEARCH_RADIUS="${SEARCH_RADIUS:-6}"
COMMIT_MESSAGE="${COMMIT_MESSAGE:-Update live listings data}"

if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    PYTHON_BIN="$ROOT/.venv/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi

next_delay() {
  "$PYTHON_BIN" - "$CONFIG_PATH" <<'PY'
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

config_path = Path(sys.argv[1])
data = json.loads(config_path.read_text(encoding="utf-8"))
polling = data.get("polling") or {}
minimum = int(polling.get("delay_min_seconds", 1800))
maximum = int(polling.get("delay_max_seconds", 3600))
if maximum < minimum:
    maximum = minimum
print(random.randint(minimum, maximum))
PY
}

while true; do
  echo "Starting live notification + publish run at $(date)."

  SEND_NOTIFICATIONS=1 \
  RUN_ZOOPLA="$RUN_ZOOPLA" \
  SKIP_ROUTES="$SKIP_ROUTES" \
  SEARCH_CHANGED="$SEARCH_CHANGED" \
  SEARCH_RADIUS="$SEARCH_RADIUS" \
  COMMIT_MESSAGE="$COMMIT_MESSAGE" \
    "$ROOT/scripts/update_split_price_search.sh"
  status=$?

  if [[ "$status" != "0" ]]; then
    echo "Live run failed with exit code $status; keeping loop alive." >&2
  fi

  delay="$(next_delay)"
  echo "Next live run in $delay seconds."
  sleep "$delay"
done
