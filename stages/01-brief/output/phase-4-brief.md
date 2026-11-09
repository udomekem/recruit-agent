# Phase 4 Brief: Recruiter dashboard

Approved by Mani 2026-11-08 with the five defaults (Q1 to Q5), built locally. Source: master-plan section 8 (phase 4 row),
section 7.2 (recruiter agreement rate), section 1 rules 3, 4, 6, 8, 12, decisions
(Next.js dashboard, `shared/project-config.md`), and the phase 3 known gap (rescoring when
a new rubric is approved).

## Goal
A recruiter signs in to a web dashboard, works through a job's ranked candidates with the
evidence beside each one, and shortlists or rejects each in a keystroke or two; every
decision that goes against the agent's recommendation is logged with a reason, and the
dashboard shows the agreement rate.

## In scope
- **Next.js dashboard** (TypeScript), its own container in Docker Compose, built and run
  locally (decided by Mani 2026-11-08). Built Vercel ready: standard Next.js build, all
  settings from environment variables, no local file writes, so phase 10 can deploy it to
  Vercel unchanged once the backend is hosted. Pages: sign in,
  jobs list, job page (ranked candidates), candidate page (evidence), review queue
  (NEEDS_REVIEW).
- **Sign in** (Q1): one recruiter login for now. The dashboard's server holds the API
  token; the browser only gets a session cookie, never the token.
- **Job page**: candidates ranked by score with band, flags, knockouts and state; filter by
  band, flag and state; the agreement rate for the job.
- **Candidate page**: each criterion with verdict, reason and the CV quote highlighted in
  the redacted CV text; screening answers with their rule outcome; reasons and flags
  (injection and hidden text shown first); the audit timeline; rubric and prompt versions.
- **Review flow** for speed: open the next undecided candidate; keyboard shortcuts for
  shortlist, reject, next and previous; the decision box pre-filled with the
  recommendation.
- **Decisions and overrides**: shortlist and reject call the existing recruiter API. A
  decision is an override when it goes against the band (shortlist a reject, reject an
  advance; maybe is never an override). Overrides need a reason; every decision stores the
  recommendation it was made against, for the agreement rate.
- **Blind review** (Q2): name and contact details hidden until the candidate is
  shortlisted.
- **Rescore** (phase 3 gap): when a newer rubric version is approved, the recruiter can
  rescore a job's scored candidates. New score rows, old ones kept, no state change.
- **NEEDS_REVIEW queue**: the reason, and the existing resolve actions (retry, reject).
- **Demo data** (Q4): a command that seeds the three phase 3 jobs and the 45 scoring CVs
  through the real pipeline.

## Out of scope (later phase)
- Rejection email drafting and sending (phase 5); a rejected candidate still goes through
  the stub draft step
- Calls, transcripts, booking (phases 6 to 8)
- Multiple recruiter accounts, roles, SSO (phase 10 or later)
- Job creation and rubric editing screens: the API stays the way to do these in phase 4
  (Q5)
- Bulk decisions (Q3)
- Hosting (phase 10). Considered and set aside 2026-11-08: the dashboard on Vercel now.
  It would need the backend hosted too (Vercel cannot reach the laptop or run the worker),
  which brings phase 10 hosting, a public login and spend caps forward

## Done criteria
- [ ] `make up` starts the dashboard; sign in works; no API token appears in the browser (a test inspects the page, its scripts and its requests).
- [ ] The job page lists a job's candidates in score order with band, flags, knockouts and state; filters work.
- [ ] The candidate page shows every criterion's verdict, reason and quote, and highlights each quote in the redacted CV text.
- [ ] Shortlist and reject work from the keyboard; the next undecided candidate opens.
- [ ] An override without a reason is refused by the API (422) and by the form.
- [ ] Every decision stores the recommendation it was made against; the agreement rate is correct on a fixed table of cases.
- [ ] Blind review: name, email and phone are not in the page (DOM) before shortlisting.
- [ ] A stale page (the candidate moved meanwhile) gets a clear conflict message, not a double decision.
- [ ] Rescore after a new rubric version writes new score rows and changes no state.
- [ ] An end to end test reviews 50 seeded candidates through the dashboard in at most 2 actions each.
- [ ] Accessibility check on every page: no serious or critical issues.
- [ ] Vercel ready: `next build` passes with only environment variables for settings; no secret is read in browser code.

## Eval bars

No new model agent in this phase; the bars are product checks, run in CI.

| Check | Dataset | Metric | Threshold |
|-------|---------|--------|-----------|
| Review speed | 50 seeded candidates | actions per decision in the end to end test | at most 2 (new) |
| Agreement rate | table of about 15 recommendation and decision pairs | computed rate and override flag match | 100% (new) |
| Override reason | override attempts without a reason | refused | 100% (new) |
| Blind review | candidate pages before shortlist | name, email or phone in the DOM | 0 (new) |
| Token exposure | every page, script and request | API token present | 0 (new) |
| Accessibility | all pages (axe) | serious or critical issues | 0 (new) |
| Speed | job page with 200 candidates, local | API response, 95th percentile | under 300 ms (new) |
| Phase 3 scorer | `score-v1`, `fair-v1`, `inject-v1` | all phase 3 bars | still pass (rescore uses the same scorer) |

## Production rules exercised

| Rule | How phase 4 shows it |
|------|----------------------|
| 3 | Every shortlist and reject is a recruiter keystroke; the dashboard has no bulk action |
| 4 | The quote is highlighted in the CV text next to every judgement |
| 6 | Blind review hides the name until shortlist |
| 8 | Decisions carry the expected version; a stale page cannot decide twice |
| 12 | The audit timeline is on the candidate page; overrides keep their reason |
| 5, 7.2 | The agreement rate starts being measured (online evals in phase 9) |

## Needs before starting
- Nothing new from accounts. Node runs inside Docker (no Node install on Windows).
- Disk: the dashboard image adds about 1 GB; C: has about 20 GB free.
- Seeding the demo data spends about $0.12 on kie.ai.

## Risks

| Risk | Fallback |
|------|----------|
| A second language and toolchain (TypeScript, Node) slows the phase | Keep the dashboard thin: it reads and calls the existing API; no business rules in the browser |
| The token leaks into the browser | Server side calls only; a test fails the build if the token shows up |
| Recruiters rubber stamp the recommendation | Overrides are cheap (one key and a reason); the agreement rate is shown, and in phase 9 a sample of agreements is re checked |
| Blind review hides something the recruiter needs | Contact details are never needed to judge fit; they appear on shortlist |
| End to end tests are flaky | Seeded data, no model calls in the test (scores loaded from fixtures) |

## Open questions (checkpoint)

| # | Question | Default if no answer |
|---|----------|---------------------|
| Q1 | Sign in | One recruiter account: a password set in `.env`, an httpOnly session cookie; the dashboard server adds the API token. Proper accounts later |
| Q2 | Blind review | On by default: name and contact hidden until shortlist (the candidate shows as "Candidate 7") |
| Q3 | Bulk actions | None in phase 4. Speed comes from the keyboard flow; bulk reject of the reject band can be considered after the agreement rate is known |
| Q4 | Demo data | Seed the three phase 3 jobs and 45 CVs through the real pipeline (about $0.12), plus a no model option that loads stored scores for tests |
| Q5 | Job and rubric screens | Not in phase 4: jobs and rubrics stay API calls; the dashboard is for reviewing candidates |
