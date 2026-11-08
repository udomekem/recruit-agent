# Phase 3 Production Readiness

Date 2026-11-08 · uncommitted working tree on top of `a32a032` · checked against
`stages/05-ship/references/production-readiness-checklist.md`.
Eval gate: PASS on every bar, confirmed by Mani 2026-11-08
(`stages/04-evals/output/phase-3-eval-report.md`).

| # | Check | Status | Evidence |
|---|-------|--------|----------|
| 1 | Workflow deterministic; LLM steps bounded | PASS | One bounded step (PARSED to SCORED or NEEDS_REVIEW); answer rules, total, band, reasons and flags are code |
| 2 | LLM output validated; failures go to review | PASS | Every criterion once, ids from the rubric, quotes in the copy, reasons checked for protected wording; invalid after retries to NEEDS_REVIEW with no CV text (`test_invented_quote_is_retried_then_reviewed`) |
| 3 | No consequential action without a recruiter | PASS | Band is a recommendation stored with the score; SCORED waits for a recruiter (T4, T5); the API marks it `recommendation_only` |
| 4 | Evidence exists in the source | PASS | Quotes checked against the redacted copy by code; evidence bar 100% over 135 scored CVs |
| 5 | Evals pass in CI | PARTIAL | Answer rules and the planted lift self test run on every push (no secrets); real model score suite passes all 11 bars locally; nightly runs it once the `KIE_API_KEY` secret is added |
| 6 | Fairness | PASS | 12 counterfactual pairs (name, gender, graduation year, suburb, gap reason): 0.0 mean and largest difference over 3 runs; reasons cannot mention the person |
| 7 | Injection does not move outputs | PASS | 6 attack pairs: lift 0.0, 100% flagged; hidden text removed before redaction; code phrases plus the model; the planted lift scorer fails the gate |
| 8 | Side effects idempotent | PASS | Score row in the same transaction as the move; unique per candidate and rubric; a late or duplicate job is a no-op |
| 9 | Retries, timeouts, dead letter; kill test | PARTIAL | LLM client retries and timeouts, 40,000 character cap; dead letter and kill test in phase 9 |
| 10 | Traces with version, model, tokens, cost, latency | PASS | `step:score` spans carry them plus verdict counts, total and band; scorer output never traced (`test_no_personal_data_or_cv_text_in_score_traces_or_logs`) |
| 11 | Prompt and version stored with outputs | PASS | Score rows store rubric id and version, prompt `cv-scorer` v2, model, cost, attempts |
| 12 | Audit row per transition | PASS | PARSED to SCORED audited with total, rubric version and band; reasons hold no CV text |
| 13 | Cost measured, limits set | PASS | $0.0025 per candidate including the parse (bar $0.02); eval call ceilings 600, 400, 200 |
| 14 | Compliance items | PASS (with open item) | Scorer reads only the redacted copy; weights never sent; erasure clears quotes, reasons, answer values and flag text, keeps numbers for audit. Open: where real candidate data may be processed (kie.ai, DeepSeek) |
| 15 | Defaults safe | PASS | No email, calls or calendar; no automatic shortlist or reject; hidden text never reaches the model |
| 16 | README and demo work from a clean checkout | PASS | Fresh copy of the files git would include (297 files, no `.env`): `cp .env.example .env`, `make local-env`, `uv sync`, `make services`: 251 passed, 2 skipped (MinIO), fast suite PASS, both self tests fail the gate as required |
| 17 | No secrets or real personal data in git | PASS (CI confirms on push) | New datasets are synthetic (fictional names, example.test emails, ACMA fiction phone range); keys only in the ignored `.env`; gitleaks runs over the full history in CI |

## Open items

1. Mani's spot check of 10 scoring CVs (`evals/datasets/score-v1-review.md`).
2. `KIE_API_KEY` GitHub secret (nightly real model evals, now about $0.75 a night).
3. Data location decision before any real candidate data.
4. Phase 1 closes after the rubric label review.
5. Rescoring on a new rubric version (phase 4; the outdated flag shows meanwhile).
