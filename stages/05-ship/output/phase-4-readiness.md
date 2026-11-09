# Phase 4 Production Readiness

Date 2026-11-09 · uncommitted working tree on top of `8da7cf7` · checked against
`stages/05-ship/references/production-readiness-checklist.md`.
Eval gate: PASS on every bar, confirmed by Mani 2026-11-09
(`stages/04-evals/output/phase-4-eval-report.md`).

| # | Check | Status | Evidence |
|---|-------|--------|----------|
| 1 | Workflow deterministic; LLM steps bounded | PASS | No new model step; rescore reuses the bounded phase 3 score step and never moves a candidate |
| 2 | LLM output validated; failures go to review | PASS | Unchanged; the new review queue page lists NEEDS_REVIEW candidates with their reason and the retry and reject actions |
| 3 | No consequential action without a recruiter | PASS | Shortlist and reject are recruiter keystrokes with a confirm step; no bulk actions; the API refuses overrides without a reason |
| 4 | Evidence exists in the source | PASS | Each quote is highlighted in the redacted CV by text match; quotes come from phase 3 and are already checked by code |
| 5 | Evals pass in CI | PASS (from the next push) | New CI jobs: `dashboard` (type check, unit tests, secret check, build) and `e2e` (whole stack, offline seed, 9 browser tests); no secrets needed |
| 6 | Fairness | PASS | Blind review: names and contact details never reach the page before shortlist (0 in the e2e test); reasons cannot mention the person (phase 3) |
| 7 | Injection does not move outputs | PASS | CV text is rendered as text only, never as HTML (unit test with an `onerror` payload); injection and hidden text flags shown first |
| 8 | Side effects idempotent | PASS | Decision row in the move's transaction with the expected version; stale pages get 409 (API and browser tests); rescore unique per candidate and rubric |
| 9 | Retries, timeouts, dead letter; kill test | PARTIAL | Unchanged; dead letter and kill test in phase 9 |
| 10 | Traces with version, model, tokens, cost, latency | PASS | Rescore runs are traced (`step:rescore`); no new model calls |
| 11 | Prompt and version stored with outputs | PASS | The candidate page shows rubric, prompt and model versions for each score |
| 12 | Audit row per transition | PASS | Decisions audited with the recruiter's reason; contact views logged as access events and shown in the history; rescore requests and failures noted on the job audit |
| 13 | Cost measured, limits set | PASS | No model cost in phase 4 except rescore (phase 3 price) and `make demo-seed` (about $0.15) |
| 14 | Compliance items | PASS (with open items) | Access log for contact details (Privacy Act); erasure clears decision reasons. Open: recruiter reasons in the audit log stay on erasure (append only); data location decision before real data |
| 15 | Defaults safe | PASS | Dashboard requires sign in; httpOnly, SameSite cookie; 5 failed sign ins lock for 15 minutes; frame, sniffing and caching headers set; token server side only |
| 16 | README and demo work from a clean checkout | PASS | Fresh copy (348 files, no `.env`, no `node_modules`): `make local-env` now also generates the dashboard password and session key; 272 passed, 2 skipped; fast suite PASS; self tests fail the gate as required; dashboard type check, 5 unit tests, secret check and build pass; Compose config valid |
| 17 | No secrets or real personal data in git | PASS (CI confirms on push) | New files are code and synthetic data; the dashboard password and session key live only in the ignored `.env`; gitleaks over the full history in CI |

## Open items

1. Mani's spot checks (phase 3 scoring CVs, phase 1 rubric labels).
2. `KIE_API_KEY` GitHub secret and a kie.ai spend cap.
3. Phase 9: shared store for the sign in limiter before any multi instance hosting; review of recruiter reasons in the audit log on erasure.
4. The stub calls and booking still run after shortlist until phases 6 to 8.
5. Data location decision before real candidate data.
