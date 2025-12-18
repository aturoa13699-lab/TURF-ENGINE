# Plan 070: Unified Daily Digest Generator

## Scope
Add a deterministic “Daily Digest” artifact generator that produces:
- `out/derived/strategy_digest.json` (canonical JSON; sort_keys + compact separators)
- `out/derived/strategy_digest.md` (human-readable)

Digest is derived-only and must not alter Lite stake_card.json or ordering.

## Non-Goals (Out of Scope)
- Any change to Lite scoring, ordering, or canonical Lite output files.
- Any changes to workflow guardrails besides routine verification.
- Any new scraping / ingestion.
- Any runtime derive-on-render changes (site builder remains read-only unless explicitly enabled elsewhere).

## Design
### Inputs
- `stake_card` (dict): a stake card already produced by compile/overlay pipeline.
- `bets` (List[Bet]): output of deterministic bet selection.
- `selection_rules` (dict): config used for selection (require_positive_ev, min_ev, min_edge).
- `bankroll_policy` (dict): policy config (flat/kelly/fractional_kelly, bankroll_start, caps).
- `simulation_summary` (optional dict): output of deterministic simulation, if executed.

### Outputs (Derived-only)
- JSON: canonicalized by `json.dumps(..., sort_keys=True, separators=(",", ":"))` with newline.
- Markdown: stable ordering; no timestamps; no environment-dependent content.

### Determinism Requirements
- Digest ordering must be stable across runs:
  - sort bet rows by (race_number, runner_number).
  - sort tag lists.
- No timestamps, random UUIDs, or non-deterministic iteration.
- Do not mutate stake_card; digest code must treat inputs as read-only.

### Gating
Digest generation is opt-in via CLI command invocation. Default pipeline behavior remains unchanged.

## Implementation Steps (Atomic Commits)
Commit 1: Plan doc (this file)

Commit 2: Digest module (new)
- Add `turf/digest.py`:
  - `build_strategy_digest(...) -> dict`
  - `render_digest_markdown(digest) -> str`
  - `write_strategy_digest(out_dir, digest, filename_base="strategy_digest") -> None`
- Use canonical JSON writing (reuse `turf.simulation.write_json`).

Commit 3: CLI integration (flagged)
- Add a new CLI command `digest` to build digest from an existing stake card.
- Writes to `out/derived/strategy_digest.{json,md}` by default.

Commit 4: Tests
- Add `tests/test_plan_070_digest.py`:
  - Determinism: identical inputs => identical digest JSON.
  - Stable sort: bets sorted deterministically.
  - Non-mutation: stake_card input unchanged after digest build.

## Acceptance Criteria
- Default existing commands unchanged.
- Digest command writes deterministic JSON + Markdown.
- Stake card inputs remain unchanged (non-mutation).
- `PYTHONPATH=. python -m pytest -q` passes.
- `bash scripts/guardian_check.sh` passes.
- `bash scripts/audit_all.sh` passes.

## Required Verification
Run in order:
1) `bash scripts/verify_repo_identity.sh`
2) `bash scripts/guardian_check.sh`
3) `PYTHONPATH=. python -m pytest -q`
4) `bash scripts/audit_all.sh`

