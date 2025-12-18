# Plan 060: Runner Narratives, Fitness Flags, and Risk Profiles

## Scope
- Add deterministic narrative summaries, fitness flags, and risk tags to PRO outputs without touching Lite data.
- Provide collapsed human-readable `risk_profile` strings and optional `model_vs_market_alert` for model-vs-market gaps.
- Keep derived fields behind feature flags and write outputs to `stake_card_pro.json` (or derived-only), never Lite.

## Invariants / Risks
- TURF_ENGINE_LITE math/order untouched; new fields are additive and deterministic for a given input.
- No new network calls; rely solely on existing data sources.
- Feature flags default OFF to avoid changing canonical outputs.

## Acceptance Criteria
- Feature flags exist in `DEFAULT_FEATURE_FLAGS`: `enable_runner_narratives`, `enable_runner_fitness`, `enable_runner_risk` (default OFF).
- Runner-level derived fields: `summary`, `fitness_flags`, `risk_tags`, `risk_profile`, optional `model_vs_market_alert`.
- Race-level flag: `trap_race` only when enabled risk logic deems it applicable.
- Outputs are written only to PRO/derived locations; Lite stake cards remain unchanged.

## Verification / Commands
- `bash scripts/audit_all.sh`
- `bash scripts/guardian_check.sh`
- `PYTHONPATH=. python -m pytest -q`
- Lite hash check for determinism.
