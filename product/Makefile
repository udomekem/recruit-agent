# Thin wrappers over Python entry points. Run from product/ inside Ubuntu (WSL2).
UV ?= uv

.PHONY: help up down services logs migrate test lint typecheck eval eval-full eval-rubric eval-cv eval-selftest smoke ci

help:
	@grep -E '^[a-z-]+:' Makefile | cut -d: -f1

up:            ## start API, worker, Postgres, Redis
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

smoke:         ## one real LLM call (needs ANTHROPIC_API_KEY); prints the trace URL
	$(UV) run python -m app.cli smoke

ci: lint test eval eval-selftest

eval-rubric:   ## rubric builder with the real model (kie.ai DeepSeek, about $0.05)
	$(UV) run python -m evals run --suite rubric

eval-cv:       ## CV parser and redaction with the real model (kie.ai DeepSeek)
	$(UV) run python -m evals run --suite cv
