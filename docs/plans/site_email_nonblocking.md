# Plan: Email gating + agent policy documentation

## Scope
- Add canonical agent policy file at repository root.
- Adjust reusable site build/deploy workflow to ensure optional email sending is non-blocking and aligned with guardrails.

## Invariants / Risks
- Preserve TURF_ENGINE_LITE determinism and do not alter Lite outputs.
- Keep workflow guardrails intact (no secrets in `if:`, module-mode CLI only).
- Avoid exposing secret values in logs or summaries.

## Acceptance Criteria
- Root agent policy captured in `/AGENTS.md` with existing guardrails and operating contract.
- Email send step remains gated on `inputs.send_email` and config readiness and will not fail the deploy if the action errors.
- Workflow YAML remains valid and continues to map secrets through env for gating.

## Verification Commands
- PYTHONPATH=. python -m pytest -q
- PYTHONPATH=. python -m cli.turf_cli demo-run --date 2025-12-15 --out /tmp/turf_cards
- ruby -ryaml -e 'Dir[".github/workflows/*.y{a,}ml"].each { |f| YAML.load_file(f) }'
- if grep -RIn --line-number -E 'python\s+cli/turf_cli\.py' .github/workflows; then echo "::error::File-mode CLI invocation found in workflows. Use: python -m cli.turf_cli"; exit 1; fi
- if grep -RIn --line-number -E 'if:.*secrets\.' .github/workflows; then echo "::error::secrets.* used inside if: expression. Map secrets to env and gate on env.*"; exit 1; fi
