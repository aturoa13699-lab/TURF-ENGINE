# Plan 074: Daily digest alignment for write_per_meeting

## Scope
- Replace `turf/daily_digest.py` with the Plan 072-aligned implementation that
  accepts `write_per_meeting` and emits deterministic per-meeting artifact paths
  plus Markdown markers.

## Out of scope
- Any Lite ordering/math changes.
- Workflow or site rendering changes.

## Invariants
- Derived-only outputs remain deterministic; inputs are not mutated.
- Default behavior unchanged when `write_per_meeting` is false.

## Acceptance criteria
- Tests for Plan 072 per-meeting digests pass (no TypeError; markers present;
  deterministic outputs).

## Verification
- `bash scripts/guardian_check.sh`
- `PYTHONPATH=. python -m pytest -q`
- `bash scripts/audit_all.sh`
