# Plan 040: PDF Race Preview Export

## Status: IMPLEMENTED

## Scope
- Add deterministic HTML/PDF race preview outputs
- Previews are **read-only** by default - they render what's present in the payload
- No derivation occurs unless explicitly enabled
- Write outputs to `out/previews/{date}_{meeting_id}.html` and `.pdf`

## Out of Scope
- Derivation of race summaries or value fields (that's Plan 020)
- Automatic inclusion of PRO fields not present in payload

## Implementation Details

### Module: `turf/pdf_race_preview.py`
- Deterministic HTML/PDF renderer
- No current time usage - uses `date_local` from payload or fixed fallback `2000-01-01`
- Preserves runner ordering from payload (no re-sorting)
- Only processes `stake_card*.json` files (ignores `runner_vector.json` etc.)
- Deduplicates by `(date, meeting_id)` to prevent duplicate outputs
- PRO fields (ev_marker, risk_profile, race_summary) rendered **only if present**

### CLI Command: `turf preview`
```bash
# HTML only (default, read-only)
PYTHONPATH=. python -m cli.turf_cli preview --stake-cards out/cards --out out/previews

# PDF generation (requires weasyprint)
PYTHONPATH=. python -m cli.turf_cli preview --stake-cards out/cards --out out/previews --format pdf

# Single file mode
PYTHONPATH=. python -m cli.turf_cli preview --single out/cards/stake_card.json --out out/previews
```

### Dependencies
- PDF generation requires optional `[pdf]` extra: `pip install turf[pdf]`
- Uses WeasyPrint for HTML-to-PDF conversion (pinned in `pyproject.toml`)

## Invariants / Risks
- **TURF_ENGINE_LITE outputs stay unchanged** - previews read existing data only
- **Read-only by default** - no derivation of race summaries or value fields
- **Deterministic output** - same input => same HTML output
- No network calls; all assets embedded in CSS
- No live timestamps - uses date from payload only
- Only accepts `stake_card*.json` files - ignores other JSON

## Acceptance Criteria
- [x] Running the preview command produces HTML artifacts in `out/previews/`
- [x] PDF generation works when weasyprint is installed
- [x] PRO fields rendered **only if present** in stake card (no derivation)
- [x] Output is deterministic - multiple runs produce identical HTML
- [x] Works with basic stake_card.json (no PRO fields required)
- [x] Ignores non-stake-card JSON files (runner_vector.json, etc.)
- [x] Deduplicates by (date, meeting_id)

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
