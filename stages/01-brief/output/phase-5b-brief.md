# Phase 5B Brief: Hira dashboard + connected inbox

Approved by Mani 2026-11-12 with the six defaults (Q1 to Q6). Source: master-plan section 8 (phase 5B row),
section 5 (connected inbox), section 6 (privacy), section 1 rules 3, 6, 7, 8, 9, 12, 14.
The UI design came first at Mani's request and is approved:
`stages/02-design/output/phase-5b-ui-design.html` and `.md` (2026-11-12, six defaults:
"hira" name, names hidden until shortlist, scores shown with evidence first, Gmail
first, one label only, dark mode follows the computer).

## Goal
A recruiter works in the Hira style dashboard and connects the Gmail inbox where
applications arrive. Every CV that lands under the chosen label is ingested once, cleaned
and redacted like an apply page CV, matched to the right open job (or held in "Needs a
job" when unsure), and scored, without the recruiter forwarding or uploading anything.

## In scope
- **Dashboard redesign** to the approved design: Candidates workbench (queue plus review
  panel with Requirements, CV, Rejection email, Notes, Activity), Jobs board, Inbox,
  To do; header navigation; mobile list to review flow; light and dark. Every phase 4
  and 5 function keeps working (shortlist, reject, override reasons, stale page conflict,
  contact reveal logging, rejection draft edit and send, retry delivery).
- **Gmail connection** (OAuth 2.0, scope `gmail.readonly` only, never send or modify):
  connect, pick one label, pause, disconnect (token deleted and revoked). Refresh token
  stored encrypted in Postgres with a key from `.env`.
- **Mailbox provider interface** with three providers: `gmail` (real), `mailpit` (the
  local test inbox from phase 5, read through its API, so the demo and the browser tests
  run with no Google account), and `fake` (unit tests).
- **Ingestion job**: a poll every 2 minutes per connected mailbox (Q3) lists new messages
  under the label since the last checkpoint; each message is processed once (unique key:
  mailbox id plus provider message id); PDF and Word attachments go through the existing
  intake (hidden text removal, parse, redact, score). No CV: logged "Not a CV". Two CVs
  in one email: two candidates. Size and type limits as the apply page.
- **Job matching**, in order: job code in the subject or a plus address
  (`careers+da-0042@`), the Seek or Indeed subject line, then the **job matcher agent**
  (new, prompt `job-matcher` v1, DeepSeek extraction tier) that sees the redacted CV
  summary and the open jobs' titles and must haves, and returns a job id and a
  confidence. Code auto matches only above the threshold with a clear gap to the next
  job (Q4); otherwise "Needs a job" with the suggestions. One CV, one job (Q5).
- **Duplicates**: the same email address and job within 90 days attaches the new files
  to the existing candidate instead of scoring again.
- **Collection notice**: an acknowledgement email with our collection notice and the
  delete my data path goes to each new inbox candidate through the phase 5 outbox (Q6);
  Mailpit locally, real sending still behind `EMAIL_SENDING_ENABLED`.
- **To do and Inbox screens** fed by real data: needs a job, not a CV, duplicates,
  connection errors (expired token shows "Reconnect").
- **Audit**: connect, disconnect, every ingested message, matcher result and recruiter
  job pick are audit rows.
- **Evals**: dataset `match-v1` (about 60 synthetic emails: job codes, plus addresses,
  Seek and Indeed subjects, direct emails with clear and ambiguous CVs, not a CV,
  duplicates, two CVs in one email, injection such as "match me to the Senior role"),
  and counterfactual pairs for the matcher.

## Out of scope (later phase)
- Microsoft 365 (Graph): designed, shown as "coming soon"; next after Gmail
- Push notifications (Gmail watch with Pub/Sub): needs a public URL; phase 10
- Google's security assessment for the restricted Gmail scope: only for a public launch
  (phase 10); testing mode allows up to 100 test users
- One CV matched to several jobs, and moving a candidate between jobs after scoring
- Reading the email body as an application letter (only attachments are CVs)
- Seek and Indeed partner connectors

## Done criteria
- [ ] The new dashboard passes every phase 4 and 5 browser test (rewritten selectors), plus new tests: connect the Mailpit inbox, an emailed CV appears matched and scored, pick a job for a "Needs a job" CV, disconnect.
- [ ] Layout checks at 1280, 1024, 736, 390 and 320 px with no sideways scrolling; keyboard only run of shortlist and reject.
- [ ] A Gmail test account (synthetic CVs only) connects, the label is read, and a sent test application is scored within 5 minutes.
- [ ] The OAuth request asks for `gmail.readonly` only (test inspects the scope list); disconnect revokes and deletes the token.
- [ ] The same message fetched twice, a worker killed mid message, and two pollers at once each produce exactly one candidate.
- [ ] Tokens are encrypted at rest (test reads the raw column).
- [ ] Matcher input holds no name, email or phone (test inspects the request).
- [ ] `make eval-match` runs the matcher suite; the fast suite runs the deterministic matching table in CI; nightly runs the full suite.

## Eval bars

| Check | Dataset | Metric | Threshold |
|-------|---------|--------|-----------|
| Deterministic matching | `match-v1` rule rows (codes, plus addresses, Seek, Indeed) | correct job | 100% |
| Matcher, clear CVs | `match-v1` clear rows, 3 runs | correct job, auto matched | at least 95% |
| Matcher, ambiguous CVs | `match-v1` ambiguous rows | wrong auto matches (must go to Needs a job) | 0 |
| Not a CV | `match-v1` | emails without a CV skipped, CVs never skipped | 100% |
| Injection | `match-v1` attacked CVs and subjects | job changed by planted text | 0 |
| Fairness | counterfactual pairs (name, gender, age signal, suburb) | pairs matched to different jobs | 0 |
| Ingestion idempotency | concurrency and crash tests | duplicate candidates | 0 |
| Cost | `match-v1` | matcher cost per email | under $0.001 |
| Phases 3 to 5 | existing suites and browser tests | all bars | still pass |

## Production rules exercised

| Rule | How phase 5B shows it |
|------|-----------------------|
| 3 | The matcher never decides when unsure; the recruiter picks the job |
| 6 | The matcher sees redacted text only; counterfactual pairs must match the same job |
| 7 | Email subjects, bodies and CVs are untrusted; planted instructions cannot change the job |
| 8, 9 | Each message has a unique key; the poller resumes from its checkpoint after a crash |
| 12 | Connect, disconnect, ingest, match and job picks are audit rows |
| 14 | Read only scope on one label, collection notice to each inbox candidate, delete path |

## Needs before starting
- A Google Cloud project with the Gmail API on and an OAuth client (web), consent
  screen in testing mode. Mani creates it; I give exact steps. The client secret goes in
  `product/.env` only.
- A separate test Gmail account (not Mani's own inbox) added as a test user. Only
  synthetic CVs are sent to it.
- No new paid services. kie.ai: about 180 matcher calls per eval run, under $0.10.
- The phase 5 commit and gate first, so 5B starts from a clean tree.

## Risks

| Risk | Fallback |
|------|----------|
| The inbox holds personal email that is not an application | One label only; nothing outside the label is listed or fetched |
| The matcher sends a CV to the wrong job | Auto match only with high confidence and a clear gap; otherwise Needs a job; 0 wrong auto matches is a bar |
| Token leak | Encrypted at rest, read only scope, revoke on disconnect, never logged or traced |
| Google blocks the app for public users | Testing mode for the demo; the assessment is a phase 10 task |
| The redesign breaks phase 4 and 5 flows | All existing browser tests must pass on the new UI before the gate |
| A flood of emails (a job ad goes viral) | Per mailbox rate limit and the existing per job budget |

## Open questions (checkpoint)

| # | Question | Default |
|---|----------|---------|
| Q1 | Build order inside 5B | Redesign first (ship it on the current data), then the inbox |
| Q2 | Test mailbox | A new Gmail account just for testing, synthetic CVs only |
| Q3 | Poll or push | Poll every 2 minutes (push needs a public URL) |
| Q4 | When the matcher may auto match | Confidence at least 0.8 and at least 0.3 ahead of the next job; else Needs a job |
| Q5 | One CV to several jobs | No: one job; the recruiter can pick a different job while it is in Needs a job |
| Q6 | Acknowledgement email with the collection notice | Yes, sent automatically on ingest (no decision in it), through the outbox |
