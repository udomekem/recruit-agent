# product/

The Recruit Agent application. Phase 0: foundations and the eval harness, with stub
steps instead of real agents. Run everything from Ubuntu (WSL2) in this folder.
Setup guide: `../stages/03-build/references/dev-environment-setup.md`.

## First run

```bash
cp .env.example .env        # then fill in keys (ANTHROPIC_API_KEY, LANGFUSE_*, RECRUITER_TOKEN)
uv sync
make up                     # API, worker, Postgres, Redis (migrations run on API start)
curl localhost:8000/health  # {"status":"ok","database":"ok","redis":"ok"}
```

## Commands

| Command | What it does |
|---------|--------------|
| `make up` / `make down` | Start or stop the whole stack |
| `make services` | Start only Postgres and Redis (needed by `make test`) |
| `make test` | All tests (state machine, journeys, LLM client, evals, config) |
| `make lint` | ruff, format check, mypy strict |
| `make eval` | Fast eval suite; exit 0 pass, 1 a bar failed, 2 harness error |
| `make eval-selftest` | Planted regression must fail the gate (proves the gate works) |
| `make smoke` | One real Haiku call through the LLM client; prints the Langfuse trace URL |
| `make migrate` | Apply database migrations |

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
| `evals/` | Harness, suites (thresholds), datasets (synthetic only), reports |
| `migrations/` | Alembic |

## Safety defaults

No email, call, or calendar code exists yet, and `EMAIL_SENDING_ENABLED`,
`PHONE_CALLS_ENABLED` and `CALENDAR_BOOKING_ENABLED` default to false. CI uses a fake
model and no tracer, so it needs no secrets. `.env` is gitignored and CI fails if one is
tracked.
