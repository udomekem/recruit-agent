# Phase 0 Brief: Foundations + eval harness

Approved 2026-11-06. Source: master-plan section 8 (phase 0 row), section 2, section 7.3.

## Goal
A developer starts the whole stack with one command, pushes a test candidate through
the full journey on stub steps (every transition audited and traced), and gets a
pass or fail eval report from `make eval` locally and in CI, before any real prompt exists.

## In scope
- `product/` layout per `stages/03-build/references/engineering-standards.md`.
- Docker Compose: API (FastAPI), worker (arq), Postgres, Redis. A health endpoint
  that checks the database and Redis.
- Typed config loaded from env, `.env.example` listing every variable
  (master-plan section 9), and the two model tier ids from `shared/project-config.md`.
- Alembic baseline migration: candidates and audit log tables only.
- State machine skeleton: every state and transition in master-plan section 2 declared
  in one table. Illegal transitions are rejected, every transition writes an audit row,
  failed steps move to NEEDS_REVIEW.
- Stub step jobs on the arq worker (canned results) with retries and timeouts.
  Transition jobs carry an idempotency key.
- Recruiter decision points (shortlist, reject, advance, send rejection) are API calls
  only. No automatic path past any of them (CLAUDE.md hard rules; one click send per
  `shared/project-config.md`).
- LLM client wrapper: takes a prompt id and version, a Pydantic output schema and a
  model tier. Validates output, retries invalid output, then routes to NEEDS_REVIEW.
  Traced. Fake model in CI, one real smoke call locally.
- Langfuse tracing on every stub step and LLM call (fields per master-plan rule 10).
  Tracing switches off cleanly when keys are absent.
- Eval harness per master-plan section 7.3 and `stages/04-evals/references/eval-harness-spec.md`:
  JSONL datasets, `make eval`, report compared with the last run, non-zero exit on a
  failed bar, push to a Langfuse dataset when keys are present. One dummy eval.
- GitHub Actions: lint, tests, migrations on a fresh Postgres, fast eval suite on every
  PR, a nightly workflow wired to the same suite, and a secret scan.

## Out of scope (belongs to a later phase)
- Jobs, screening questions, apply page, upload, rubric builder (phase 1)
- Any real prompt, CV parsing, redaction, scoring (phases 2 and 3)
- Dashboard and Next.js (phase 4)
- Email, voice and calendar integrations (phases 5, 6, 8)
- Dead letter queue, chaos tests, rate limits, cost dashboards, online evals, data deletion (phase 9)
- Deploying to Railway or Vercel (phase 10). Phase 0 runs locally and in CI only.
- LLM judge calibration (first needed in phase 5)

## Done criteria
Each line is checkable by a command, a test, or an eval.
- [ ] `docker compose up` starts API, worker, Postgres and Redis; `curl localhost:8000/health` returns 200 with database and Redis both ok.
- [ ] `alembic upgrade head` then `alembic downgrade base` both succeed on an empty database (run in CI).
- [ ] Integration test: a candidate created through the API reaches SCORED on stub steps, then with recruiter decision calls reaches INTERVIEW_BOOKED. A second candidate goes REJECTED to REJECTION_SENT.
- [ ] Test: without a decision call the worker never moves a candidate past SCORED, SCREEN_SCORED or REJECTION_DRAFTED.
- [ ] Test generated from the transition table: every illegal transition is rejected.
- [ ] Test: audit rows for a candidate equal its transitions, each with actor, from state, to state, reason and time.
- [ ] Test: a stub step that fails all retries leaves the candidate in NEEDS_REVIEW with the reason in the audit log.
- [ ] Test: the same transition job enqueued twice advances the candidate once.
- [ ] Test: with a fake model, invalid JSON is retried then routed to NEEDS_REVIEW; valid JSON returns a validated Pydantic object.
- [ ] Test: with a fake tracer, every stub step and LLM call emits a span with candidate id, prompt version, model, tokens, cost and latency.
- [ ] `make smoke` makes one real extraction tier call through the LLM client, exits 0 and prints the Langfuse trace URL; the trace shows the fields above.
- [ ] `make eval` writes a report to `product/evals/reports/`, exits 0 when bars pass and non-zero when one fails; with Langfuse keys set it prints the dataset run URL.
- [ ] Harness self test: the planted regression variant of the dummy agent makes the eval job fail.
- [ ] CI green on main: lint, tests, migrations, fast eval suite, secret scan. Eval report uploaded as a CI artifact.
- [ ] `git ls-files` shows no `.env`, and a test confirms `.env.example` lists every variable the config reads.

## Eval bars
No real agents this phase. These bars prove the harness and the skeleton.

| Agent / check | Dataset | Metric | Threshold |
|---------------|---------|--------|-----------|
| Dummy agent (deterministic stub) | `evals/datasets/dummy-v1.jsonl`, 10 cases | Exact match | 100% |
| Harness gate | Planted regression variant of the dummy agent | Run makes `make eval` and CI exit non-zero | 1 of 1 |
| Harness determinism | Dummy eval run 3 times | Identical results across runs | 100% |
| State machine | Transition table | Illegal transitions rejected | 100% |
| Audit log | Two full test journeys | Transitions with an audit row | 100% |
| Tracing | Stub pipeline run, fake tracer | Spans with all required fields | 100% |
| Idempotency | Duplicate transition jobs | Candidates advanced twice | 0 |

## Production rules exercised
| Rule | How phase 0 shows it |
|------|----------------------|
| 1 | The state table owns every move; stubs mark where bounded LLM steps will sit |
| 2 | LLM client validates against Pydantic, retries, then NEEDS_REVIEW |
| 3 | Decision points are API calls only, and a test proves it |
| 5 | Harness and CI gate exist before the first prompt |
| 8 | Transition jobs carry idempotency keys (full audit in phase 9) |
| 9 | State lives in Postgres; worker retries and timeouts (dead letter queue in phase 9) |
| 10 | Traces from day one |
| 11 | LLM client requires a prompt id and version; eval report records git SHA, dataset version and model |
| 12 | An audit row for every transition |
| 13 | Two model tiers set in config |

## Needs before starting
- Ready: Anthropic API key and Langfuse keys in `product/.env`; GitHub repo (private).
- To verify before 03-build: Docker Desktop with WSL2 on Mani's Windows machine
  (`docker compose version` in PowerShell). If missing, 03-build adds a setup guide
  to its references first.
- A way to run `make` (WSL2 or Git Bash).
- CI needs no secrets (fake model, fake tracer).
- Start now for phase 6 (longest lead time): Twilio account and the Australian number
  regulatory bundle.

## Risks
| Risk | Fallback |
|------|----------|
| Docker and `make` friction on Windows | Work inside WSL2; `make` targets are thin wrappers over Python entry points that run anywhere |
| Phase 0 grows into real features | Stubs return canned data; anything with business logic waits for its phase |
| CI service containers (Postgres, Redis) slow to start | Health checks with retries in the workflow |
| Langfuse project is in the JP region, so traces leave Australia; master-plan section 6 does not cover cross border disclosure (APP 8) | Fine while data is synthetic. Decide the region and add a section 6 line before any real person's data is traced (phase 6 real calls at the latest) |

## Open questions
Master-plan section 10 lists none for phase 0. Answered at the 2026-11-06 checkpoint:

| Question | Decision |
|----------|----------|
| Exact model ids for the two tiers | Recorded in `shared/project-config.md` |
| Repo visibility (setup said public, repo created private) | Private while building, public at phase 0 ship; recorded in `shared/project-config.md` |
| LLM client wrapper in phase 0 or phase 1 | Phase 0 |
| Docker Desktop installed? | Unknown; verify before 03-build (see Needs) |
