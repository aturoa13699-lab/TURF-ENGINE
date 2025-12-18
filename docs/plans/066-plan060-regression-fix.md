# Plan 066: Plan 060 Regression Fix (Runner Summary + Trap Race Gating)

Why: Plan 060 tests were failing because runner summaries were absent when narratives were enabled and trap_race was gated on the wrong flag.

## Scope
Fix the two failing Plan 060 regression tests by adjusting PRO overlay gating and runner insights output:
1) Ensure `summary` is present when `enable_runner_narratives=true`.
2) Ensure `trap_race` is set only when `enable_trap_race=true` (not implicitly tied to runner risk).

## Out of Scope
- Any changes to Lite compilation math, runner ordering, or canonical Lite stake_card.json output.
- Any changes to site rendering logic or workflow orchestration (workflow 065 remains intact).
- Any new features beyond the minimum required to pass the two failing tests.

## Repo Reality / Targets
- `engine/turf_engine_pro.py`: PRO overlay wiring and gating.
- `turf/runner_insights.py`: Deterministic insight derivation (summary/fitness/risk) and trap-race heuristic.
- `turf/feature_flags.py`: Defaults and override resolution (add missing flag only if absent).
- `tests/test_plan_060_runner_insights.py`: Existing regression tests (must pass without weakening assertions).

## Invariants (Non-negotiable)
- Lite output is untouched: no changes to Lite ordering or math.
- All Plan 060 extras remain feature-flagged and default OFF.
- Overlay continues operating on a deep copy (no mutation of input stake cards).
- Determinism preserved: repeated runs with identical inputs produce identical JSON outputs.

## Implementation Plan (Smallest Diff)
### 1) Trap race gating correctness (Overlay)
- In `engine/turf_engine_pro.py`, gate trap detection on `enable_trap_race` ONLY.
- Do not require `enable_runner_risk` to be enabled for trap detection.
- Keep existing deep-copy semantics and forecast/value/summary ordering unchanged.

### 2) Runner summary presence when narratives enabled (Insights)
- In `turf/runner_insights.py`, ensure `derive_runner_insights(... enable_summary=True ...)` returns a dict containing:
  - `summary` (string)
- Summary must be deterministic, missing-data-safe, and must not mutate the runner input.

### 3) Default flag completeness
- If `enable_trap_race` is missing from `DEFAULT_FEATURE_FLAGS`, add it with default `False`.
- Ensure `resolve_feature_flags()` behavior remains unchanged (copy defaults → apply only known overrides).

### 4) Keep behavior strictly PRO-only
- No changes to Lite artifacts unless explicitly behind overlay-only flags.
- Verify any new fields appear only in PRO outputs and only when enabled.

## Risks
- Changing overlay gating could unintentionally change race-level fields across outputs.
- Runner insight changes could introduce non-determinism if lists are not stable/sorted.
- Missing-data branches could cause KeyErrors or inconsistent field presence.

## Acceptance Criteria
- `tests/test_plan_060_runner_insights.py::test_plan060_enabled_fields_present_and_deterministic` passes:
  - With runner flags enabled, runner contains `summary` and output is deterministic across runs.
- `tests/test_plan_060_runner_insights.py::test_plan060_trap_race_only_when_flag_enabled` passes:
  - `trap_race` absent when `enable_trap_race=false`
  - `trap_race` present/True when `enable_trap_race=true` and fixture triggers heuristic.
- No new fields appear when flags are not enabled.
- Input stake card object is not mutated by overlay (deep copy discipline holds).

## Verification (Required)
Run from repo root after identity check:
1) `bash scripts/verify_repo_identity.sh`
2) `bash scripts/guardian_check.sh`
3) `PYTHONPATH=. python -m pytest -q`
4) `bash scripts/audit_all.sh`

## Rollback Plan
- Revert only the overlay gating hunk and/or insights summary changes if any unrelated regressions appear.
- Keep feature flag defaults and workflow 065 changes intact.
