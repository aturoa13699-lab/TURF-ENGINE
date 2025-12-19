# Plan 076: RA + Market Odds Ingestion for Daily Stake Cards

## Status: Implemented (with Betfair cert-based authentication)

## Summary

End-to-end pipeline for Racing Australia (RA) meeting/race capture and parsing, market odds collection (via pluggable adapters including Betfair with certificate-based authentication), and stake card compilation for all races on a given date.

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
   - `BetfairAdapter`: Betfair Exchange with cert authentication (see below)
   - Convert odds to TURF schema: `{"runners": [{"runner_name": "...", "price_now_dec": ...}]}`

3. **`turf/betfair.py`** - Betfair API client with cert-based SSO
   - Certificate-based authentication (non-interactive)
   - Market discovery for Australian horse racing
   - Deterministic runner name matching using fuzzy matching (rapidfuzz)
   - Best back price / last traded price extraction

4. **`turf/collect_pipeline.py`** - Orchestration
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

### Workflows

1. **`turf_collect_daily.yml`** - Daily stake card collection
   - Scheduled at 17:30 UTC (04:30 AEDT)
   - Manual dispatch with date/odds-source/simulate options
   - Collects stake cards and generates digests
   - Uploads artifacts
   - Includes CLI guardrail verification

2. **`betfair_cert_bootstrap.yml`** - Certificate generation helper
   - One-time workflow to generate Betfair API credentials
   - Generates RSA key + self-signed certificate
   - Uploads as short-retention artifact (1 day)
   - Provides setup instructions in workflow summary

## Betfair Integration

### Required GitHub Secrets

| Secret | Description |
|--------|-------------|
| `BETFAIR_APP_KEY` | Betfair Application Key (X-Application header) |
| `BETFAIR_USERNAME` | Betfair account username |
| `BETFAIR_PASSWORD` | Betfair account password |
| `BETFAIR_CERT_PEM_B64` | Base64-encoded PEM certificate (.crt) |
| `BETFAIR_KEY_PEM_B64` | Base64-encoded PEM private key (.key) |

### Certificate Setup

1. **Generate certificate** (run `betfair_cert_bootstrap.yml` workflow):
   - Generates 2048-bit RSA key and self-signed certificate
   - Downloads as `betfair_cert_material` artifact

2. **Upload to Betfair**:
   - Go to [Betfair Developer Portal](https://developer.betfair.com/)
   - Navigate to "My Apps" / "Application Keys"
   - Upload the `.crt` file from the artifact
   - Note your Application Key

3. **Add GitHub Secrets**:
   - `BETFAIR_APP_KEY`: Your application key
   - `BETFAIR_USERNAME`: Your Betfair username
   - `BETFAIR_PASSWORD`: Your Betfair password
   - `BETFAIR_CERT_PEM_B64`: Contents of `cert_b64.txt`
   - `BETFAIR_KEY_PEM_B64`: Contents of `key_b64.txt`

4. **Test the connection**:
   ```bash
   python -m cli.turf_cli collect-stake-cards \
     --odds-source betfair \
     --date 2025-12-18
   ```

### Certificate File Layout (at runtime)

The adapter writes certificates to:
```
~/.betfair/
  client-2048.crt   # chmod 600
  client-2048.key   # chmod 600
```

### Runner Name Matching

Betfair runner names are matched to RA runner names using:
1. Normalization: lowercase, strip punctuation, collapse whitespace
2. Exact match first
3. Fuzzy match using rapidfuzz (min score 80)
4. Deterministic tie-breaking: lowest lexical candidate wins

Unmatched runners are logged in the snapshot's `warnings` field.

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
- `BETFAIR_CERT_PEM_B64` - Base64-encoded certificate PEM
- `BETFAIR_KEY_PEM_B64` - Base64-encoded private key PEM

## Testing

Test files:
- `tests/test_plan_076_collect_pipeline.py` - Pipeline tests
- `tests/test_betfair_adapter.py` - Betfair adapter tests with mocked HTTP

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
6. Betfair config validation and error messages
7. Runner name fuzzy matching (deterministic)
8. Authentication flow with mocked HTTP

## Acceptance Criteria

- [x] `python -m cli.turf_cli --help` shows `collect-stake-cards`
- [x] `PYTHONPATH=. python -m pytest -q` passes
- [x] Offline run using fixtures produces deterministic stake cards
- [x] Existing workflows remain intact
- [x] Derived-only publishing works
- [x] No `secrets.*` in workflow `if:` expressions
- [x] No `python cli/turf_cli.py` file-mode invocation
- [x] Betfair adapter raises clear error when secrets missing
- [x] Runner name matching is deterministic

## Risks

1. **Network dependency**: Real RA/odds fetching depends on network
   - Mitigation: Offline-first design; pipeline works with captured fixtures

2. **Odds API rate limits**: TheOddsAPI and Betfair have rate limits
   - Mitigation: Capture and cache raw responses

3. **Runner name matching**: Odds APIs may use different runner names than RA
   - Mitigation: Fuzzy matching with rapidfuzz, deterministic tie-breaking

4. **Betfair auth complexity**: Cert-based auth requires setup
   - Mitigation: Bootstrap workflow generates certs with clear instructions

## Required Checks

```bash
# Verify CLI command exists
python -m cli.turf_cli --help | grep collect-stake-cards

# Run tests
PYTHONPATH=. python -m pytest -q

# Verify workflow YAML syntax
ruby -ryaml -e 'Dir[".github/workflows/*.y{a,}ml"].each { |f| YAML.load_file(f) }'

# Verify no secrets in if: expressions
grep -RIn --line-number -E 'if:.*secrets\.' .github/workflows || echo "OK"

# Verify no file-mode CLI invocation
grep -RIn --line-number -E 'python\s+cli/turf_cli\.py' .github/workflows || echo "OK"
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

# With Betfair (requires secrets configured)
export BETFAIR_APP_KEY="your-app-key"
export BETFAIR_USERNAME="your-username"
export BETFAIR_PASSWORD="your-password"
export BETFAIR_CERT_PEM_B64="$(base64 -w0 ~/.betfair/client-2048.crt)"
export BETFAIR_KEY_PEM_B64="$(base64 -w0 ~/.betfair/client-2048.key)"

python -m cli.turf_cli collect-stake-cards \
  --date 2025-12-18 \
  --capture-dir data/raw \
  --out out/stake_cards \
  --odds-source betfair
```
