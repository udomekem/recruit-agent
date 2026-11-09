# Phase 4 Post Brief: the demo video

Raw material only. The post is written and published through Mani's own process.
Numbers from the 2026-11-08 test runs on synthetic candidates (`phase-4-eval-report.md`).

## One line hook candidates

1. My AI recruiter ranks 50 candidates. A human decides all 50 in under half a minute.
2. You can disagree with my AI. You just have to say why.
3. The recruiter never sees a candidate's name until they shortlist them.

## The one number or surprise

- 50 candidates decided with 100 key presses (two each) in 24 seconds, in an automated
  browser test.
- Building the demo data exposed a privacy filter bug from two phases ago: it treated
  "TAFE NSW, 2012" as a home address and deleted people's qualifications.

## What I built (plain)

A dashboard where a recruiter works through a ranked list. Each candidate shows the AI's
judgement for every requirement next to the CV, with the proving line highlighted. Names
and contact details stay hidden until shortlist. One key to shortlist or reject, Enter to
confirm, the next candidate opens. Going against the AI needs a written reason, and every
decision is logged against the AI's recommendation: the agreement rate.

## What broke or surprised me

- The privacy filter from phase 2 removed "TAFE NSW, 2012" because a year looks like a
  postcode. Found only because the demo data could not find quotes it expected.
- The contact view was logged after the page read the history, so the first view never
  showed. Small, but it is the Privacy Act trail.
- My own safety rails stopped me reading the dashboard password, even for a local test.
  The browser tests now get it inside their container and never print it.

## What the evals showed

| Check (synthetic, automated browser tests) | Result |
|--------------------------------------------|--------|
| Decisions for 50 candidates | 100 key presses, 24 seconds |
| Names, emails or phones on screen before shortlist | 0 |
| API key reaching the browser | 0 |
| Overrides with no real reason accepted | 0 |
| Serious accessibility issues | 0 |

## What it does not do yet

One recruiter login. Runs locally (built to move to Vercel later). Rejection emails are
phase 5; calls are phases 6 to 8. Synthetic data only.

## Visuals to capture

The ranked list; a quote lighting up in the CV; "Applicant 5" with `[NAME]` in the CV; the
override box; the drill at speed; the agreement rate. Never the sign in password or `.env`.

## Try it

github.com/udomekem/recruit-agent: `cp .env.example .env`, `make local-env`, `make up`,
`make demo-seed-offline`, open http://localhost:3000 (password in `.env`).
