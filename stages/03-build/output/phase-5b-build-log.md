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
