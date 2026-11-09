# Phase 4 Build Log: Recruiter dashboard

Built 2026-11-08 in `~/code/recruit-agent`. Inputs: `phase-4-brief.md` (approved, five
defaults, built locally and Vercel ready) and `phase-4-design.md` (approved, five defaults).

## What was built

| Area | Files |
|------|-------|
| Decision record: every shortlist or reject on a scored (or needs review) candidate stores the recommendation it was made against, in the move's transaction; an override with a reason under 10 characters is refused (422) before anything moves | `app/workflow/decisions.py`, `app/api/main.py`, `app/scoring/agreement.py` |
| Agreement rate (overrides: shortlist a reject, reject an advance; maybe and unscored never count) per job and on the jobs list | `app/scoring/agreement.py`, `app/api/scores_api.py`, `app/api/dashboard_api.py` |
| Contact details only after shortlist (403 before, 410 after erasure); every read writes an access event | `app/api/dashboard_api.py`, `AccessEvent` |
| Jobs list, review queue, access log, candidate detail now carries its job and erased flag | `app/api/dashboard_api.py`, `app/api/main.py` |
| Rescore on a newer approved rubric: undecided candidates only, a new Score row, no state change, job audit notes, failure keeps the old score | `app/workflow/decisions.py`, `app/workflow/dispatch.py`, `app/workflow/pipeline.py`, `app/workers/worker.py` |
| Decisions and access events tables + migration 0005; erasure clears decision reasons | `app/db/models.py`, `migrations/versions/0005_decisions.py`, `app/workflow/machine.py` |
| Next.js 16 dashboard (TypeScript, Tailwind 4): sign in (signed httpOnly cookie, 5 failures per 15 minutes), jobs, ranked job page with filters and rescore, candidate page (evidence beside the CV with quotes highlighted by text match, answers, flags first, history with contact views), review queue | `dashboard/` |
| Keyboard flow: `j` `k` move, `s` `r` open the decision box, `Enter` confirms and opens the next undecided candidate, `Esc` cancels; buttons for every action | `dashboard/app/(app)/candidates/[id]/review-panel.tsx`, `jobs/[id]/row-keys.tsx` |
| Token stays on the server: API client is server only; a check fails on public variables or client code reading settings or importing server modules | `dashboard/lib/api.ts`, `dashboard/scripts/check-public-env.mjs` |
| Dashboard container (standalone build) and Compose service; `make local-env` generates the dashboard password and session key | `dashboard/Dockerfile`, `docker-compose.yml`, `scripts/init_local_env.py`, `.env.example` |
| Demo data: `make demo-seed-offline` (real job service and intake, parse and score rows from the coverage plans, moves through the state machine; no model) and `make demo-seed` (through the API with the real model) | `scripts/demo_seed.py` |
| Browser tests in the official Playwright image (`make e2e`); unit tests (vitest); CI jobs `dashboard` and `e2e` | `dashboard/e2e/`, `scripts/e2e.sh`, `.github/workflows/ci.yml`, `Makefile` |

## Verified (2026-11-08)

| Check | Result |
|-------|--------|
| ruff, format, mypy strict (60 files) | clean |
| Backend tests | 272 passed, 2 skipped (MinIO) |
| Migration 0005 up, down, up | ok |
| Dashboard: type check, 5 unit tests (quote highlighting), secret check, production build | pass |
| Browser tests against the Docker stack, seeded offline | 9 of 9 pass |

| Brief bar | Threshold | Result |
|-----------|-----------|--------|
| Review speed | at most 2 actions per decision | 50 candidates, 100 actions (2 each), 24 seconds |
| Agreement rate | table matches | 8 pair table and a 10 decision rate test pass; dashboard shows 100% after the drill |
| Override reason | 100% refused | API: "ok", "x", "too short" refused (422), nothing moved; form: empty and 9 characters refused |
| Blind review | 0 personal details before shortlist | 0 of every seeded name, name part, email and phone across 3 candidate pages, the job page and all responses; contact panel after shortlist |
| Token exposure | 0 | 0 across every page, response, request, header and cookie |
| Accessibility | 0 serious or critical | 0 on sign in, jobs, job, candidate, decision box, review queue (axe) |
| Speed | under 300 ms (95th percentile) | ranked list with 200 candidates: pass (API test) |
| Stale page | conflict message, no second decision | pass (two tabs) |
| Vercel ready | build with environment settings only | `next build` passes; secret check passes |

Screenshots from the browser tests: `dashboard/test-results/candidate-page.png` (evidence
beside the CV, quotes highlighted, no name) and `job-after-review.png` (drill job after 50
keyboard decisions, 100% agreement).

## Found while building, and fixed

1. **Phase 2 redaction removed qualifications**: "Certificate IV ..., TAFE NSW, 2012" matched the suburb pattern (a year looks like a postcode), so the institution and year became `[ADDRESS]`. Found because the offline seed could not find 9 quotes. Matches that name an organisation (TAFE, university, Health, Transport, department and so on) are now kept; home addresses are still removed. Regression test added.
2. **Contact views were missing from the history on first load**: the page read the access log before the contact read was logged. The contact is now read first.
3. **The demo drill copies changed the applicant's name but not the CV**, so redaction could not remove the name printed in the CV. Copies now keep the person and change only email and phone, as a real second application would.
4. **Next.js adds its own empty alert element**, and a filter menu's options ("Salary above band") matched the label "Band"; tests now target our own alerts and the menus have explicit labels and ids.
5. **Key hints were invisible on the coloured buttons** (white on white); fixed in the stylesheet.
6. **Answer notes said "answered False, required True"**; now "answered no, required yes".
7. **Reading the generated dashboard password into the session was blocked** (correctly). The browser tests get it straight from `.env` inside their container instead; it is never printed.

## Deviations from the design

- The design's "review drill" of 50 is a fourth demo job (the analyst CVs repeated with new emails and phones), so the three phase 3 jobs stay at 15 each.
- Decisions are also recorded for a reject from NEEDS_REVIEW (recommendation "none", never an override).
- Recruiter reasons in the audit log are kept on erasure (the audit log is append only by phase 0 design); the Decision copy is cleared. Noted for the phase 9 privacy review.

## Known gaps

- After shortlist the phase 0 stub steps still run the calls and booking, so a shortlisted demo candidate moves on to "screen scored" by itself. Real calls arrive in phases 6 to 8.
- The sign in rate limit is in memory (one process); Vercel (phase 10) needs a shared store.
- One recruiter account; proper accounts and roles later.
- Job creation and rubric editing are still API calls (brief Q5).
- Workspace hygiene: one dashboard check run mounted the wrong folder and left a vitest cache folder (`mani-workspace/node_modules`, about 5 MB, nothing else changed); moved to the Recycle Bin with Mani's OK, 2026-11-08. The check script now mounts only the dashboard folder by absolute path.
