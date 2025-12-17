# Plan 010: Wake-up Email Reliability and Summary Hygiene

## Scope
- Harden the wake-up email workflow so missing SMTP config never blocks deploys and summaries communicate email status.
- Include Sydney-local run timestamp, Pages URL, and a clear email status line (sent/skipped + reason) in the job summary.
- Keep optional weather/rail context strictly conditional on existing inputs; no new network calls by default.
- Ensure wrappers inherit secrets and the reusable workflow maps SMTP/mail secrets to env defaults (including SMTP_PORT) before gating on `can_email`.

## Invariants / Risks
- TURF_ENGINE_LITE outputs remain unchanged; only workflows and summaries are touched.
- Never echo secret values in logs or summaries; continue env-based gating (no `secrets.*` in `if:` expressions).
- Email sending stays non-blocking and respects existing `send_email` + `can_email` gating.

## Acceptance Criteria
- Workflow summary includes: Sydney-local timestamp, Pages URL, and an “email status” line showing sent/skipped with reason.
- Wrapper workflows pass SMTP secrets via `secrets: inherit`, and the reusable workflow maps them to env with safe defaults (SMTP_PORT default 465) before gating email.
- Secret-backed values are never printed; summaries show only presence/status booleans.
- Optional weather/rail fields appear only when already available from inputs/artifacts; defaults avoid network calls.
- Deploy/job succeeds even when email config is incomplete or send step fails.
- Email summary clearly reports send intent, `can_email`, missing vars, and whether send was attempted.

## Verification / Commands
- `bash scripts/audit_all.sh`
- `bash scripts/guardian_check.sh`
