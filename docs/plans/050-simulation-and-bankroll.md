# Plan 050: Simulation and Bankroll Tools

## Scope
- Implement bankroll sizing policies (flat, fractional Kelly, capped Kelly) and CLI entrypoints.
- Add seeded Monte Carlo simulation for stake cards with configurable run counts.
- Emit metrics and selections under `out/derived/sim/` without changing Lite outputs.

## Invariants / Risks
- TURF_ENGINE_LITE ordering/math unchanged; simulations and bankroll outputs are derived-only and feature-flagged where needed.
- Deterministic results for identical seeds; no time-based randomness.
- No network dependencies for simulations; rely on existing data inputs only.

## Acceptance Criteria
- CLI command: `turf bankroll --stake-cards ... --policy flat|kelly|fractional_kelly --seed S --iters N --out out/derived/sim`.
- Outputs: `out/derived/sim/.../bankroll_summary.json`, `.../bets_selected.json`, `.../strategy_inputs.json` with deterministic ordering and input sha.
- Bankroll logic enforces max-risk constraints and matches expected stakes in tests; simulations are reproducible with fixed seeds and do not change Lite outputs.

## Verification / Commands
- `bash scripts/audit_all.sh`
- `bash scripts/guardian_check.sh`
- `PYTHONPATH=. python -m cli.turf_cli bankroll --stake-cards <dir> --seed 123 --iters 200 --out out/derived/sim`
- Lite hash check for determinism.
