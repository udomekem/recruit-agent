# Phase 1 Post Brief: Turning a JD into a rubric (draft)

Raw material only. The post is written and published through Mani's own process.
Numbers below are from 2026-11-07 on draft labels; re-check them after the label review
and before posting.

## One line hook candidates

1. I gave my AI recruiting agent a job ad that said "suit someone under 30". Here is what it did.
2. My AI recruiter turns a job ad into a scoring rubric for 0.1 cents. The hard part was making it fair.
3. The model I trusted ran out of credit mid build. I swapped it out in an afternoon, and the tests told me if it still worked.

## The one number or surprise

- A full test of the rubric builder (15 ads, 3 runs each, 45 rubrics) cost about 5 cents
  on DeepSeek through kie.ai. One rubric costs about a tenth of a cent.
- The provider swap: the Anthropic account ran out of credit, so the agent moved to
  DeepSeek. Because the evals already existed, the switch was measured, not guessed.

## What I built (plain)

A recruiter pastes a job ad. The agent turns it into a rubric: must haves, nice to haves,
weights, and the exact line of the ad each one came from. The recruiter edits and approves
it; only then does the job open. Candidates apply on a page that tells them AI helps screen
but a person decides, and asks for consent. CVs are checked by their content, stored
encrypted, and can be deleted on request.

## What broke or surprised me

- The new model kept turning "Darwin, onsite" into a scoring criterion, quoting a line
  that was not in the ad. The quote check caught it. Fix: a new prompt version saying
  location and salary are screening questions, not criteria.
- My fairness filter first blocked "Single Touch Payroll" (it contains "single") and
  "working with young people". A fairness filter needs false positive tests too.
- The first real eval run hit "credit balance too low" on every call and scored it as 45
  agent failures. Now an outage stops the eval instead of faking a result.
- MinIO stopped publishing its Docker images; the storage moved to another build of the
  same server.
- kie.ai names the model with a dot, my price table with a dash: the first call cost $0.

## What the evals showed (2026-11-07, draft labels, worst of 3 runs)

| Check | Result |
|-------|--------|
| Requirements found | 98.6% |
| Requirements invented | 1.4% |
| Discriminatory criteria created | 0 |
| Discriminatory ads flagged | 9 of 9 |
| Planted instructions in ads obeyed | 0 |
| Cost per rubric | about $0.001 |

## What it does not do yet

No CV reading or scoring (phases 2 and 3). The apply page has no spam protection, so it is
not public. The notice wording has not had a lawyer's review. The eval labels were drafted
by AI and are awaiting human review.

## Visuals to capture

The age wording ad and its two flags; the 422 from the guard; the apply page; the eval
table; the Langfuse experiment (crop the project id). Synthetic data only.

## Try it

Repo is public: github.com/udomekem/recruit-agent. `cp .env.example .env`, add a kie.ai
key and MinIO settings, `make up`, follow `product/README.md`.
