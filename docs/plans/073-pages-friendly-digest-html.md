# Plan 073 — Pages-friendly digest HTML (derived-only)

## Goal
Make digest artifacts published to GitHub Pages easy to browse by emitting
deterministic HTML wrappers and an index page under `public/derived/`.

## Scope
- Add a deterministic renderer that converts:
  - `daily_digest.md` -> `daily_digest.html`
  - `meetings/*.md` -> `meetings/*.html`
  - emits `public/derived/index.html` linking to the above.
- Wire this into the Pages workflow after the site build.
- Optionally add the digest link to the email body (workflow-only).

## Out of scope
- Any change to Lite outputs, scoring, ordering, overlays, or betting logic.
- Any new model derivations at render time.

## Determinism requirements
- No timestamps.
- Stable ordering of meetings/pages based on sorted paths.
- HTML content must be byte-stable for identical inputs.

## Acceptance criteria
- `python -m cli.turf_cli daily-digest ... --write-per-meeting` produces `.md`/`.json` digests.
- Workflow emits `public/derived/index.html` and `public/derived/daily_digest.html`.
- Per-meeting `.html` emitted only when per-meeting `.md` exists.
- All outputs deterministic across repeated runs.

## Required checks
- bash scripts/guardian_check.sh
- PYTHONPATH=. python -m pytest -q
- bash scripts/audit_all.sh
