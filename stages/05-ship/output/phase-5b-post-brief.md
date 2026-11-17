# Phase 5B Post Brief: My recruiting agent reads its own inbox

Raw material only. The post is written and published through Mani's own process.
Numbers come from the 2026-11-17 eval runs on synthetic CVs (`phase-5b-eval-report.md`,
and `phase-5b-readiness.md` for the parser fix).

## One line hook candidates

1. My recruiting agent now reads its own inbox, and when it isn't sure which job a CV is for, it asks me.
2. Most emailed CVs never needed AI. A job code in the subject line did the work.
3. My first job matcher judged the applicant instead of the job, and half the good CVs got stuck.

## The one number or surprise

- 0 CVs filed under the wrong job, over 3 runs of 53 synthetic CVs (clear fits, weak
  ones, no fit at all, and pairs of open jobs of the same kind).
- The first matcher filed only 48% of the clear CVs. It was scoring how strong the person
  looked, when all I asked was which job the CV was for. Rewriting that one instruction
  took it to 96%.

## What I built (plain)

A recruiter connects an inbox (Gmail, read only, one label). Every CV that lands there is
read once, stripped of personal details and matched to a job on the job board. Plain
code tries first: a job code in the subject, the job's own email address, or a Seek or
Indeed subject line. If the email gives no job, an AI reads the redacted CV and files it
only when one job clearly fits. Anything else waits in "Needs a job" for the recruiter
to pick. Each new candidate gets an email confirming their CV arrived. I also moved the
whole dashboard to a new design (Hira).

## What broke or surprised me

- The matcher's first prompt told it a CV with "several must haves missing" was a 0.6 to
  0.8 fit. So it rated people instead of jobs. Decent CVs landed under the line, and 3
  fairness pairs (the same CV with a different name or suburb) ended up in different
  places. The fix was to say fit means the field and kind of role, nothing else. How
  strong the person is gets scored later, by a different step.
- Two workers could download the same email at the same moment. Now each email is
  claimed before it's fetched, and a test runs two pollers at once to prove it.
- The candidate list drew every person at once. After many test runs (1,807 synthetic
  candidates) the page took 9.3 seconds and broke a test. It now shows 100 at a time and
  loads in 2.7 seconds.
- The best one came from recording the demo. All three demo CVs went to review. The CV
  reader from two phases ago required an employer and a university, so for "Bachelor of
  Nursing" with no university the model wrote "Not stated", my own check rejected it as
  made up, three times, and gave up. Real CVs leave those out all the time. My test data
  always had both, so no eval ever caught it. Both fields are now optional, and the
  parser evals still pass (field accuracy 99.6%).

## What the evals showed

| Check (2026-11-17, synthetic, 3 runs) | Result | Bar |
|---------------------------------------|--------|-----|
| Code rules (job code, plus address, Seek, Indeed), 16 cases | 100% | 100% |
| Clear CVs filed under the right job | 96.3% | at least 95% |
| CVs filed under the wrong job | 0 | 0 |
| Fairness pairs filed differently (name, gender, age, suburb), 12 pairs | 0 | 0 |
| Attacked CVs moved to another job, 6 cases | 0 | 0 |
| AI cost per email | $0.00037 | under $0.001 |

## What it does not do yet

Live Gmail is built and tested against recorded responses, but it isn't connected to a
real account yet (that needs a Google Cloud app in testing mode). Microsoft 365 says
"coming soon". Gmail is checked every 2 minutes rather than pushed. A PDF that isn't a CV
still gets read and scored instead of thrown away. It all runs locally on synthetic data.

## Visuals to capture

The Inbox page with the test inbox connected; the three demo emails in Mailpit; the
recent emails table with redacted subjects and how each was matched (job code, plus
address, "Needs a job"); picking a job; the acknowledgement email; the eval table. Never
a real inbox, the password, `.env`, or a Google consent screen showing a real address.

## Try it

github.com/udomekem/recruit-agent: `cp .env.example .env`, `make local-env`, `make up`,
`make demo-seed-offline`, open http://localhost:3000, connect the test inbox, then run
`make demo-inbox` and press "Check now". The third email needs a kie.ai key. This works
once the phase 5 and 5B commits are pushed, which hasn't happened yet.
