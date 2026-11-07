# Phase 2 Production Readiness

Date 2026-11-08 · after commit `59ff03b` plus the clean clone fix · checked against
`stages/05-ship/references/production-readiness-checklist.md`.
Eval gate: PASS, confirmed by Mani 2026-11-08 (`stages/04-evals/output/phase-2-eval-report.md`).

| # | Check | Status | Evidence |
|---|-------|--------|----------|
| 1 | Workflow deterministic; LLM steps bounded | PASS | The parse step is one bounded step (APPLIED to PARSED or NEEDS_REVIEW); redaction steps 1 to 5 are code |
| 2 | LLM output validated; failures go to review | PASS | Values must appear in the CV, dates and order checked, empty profile rejected; invalid after retries to NEEDS_REVIEW (`test_invalid_parser_output_goes_to_review_without_personal_data`) |
| 3 | No consequential action without a recruiter | PASS | Parsing makes no decision; scoring and decisions are later phases |
| 4 | Evidence exists in the source | PASS | Every extracted employer, title, institution, skill, credential and personal span is checked against the CV text |
| 5 | Evals pass in CI | PARTIAL | Fast suite on every push; real model CV suite passes all 10 bars locally; nightly runs it once the `KIE_API_KEY` secret is added |
| 6 | Fairness | PASS (input side) | 0 identifier and 0 protected attribute leaks in the text the scorer will read; scoring counterfactuals are phase 3 |
| 7 | Injection does not move outputs | PASS | 2 hidden instruction CVs, 0 planted terms over 3 runs |
| 8 | Side effects idempotent | PASS | The parse row is written in the same transaction as the move; a duplicate or late job is a no-op |
| 9 | Retries, timeouts, dead letter; kill test | PARTIAL | Storage read retries, extraction time and page limits, LLM retries; dead letter and kill test in phase 9 |
| 10 | Traces with version, model, tokens, cost, latency | PASS | Parse spans carry them; parser output never traced (`trace_output=False`) |
| 11 | Prompt and version stored with outputs | PASS | CvParse rows store prompt id, version (v2), model, cost, attempts |
| 12 | Audit row per transition | PASS | PARSED and NEEDS_REVIEW moves audited; reasons hold counts or error types, never CV text |
| 13 | Cost measured, limits set | PASS | $0.00066 per CV (bar $0.01); eval call ceiling 300 |
| 14 | Compliance items | PASS (with open item) | Data minimisation before the provider; raw text not stored; referees dropped; erasure deletes parse data. Open: where real candidate data may be processed (kie.ai, DeepSeek) before real data |
| 15 | Defaults safe | PASS | No real email, calls or calendar; scanned CVs never sent to a model |
| 16 | README and demo work from a clean checkout | PASS (after fix) | The check found that `make services` failed on a fresh copy (Docker Compose needs MinIO credentials a new user could not know). Added `make local-env` (generates local-only secrets, never overwrites, never prints) with a test. Clean checkout: 171 passed, 2 skipped (MinIO), both evals pass |
| 17 | No secrets or real personal data in git | PASS | gitleaks clean on every commit; CVs are synthetic (fictional names, example.test emails, ACMA fiction phone range) |

## Open items

1. `KIE_API_KEY` GitHub secret (nightly real model evals).
2. Data location decision before any real candidate data.
3. C: disk space: about 2 GB free; Docker rebuilds grow the WSL disk.
4. Phase 1 closes after the rubric label review.
