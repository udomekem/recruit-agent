# product/

The Recruit Agent application: jobs and AI drafted rubrics (phase 1), an apply page with
encrypted CV storage, CV parsing with redaction (phase 2), scoring with evidence, fairness
and injection checks (phase 3), the recruiter dashboard (phase 4, `dashboard/`), and
rejection emails drafted by AI, checked by code and sent with one click (phase 5), and the
Hira dashboard design with a connected inbox whose emailed CVs are matched to jobs
(phase 5B). Calls are still stubs.
Run everything from Ubuntu (WSL2) in this folder.
Setup guide: `../stages/03-build/references/dev-environment-setup.md`.

## First run

```bash
cp .env.example .env
make local-env              # generates local-only secrets: recruiter token, dashboard password, MinIO login and key
# add KIE_API_KEY (model calls) and, optionally, LANGFUSE_* keys to .env
uv sync
make up                     # API, worker, dashboard, Postgres, Redis, MinIO, Mailpit (migrations run on API start)
curl localhost:8000/health  # {"status":"ok","database":"ok","redis":"ok"}
make demo-seed-offline      # demo jobs and synthetic candidates, no model needed
```

Then open http://localhost:3000 and sign in with `DASHBOARD_PASSWORD` from `.env`. Keys on a
candidate: `s` shortlist, `r` reject, `Enter` confirm, `j` / `k` next and previous.

Rejection emails (phase 5): after a reject the worker drafts the email (the writer needs
`KIE_API_KEY`; without it the plain template is used). On the candidate page read it,
`e` to edit, `Enter` to send. Every draft and every edit passes eight hard rule checks
first. Sent emails land in the local test inbox at http://localhost:8025 (Mailpit):
nothing leaves the machine. The review queue lists drafts to send and emails not
delivered.

Connected inbox (phase 5B): on the Inbox page, "Connect the test inbox" reads the local
Mailpit inbox (emails tagged `Applications` stand in for a Gmail label). `make demo-inbox`
emails three synthetic CVs: one with a job code in the subject, one to the job's plus
address, one with no job. Press "Check now". Code rules file the first two; the job
matcher (AI, redacted CV only) files the third only when one job clearly fits, otherwise
it waits under "Needs a job" for you to pick. Each new candidate gets an acknowledgement
email with the collection notice (in Mailpit). Gmail (read only, one label) needs a
Google Cloud OAuth client: set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env`
and add `http://localhost:3000/inbox/callback` as its redirect address.

Tests and the fast evals need no API key: `make services && make test && make eval`.

## Commands

| Command | What it does |
|---------|--------------|
| `make up` / `make down` | Start or stop the whole stack |
| `make services` | Start only Postgres and Redis (needed by `make test`) |
| `make test` | All tests (state machine, journeys, LLM client, evals, config) |
| `make lint` | ruff, format check, mypy strict |
| `make eval` | Fast eval suite; exit 0 pass, 1 a bar failed, 2 harness error |
| `make eval-selftest` | Planted regressions must fail the gate (proves the gate works), including a scorer that lifts injected CVs |
| `make eval-rubric` / `make eval-cv` / `make eval-score` | Real model evals: rubric builder, CV parser, and the CV scorer with fairness and injection pairs (about $0.40) |
| `make eval-reject` | Rejection writer (DeepSeek) graded by a GPT judge, judge calibration, fairness and injection (about $0.40) |
| `make eval-match` | Job matcher evals: code rules, clear and unclear CVs, fairness pairs, attacked CVs (real model, about $0.06, 10 minutes) |
| `make demo-inbox` | Email three synthetic CVs to the local test inbox (Mailpit) |
| `make smoke` | One real model call (kie.ai DeepSeek by default) through the LLM client; prints the Langfuse trace URL |
| `make migrate` | Apply database migrations |
| `make demo-seed-offline` / `make demo-seed` | Demo jobs and candidates: no model, or through the API with the real model (about $0.15) |
| `make dashboard-check` | Dashboard type check, unit tests and secret check (in Docker) |
| `make e2e` | Dashboard browser tests in the Playwright image (needs `make up`) |

## Try the phase 0 pipeline

```bash
TOKEN=$(grep '^RECRUITER_TOKEN=' .env | cut -d= -f2- | tr -d '"')
ID=$(curl -s -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"display_label":"Test candidate 1"}' localhost:8000/candidates | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
curl -s -H "Authorization: Bearer $TOKEN" localhost:8000/candidates/$ID   # SCORED, waiting for you
curl -s -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"reason":"strong match"}' localhost:8000/candidates/$ID/shortlist
```

Recruiter actions: `shortlist`, `reject`, `send-rejection`, `advance`, `resolve-retry`,
`withdraw`. Each needs a `reason`. The worker never takes these actions itself.

## Layout

| Path | Holds |
|------|-------|
| `app/domain/states.py` | States and the transition table (the only source of legal moves) |
| `app/workflow/machine.py` | The only writer of candidate state: checks, audit row, idempotency |
| `app/workflow/pipeline.py` | Runs system steps with retries and timeouts; failures go to NEEDS_REVIEW |
| `app/workflow/steps.py` | Phase 0 stub steps (canned results) |
| `app/llm/` | The LLM client every agent will use, providers, versioned prompts |
| `app/prompts/` | Prompt files, one per version |
| `app/observability/tracing.py` | Langfuse, no-op and recording tracers |
| `app/api/main.py` | Recruiter API |
| `app/workers/worker.py` | arq worker |
| `app/rejection/` | Phase 5: reason sources, hard rule checks, the draft step, edits, the outbox and delivery |
| `app/inbox/` | Phase 5B: mailbox providers (Mailpit, Gmail, fake), code rules, polling and ingest, job matching, Gmail sign in, token encryption |
| `app/agents/job_matcher.py` | The job matcher agent (prompt `job-matcher` v2) |
| `app/integrations/email.py` | Email providers: log (tests), Mailpit (local), Resend (real, switched off) |
| `evals/` | Harness, suites (thresholds), datasets (synthetic only), reports |
| `migrations/` | Alembic |

## Safety defaults

`EMAIL_SENDING_ENABLED`, `PHONE_CALLS_ENABLED` and `CALENDAR_BOOKING_ENABLED` default to
false. Rejection emails go only to the local Mailpit inbox (`EMAIL_PROVIDER=mailpit`, set
by Docker Compose) or nowhere (`log`, the default). Real sending (`resend`) needs the
switch on, a key and a sending domain. No call or calendar code exists yet. CI uses a fake
model and no tracer, so it needs no secrets. `.env` is gitignored and CI fails if one is
tracked.
