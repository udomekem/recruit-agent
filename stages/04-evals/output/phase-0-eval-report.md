# Phase 0 Eval Report

Date 2026-11-07 · git `ac091bd` · Ubuntu 24.04 (WSL2) and GitHub Actions.
Agent: `dummy` v1 (deterministic stand-in, no model) and `v1-regressed` (planted bug).
Prompt versions: `smoke-echo` v1 (smoke only). Dataset: `dummy-v1` (10 synthetic cases).
Status: gate confirmed PASS by Mani, 2026-11-07.

## Commands run

| Where | Command | When |
|-------|---------|------|
| Local | `python -m evals run --suite fast` x3, `--suite selftest`, `--suite nope` | 2026-11-07 07:42 UTC |
| Local | `pytest tests/test_transition_table.py tests/test_machine.py tests/test_journeys.py tests/test_llm_client.py` x3 | 2026-11-07 07:41 UTC |
| Local | transition table enumeration (every from, to, actor combination) | 2026-11-07 07:40 UTC |
| CI | full `CI` workflow, run 42352156723 | 2026-11-07 07:39 UTC |
| Local | `make smoke` (real Haiku call) and `make eval` with Langfuse push | 2026-11-07 06:2x UTC (pre-commit, same code) |

## Bars

| Bar | Metric | Threshold | Result (3 run spread) | Status |
|-----|--------|-----------|-----------------------|--------|
| Dummy agent exact match | exact match on dummy-v1 | 100% | 100% in 3 of 3 runs (spread 0) | PASS |
| Harness gate | planted regression makes the gate fail | 1 of 1 | gate FAIL as expected, 3 failing cases named; selftest exit 0, locally and in CI | PASS |
| Harness determinism | identical results across 3 runs | 100% | 100% (10 of 10 cases identical, every run) | PASS |
| State machine | illegal transitions rejected | 100% | 567 of 567 illegal combinations refused (612 total, 46 table rows) | PASS |
| Audit log | transitions with an audit row, across full journeys | 100% | `state_version` equals audit rows in every journey test (booked, rejected, review, withdrawn); live stack: 11 of 11 | PASS |
| Tracing | spans with all required fields | 100% | every step span and generation span in tests; live Langfuse generation had model, version, tokens, cost, latency | PASS |
| Idempotency | candidates advanced twice | 0 | 0 (duplicate job, concurrent clicks, stale version tests) | PASS |

Bar tests passed 3 of 3 runs (42 tests each). Full suite: 53 passed locally and in CI.

## Adversarial and edge cases covered

- Malformed dataset row, unknown suite: harness error, exit 2, never a pass.
- Invalid model output, always invalid output, refusal, auth error, rate limit, call ceiling
  (fake model).
- Untrusted text trying to close its data block and inject instructions: stays fenced.
- Real API rejection (unsupported schema keyword) on the first smoke call: client failed
  fast without retrying; fixed and covered by a regression test.

## Phase 0 done criteria

| Done criterion (brief) | Evidence | Status |
|------------------------|----------|--------|
| `docker compose up` + `/health` 200 with database and Redis ok | live stack, 2026-11-07 | PASS |
| Alembic upgrade and downgrade on an empty database (in CI) | CI step "Migrations up, down, up" | PASS |
| Candidate reaches INTERVIEW_BOOKED; another reaches REJECTION_SENT | `test_full_journey_to_interview_booked`, `test_rejection_journey_waits_for_send`, live stack | PASS |
| Worker never passes SCORED, SCREEN_SCORED, REJECTION_DRAFTED | `test_worker_never_passes_a_decision_point`, table test | PASS |
| Every illegal transition rejected (generated from the table) | `test_every_illegal_pair_is_refused` | PASS |
| Audit rows equal transitions, with actor, states, reason, time | `test_audit_rows_equal_transitions`, `test_audit_row_has_every_field` | PASS |
| Step failing all retries leaves NEEDS_REVIEW with reason | `test_failed_step_goes_to_review_then_resolves` | PASS |
| Same job twice advances once | `test_duplicate_job_advances_once`, `test_same_job_twice_moves_once` | PASS |
| Fake model: invalid retried then raised; valid returns Pydantic object | `test_llm_client.py` | PASS (see note 1) |
| Spans carry candidate id, prompt version, model, tokens, cost, latency | `test_every_step_span_has_required_fields`, `test_generation_span_has_required_fields` | PASS |
| `make smoke` real call exits 0 and prints the trace URL; trace shows the fields | smoke runs and Langfuse API check | PASS |
| `make eval` writes a report, exit 0 on pass, non-zero on fail, Langfuse URL with keys | eval runs, exit codes 0/1/2 | PASS |
| Harness self test fails the eval job on the planted regression | `make eval-selftest`, CI step | PASS |
| CI green on main: lint, tests, migrations, fast evals, secret scan, report artifact | run 42352156723, artifact `eval-reports` | PASS |
| No `.env` in git; `.env.example` lists every variable | CI "No .env committed", `test_env_example_lists_every_setting` | PASS |

Note 1: the brief says invalid output is "routed to NEEDS_REVIEW". The client raises a
typed failure and the pipeline sends any failed step to NEEDS_REVIEW; the two meet when the
first real LLM step joins the pipeline (phase 1 or 2). Carried as a known gap in the build log.

## Compared with last run

First phase: baseline `baseline-fast.json` created at this commit; all checks "same" against it.

## Gate

**PASS** (every bar PASS). Confirmed by Mani at the stage 04 checkpoint, 2026-11-07.
