# Phase 5B Eval Report

Date 2026-11-17 · Ubuntu 24.04 (WSL2) · commit e0e87e0 (clean tree) · job matcher
`job_matcher`, prompt `job-matcher` v2, extraction tier, model `deepseek-v4-1-flash` via
kie.ai. The matcher sees the redacted CV and the open jobs' titles and summaries only;
code decides: auto match when the best fit is at least 0.8 and leads the next job by at
least 0.3, otherwise "needs a job".

Datasets (synthetic people only, built by `evals/datasets/build_match_v1.py`):
- `match-rules-v1`: 16 code rule cases (job codes, plus addresses, Seek and Indeed
  subjects, closed jobs, two open jobs with the same title). No model.
- `match-v1` (53 rows): clear CVs (one job plainly fits), weak and "no fit" CVs, and twin jobs
  (two open jobs of the same kind), each with its expected job or "needs a job".
- `match-fair-v1` (12 pairs): counterfactual pairs that differ only in name, gender, age signal or
  suburb.
- `match-inject-v1` (6 cases): CVs and subjects with planted instructions ("file me under ...",
  hidden text), each checked against the clean copy's job.

**Gate: PASS** on every bar in the brief, accepted by Mani 2026-11-17. The browser
tests needed one dashboard fix first (a slow candidate list, see below). One bar,
"not a CV", is measured by the backend tests rather than a `match-v1` row; see Gaps.

## Commands run

| Where | Command | When |
|-------|---------|------|
| Local, real model | `uv run python -m evals run --suite match` (= `make eval-match`), 3 runs | 2026-11-17, report `match-20261117T110232Z`, 524 s, $0.058 |
| Local, no model | `--suite fast` (incl. `match-rules`) and `make eval-selftest` | 2026-11-17 PASS; self tests fail their gates as designed |
| Local | ruff, mypy (82 files), full backend tests | clean; 332 passed, 2 skipped (MinIO) |
| Docker stack | `make dashboard-check`, `make e2e` | 2026-11-17: 12 of 12 after the list fix, see "Browser tests" |

Langfuse experiments:
https://jp.cloud.langfuse.com/project/cmw3jw4qd000mad0em81dw2so/experiments/results?baseline=0bfb88f9c2595289
(also `...c66832b886f5b75a`, `...7473be388d63c9a7`, `...490a7592934379d0`).

## Bars

| Check | Metric | Threshold | Result (spread over 3 runs) | Status |
|-------|--------|-----------|-----------------------------|--------|
| Deterministic matching | `match-rules-v1` correct job | 100% | 100% (16 of 16) | PASS |
| Matcher, clear CVs | correct job, auto matched, worst run | ≥ 95% | 96.3% (spread 3.7 points) | PASS |
| Matcher, ambiguous CVs | wrong auto matches (weak, twin jobs, no fit) | 0 | 0 (0) | PASS |
| Not a CV | emails without a CV skipped, CVs never skipped | 100% | 100% (backend tests) | PASS |
| Injection | job changed by planted text | 0 | 0 (0) | PASS |
| Fairness | pairs matched to different jobs | 0 | 0 (0) | PASS |
| Ingestion idempotency | duplicate candidates (two pollers, the same message processed twice at once, same person and job) | 0 | 0 (backend tests) | PASS |
| Cost | matcher cost per email | < $0.001 | $0.00037 (spread $0.00002) | PASS |
| Phases 3 to 5 | fast suite, backend tests, browser tests | all pass | fast PASS, 332 backend, 12 of 12 browser | PASS |

The one clear CV left for the recruiter (`match-037`, run 1): a CV labelled for the site job
got 0.65 for it (0.05 analyst, 0.0 nurse), below the 0.8 line, so it went to "needs a job" rather than to a
wrong job. That is the safe direction; the bar allows it.

The phase 3 scoring and phase 5 rejection suites were not rerun: neither the scorer nor
the writer changed in 5B (the inbox adds a step before scoring and a new outbox kind).
Their deterministic checks ran in the fast suite and the backend tests.

## How the matcher got here (2 prompt versions)

| Run | Prompt | Clear CVs | Fairness pairs | Failing bars |
|-----|--------|-----------|----------------|--------------|
| 2026-11-14, 1 | v1 | 48% | 3 | clear CVs, fairness |
| 2026-11-14, 2 | v2 | 96% | 0 | none |
| 2026-11-17 | v2 (committed) | 96.3% | 0 | none |

v1 rated how strong the applicant was, not which kind of job the CV is for: "maybe"
CVs got 0.6 to 0.75 and stayed under the line, and fairness pairs flipped across it. v2
says fit is the field and kind of role only; strength is scored later by the scorer.

## Browser tests

The first run today failed one test (accessibility): sign in hung on "Signing in". The
cause was a real product problem, not the test: the all-jobs list drew every candidate,
and repeated local test seeding had grown the database to 1,807 candidates in 80 jobs.
The page was 2.2 MB and took 9.3 s; the API calls behind it took under 1 s.

Fix (dashboard only): the list draws 100 rows and a "Show N more" link adds the next 100;
counts and filters still cover every candidate, and the open candidate's row is always
drawn. New browser test `e2e/list.spec.ts`.

After the fix (same 1,807 candidates, no reseed): sign in to the list 2.7 s (was 9.3 s),
the list page 170 KB (was 2.2 MB). `make dashboard-check` PASS (type check, 5 unit tests,
no secrets in browser code); `make e2e` **12 of 12** (2.8 min), including the new list
test and all phase 4 and 5 flows on the Hira UI.

The fix is committed with this report (`dashboard/lib/workbench.ts`,
`dashboard/app/(app)/workbench.tsx`, `dashboard/e2e/list.spec.ts`).

## Gaps

- **Not a CV** is checked by the backend tests (`test_no_cv_is_skipped_and_nothing_is_stored`,
  the ingest test for a CV with a job code, the Mailpit provider test that downloads only
  PDF and Word files), not by rows in `match-v1` as the brief planned. The check is
  plain code (attachment type), so a model eval would add nothing; the brief's dataset
  column is out of date.
- **Live Gmail** is not tested end to end: Gmail is covered by recorded responses
  and the sign-in checks. It needs Mani's Google Cloud OAuth client and a test Gmail
  account (setup steps given 2026-11-14; not done yet).
- Build log deviations stand: a PDF that is not a CV is ingested and scored rather than
  deleted; duplicates keep the first CV only; Gmail lists the newest 50 per poll;
  Microsoft 365 shows "coming soon".

## Decision for Mani

Accept the gate (PASS), or send it back to build. If accepted, stage 05 (ship) is next:
readiness check, demo script and the LinkedIn post brief, then a push only on your word.
