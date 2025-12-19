# Plan 076: RA + Market Odds Ingestion for Daily Stake Cards

## Status: Implemented

## Summary

End-to-end pipeline for Racing Australia (RA) meeting/race capture and parsing, market odds collection (via pluggable adapters), and stake card compilation for all races on a given date.

## Scope

### New Modules

1. **`turf/ra_collect.py`** - RA HTML capture and parsing
   - Fetch RA pages (meeting schedule + per race HTML) via `requests`
   - Store raw HTML under deterministic paths: `data/raw/ra/<date>/<meeting_id>/race_<n>.html`
   - Parse stored HTML using existing `turf.parse_ra.parse_meeting_html`
   - Operate offline from captured files (tests use fixtures)

2. **`turf/odds_collect.py`** - Pluggable odds source adapters
   - `NoneAdapter`: No odds (use RA prices)
   - `FixtureAdapter`: Load from fixture files (for testing)
   - `TheOddsAPIAdapter`: The Odds API (requires `THEODDSAPI_KEY`)
   - `BetfairAdapter`: Betfair Exchange (requires `BETFAIR_APP_KEY`, `BETFAIR_USERNAME`, `BETFAIR_PASSWORD`)
   - Convert odds to TURF schema: `{"runners": [{"runner_name": "...", "price_now_dec": ...}]}`

3. **`turf/collect_pipeline.py`** - Orchestration
   - Discover races from captured RA HTML
   - Parse RA data into market snapshots
   - Fetch/merge market odds
   - Compile Lite stake cards
   - Optionally apply PRO overlay
   - Write stake cards to output directory
   - Generate daily digests

### CLI Command

New command in `cli/turf_cli.py`:

```
python -m cli.turf_cli collect-stake-cards [OPTIONS]

Options:
  --date YYYY-MM-DD           Date (default: Australia/Sydney today)
  --out PATH                  Output directory (default: out/stake_cards)
  --capture-dir PATH          Capture directory (default: data/raw)
  --odds-source TEXT          none | fixture | theoddsapi | betfair
  --odds-fixtures-dir PATH    Fixtures dir for --odds-source fixture
  --prefer-pro/--no-prefer-pro
  --render-digest-pages/--no-render-digest-pages
  --simulate/--no-simulate
  --seed INT
  --write-per-meeting/--no-write-per-meeting
```

### Workflow

New workflow `turf_collect_daily.yml`:
- Scheduled at 17:30 UTC (04:30 AEDT)
- Manual dispatch with date/odds-source/simulate options
- Collects stake cards and generates digests
- Uploads artifacts

## Invariants

- **Lite math unchanged**: No changes to scoring logic or existing Lite output fields
- **Deterministic outputs**: Same captured inputs always produce identical artifacts
- **No mutation**: Input files are never modified; deep copy where needed
- **Feature flags**: All new features behind flags; default behavior unchanged
- **Workflow guardrails**: No `secrets.*` in `if:` expressions; use `python -m cli.turf_cli`

## File Structure

```
data/raw/ra/<date>/<meeting_id>/race_<n>.html    # Captured RA HTML
data/raw/<source>/<date>/<meeting_id>/race_<n>.json  # Captured odds

out/stake_cards/<date>/<meeting_id>/
  stake_card_r<n>.json        # Lite stake card
  stake_card_r<n>_pro.json    # PRO overlay (if available)

out/stake_cards/digests/<date>/
  daily_digest.json
  daily_digest.md
```

## Environment Variables

For odds sources:
- `THEODDSAPI_KEY` - The Odds API key
- `BETFAIR_APP_KEY` - Betfair application key
- `BETFAIR_USERNAME` - Betfair username
- `BETFAIR_PASSWORD` - Betfair password

## Testing

Test file: `tests/test_plan_076_collect_pipeline.py`

Fixtures:
- `tests/fixtures/ra/2025-12-18/TEST_RANDWICK/race_*.html`
- `tests/fixtures/ra/2025-12-18/TEST_ROSEHILL/race_*.html`
- `tests/fixtures/odds/2025-12-18/TEST_RANDWICK/race_*.json`

Tests verify:
1. Stake cards generated deterministically (same output across runs)
2. Meeting/race ordering stable (sorted by meeting_id, race_number)
3. Runner mapping preserves runner_number stability
4. Digest artifacts generated and stable
5. No mutation of input fixture files

## Acceptance Criteria

- [x] `python -m cli.turf_cli --help` shows `collect-stake-cards`
- [x] `PYTHONPATH=. python -m pytest -q` passes
- [x] Offline run using fixtures produces deterministic stake cards
- [x] Existing workflows remain intact
- [x] Derived-only publishing works
- [x] No `secrets.*` in workflow `if:` expressions
- [x] No `python cli/turf_cli.py` file-mode invocation

## Risks

1. **Network dependency**: Real RA/odds fetching not implemented; stubs return None
   - Mitigation: Offline-first design; pipeline works with captured fixtures

2. **Odds API rate limits**: TheOddsAPI and Betfair have rate limits
   - Mitigation: Capture and cache raw responses

3. **Runner name matching**: Odds APIs may use different runner names than RA
   - Mitigation: merge_odds_into_market uses case-insensitive name matching

## Required Checks

```bash
# Verify CLI command exists
python -m cli.turf_cli --help | grep collect-stake-cards

# Run tests
PYTHONPATH=. python -m pytest -q

# Run guardrails
bash scripts/guardian_check.sh
bash scripts/audit_all.sh
```

## Local Usage

```bash
# Offline run with fixtures (for testing)
mkdir -p data/raw/ra/2025-12-18/RANDWICK
cp tests/fixtures/ra/2025-12-18/TEST_RANDWICK/*.html data/raw/ra/2025-12-18/RANDWICK/

python -m cli.turf_cli collect-stake-cards \
  --date 2025-12-18 \
  --capture-dir data/raw \
  --out out/stake_cards \
  --odds-source none

# With odds fixtures
python -m cli.turf_cli collect-stake-cards \
  --date 2025-12-18 \
  --capture-dir data/raw \
  --out out/stake_cards \
  --odds-source fixture \
  --odds-fixtures-dir tests/fixtures/odds
```
