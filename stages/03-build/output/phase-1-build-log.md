# Phase 1 Build Log: Jobs and intake

Built 2026-11-07 in `~/code/recruit-agent`. Inputs: `phase-1-brief.md`, `phase-1-design.md`
(both approved 2026-11-07, all defaults), `engineering-standards.md`.

## What was built

| Area | Files |
|------|-------|
| Job states and table (J1 to J11) | `app/domain/jobs.py` |
| Five standard questions, answer typing, knockout rules as data | `app/domain/questions.py` |
| Protected attribute guard (reviewed list, false positive tests) | `app/domain/guard.py` |
| Collection notice v1 (12 month retention) | `app/domain/notice.py` |
| Tables: jobs, job audit, questions, rubric versions, answers, candidate intake fields | `app/db/models.py`, `migrations/versions/0002_jobs_and_intake.py` |
| Job machine and service (create, transition, versioned rubrics, approve and open) | `app/workflow/jobs.py` |
| Rubric builder agent + prompt v1 (Sonnet, effort medium, refusal fallback, code checks) | `app/agents/rubric_builder.py`, `app/prompts/rubric-builder/v1.md` |
| LLM client: `check` hook, per agent effort, judgement tier fallback | `app/llm/client.py`, `app/llm/providers.py` |
| Rubric build as a pipeline job step and worker function | `app/workflow/pipeline.py`, `dispatch.py`, `app/workers/worker.py` |
| CV storage (S3 compatible, SSE, random keys) and memory store for tests | `app/integrations/storage.py` |
| CV file checks (content based, zip bomb limits, no macros) | `app/intake/files.py` |
| Intake adapter (one path for every source) | `app/intake/service.py` |
| New actor `candidate` and T23 (apply) | `app/domain/states.py` |
| Erasure (CV deleted, personal fields cleared, audit kept without personal data) | `app/workflow/machine.py` |
| Job, rubric, apply page, bulk upload and erase endpoints; apply page templates | `app/api/jobs_api.py`, `app/api/intake_api.py`, `app/templates/` |
| MinIO in Docker Compose (Chainguard image), API waits for storage | `docker-compose.yml` |
| Eval dataset (15 ads, draft labels), review page and approve command | `evals/datasets/build_rubric_v1.py`, `rubric-v1.jsonl`, `rubric-v1-review.md`, `evals/review.py` |
| Harness: real model agents, multi bar checks, draft label gate, cached Langfuse push | `evals/harness.py`, `evals/agents.py`, `evals/rubric_metrics.py`, `evals/suites.toml` |
| CI: MinIO + encryption test; nightly real model rubric suite with secret guard | `.github/workflows/ci.yml`, `nightly.yml` |
| Tests (133) | `tests/test_jobs.py`, `test_rubric_builder.py`, `test_guard.py`, `test_intake.py`, `test_storage_s3.py`, extended `test_evals.py`, `test_config.py` |

## Verified in this session (2026-11-07)

| Check | Result |
|-------|--------|
| `make lint` (ruff, format, mypy strict, 44 files) | clean |
| `make test` with real MinIO (`S3_TEST=1`) | 133 passed |
| Migration 0002 up, down to base, up; `alembic check` | ok, no drift |
| Rubric builder, real Sonnet, 2 ads (pre credit outage) | BA ad: 5 must, 3 nice, 1 attempt, $0.0105, 5.5 s. Age ad: no age criteria, both phrases flagged, $0.0094 |
| Live stack: create job, build fails (no credit) to NEEDS_REVIEW with reason, hand rubric (J11), approve (J6) | OPEN, rubric v1 |
| Live apply: real multipart PDF | 201, candidate "Applicant 1", worker moved it to SCORED |
| Live duplicate (email in different case) / fake PDF | 200 "already have your application" / 422 |
| Stored CV in MinIO | `encrypted=True`, random key |
| Apply page in the browser | job, five questions, CV upload, full notice, unticked consent, notice v1 |
| `make eval`, `make eval-selftest` | pass |
| gitleaks on 59 staged files | no leaks; `.env` not staged |
| Real model rubric suite (45 builds) | **not measured**: Anthropic account out of credit (see below) |
| CI on GitHub | not run yet (needs push) |

## Found while building, and fixed

1. **Guard false positives.** The first guard list blocked "Single Touch Payroll" (an ATO
   payroll system, ad 015), "native mobile development" and "working with young people".
   Patterns narrowed; 26 guard tests, plus a test that no label phrase trips the guard.
2. **Applicant as actor.** An applicant is neither a recruiter nor the system, so the audit
   log would have mislabelled who created a candidate. Added actor `candidate` and T23.
3. **Migration downgrade.** Autogenerate left the new foreign key unnamed, so downgrade
   failed. Named it.
4. **Provider outage scored as agent failure.** The first real rubric run hit "credit
   balance is too low" on every call; the harness recorded 45 invalid outputs and several
   metrics looked fine on empty output. Provider, auth and billing failures are now a
   harness error (exit 2, "eval not measured"); invalid output and refusals still count
   against the agent. Regression test added.
5. **MinIO images withdrawn.** `minio/minio` (Docker Hub) and `quay.io/minio/minio` no
   longer pull. Switched to `cgr.dev/chainguard/minio` (same server); it has no shell, so
   the API retries the bucket check on start instead of a container healthcheck.
6. **Worker start up race in the live check**: job created before the worker was ready;
   not a bug (the job was picked up 7.7 s later), the check script now waits.

## Deviations from the design

- Bulk upload is a recruiter endpoint taking files plus a JSON list of name and email per
  file (design said "many CVs with name and email"); answers are optional for bulk.
- A recruiter supplied rubric skips the "quote must be in the ad" check (the recruiter is
  accountable) but keeps ids, weights and the guard.
- Erasure keeps yes/no and number answers (no personal data) and clears text answers.
- The app uses the local MinIO root credentials (`S3_ACCESS_KEY`). A scoped storage user is
  a hardening item (phase 9).

## Blocked / waiting on Mani

1. **Anthropic credit.** Top up the account (and set a spend limit), then the real model
   rubric suite can run (about $0.50 to $1.00 per run).
2. **Label review.** `evals/datasets/rubric-v1-review.md`; then
   `uv run python -m evals approve rubric-v1 --by Mani` (all, or `--cases ...`). Until then
   the gate cannot pass, by design.
3. **GitHub secrets** for the nightly real model run: `ANTHROPIC_API_KEY` (required),
   `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` (optional). Without the key the nightly
   job warns and skips the real model evals.

## Known gaps (carried)

- No rate limiting or spam protection on the apply page (phase 10, before anything is public).
- Retention enforcement job (phase 9); `closed_at` is stored.
- Candidate self service deletion link (phase 10); erasure is a recruiter action now.
- Langfuse JP region: job ads only in traces; applicant data never traced (tested).
