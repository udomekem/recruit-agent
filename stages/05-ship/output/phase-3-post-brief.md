# Phase 3 Post Brief: The AI judges, code scores

Raw material only. The post is written and published through Mani's own process.
Numbers from the 2026-11-08 runs on synthetic CVs (`phase-3-eval-report.md`).

## One line hook candidates

1. My AI recruiter failed its own test because it did not know what day it was.
2. Same CV, different name, gender, age and suburb. My AI scored them exactly the same.
3. I let the AI judge CVs. I did not let it add up the score.

## The one number or surprise

- The first version passed 7 of 11 tests. It marked a candidate with 3 years and 2 months
  of experience as "partly" meeting a 3 year requirement, because it had no idea what
  "Present" meant. One line telling it today's date fixed it.
- Final run: 12 counterfactual pairs (name, gender, graduation year 20 years apart,
  suburb, reason for a career gap) scored 0.0 points apart over three runs.

## What I built (plain)

For each requirement in the job, the AI says met, partly met or not met, and quotes the
line in the CV that proves it. Code checks the quote is really there, then adds up the
score with weights the AI never sees, and suggests advance, maybe or reject. No right to
work in Australia means reject, whatever the CV. A recruiter still makes every decision.

## What broke or surprised me

- The AI did not know today's date, so it could not count years up to "Present".
- It gave partial credit for the wrong kind of job (a carpenter for "years supervising
  sites"). The rules now say only that kind of role counts.
- What looked like a successful attack (an 8 point lift) was really the AI being
  inconsistent: the attacked and clean CVs it read were identical. Fixing consistency fixed
  the "attack".
- My guard against protected wording let "close to retirement age" through, because it
  was built for job ads, not for comments about a person. Now there are two guards.
- Raising the AI's effort cut the biggest run to run swing from 10 points to 2.5.

## What the evals showed

| Check (synthetic, 3 runs) | Result |
|---------------------------|--------|
| 45 CVs: same recommendation as expected | 100% |
| Requirement judgements correct | 99.7% |
| Quotes really in the CV | 100% |
| Biggest score swing between runs | 2.5 points |
| Fairness pairs: score difference | 0.0 points |
| Hidden text and "note to the AI" attacks: score lift | 0.0, all 6 flagged |
| Cost per candidate (read + score) | about a quarter of a cent |

## What it does not do yet

No dashboard yet (phase 4); scores are an API. Labels were built by design, not by a panel
of recruiters. Synthetic data only: where real candidate data may be processed is still an
open decision. Text inside images is not checked.

## Visuals to capture

The ranked list; one evidence view with quotes; `formula.py`; a PDF with its white text
revealed; the eval history table (7, 10, 11 of 11). Synthetic CVs only.

## Try it

github.com/udomekem/recruit-agent: `cp .env.example .env`, `make local-env`, add a kie.ai
key, `make up`, follow `product/README.md`. `make eval` runs the answer rule tests with no
key.
