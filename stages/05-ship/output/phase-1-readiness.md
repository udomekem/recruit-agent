# Phase 1 Production Readiness (draft)

Date 2026-11-07 · commit `cbb5907` · checked against
`stages/05-ship/references/production-readiness-checklist.md`.
**Draft:** the stage 05 contract starts after a PASS gate. The gate is provisional (all
bars met on draft labels, review pending), so this is prepared early at Mani's request and
the phase stays open until the labels are reviewed.

| # | Check | Status | Evidence |
|---|-------|--------|----------|
| 1 | Workflow deterministic; LLM steps bounded | PASS | Job table J1 to J11 plus candidate table T1 to T23; the rubric builder is one bounded job step |
| 2 | LLM output validated; failures go to review | PASS | Schema plus code checks (quotes, weights, ids, guard), retried with reasons, then J3 NEEDS_REVIEW (`test_invalid_model_output_moves_job_to_review`); closes the phase 0 partial |
| 3 | No consequential action without a recruiter action | PASS | Rubric approval opens the job (J6); erase and bulk upload need the recruiter token; nothing is scored against an unapproved rubric |
| 4 | Scores cite evidence in the source | PASS (rubric) | Every criterion quotes the ad; code rejects quotes not in the ad. Candidate scores arrive in phase 3 |
| 5 | Evals pass in CI | PARTIAL | Fast suite in CI on every push; real model rubric suite meets all bars locally (provisional, draft labels); nightly needs the `KIE_API_KEY` secret |
| 6 | Fairness | PASS (rubric) | Guard blocks protected wording in criteria and questions (26 tests); 0 protected criteria, 9 of 9 discriminatory ads flagged. CV fairness counterfactuals: phase 3 |
| 7 | Injection cases do not move scores or actions | PASS (rubric) | 2 injection ads, 0 planted criteria over 3 runs; ad text fenced as data |
| 8 | Side effects idempotent | PASS | Duplicate application returns the first; job moves keyed; CV delete safe to repeat; erase twice is a no-op |
| 9 | Retries, timeouts, dead letter; kill test | PARTIAL | Client and step retries, storage retries, startup wait for storage. Dead letter queue and kill test: phase 9 |
| 10 | Traces show prompt version, model, tokens, cost, latency | PASS | Rubric build spans and generations; smoke trace on DeepSeek; cost name normalisation fixed |
| 11 | Prompt and rubric versions stored with outputs | PASS | Rubric rows store prompt id, version (v2), model, cost; recruiter edits are new versions; approved version stored on the job |
| 12 | Audit row for every transition | PASS | Job audit and candidate audit; T23 records the applicant as actor; erasure audited without personal data |
| 13 | Cost measured; limits set | PASS | $0.0011 per rubric (bar $0.05); per run call ceiling 200 in evals; per process ceiling in the app |
| 14 | Compliance items for this phase | PASS (draft wording) | Collection notice v1 (purpose, AI assistance with human decisions, call disclosure, retention 12 months, access and deletion), unticked consent, consent version stored, erasure path. Wording is not legal advice; lawyer review in phase 10. Langfuse JP region holds no applicant data (sentinel test) |
| 15 | Defaults safe | PASS | No email, call or calendar code; flags off; test candidate endpoint off in production; CV links never public |
| 16 | README and demo work from a clean clone | NOT RUN | Phase 0 clean clone passed; re-run with MinIO and the kie.ai key before closing the phase |
| 17 | No secrets or real personal data in git | PASS | gitleaks history scan in CI; `.env` untracked; synthetic data only; MinIO and kie.ai keys only in `.env` |

## Open before closing phase 1

1. Mani reviews `rubric-v1` labels; gate confirmed (numbers may move if labels change).
2. `KIE_API_KEY` GitHub secret, so the nightly real model run is live.
3. Clean clone check (item 16) with MinIO and the kie.ai key.
4. Spend cap on the kie.ai account.

## Not ready for (by design)

Public traffic to the apply page (no rate limiting or spam protection until phase 10),
real candidate data, scoring, email, calls.
