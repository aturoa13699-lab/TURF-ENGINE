# Repo Identity Guard

## Scope
- Add a repo identity verification script to block work in the wrong repository.
- Integrate the verification into the audit pipeline so checks fail fast on mismatched remotes.
- Allow a small, explicit remote allowlist to support forks without disabling the guard.
- Update contributor policy to require running the guard before edits.

## Out of Scope
- Changes to Lite math, ordering, or feature flags.
- Workflow behavioral changes beyond the identity check requirement.

## Invariants
- TURF_ENGINE_LITE determinism and outputs remain unchanged.
- Email/workflow guardrails stay intact (non-blocking, env-gated secrets).
- No secrets are printed in logs.

## Acceptance Criteria
- `scripts/verify_repo_identity.sh` exits non-zero when no configured remote URL contains any allowed substring and prints a success message otherwise.
- The script prints the currently checked-out branch and HEAD commit to aid recovery/migration workflows.
- Allowed substrings default to `github.com/aturoa13699-lab/TURF-ENGINE` and can be extended via space-separated `ALLOWED_REPO_SUBSTRINGS` while still failing on unexpected remotes.
- `scripts/audit_all.sh` runs the identity check before other verification commands.
- Contributor policy in `AGENTS.md` instructs running the identity check before work.

## Verification Commands
- `bash scripts/audit_all.sh`
- `bash scripts/guardian_check.sh`
