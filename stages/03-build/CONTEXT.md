# Stage 03: Build

Implement the approved design in `product/`, with tests, in small verified steps.

## Inputs

| Source | File/Location | Section/Scope | Why |
|--------|--------------|---------------|-----|
| Previous stage | `../02-design/output/phase-N-design.md` | Full file | What to build |
| Shared | `../../shared/project-config.md` | Decisions and accounts status | Stack and keys available |
| Reference | `references/engineering-standards.md` | Full file | Layout, commands, conventions |
| Code | `../../product/` | Only files this phase touches | Existing code |

## Process

1. Read the design and the standards. List the files to create or change.
2. Work in vertical slices: schema and migration, logic, tests, wiring. Run tests
   after each slice.
3. Write unit tests for every rule in code (knockouts, state transitions,
   idempotency, redaction). LLM calls are mocked in unit tests.
4. Add tracing and an audit log entry for every transition and side effect.
5. Keep secrets in `product/.env`; update `product/.env.example`.
6. **[Checkpoint]** Demo the slice to the user (run it, show output) before moving
   to the next major slice when it changes a recruiter or candidate experience.
7. Run the audit. Write the build log.

## Checkpoints

| After Step | Agent Presents | Human Decides |
|------------|---------------|---------------|
| 6 | Running slice and what it does | Keep going, or change direction |

## Audit

| Check | Pass Condition |
|-------|---------------|
| Tests | `make test` passes |
| Lint and types | `make lint` passes |
| Design match | Every entity, transition, and side effect in the design exists |
| Secrets | No keys, `.env`, or real personal data in git |
| Safety | No real call or email is possible from tests or default config |
| Docs | `product/README.md` explains how to run this phase's features |

## Outputs

| Artifact | Location | Format |
|----------|----------|--------|
| Code and tests | `../../product/` | Per engineering standards |
| Build log | `output/phase-N-build-log.md` | Markdown: files changed, how to run, deviations from design with reasons, known gaps |
