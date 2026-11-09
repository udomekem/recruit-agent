#!/usr/bin/env bash
# Dashboard end to end tests (phase 4 design section 9). Needs `make up`.
# Seeds fresh demo jobs offline (no model), then runs Playwright in its official Docker
# image (design Q1: nothing installed on the host). The dashboard password and the API
# token are passed from .env into the test container only; they are never printed.
set -euo pipefail
cd "$(dirname "$0")/.."

PLAYWRIGHT_IMAGE="mcr.microsoft.com/playwright:v1.65.0-noble"

uv run python -m scripts.demo_seed --offline

set -a
# shellcheck disable=SC1091
. ./.env
set +a

docker run --rm --network host --ipc=host \
  -u "$(id -u):$(id -g)" -e HOME=/tmp \
  -e DASHBOARD_PASSWORD -e RECRUITER_TOKEN \
  -e DASHBOARD_URL="${DASHBOARD_URL:-http://localhost:3000}" \
  -v "$PWD":/work -w /work/dashboard \
  "$PLAYWRIGHT_IMAGE" npx playwright test "$@"
