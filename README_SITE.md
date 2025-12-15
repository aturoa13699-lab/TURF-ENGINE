# TURF ENGINE LITE — Static site renderer

This pack turns Lite stake cards into a static site suitable for GitHub Pages. It keeps
forecast fields overlay-only (ordering isolated) and adds lightweight staking annotations.

## Files
- `site/build_site.py` — renders HTML from `out/stake_cards/*.json`
- `site/templates/*` — minimal header/footer templates with relative CSS prefix support
- `site/static/styles.css` — dark theme styling
- `.github/workflows/site_daily.yml` — scheduled Pages deploy that pulls the latest stake card artifact, renders the site, and publishes
- `.github/workflows/site_publish_and_email.yml` — end-to-end build + deploy + optional SMTP email containing the Pages URL; runs the demo pipeline via `cli/turf_cli.py demo-run`

## Usage

Render locally after running the stake-card pipeline:

```bash
python site/build_site.py --stake-cards out/stake_cards --out public
```

Generated pages live in `public/`:
- `public/index.html` — race listing and top pick per race
- `public/races/<MEETING>_R<RACE>.html` — per-race view with LiteScore, tags, overlay fields, EV, and fractional Kelly units

## GitHub Pages workflow

The default Pages workflow downloads the latest `turf_daily` artifact for the resolved Australia/Sydney date. If no artifact is found, it falls back to running `scripts/run_turf_daily.sh` using the demo fixtures. The new `site_publish_and_email.yml` workflow always regenerates demo cards with `cli/turf_cli.py demo-run`, renders `public/`, deploys to Pages, and emails the resulting URL (when SMTP secrets are provided).

Enable Pages in **Settings → Pages** with source "GitHub Actions" and keep the workflow as-is.
