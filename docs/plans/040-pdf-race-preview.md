# Plan 040: PDF Race Preview Export

## Status: IMPLEMENTED

## Scope
- Add deterministic HTML/PDF race preview outputs without altering Lite data.
- Include RaceSummaryPanel and compact runner rows (EV + risk + narrative) in exported previews.
- Write outputs to `out/previews/{date}_{meeting_id}.html` and `out/previews/{date}_{meeting_id}.pdf`.

## Implementation Details

### Module: `turf/pdf_race_preview.py`
- Deterministic HTML/PDF renderer
- No current time usage - uses `date_local` from payload or fixed fallback `2000-01-01`
- Preserves runner ordering from payload (no re-sorting)
- Works with basic `stake_card.json` - PRO fields rendered only if present

### CLI Command: `turf preview`
```bash
# HTML only (default)
PYTHONPATH=. python -m cli.turf_cli preview --stake-cards out/cards --out out/previews

# PDF generation (requires weasyprint)
PYTHONPATH=. python -m cli.turf_cli preview --stake-cards out/cards --out out/previews --format pdf

# Single file mode
PYTHONPATH=. python -m cli.turf_cli preview --single out/cards/stake_card.json --out out/previews --format both
```

### Dependencies
- PDF generation requires optional `[pdf]` extra: `pip install turf[pdf]`
- Uses WeasyPrint for HTML-to-PDF conversion

## Invariants / Risks
- **TURF_ENGINE_LITE outputs stay unchanged** - previews derive from existing data, no mutation
- **Deterministic output** - same input => same HTML output (PDF may have metadata variations)
- No network calls by default; all assets embedded in CSS
- No live timestamps - uses date from payload only
- Feature-flagged behavior defaults OFF to avoid impacting Lite flows

## Acceptance Criteria
- [x] Running the preview command produces HTML artifacts in `out/previews/`
- [x] PDF generation works when weasyprint is installed
- [x] RaceSummaryPanel content included when present in stake card
- [x] Runner rows show EV markers, risk chips when present (PRO fields)
- [x] Output is deterministic - multiple runs produce identical HTML
- [x] Works with basic stake_card.json (no PRO fields required)

## Verification / Commands
```bash
# Run tests
PYTHONPATH=. python -m pytest test_pdf_race_preview.py -v

# Run full test suite
PYTHONPATH=. python -m pytest -q

# Generate demo previews
PYTHONPATH=. python -m cli.turf_cli demo-run --date 2025-12-15 --out out/cards
PYTHONPATH=. python -m cli.turf_cli preview --stake-cards out/cards --out out/previews --format html

# Audit scripts
bash scripts/audit_all.sh
bash scripts/guardian_check.sh
```

## Files Changed
- `turf/pdf_race_preview.py` (NEW) - Deterministic preview renderer
- `cli/turf_cli.py` - Added `preview` command
- `test_pdf_race_preview.py` (NEW) - Determinism and correctness tests
- `docs/plans/040-pdf-race-preview.md` - This plan document
