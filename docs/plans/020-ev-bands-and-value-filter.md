# Plan 020: EV Bands, Value Filters, and Race Summary

## Scope
- Add derived value/risk fields to PRO outputs without altering Lite results.
- Produce race-level summaries (top picks, value picks, fades, trap flag, strategy string) in `stake_card_pro.json`.
- Add compact mobile/emoji row formatting for CLI view commands when `--format mobile`.

## Invariants / Risks
- TURF_ENGINE_LITE math, ordering, and canonical outputs remain unchanged; new data is PRO/derived-only and behind flags.
- Deterministic outputs for a given input date; no network calls introduced.
- Ensure feature flags default OFF and guard against mutating `stake_card.json`.

## Acceptance Criteria
- Runner fields in PRO output: `ev`, `ev_band`, `ev_marker`, `confidence_class`, `risk_profile`, `model_vs_market_alert|null`.
- Race block includes `race_summary` with `top_picks`, `value_picks`, `fades`, `trap_race`, and `strategy` string.
- CLI supports compact emoji/mobile row as default for `--format mobile` and a readable pretty view option.
- All new data written to `stake_card_pro.json` or `out/derived/*`; Lite output unchanged.

## Verification / Commands
- `bash scripts/audit_all.sh`
- `bash scripts/guardian_check.sh`
- Targeted CLI demos for new formats (e.g., `PYTHONPATH=. python -m cli.turf_cli view stake-card --format mobile --date 2025-12-15 --out /tmp/turf_cards`).
