# Plan 050: Simulation and Bankroll Tools

## Scope
- Implement bankroll sizing policies (flat, fractional Kelly, capped Kelly, edge-weighted) and CLI entrypoints.
- Add seeded Monte Carlo simulation for stake cards with configurable run counts and bet types.
- Emit metrics and time-series outputs under `out/sim/` without changing Lite outputs.

## Invariants / Risks
- TURF_ENGINE_LITE ordering/math unchanged; simulations and bankroll outputs are derived-only and feature-flagged where needed.
- Deterministic results for identical seeds; no time-based randomness.
- No network dependencies for simulations; rely on existing data inputs only.

## Acceptance Criteria
- CLI commands: `turf bankroll --stake-card ... --bank ... --max-risk ... --mode flat|kelly|capped_kelly|edge` and `turf simulate --stake-card ... --runs N --seed S --bet-type win|place|quinella|multi`.
- Outputs: `out/sim/metrics.json`, `out/sim/equity_curve.csv`, `out/sim/percentiles.csv`.
- Bankroll logic enforces max-risk constraints and matches expected stakes in tests; simulations are reproducible with fixed seeds.

## Verification / Commands
- `bash scripts/audit_all.sh`
- `bash scripts/guardian_check.sh`
- Targeted seeded runs (e.g., `PYTHONPATH=. python -m cli.turf_cli simulate --stake-card ... --runs 10000 --seed 123 --out out/sim`).
