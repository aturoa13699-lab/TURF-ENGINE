# Plan 065: Pages workflow reliability fixes (publish.json + email step id)

## Scope
- Fix `.github/workflows/site_build_and_deploy.yml` so `publish.json` captures the deployed Pages URL.
- Add missing `id` to the optional email step so downstream references to `steps.send_email.*` resolve.
- Add this plan doc (no code/runtime logic changes elsewhere).

## Out of scope
- Any LITE math/ordering changes.
- Any CLI or engine logic changes.
- Any site rendering logic changes.
- Changes to other workflows (unless required to keep this workflow valid YAML).

## Invariants
- LITE determinism remains intact (no changes to compilation or scoring).
- Email remains optional and non-blocking.
- Workflow guardrails remain satisfied (no `secrets.*` in `if:` expressions).
- Pages deploy behavior remains unchanged aside from capturing URL correctly in diagnostics.

## Changes
1. Move `publish.json` creation + upload to after the `deploy-pages` step so `steps.deployment.outputs.page_url` is available.
2. Add `id: send_email` to the optional email step to support later status summary references.

## Acceptance criteria
- Workflow YAML validates.
- `publish.json` artifact contains a non-empty `page_url` on successful deploys.
- Email step status summary does not error due to missing `steps.send_email.*`.
- Guardrails pass (no file-mode CLI invocation for `cli/turf_cli.py`; no `secrets.*` in `if:`).

## Required checks
Run:
- `bash scripts/verify_repo_identity.sh`
- `bash scripts/guardian_check.sh`
- `PYTHONPATH=. python -m pytest -q`
- `bash scripts/audit_all.sh`

Manual workflow sanity:
- Run `Publish site & email URL` with `send_email=false` → deploy succeeds and artifact contains `page_url`.
- Run with `send_email=true` but no SMTP secrets configured → deploy succeeds; email is skipped; summary reports missing config.

