# AGENTS.md (Canonical)

This file is the **sole authoritative agent policy** for this repository.

Rules:
- Do not create or add new “agent instruction” files with policy content (e.g., CLAUDE.md, AGENT.md, docs/AGENTS.md).
- If a tool requires a different filename, that file must be **pointer-only** and must not contain rules.
- Any policy changes must be made here (root /AGENTS.md).

## Pointer-Only Other Agent Files

This repository’s authoritative agent rules are in **/AGENTS.md**.
Do not add new rules here. This file is pointer-only.

## TURF_ENGINE_LITE Invariants (Non-negotiable)

- **Do NOT change LITE ordering or math.**
- All “extras” must be **feature-flagged** and **default OFF**.
- LITE canonical output must remain stable/deterministic for a given input date.
- Enhancements must write to `stake_card_pro.json` and/or `out/derived/*` — never mutate the canonical Lite output.

## Required Working Style: Plan → Build → Guardian

Every change must follow:

### Phase 1 — Plan
- Write a short plan (5–15 lines) **before** editing.
- Identify risks and invariants (especially anything that could break Lite determinism).
- Before doing any work: print `git remote -v` and run `bash scripts/verify_repo_identity.sh`. If it fails, STOP.

### Phase 2 — Build
- Implement the smallest diff that satisfies the plan.
- Prefer deterministic, offline-friendly logic.
- Avoid “magic” changes without explanation.

### Phase 3 — Guardian
- Run required verification commands.
- If anything fails: fix or revert. Do not explain away failures.
- Report results using the required reporting template.

## Verification Commands (Required)

Run these after changes (and before claiming done):

```bash
bash scripts/audit_all.sh
bash scripts/guardian_check.sh
```

If you cannot run those scripts, run the equivalent minimum:

```bash
PYTHONPATH=. python -m pytest -q
PYTHONPATH=. python -m cli.turf_cli demo-run --date 2025-12-15 --out /tmp/turf_cards

ruby -ryaml -e 'Dir[".github/workflows/*.y{a,}ml"].each { |f| YAML.load_file(f) }'

if grep -RIn --line-number -E 'python\s+cli/turf_cli\.py' .github/workflows; then
  echo "::error::File-mode CLI invocation found in workflows. Use: python -m cli.turf_cli"
  exit 1
fi

if grep -RIn --line-number -E 'if:.*secrets\.' .github/workflows; then
  echo "::error::secrets.* used inside if: expression. Map secrets to env and gate on env.*"
  exit 1
fi
```

## Workflow Guardrails (Never Regress)

- Workflows must not run file-mode CLI: `python cli/turf_cli.py ...`
  - Must use module-mode: `python -m cli.turf_cli ...`
- Workflows must not use `secrets.*` inside `if:` expressions.
  - Map `secrets.* -> env.*` and gate on `env.*` instead.
- Workflow YAML must parse (Ruby YAML validator is acceptable).
- Pages deploy must always generate `public/index.html` and include `public/.nojekyll`.

## Email Reliability Rules (Pages URL Wake-up Email)

- The send-mail step must be **non-blocking** (deploy succeeds even if email fails).
- Never print secret values in logs or summaries.
- Email sending must be gated by:
  - `inputs.send_email == true`
  - and `can_email == true` from an explicit email-config check.
- Email-config check must:
  - Inspect env-mapped secrets (MAIL_TO, MAIL_FROM, SMTP_SERVER, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD)
  - Set outputs like `can_email`, `missing`
  - Write a human-readable job summary (without secrets).

## Plans Required for Workflow/Core Changes

If you modify any of:
- `.github/workflows/**`
- `turf/**`, `engine/**`, `cli/**`, `tools/**`, `scripts/**`, `site/**`

…you must also update/add a short plan in:
- `docs/plans/`

Plan must include:
- scope (in/out)
- invariants (Lite determinism)
- acceptance criteria
- test/verification commands

## Required Reporting Format

When finished, provide:

### Summary
- What changed and why (3–8 bullets)

### Risks / Invariants
- Confirm Lite invariants preserved

### Testing
- Commands run + results (copy/paste)

### Diffstat
- `git diff --stat`

### Key Hunks
- Show the most important diff snippets

### Artifacts
- Mention generated audit artifacts (if applicable)

## Agent Docs Consistency

- Root `/AGENTS.md` is canonical.
- Any other agent doc must be pointer-only.
- CI will fail if additional agent policy files are introduced or contain policy-like text.

## Packaging & Dependency Sanity

- Keep runtime deps consistent between `requirements.txt` and `pyproject.toml`.
- Keep dev deps in `requirements-dev.txt`.
- Optional extras belong in `pyproject.toml` extras.
- Avoid adding deps without updating plans + explaining why.

## Codex Operating Contract (Use for Tasks)

PHASE 1 (Plan):
- Produce a short plan + risks/invariants.

PHASE 2 (Build):
- Implement minimal diff.
- Keep Lite outputs unchanged; extras behind flags.

PHASE 3 (Guardian):
- Run `bash scripts/audit_all.sh` and `bash scripts/guardian_check.sh`.
- If failing, fix or revert until green.
- Report using the required reporting format.
