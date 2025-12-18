# Plan 072: Per-meeting digest artifacts (opt-in) + daily index links

## Goal
Extend the Plan 071 daily digest aggregator to optionally emit **per-meeting**
digest artifacts alongside the combined daily index, so Pages can link directly
to each meeting’s strategy sheet while keeping the daily index as the entry point.

## Scope
- Add `--write-per-meeting` (default **OFF**) to `daily-digest`.
- When enabled:
  - Write per-meeting artifacts under: `out/derived/meetings/<meeting_id>/`
    - `strategy_digest.json`
    - `strategy_digest.md`
  - Add stable per-meeting artifact paths into `daily_digest.json`.
  - Add stable links/paths into `daily_digest.md`.

## Out of scope
- Any Lite scoring/math/order changes.
- Any new betting logic or selection policy changes.
- Site rendering changes (Pages will simply publish artifacts; linking can be a later plan).

## Determinism / Safety invariants
- Inputs must not be mutated.
- Output ordering must be stable across platforms.
- Default behavior unchanged when `--write-per-meeting` is OFF.
- No timestamps in Markdown outputs.
- Paths written in the daily index should be **relative to out_dir** and deterministic.

## Acceptance criteria
- With `--write-per-meeting` OFF:
  - No `out/derived/meetings/` tree is created (or it remains empty).
  - Daily digest output structure remains compatible with Plan 071.
- With `--write-per-meeting` ON:
  - Each included meeting has per-meeting digest files written.
  - `daily_digest.json` includes `digest_json_path` and `digest_md_path` for each meeting.
  - `daily_digest.md` contains the per-meeting relative paths.
- Determinism:
  - Running twice on identical inputs produces identical JSON/Markdown and identical per-meeting digest bytes.

## Required verification
1. `bash scripts/guardian_check.sh`
2. `PYTHONPATH=. python -m pytest -q`
3. `bash scripts/audit_all.sh`

