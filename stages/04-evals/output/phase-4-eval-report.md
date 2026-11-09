# Phase 4 Eval Report

Date 2026-11-08 · Ubuntu 24.04 (WSL2) · dashboard Next.js 16.4.5 in Docker, API and worker
from the same stack. No new model agent in this phase: the bars are product checks (brief).
Data: `make demo-seed-offline`: the three phase 3 jobs (15 CVs each) and a 50 candidate
review drill job, synthetic people only, scores from the CVs' coverage plans (no model).

**Status: gate PASS, confirmed by Mani 2026-11-09.**

## Commands run

| Where | Command | Result |
|-------|---------|--------|
| Local, Docker stack | `make e2e` (Playwright 1.65 image, 9 browser tests) | 9 passed, 2026-11-08 |
| Local | full backend tests | 272 passed, 2 skipped (MinIO) |
| Local, node:22 | dashboard type check, unit tests, secret check, `next build` | pass |
| Local | `make eval`, `make eval-selftest` | gate PASS; both self tests fail the gate as required |

## Bars

| Bar | Metric | Threshold | Result | Evidence | Status |
|-----|--------|-----------|--------|----------|--------|
| Review speed | actions (key presses and clicks) per decision, 50 seeded candidates | at most 2 | 2.0 (100 actions, 50 decisions, 24 s) | `e2e/speed.spec.ts` | PASS |
| Agreement rate | override flag and rate on a fixed table | 100% | 8 of 8 pairs; 10 decision rate exact; 100% shown after the drill | `test_override_table`, `test_agreement_rate_counts_only_advance_and_reject`, speed test | PASS |
| Override reason | overrides without a real reason refused | 100% | API: 3 of 3 refused with 422, nothing moved; form: empty and 9 characters refused | `test_override_needs_a_real_reason`, `e2e/override.spec.ts` | PASS |
| Blind review | seeded names, name parts, emails, phones in pages and responses before shortlist | 0 | 0 | `e2e/blind.spec.ts`, `test_contact_details_only_after_shortlist_and_logged` | PASS |
| Token exposure | API token in any page, script, response, request, header or cookie | 0 | 0 | `e2e/token.spec.ts`, `check-public-env.mjs` | PASS |
| Accessibility | serious or critical axe issues on 6 views | 0 | 0 | `e2e/a11y.spec.ts` | PASS |
| Speed | ranked list API, 200 candidates, 95th percentile | under 300 ms | pass | `test_ranked_list_with_200_candidates_is_fast` | PASS |
| Phase 3 scorer | phase 3 bars | still pass | unchanged scorer and prompt; the phase 2 redaction fix only keeps organisation names, so phase 3 inputs are unchanged or richer (rerun nightly once the key is set) | | PASS (by construction) |

## Phase 4 done criteria

| Done criterion (brief) | Evidence | Status |
|------------------------|----------|--------|
| `make up` starts the dashboard; sign in works; no token in the browser | stack healthy; `e2e/auth.spec.ts`, `e2e/token.spec.ts` | PASS |
| Ranked job page with band, flags, knockouts, state; filters work | screenshot `job-after-review.png`; `e2e/override.spec.ts` uses the band and state filters | PASS |
| Candidate page shows every verdict, reason and quote, highlighted in the CV | screenshot `candidate-page.png`; `lib/highlight.test.ts` (5 tests) | PASS |
| Shortlist and reject from the keyboard; next undecided opens | `e2e/speed.spec.ts` | PASS |
| Override without a reason refused by the API (422) and the form | as above | PASS |
| Every decision stores its recommendation; agreement rate correct | `test_agreeing_decisions_are_recorded`, `test_override_with_a_reason_is_logged` | PASS |
| Blind review: no name, email or phone in the DOM before shortlist | `e2e/blind.spec.ts` | PASS |
| Stale page gets a conflict message, not a double decision | `test_stale_page_cannot_decide_twice`, `e2e/override.spec.ts` | PASS |
| Rescore writes new score rows and changes no state | `test_rescore_on_a_new_rubric_keeps_state_and_old_score` | PASS |
| 50 seeded candidates reviewed in at most 2 actions each | `e2e/speed.spec.ts` | PASS |
| Accessibility: no serious or critical issues | `e2e/a11y.spec.ts` | PASS |
| Vercel ready: `next build` with environment settings only; no secret read in browser code | build and secret check | PASS |

## Gate

**PASS** on every bar, confirmed by Mani at the checkpoint, 2026-11-09. CI runs the
dashboard checks and the browser tests for the first time on the next push.
