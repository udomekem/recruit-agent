# Engineering Standards

## Layout of `product/`

```
product/
├── app/
│   ├── api/            FastAPI routes
│   ├── domain/         states, transitions, rules (pure code, no I/O)
│   ├── agents/         one module per agent: prompt, schema, runner
│   ├── prompts/        versioned prompt files
│   ├── integrations/   anthropic, vapi, email, calendar, storage
│   ├── workers/        arq jobs
│   └── db/             models, Alembic migrations
├── dashboard/          Next.js recruiter UI
├── evals/
│   ├── datasets/       versioned JSONL, synthetic only
│   ├── runners/        one runner per agent
│   └── reports/        generated, gitignored except baselines
├── tests/              unit and integration tests
├── docker-compose.yml
├── Makefile
├── .env.example
└── README.md
```

## Commands (Makefile)

`make up`, `make test`, `make lint`, `make eval` (fast suite), `make eval-full`
(adds simulated calls), `make migrate`.

## Conventions
- Python 3.12, type hints everywhere, Pydantic v2, ruff, mypy.
- `domain/` has no network or database calls so it is trivially testable.
- Agents are functions: typed input in, typed output out, trace id passed through.
- One state machine module owns all transitions; nothing else writes status.
- Every outbound action goes through an `Outbox` with an idempotency key.
- Config via environment. Provider calls have timeouts and retries.
- Defaults are safe: sandbox providers, sending and calling disabled until a flag is set.
- Commit small, one slice per commit, message says what and why.
