# Plan 071 — Multi-stake-card Daily Digest (Directory Aggregation)

Scope:
- Aggregate multiple stake-card JSON files from a directory into a single daily digest.
- Emit:
  - out/derived/daily_digest.json
  - out/derived/daily_digest.md

Out of scope:
- Any Lite math/ordering changes.
- Any changes to Plan 070 single-file digest semantics.
- Any changes to site rendering behavior.

Invariants:
- Derived-only outputs: digest artifacts only.
- Determinism: same inputs + same flags => byte-identical daily_digest.json + daily_digest.md.
- No input mutation: do not modify stake card payloads in-place.
- Ordering is stable:
  - meetings ordered by (date_local, meeting_id, source_path)
  - files discovered deterministically (sorted paths)

Design:
- Input: directory containing stake cards (stake_card*.json).
- De-dupe per meeting key (date_local, meeting_id).
- Prefer *_pro.json for the same meeting key when prefer_pro=True.
- For each selected stake card:
  1) select_bets_from_stake_card(...)
  2) optionally simulate_bankroll(...)
  3) build_strategy_digest(...)
  4) collect into a daily index
- Markdown output is generated from the index with stable formatting (no timestamps).

Acceptance criteria:
- Running daily-digest twice produces identical artifacts.
- prefer_pro selection works (pro chosen over lite for same meeting key).
- Input payloads remain unchanged after processing.

Required checks:
- bash scripts/guardian_check.sh
- PYTHONPATH=. python -m pytest -q
- bash scripts/audit_all.sh

