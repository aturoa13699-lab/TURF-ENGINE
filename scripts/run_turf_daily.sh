#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATE_AU="${1:-$(TZ=Australia/Sydney date +%Y-%m-%d)}"

OUT_DIR="$REPO_ROOT/out"
RAW_DIR="$OUT_DIR/raw"
STAKE_DIR="$OUT_DIR/stake_cards"
EMAIL_DIR="$OUT_DIR/email"

mkdir -p "$RAW_DIR" "$STAKE_DIR" "$EMAIL_DIR"

MEETING_ID="DEMO_${DATE_AU//-/}"
CAPTURE_MARKET="${DATE_AU}T10:00:00+11:00"
CAPTURE_ODDS="${DATE_AU}T10:05:00+11:00"

printf "[turf-daily] using date %s (Australia/Sydney)\n" "$DATE_AU"

python -m turf.cli ra parse \
  --html "$REPO_ROOT/data/demo_meeting.html" \
  --meeting-id "$MEETING_ID" \
  --race-number 1 \
  --captured-at "$CAPTURE_MARKET" \
  --out-market "$RAW_DIR/market_snapshot.json" \
  --out-speed "$RAW_DIR/runner_speed_derived.json"

python -m turf.cli odds parse \
  --html "$REPO_ROOT/data/demo_odds.html" \
  --meeting-id "$MEETING_ID" \
  --race-number 1 \
  --captured-at "$CAPTURE_ODDS" \
  --out "$RAW_DIR/market_odds.json"

python -m turf.cli compile merge-odds \
  --market "$RAW_DIR/market_snapshot.json" \
  --odds "$RAW_DIR/market_odds.json" \
  --out "$RAW_DIR/market_with_odds.json"

python -m turf.cli compile stake-card \
  --market "$RAW_DIR/market_with_odds.json" \
  --speed "$RAW_DIR/runner_speed_derived.json" \
  --out "$STAKE_DIR/stake_card_${DATE_AU}.json"

python "$REPO_ROOT/email/render_email.py" \
  --stake-cards "$STAKE_DIR" \
  --date "$DATE_AU" \
  --out "$EMAIL_DIR/rendered_summary.html"

printf "[turf-daily] artifacts written to %s\n" "$OUT_DIR"
