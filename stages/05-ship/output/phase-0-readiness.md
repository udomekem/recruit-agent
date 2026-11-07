# Phase 0 Production Readiness

Date 2026-11-07 · checked against `stages/05-ship/references/production-readiness-checklist.md`.
Eval gate: PASS (`stages/04-evals/output/phase-0-eval-report.md`, confirmed by Mani).

| # | Check | Status | Evidence |
|---|-------|--------|----------|
| 1 | Workflow deterministic; LLM steps bounded | PASS | One transition table (`app/domain/states.py`); only `machine.py` writes state; `test_transition_table.py` |
| 2 | LLM output validated against a schema; failures go to review | PASS (partial) | `LLMClient` validates and retries, then raises `LLMOutputInvalid`; pipeline sends failed steps to NEEDS_REVIEW. Wired together when the first LLM step lands (phase 1 or 2) |
| 3 | No consequential action without a recruiter action | PASS | Decision rows have no system actor; `test_worker_never_passes_a_decision_point`; live stack waited at SCORED and SCREEN_SCORED |
| 4 | Scores cite evidence in the source text | N/A | No scoring yet (phase 3) |
| 5 | Evals pass in CI | PASS | CI run 42352156723: fast suite and self test |
| 6 | Fairness counterfactuals | N/A | No scoring yet (phase 3); dataset format already has `pair_id` |
| 7 | Injection cases do not move scores or actions | PASS (partial) | Data block fencing tested (`test_untrusted_text_is_fenced_and_cannot_close_the_block`); score tests arrive with scoring (phase 3) |
| 8 | Side effects idempotent; duplicate event test | PASS | Unique idempotency key per move; `test_same_job_twice_moves_once`, `test_duplicate_job_advances_once`, concurrent click test |
| 9 | Retries, timeouts, dead letter; kill test | PASS (partial) | Step retries and timeouts, NEEDS_REVIEW after the last try (tested). Dead letter queue and kill test: phase 9 |
| 10 | Traces show prompt version, model, tokens, cost, latency | PASS | Langfuse smoke trace (Haiku, v1, 447/39 tokens, $0.0000642, 1219 ms); recording tracer tests |
| 11 | Prompt and rubric versions stored with outputs | PASS (partial) | Prompt id and version on every LLM result and span; eval report records git SHA, dataset and agent versions. Rubric versions arrive in phase 1 |
| 12 | Audit row for every transition | PASS | `state_version` equals audit rows in every test journey; live 11 of 11 |
| 13 | Cost per candidate measured; limits set | PASS (partial) | Per call cost from the price table, in traces; per process call ceiling (tested). Per candidate budgets: phase 9 |
| 14 | Compliance items for this phase | N/A | No personal data in phase 0. Open item: Langfuse project is in the JP region; decide region and add an APP 8 note before real data (phase 6 at the latest) |
| 15 | Defaults safe: no real send or call | PASS | No email, call or calendar code; flags default false (`test_side_effects_off_by_default`); CI has no keys |
| 16 | README and demo steps work from a clean clone | PASS (after fix) | Fresh clone + `cp .env.example .env`: lint ok, tests pass, evals exit 0, self test exit 0. The check found a bug (blank `KEY=` lines read as set secrets); fixed, regression test added, smoke now exits 2 with "not set" |
| 17 | No secrets or real personal data in git | PASS | gitleaks on full history in CI; `.env` not tracked; datasets synthetic |

## Found during this check

- **Blank secrets counted as set.** Copying `.env.example` left `ANTHROPIC_API_KEY=` and
  the Langfuse keys as empty strings, so tracing switched on with blank keys and the smoke
  command tried a call with an empty key. Blank secrets now mean "not set"
  (`app/config.py`), with `test_blank_secrets_from_env_example_count_as_unset`.

## Not ready for (by design, later phases)

Real candidate data, real email, calls or calendar, public access, multiple recruiters.
