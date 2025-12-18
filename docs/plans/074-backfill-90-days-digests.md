# Plan 074 — 90-Day Digest Backfill + Derived-Only Pages Mode

## Scope
- **In**: Deterministic backfill CLI (`backfill-digests`) writing derived-only digest artifacts (JSON/MD + optional per-meeting) and HTML wrappers; top-level backfill index; workflow switch to publish derived-only digests; repo hygiene ignores.
- **Out**: Any Lite math/order changes, new ingestion sources, or stake-card input mutations.

## Invariants
- Lite scoring/ordering untouched; stake-card inputs remain read-only.
- Outputs deterministic: stable ordering, no timestamps; simulation RNG always seeded (default 1337).
- Derived/PRO-only artifacts live under `out/derived`-style paths; never modify canonical Lite outputs.

## Acceptance Criteria
- `python -m cli.turf_cli backfill-digests --days 3 --out out/backfills --render-html` produces per-day derived digests (JSON/MD), optional per-meeting digests, HTML wrappers under `public/derived`, and `out/backfills/index.{json,md}` ordered by date.
- Two runs with identical inputs/seed yield byte-identical index + per-day artifacts; stake-card inputs unchanged.
- Workflow input `publish_derived_only` skips `site/build_site.py`, publishes derived digest pages, and keeps guardrails (no secrets in `if:`, module-mode CLI).

## Phase 2 — Backfill Publish Workflow (Derived-Only Pages)
- Add a dedicated workflow (`.github/workflows/backfill_publish.yml`) for manual dispatch to run `backfill-digests` (default 90 days, seed 1337) with HTML + per-meeting digests enabled and publish under `public/backfills`.
- Workflow must keep guardrails (module-mode CLI, no `secrets.*` in `if:`) and produce deterministic landing pages: `public/index.html` linking to `/backfills/index.html`, `public/backfills/index.{json,md}` copied from backfill output, plus a minimal `public/backfills/index.html` wrapper (timestamp-free).
- Pages artifact must include `.nojekyll` and only derived outputs; Lite math/ordering untouched.
- Add a safety guard step to `site_build_and_deploy.yml` to fail fast if the `daily-digest` Typer command is missing (no other workflow changes).

## Verification
- `bash scripts/verify_repo_identity.sh`
- `bash scripts/guardian_check.sh`
- `ruby -ryaml -e 'Dir[".github/workflows/*.y{a,}ml"].each { |f| YAML.load_file(f) }; puts "YAML_OK"'`
- `PYTHONPATH=. python -m pytest -q`
- `bash scripts/audit_all.sh`
