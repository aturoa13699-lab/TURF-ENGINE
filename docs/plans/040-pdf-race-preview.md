# Plan 040: PDF Race Preview Export

## Scope
- Add deterministic HTML/PDF race preview outputs without altering Lite data.
- Include RaceSummaryPanel and compact runner rows (EV + risk + narrative) in exported previews.
- Write outputs to `out/previews/meeting.html` and `out/previews/meeting.pdf`.

## Invariants / Risks
- TURF_ENGINE_LITE outputs stay unchanged; previews derive from existing data and flags.
- No network calls by default; optional assets must be cached or skipped offline.
- Keep exports deterministic for the same input date/seed.

## Acceptance Criteria
- Running the preview command produces both HTML and PDF artifacts in `out/previews/` with RaceSummaryPanel content included.
- Runner rows show EV markers, risk chips, and narrative summaries in the preview.
- Feature-flagged behavior defaults OFF to avoid impacting Lite flows.

## Verification / Commands
- `bash scripts/audit_all.sh`
- `bash scripts/guardian_check.sh`
- Preview generation command (e.g., `PYTHONPATH=. python -m cli.turf_cli preview --date 2025-12-15 --out out/previews --format pdf`).
