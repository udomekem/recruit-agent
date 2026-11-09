# Thin wrappers over Python entry points. Run from product/ inside Ubuntu (WSL2).
UV ?= uv

.PHONY: help local-env up down services logs migrate test lint typecheck eval eval-full eval-rubric eval-cv eval-score eval-selftest smoke ci demo-seed demo-seed-offline dashboard-check e2e

help:
	@grep -E '^[a-z-]+:' Makefile | cut -d: -f1

local-env:     ## once, after cp .env.example .env: generate local-only secrets (token, MinIO)
	python3 scripts/init_local_env.py

up:            ## start API, worker, Postgres, Redis, MinIO
	docker compose up -d --build --wait

down:
	docker compose down

services:      ## start only Postgres and Redis (for tests)
	docker compose up -d --wait postgres redis

logs:
	docker compose logs -f api worker

migrate:
	$(UV) run alembic upgrade head

test:          ## needs Postgres and Redis (make services)
	$(UV) run pytest -q

lint:
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(UV) run mypy app evals

typecheck:
	$(UV) run mypy app evals

eval:          ## fast suite (every PR)
	$(UV) run python -m evals run --suite fast

eval-full:     ## full suite (nightly)
	$(UV) run python -m evals run --suite full

eval-selftest: ## passes only if the planted regression makes the gate fail
	$(UV) run python -m evals run --suite selftest
	$(UV) run python -m evals run --suite selftest-score

smoke:         ## one real LLM call (needs ANTHROPIC_API_KEY); prints the trace URL
	$(UV) run python -m app.cli smoke

ci: lint test eval eval-selftest

eval-rubric:   ## rubric builder with the real model (kie.ai DeepSeek, about $0.05)
	$(UV) run python -m evals run --suite rubric

eval-cv:       ## CV parser and redaction with the real model (kie.ai DeepSeek)
	$(UV) run python -m evals run --suite cv

eval-score:    ## CV scorer, fairness, injection with the real model (kie.ai DeepSeek, about $$0.40)
	$(UV) run python -m evals run --suite score

demo-seed-offline: ## demo jobs and 95 synthetic candidates, no model (needs make up)
	$(UV) run python -m scripts.demo_seed --offline

demo-seed:     ## demo jobs through the API with the real model (about $$0.15; needs make up)
	$(UV) run python -m scripts.demo_seed --real

dashboard-check: ## dashboard type check, unit tests, secret check (in Docker)
	docker run --rm -u "$$(id -u):$$(id -g)" -e HOME=/tmp -e NEXT_TELEMETRY_DISABLED=1 -v "$$PWD/dashboard":/app -w /app node:22-alpine sh -c "npm ci --no-audit --no-fund >/dev/null && npx next typegen >/dev/null && npx tsc --noEmit && npx vitest run && node scripts/check-public-env.mjs"

e2e:           ## dashboard browser tests in the Playwright image (needs make up)
	bash scripts/e2e.sh
