# Plan: Strengthen daily-digest guard in site workflow

- **Scope:** Update `.github/workflows/site_build_and_deploy.yml` guardrail step to check `daily-digest` in sanitized CLI help output; no other workflow logic or Python code changes.
- **Invariants:** Do not change CLI behavior, Turf Lite outputs, or workflow triggers/permissions.
- **Acceptance Criteria:** Guard step uses module-mode CLI help, strips ANSI codes, and greps combined stdout/stderr for `daily-digest` while preserving existing error messaging behavior.
- **Tests/Checks:** YAML parses; guardrails for file-mode and secrets if-expressions stay clean; run `python -m cli.turf_cli --help` locally (if applicable) and YAML lint command from root policy.
- **Risk:** Low—guard step only; ensure pipefail set to fail on missing command.
