#!/usr/bin/env bash
# Dashboard end to end tests (phase 4 design section 9). Needs `make up`.
# Seeds fresh demo jobs offline (no model), then runs Playwright in its official Docker
# image (design Q1: nothing installed on the host). The dashboard password and the API
# token are passed from .env into the test container only; they are never printed.
set -euo pipefail
cd "$(dirname "$0")/.."

PLAYWRIGHT_IMAGE="mcr.microsoft.com/playwright:v1.65.0-noble"

uv run python -m scripts.demo_seed --offline

# Read only the two values needed. `.env` is not a shell script (found in CI: a comment
# with brackets broke `source .env`), so never source it.
env_value() {
  grep -E "^$1=" .env | tail -1 | cut -d= -f2- | sed -E 's/[[:space:]]+#.*$//; s/^"(.*)"$/\1/; s/^'"'"'(.*)'"'"'$/\1/'
}
DASHBOARD_PASSWORD="$(env_value DASHBOARD_PASSWORD)"
RECRUITER_TOKEN="$(env_value RECRUITER_TOKEN)"
export DASHBOARD_PASSWORD RECRUITER_TOKEN

docker run --rm --network host --ipc=host \
  -u "$(id -u):$(id -g)" -e HOME=/tmp \
  -e DASHBOARD_PASSWORD -e RECRUITER_TOKEN \
  -e DASHBOARD_URL="${DASHBOARD_URL:-http://localhost:3000}" \
  -v "$PWD":/work -w /work/dashboard \
  "$PLAYWRIGHT_IMAGE" npx playwright test "$@"
