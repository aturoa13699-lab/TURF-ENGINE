# Plan 060: Runner Narratives, Fitness Flags, and Risk Profiles

## Scope
- Add deterministic narrative summaries, fitness flags, and risk tags to PRO outputs without touching Lite data.
- Provide collapsed human-readable `risk_profile` strings and optional `hype_warning` for model-vs-market gaps.
- Keep derived fields behind feature flags and write outputs to `stake_card_pro.json` or `out/derived/*`.

## Invariants / Risks
- TURF_ENGINE_LITE math/order untouched; new fields are additive and deterministic for a given input.
- No new network calls; rely solely on existing data sources.
- Feature flags default OFF to avoid changing canonical outputs.

## Acceptance Criteria
- Runner-level derived fields: `summary`, `fitness_flags`, `risk_tags`, `risk_profile`, optional `hype_warning` or `model_vs_market_alert`.
- Race-level flags include `trap_race` where applicable and align with EV/risk logic when enabled.
- Outputs are written only to PRO/derived locations; Lite stake cards remain unchanged.

## Verification / Commands
- `bash scripts/audit_all.sh`
- `bash scripts/guardian_check.sh`
- Targeted CLI run to generate PRO outputs with flags enabled (e.g., `PYTHONPATH=. python -m cli.turf_cli demo-run --date 2025-12-15 --out /tmp/turf_cards --pro-flags narratives,risk`).
