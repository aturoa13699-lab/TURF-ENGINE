# TURF Registry, Lite Compiler & CLI Actions

This repo contains a deterministic scaffold for:

- `turf.track_registry.v1` + resolver (exact/alias/fuzzy)
- Racing Australia (RA) and odds parsing helpers that emit Lite inputs with provenance
- A Lite stake-card compiler + overlay-only forecast writer
- Typer CLI with `turf ra parse`, `turf odds parse`, `turf compile merge-odds`, `turf compile stake-card`
- GitHub Actions running the full test suite

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .

# Resolve tracks

turf resolve --registry data/nsw_seed.json --tracks "werigee" "wagga riverside" --state-hint VIC

# Parse Racing Australia style HTML (see data/demo_meeting.html)
turf ra parse --html data/demo_meeting.html --meeting-id DEMO --race-number 1 \
  --captured-at 2025-12-13T10:00:00+11:00 \
  --out-market out/market_snapshot.json --out-speed out/runner_speed_derived.json

# Parse odds HTML and merge
turf odds parse --html data/demo_odds.html --meeting-id DEMO --race-number 1 \
  --captured-at 2025-12-13T10:01:00+11:00 --out-path out/market_odds.json

turf compile merge-odds --market out/market_snapshot.json --odds out/market_odds.json \
  --out out/market_with_odds.json

# Build Lite stake card with overlay-only forecast
turf compile stake-card --market out/market_with_odds.json --speed out/runner_speed_derived.json \
  --out out/stake_card.json

# Minimal scrape plan
turf plan --registry data/nsw_seed.json --date 2025-12-09 --states NSW --tracks "Wagga" "Ballina" > plan.json
cat plan.json
```

## Race Previews (HTML/PDF)

Generate deterministic race preview documents from stake cards:

```bash
# HTML preview (default, read-only)
PYTHONPATH=. python -m cli.turf_cli preview --stake-cards out/cards --out out/previews

# PDF generation (requires weasyprint)
pip install .[pdf]
PYTHONPATH=. python -m cli.turf_cli preview --stake-cards out/cards --out out/previews --format pdf

# Single file mode
PYTHONPATH=. python -m cli.turf_cli preview --single out/cards/stake_card.json --out out/previews
```

PRO fields (EV markers, risk profiles, race summaries) are rendered **only if present** in the stake card. No derivation is performed — previews are read-only.

## Repo layout

- `turf/models.py` — Pydantic models
- `turf/normalise.py` — normalisation helpers
- `turf/resolver.py` — index + resolve
- `turf/parse_ra.py` — RA HTML parser → market + speed sidecar JSON
- `turf/parse_odds.py` — odds HTML parser → lightweight odds JSON
- `turf/compile_lite.py` — Lite score + overlay builder and odds merger
- `turf/cli.py` — Typer CLI surface
- `data/nsw_seed.json` — seed registry for NSW
- `data/demo_meeting.html`, `data/demo_odds.html` — fixtures for CLI/tests
- `test_resolver.py`, `test_cli_pipeline.py` — unit tests (pytest)
- `.github/workflows/ci.yml` — GitHub Actions workflow running the tests
- `cli/turf_cli.py` — demo automation CLI (Lite + PRO overlay + site render)
- `engine/turf_engine_pro.py` — deterministic RunnerVector builder + logit overlay
- `tools/db_init_if_missing.py`, `tools/db_append.py`, `tools/backtest.py` — DuckDB utilities for logging forecasts and running lightweight backtests

> The DB helpers will use DuckDB when available and fall back to SQLite automatically in CI or offline environments.

## GitHub Actions

The workflow in `.github/workflows/ci.yml` installs the package in editable mode and runs the pytest suite on every push and pull request. The tests exercise the RA/odds parsers, odds merge, and Lite stake-card generation to keep the CLI deterministic.

For a scheduled daily pipeline (stake-card generation + HTML email summary), see `README_AUTOMATION.md`, which documents the `turf_daily.yml` workflow, runner script, and email renderer.

For static site deploys and emailed Pages URLs, see `README_SITE.md` plus `.github/workflows/site_publish_and_email.yml`. The workflow builds demo stake cards with `cli/turf_cli.py demo-run`, renders `public/`, deploys to GitHub Pages, and optionally emails the deployed URL using SMTP secrets.

For backfill + DuckDB logging + backtests, see `tools/` and `.github/workflows/turf_backfill_and_backtest.yml`, which append forecasts to `data/turf.duckdb` and emit simple Brier/logloss/ROI metrics as artifacts.

## Simulation / Bankroll (Plan 050)

- `python -m cli.turf_cli bankroll --stake-cards out/cards --out out/derived/sim --seed 123 --iters 1000`
- Deterministic, seeded Monte Carlo using PRO/derived stake cards (prefers `stake_card_pro.json` when present).
- Outputs land under `out/derived/sim/**` (e.g., `bankroll_summary.json`, `bets_selected.json`, `strategy_inputs.json`).
- Lite outputs remain unchanged; selection defaults only place bets when forecast EV is present and positive.

## Notes

- The registry builder is left as a stub in `turf/registry_builder.py` for future work (RA/R&S ingestion).
- The Lite overlay is ordering-isolated by design; it only writes to `forecast.*` fields.
