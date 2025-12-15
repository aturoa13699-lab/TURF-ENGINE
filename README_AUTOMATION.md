# TURF ENGINE LITE — Daily Automation Pack

This pack wires a scheduled GitHub Actions workflow that builds a Lite stake card from the demo HTML fixtures, renders an email summary, and uploads artifacts. Swap the demo scrape commands for your real scrapers when you are ready.

## Files

- `.github/workflows/turf_daily.yml` — scheduled workflow (03:00 UTC) with manual dispatch input for date
- `scripts/run_turf_daily.sh` — bash runner that parses demo HTML, merges odds, builds a stake card, and renders email HTML
- `email/render_email.py` — turns stake card JSON files into a simple HTML digest

## Secrets and variables

Set these in **Settings → Secrets and variables → Actions**:

Required SMTP secrets for the email step:
- `EMAIL_SERVER`
- `EMAIL_PORT`
- `EMAIL_USERNAME`
- `EMAIL_PASSWORD`
- `EMAIL_FROM`
- `EMAIL_TO`

Optional variables:
- `RA_BASE_URL` — placeholder for your scraper to target specific domains
- `ODDS_BASE_URL`

The email step is skipped if `EMAIL_SERVER` is unset/empty.

## Running locally

```bash
./scripts/run_turf_daily.sh           # uses Australia/Sydney today
./scripts/run_turf_daily.sh 2025-12-13
python email/render_email.py --stake-cards out/stake_cards --date 2025-12-13 --out out/email/rendered_summary.html
```

Outputs land in `out/`:
- `out/raw/` — market, sidecar, odds, merged market
- `out/stake_cards/` — stake card JSON
- `out/email/rendered_summary.html` — email body preview

For GitHub Pages rendering of the stake cards, see `README_SITE.md`, `.github/workflows/site_daily.yml`, and the extended Pages + email workflow in `.github/workflows/site_publish_and_email.yml`.

For backfill/DB/backtests, the companion workflow `.github/workflows/turf_backfill_and_backtest.yml` uses `cli/turf_cli.py demo-run`, `tools/db_append.py`, and `tools/backtest.py` to populate `data/turf.duckdb` and emit metrics.

## Workflow behavior

- Resolves run date (input or Australia/Sydney today)
- Installs dependencies and the `turf` CLI
- Calls `scripts/run_turf_daily.sh` to generate artifacts
- Uploads the `out/` directory
- Sends the HTML email via SMTP if secrets are present

To adjust the schedule, edit the `cron` block in `.github/workflows/turf_daily.yml`.
