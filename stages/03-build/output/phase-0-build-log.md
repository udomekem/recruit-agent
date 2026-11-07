# Phase 0 Build Log: Foundations + eval harness

Built 2026-11-07 in `~/code/recruit-agent` (Ubuntu 24.04, WSL2). Inputs:
`stages/02-design/output/phase-0-design.md`, `stages/03-build/references/engineering-standards.md`.

## How to run

From `product/` in Ubuntu: `make up`, `make test` (needs `make services`), `make lint`,
`make eval`, `make eval-selftest`, `make smoke`. Details in `product/README.md`.

## What was built

| Area | Files |
|------|-------|
| Config, `.env.example`, safe defaults | `app/config.py`, `.env.example` |
| States + transition table (T1 to T22, WITHDRAWN) | `app/domain/states.py` |
| Tables + migration | `app/db/models.py`, `migrations/versions/0001_baseline.py` |
| State machine (only writer of state, audit, idempotency, row lock) | `app/workflow/machine.py` |
| Stub steps, pipeline (retries, timeouts, NEEDS_REVIEW, no-answer rule) | `app/workflow/steps.py`, `pipeline.py`, `dispatch.py` |
| Recruiter API (bearer token, 409 on illegal or stale moves, health) | `app/api/main.py` |
| arq worker | `app/workers/worker.py` |
| LLM client (structured outputs, validation retries, backoff, refusal, call ceiling, fencing) | `app/llm/` |
| Smoke prompt | `app/prompts/smoke-echo/v1.md`, `app/cli.py` |
| Tracing (Langfuse, no-op, recording) | `app/observability/tracing.py` |
| Eval harness, suites, dataset, baseline | `evals/` |
| Docker, Makefile | `Dockerfile`, `docker-compose.yml`, `Makefile` |
| CI + nightly + secret scan | `.github/workflows/ci.yml`, `nightly.yml` |
| Tests (53) | `tests/` |

## Verified in this session (2026-11-07)

| Check | Result |
|-------|--------|
| `make lint` (ruff, format, mypy strict) | clean |
| `make test` | 53 passed |
| Alembic up, down, up on an empty database | ok |
| `make up` + `/health` | 200, database ok, redis ok |
| Live stack: create, shortlist, advance via curl, real arq worker | INTERVIEW_BOOKED, 11 audit rows; worker stopped at SCORED and SCREEN_SCORED |
| Live: illegal move / no token | 409 / 401 |
| `make smoke` (real Haiku call) | correct echo, 1 attempt, 447 in / 39 out tokens, $0.000064, about 1.2 to 1.8 s |
| Langfuse trace for smoke | one generation with model, prompt version v1, usage, cost, latency |
| `make eval` | gate PASS, exit 0, two Langfuse dataset runs, baseline saved |
| `make eval-selftest` | gate FAIL as expected (3 failing cases named), exit 0 |
| gitleaks on committed history | no leaks |
| gitleaks on the 58 files to commit | no leaks (one false positive on `RECRUITER_ID=recruiter-dev` in `.env.example`, marked `gitleaks:allow`) |
| CI on GitHub | not run yet (needs push) |

## Deviations from the design, with reasons

1. **Stub behaviour is injected, not stored.** Tests make steps fail or calls go
   unanswered through a `StubBehaviour` object passed to the pipeline. No test flags in
   the database.
2. **Planted regression breaks 3 of 10 cases, not 2.** It mislabels two answers; one of
   them appears twice in the dataset after normalising. Bar unchanged.
3. **Schema constraint keywords are stripped before sending.** The first real smoke call
   returned a 400: structured outputs reject `minimum` on integers. The schema sent to the
   model now drops `minimum`, `maximum`, `minLength` and similar; Pydantic still enforces
   them, and a regression test proves an out of range answer is retried. The client
   correctly failed fast on that 400 instead of retrying.
4. **Langfuse auto-instrumentation filtered.** Langfuse v5 also records the Anthropic SDK
   call as its own generation, which would double every call's tokens and cost. The tracer
   now exports only our spans (`should_export_span=is_langfuse_span`); verified on a second
   smoke trace.
5. **Candidate version.** Creation (T1) is the first transition, so a new candidate is at
   version 1 with one audit row; `state_version` always equals the number of audit rows.
6. **States stored as text**, validated in code, so adding a state later needs no enum
   migration.

## Known gaps (carried to later phases)

- An LLM step inside the pipeline does not exist yet; the client raises
  `LLMOutputInvalid` and the pipeline sends any failed step to NEEDS_REVIEW, but the two
  are first wired together in phase 1 or 2.
- Refusal fallback for the judgement tier (Sonnet 5.5) is not configured; add server side
  `fallbacks` when the first judgement prompt ships (phase 3).
- Worker crash recovery relies on arq re-running jobs plus version-guarded no-ops; the kill
  test is phase 9. No dead letter queue yet (phase 9).
- `ArqDispatcher` is verified live but has no unit test.
- `make up` builds the images on first run (a few minutes).
- A local `RECRUITER_TOKEN` was generated into `product/.env` for the live check.

## Stage 03 audit (2026-11-07)

| Check | Result |
|-------|--------|
| Tests: `make test` passes | PASS (53) |
| Lint and types: `make lint` passes | PASS |
| Design match: every entity, transition and side effect exists | PASS (deviations listed above) |
| Secrets: no keys, `.env` or real personal data in git | PASS (gitleaks, `.env` not staged) |
| Safety: no real call or email possible from tests or default config | PASS (no such code; flags default false; CI has no keys) |
| Docs: `product/README.md` explains how to run phase 0 | PASS |
