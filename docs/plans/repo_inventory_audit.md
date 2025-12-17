# Plan: Add repo inventory audit helper script

## Scope
- Add a read-only helper script `scripts/repo_inventory.sh` to collect repo identity, branches, workflow triggers, guardrails, and file inventory.
- Write outputs to `out/diagnostics/repo_inventory.md` and `out/diagnostics/repo_inventory.json` plus supporting raw files.
- Do not modify TURF LITE logic or workflows; focus solely on diagnostics scripting and a manual workflow runner.

## Invariants / Risks
- Preserve TURF_ENGINE_LITE determinism (no data/output mutations beyond diagnostics files under out/).
- Keep features read-only; script must not modify tracked files or git state.
- Avoid new dependencies; rely on existing system tools (bash, python, ruby yaml) with graceful fallbacks and keep ruby optional with warning-based skip when neither Python YAML nor Ruby is available.
- Ensure remote URLs are redacted in outputs to avoid leaking credentials.

## Acceptance Criteria
- Running `bash scripts/repo_inventory.sh` succeeds after repo identity verification and writes the requested markdown/json outputs under `out/diagnostics/`.
- Markdown report includes identity, branches, recent history, workflows with triggers and Pages flag, guardrail hits, file inventory summary, and quick risk notes.
- JSON report includes identity, branches, workflows with trigger flags/schedules and Pages flag, file counts by top dir, and guardrail hits arrays.
- Script gracefully handles missing tools (e.g., uses find when tree is unavailable), keeps YAML parsing robust to `on` key boolean handling, and does not alter repository files.
- If PyYAML is unavailable, falls back to Ruby for workflow parsing; if both are missing, emits a clear warning, skips trigger parsing, and still produces inventory outputs.
- Manual GitHub Actions workflow exists to run the inventory helper, upload diagnostics artifacts, and surface a summary snippet in the job summary with read-only permissions.

## Verification / Tests
- `bash scripts/repo_inventory.sh`
- `bash scripts/audit_all.sh`
- `bash scripts/guardian_check.sh`
- `.github/workflows/repo_inventory.yml` validation via guardian scripts
