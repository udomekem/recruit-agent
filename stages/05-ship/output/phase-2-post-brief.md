# Phase 2 Post Brief: Why the scorer never sees your name

Raw material only. The post is written and published through Mani's own process.
Numbers from 2026-11-07 and 2026-11-08 runs on synthetic CVs.

## One line hook candidates

1. My AI recruiter reads your CV without ever seeing your name.
2. I tested whether my AI would notice "proud mum of three" on a CV. It did, two times out of three. That was not good enough.
3. Before an AI scores a CV, it should forget who wrote it.

## The one number or surprise

- 30 test CVs, 3 runs each: zero names, contacts, ages, nationalities, religions or
  family details left in the text the scorer reads, and 98.5% of CV fields extracted
  correctly. The whole test cost about 6 cents.
- The model alone caught "Proud mum of three" in 2 of 3 runs. Two out of three is not a
  privacy control, so code now catches common family phrasing every time and the model is
  the second line.

## What I built (plain)

When a CV arrives, code removes everything the system already knows about the person (name,
email, phone from the application form) plus anything shaped like an address, phone number,
link or date of birth, and labelled lines like "Religion:". Only then does an AI read it, to
pull out roles, dates, skills and qualifications, and to point out anything personal the code
missed. The scorer in the next phase will only ever read the cleaned copy.

## What broke or surprised me

- The AI skipped whole fields (skills came back empty) until every field was marked
  required.
- It left every graduation year blank until the instructions said a year on the same line
  is the completion year.
- Some runs returned a completely empty profile, which passed every check because there was
  nothing to check. Empty is now a failure.
- My own test CVs split email addresses across lines, which would have made the leak test
  unfair. Real CVs wrap between words; fixed.
- The build filled my laptop's disk to zero and Linux started throwing input/output errors.
  Recovered without losing work; now I check free space before every rebuild.
- A fresh copy of the repo could not start, because it needed storage passwords nobody
  would know. One command now generates them.

## What the evals showed

| Check | Result |
|-------|--------|
| Personal details left in the text the scorer reads | 0 |
| Applicant's own details sent to the AI | 0 |
| CV fields extracted correctly | 98.5% |
| Job relevant words wrongly removed | 0% |
| Hidden instructions in a CV that changed the result | 0 |
| Cost per CV | about $0.0007 |

## What it does not do yet

No scoring yet (phase 3). Scanned CVs go to a person. Dates are kept on purpose because
experience needs them; whether they leak age is what the phase 3 fairness tests measure.
Synthetic data only: where real candidate data may be processed is still an open decision.

## Visuals to capture

Original CV next to the redacted text; the test showing what the model receives; the eval
table; "Proud mum of three" becoming `[PROTECTED]`. Synthetic CVs only.

## Try it

github.com/udomekem/recruit-agent: `cp .env.example .env`, `make local-env`, add a kie.ai
key, `make up`, follow `product/README.md`.
