# Phase 5B Build Log: Hira dashboard + connected inbox

Inputs: `phase-5b-brief.md`, `phase-5b-design.md`, `phase-5b-ui-design.html` (all
approved 2026-11-12). Brief Q1: the redesign first, then the inbox.

## Part 1: dashboard redesign (2026-11-12, uncommitted)

| Area | Files |
|------|-------|
| Hira tokens, fonts (DM Sans, Manrope), light and dark from the computer setting, list and review as separate screens under 680 px, list scrolls on its own on desktop | `dashboard/app/globals.css` |
| Header with the hira mark, company, tabs Candidates, Jobs, Inbox, To do | `dashboard/app/(app)/layout.tsx`, `nav.tsx`, `dashboard/app/brand.tsx` |
| Candidates workbench: heading and counts, status tabs, job, recommendation and flag filters, number search, ranked queue, review panel with Requirements (evidence), CV (quotes highlighted), Rejection email, Activity; decision bar (s, r, Enter, Esc, j, k as before) | `dashboard/app/(app)/workbench.tsx`, `candidates/[id]/review-tabs.tsx`, `review-panel.tsx`, `rejection-panel.tsx`, `dashboard/lib/workbench.ts`, `filter/page.tsx` |
| Routes: `/` every job, `/jobs/[id]` one job, `/candidates/[id]` one candidate open (list of their job by default); all the old links still work | `page.tsx` files |
| Jobs board, To do (old review queue, same actions), Inbox placeholder ("coming next in phase 5B"), sign in | `jobs/page.tsx`, `review/page.tsx`, `inbox/page.tsx`, `login/` |
| Removed, replaced by the tabs and the queue: `evidence.tsx`, `row-keys.tsx` | |

### Verified
- Type check, unit tests, secret check: pass.
- Browser tests 10 of 10 against the rebuilt stack: accessibility (now also the CV tab,
  jobs board and inbox), sign in and out, blind review, contact after shortlist, override
  reason, stale page conflict, reject, edit and send with one Mailpit email, 50 candidates
  in 100 key presses (29 s), token never in the browser.

### Found and fixed
1. **A list page logged a contact view on its own.** List pages show their first
   candidate; when that one was shortlisted, the page fetched the contact details and
   the access log recorded a view nobody made. Contact details now load only when the
   recruiter opens the candidate; the browser test checks a job page shows none.
2. **Tests passed too early.** The "Evidence" heading is already on a list page, so tests
   moved on before the click landed. They now wait for the candidate's address.
3. **Contrast**: faded counts and key hints failed axe; full colour now.

### Deviations and gaps
- No Notes tab yet (the design had one): notes need storage and an audit trail; later.
- No focus view toggle.
- The Candidates page over every job asks the API once per job; with the e2e seed's
  ~50 jobs and 1,100 candidates it loads in several seconds. An API endpoint for the
  cross job queue is planned with the inbox part.

## Part 2: connected inbox (2026-11-13 to 14, uncommitted)

| Area | Files |
|------|-------|
| Tables: mailboxes, mailbox events, OAuth states, inbox messages, inbox attachments, job matches; job codes (backfilled, DA-0042 style); outbox kind (acknowledgement) | `app/db/models.py`, `migrations/versions/0007_connected_inbox.py`, `app/workflow/jobs.py` |
| Providers behind one interface: Mailpit (local test inbox, a tag stands in for a label), Gmail (`gmail.readonly`, refresh token), fake (tests); only PDF and Word attachments are downloaded, bodies never read | `app/inbox/providers.py` |
| Code rules: job code, plus address, Seek and Indeed subjects (exactly one open job), closed jobs refused; sender kind; subject redaction; contact guess | `app/inbox/rules.py` |
| Poll (lease per mailbox, unique message key, daily and per poll limits, crashed messages picked up again) and process (claim, fetch, check CVs, duplicate window, store and create the candidate with T24 and the acknowledgement in one transaction) | `app/inbox/ingest.py`, `app/domain/states.py` (T24) |
| Job matcher agent (`job-matcher` v2, DeepSeek extraction tier, redacted CV only) and the matching step between PARSED and scoring; unsure goes to NEEDS_REVIEW "needs a job" | `app/agents/job_matcher.py`, `app/prompts/job-matcher/`, `app/inbox/match.py`, `app/workflow/pipeline.py` |
| Gmail connect: PKCE, one time state bound to the recruiter (10 minutes), exact scope check (a wider grant is revoked), encrypted token (Fernet, `INBOX_TOKEN_KEY` from `make local-env`), revoke on disconnect | `app/inbox/oauth.py`, `app/inbox/crypto.py`, `scripts/init_local_env.py` |
| Acknowledgement email with the collection notice, through the phase 5 outbox | `app/domain/notice.py`, `app/rejection/outbox.py` |
| API: inbox page data, connect Mailpit, Gmail start and callback, labels, label and pause, check now, disconnect, pick a job | `app/api/inbox_api.py` |
| Queue and cron: poll and message jobs, a poll every 2 minutes | `app/workflow/dispatch.py`, `app/workers/worker.py` |
| One call ranking for every job (the Candidates view timed out at ~55 jobs) | `app/api/scores_api.py` (`/queue`), `dashboard/lib/workbench.ts` |
| Dashboard: Inbox page (connect, label, pause, check now, disconnect, recent emails with redacted subjects, job picker for "needs a job"), Google callback route, job codes on the job board | `dashboard/app/(app)/inbox/`, `actions.ts`, `jobs/page.tsx`, `lib/api.ts` |
| Tests and evals | `tests/test_inbox.py` (25), `dashboard/e2e/inbox.spec.ts`, `evals/datasets/build_match_v1.py`, `evals/match_agents.py`, `evals/match_metrics.py`, `evals/suites.toml` (`match`, `match-rules` in fast), `make eval-match` |

### Verified
- Backend tests: 332 passed, 2 skipped (MinIO), before the final rerun; the inbox tests
  cover processing once (two pollers, the same message twice at once), no CV, the
  matcher sure and unsure, the recruiter's pick and a stale pick, duplicates, revoked
  access, label rules, disconnect deleting and revoking the token, the Gmail sign in
  checks (foreign, reused and wider grants refused), and the real Mailpit container.
- Browser test: connect the test inbox, email a CV with a job code through Mailpit, see
  it added under that job; the sender's name and address never appear.
- `/queue` with ~60 jobs and ~1,300 candidates: about 2 s.

### Real model evals (`make eval-match`, kie.ai DeepSeek, 2026-11-14)

| Bar | Threshold | Run 1 (matcher v1) | Run 2 (matcher v2) |
|-----|-----------|--------------------|--------------------|
| Code rules (16 cases) | 100% | 100% | 100% |
| Clear CVs auto matched to their job, worst of 3 runs | at least 95% | 48% FAIL | 96% PASS |
| Wrong auto matches (clear, weak, twin jobs, no fit), worst run | 0 | 0 | 0 |
| Fairness pairs landing on different jobs | 0 | 3 FAIL | 0 PASS |
| Attacked CVs moved to another job | 0 | 0 | 0 |
| Matcher cost per email | under $0.001 | $0.00046 | $0.00040 |

Run 1 showed the matcher rating the applicant's strength, not the kind of job: "maybe"
CVs got 0.6 to 0.75 and stayed below the 0.8 line, and fairness pairs flipped across it.
v1's own scale invited that ("the right role with several must haves missing" was 0.6
to 0.8). v2 says fit is the field and kind of role only; strength is scored later.

### Found and fixed
1. **The Candidates page timed out** with the e2e seed's ~55 jobs (one API call per job);
   now one call ranks every job (three queries).
2. **Two workers could download the same email**: a message is now claimed before it is
   fetched; a crashed claim is picked up again by the next poll.
3. **Import cycle**: the inbox could not import the intake adapter (it imports the
   pipeline); the email normaliser is repeated instead.
4. Test database cleanup now includes the inbox tables.

### Deviations and gaps
- A PDF that parses as "not a CV" is not deleted automatically (design Q5): it is
  ingested and its score shows it; deleting automatically needs a reliable signal first.
- Duplicates keep the first CV only; the second file is not stored.
- Gmail lists the newest 50 messages per poll; more than 50 new emails within 2 minutes
  would wait for a later poll only if still among the newest 50 (push is phase 10).
- Job codes come from a count; two jobs created at the same instant can clash (the
  unique constraint refuses the second; retry).
- Gmail itself is tested with recorded responses only; the real connection needs Mani's
  Google Cloud OAuth client and a test Gmail account.
- Microsoft 365 shows as "coming soon".
