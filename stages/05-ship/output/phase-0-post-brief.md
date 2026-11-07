# Phase 0 Post Brief: Before writing a single prompt

Raw material only. The post itself is written and published through Mani's own process.

## One line hook candidates

1. I am building an AI that screens job applicants. I spent the first phase writing zero prompts.
2. The most important file in my AI recruiting agent has no AI in it.
3. My first real call to the model failed. That was the system working.

## The one number or surprise

The first real model call came back with a 400 error: the API rejected a schema rule
(`minimum` on a number). The client failed fast, did not retry or guess, and the fix
became a permanent test. Second surprise: tracing was quietly counting every call's cost
twice, caught by reading the trace back.

## What I built (plain)

The skeleton of an agent that will screen CVs, phone shortlisted candidates and book
interviews. Before any AI does anything, there is a fixed map of every step a candidate
can take, a log of every move, and a rule that only a human recruiter can shortlist,
reject or advance someone.

## What broke or surprised me

- The first real API call: 400 on an unsupported schema keyword. Fixed by stripping those
  keywords from what the model sees while still enforcing them on the answer.
- Langfuse auto captured the SDK call as a second generation, doubling cost in the
  dashboard.
- A clean clone check: copying the example config switched tracing on with blank keys.

## What the evals showed (2026-11-07, commit ac091bd)

| Check | Result |
|-------|--------|
| Illegal moves refused | 567 of 567 |
| Duplicate jobs moving a candidate twice | 0 |
| Planted bug caught by the eval gate | yes, 3 broken cases named |
| Tests | 54 passing, in CI on every push |
| One real model call | $0.000064, 1.2 s, fully traced |

## What it does not do yet

No CV reading, no scoring, no emails, no calls. Every step is a stub. That is phases 1 to 8.

## Visuals to capture

Transition table in the editor; terminal showing SCORED then 409 on a skipped step; audit
trail JSON; `make eval-selftest` output; Langfuse trace page (crop the project id);
green GitHub Actions run. Synthetic candidates only; no keys or tokens on screen.

## Try it

Not public yet. Repo goes public after phase 0 ships (per project config); then: clone,
`cp .env.example .env`, `make up`, follow `product/README.md`.
