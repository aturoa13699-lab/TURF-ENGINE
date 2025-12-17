# Plan 030: Weekly Backtest and Patch Candidates Report

## Scope
- Generate weekly backtest artifacts and a ranked “what to improve next” report.
- Produce structured outputs for loss clusters and experiment suggestions without changing Lite outputs.
- Integrate with a scheduled workflow that uploads artifacts and optionally emails summaries (gated, non-blocking).

## Invariants / Risks
- TURF_ENGINE_LITE determinism remains untouched; backtests and reports are derived-only.
- All experiment suggestions are flag-only; no automatic patches to Lite logic.
- Email remains optional and non-blocking with secrets redacted from logs and summaries.

## Acceptance Criteria
- Outputs include `out/backtest/report.md`, `out/backtest/metrics.json`, `out/backtest/metrics_summary.json`, `out/backtest/patch_candidates.md`, `out/backtest/loss_clusters.json`, and `out/backtest/experiments.yml`.
- Report includes a “Next Experiments” section generated from `experiments.yml` with flag-only recommendations.
- Scheduled workflow uploads artifacts and gates email sending on env-based readiness (`send_email && can_email`) with non-blocking email.
- Workflow input `send_email` and artifact summary (top patch candidates) are written to the job summary; no secrets or derived-only fields leak when disabled.

## Verification / Commands
- `bash scripts/audit_all.sh`
- `bash scripts/guardian_check.sh`
- Scheduled/manual workflow dry run that generates artifacts without altering Lite outputs.
