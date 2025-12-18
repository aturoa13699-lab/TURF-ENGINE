# Plan 072: Per-meeting digest artifacts (opt-in)

## Scope
- Extend the daily digest aggregator to optionally emit **per-meeting** digest artifacts (JSON + Markdown) alongside the combined daily index.
- Add a `write_per_meeting` flag to `build_daily_digest` and propagate through without changing default behavior.
- Per-meeting artifacts live under `out_dir/meetings/<date_local>_<slug>/` (flag-controlled).

## Out of scope
- Any Lite math/ordering changes.
- Any changes to stake-card generation, overlay logic, or site renderer behavior.

## Invariants
- Determinism: stable ordering, no timestamps in outputs, deterministic slugs.
- Default OFF: behavior identical to Plan 071 when `write_per_meeting=False`.
- Non-mutation: input stake-card JSON files are never modified.
- Per-meeting paths: `digest_json_path` / `digest_md_path` appear in meeting records **only** when `write_per_meeting=True`.

## Implementation
- Add deterministic helpers:
  - `_slugify(meeting_id)` for stable folder naming.
  - `_render_meeting_digest_markdown()` for per-meeting markdown output.
- Emit artifacts under:
  - `out_dir/meetings/<date_local>_<slug>/strategy_digest.json`
  - `out_dir/meetings/<date_local>_<slug>/strategy_digest.md`
- Update `render_daily_digest_markdown` to surface per-meeting paths when present (without changing ordering).

## Acceptance criteria
- `build_daily_digest(..., write_per_meeting=True)` writes per-meeting artifacts and includes relative paths in meeting records.
- `write_per_meeting=False` creates no `out_dir/meetings/` directory and does not include per-meeting paths.
- Outputs are deterministic across repeated runs.

## Required checks
- `bash scripts/guardian_check.sh`
- `PYTHONPATH=. python -m pytest -q`
- `bash scripts/audit_all.sh`
