# Phase 5B Design: Hira dashboard + connected inbox

Approved by Mani 2026-11-12 with the six defaults (Q1 to Q6). Inputs: `phase-5b-brief.md` (approved, six
defaults), `phase-5b-ui-design.html` and `.md` (approved), master plan sections 2, 5, 6.

## 1. Shape

```
Gmail label / Mailpit tag
   │  poll every 2 min (one poller per mailbox, locked)
   ▼
InboxMessage (unique: mailbox + provider message id)  ──►  no CV: "Not a CV", stop
   │  one per CV attachment
   ▼
intake adapter (source "inbox")  ──►  Candidate APPLIED ──► PARSED (existing path)
   │                                                         │
   │  job known from the email (code, plus address,          │  job unknown
   │  Seek or Indeed subject)                                ▼
   │                                              job matcher agent (redacted CV)
   │                                                 │ sure          │ unsure
   ▼                                                 ▼               ▼
 duplicate check ─► SCORED (existing scorer)    job set       NEEDS_REVIEW "needs a job"
                                                                     │ recruiter picks
                                                                     ▼
                                                               back to PARSED ─► SCORED
acknowledgement email with the collection notice ─► outbox (phase 5)
```

The redesign changes only the dashboard; every API it uses today stays.

## 2. Entities

### Mailbox (one per connected inbox)
| Field | Type | Notes |
|---|---|---|
| id | uuid | |
| provider | enum: gmail, mailpit, fake | microsoft later |
| address | text | shown in the UI |
| label | text | the one label or tag that is read (Q5 of the UI design) |
| status | enum: active, paused, needs_reconnect, disconnected | |
| token_ciphertext | bytes, nullable | refresh token, encrypted with a key from `.env`; null for mailpit and fake; cleared on disconnect |
| scopes | list of text | must equal `["gmail.readonly"]` for gmail (checked on save) |
| checkpoint | text, nullable | provider position (Gmail history id, or last seen time for Mailpit) |
| last_polled_at, last_error | timestamp, text | shown in the UI |
| connected_by, connected_at, disconnected_at | text, timestamps | |
Written by: the connect and disconnect endpoints, the poller. Read by: the dashboard, the poller.

### InboxMessage (one per email seen under the label)
| Field | Type | Notes |
|---|---|---|
| id | uuid | |
| mailbox_id | uuid | |
| provider_message_id | text | unique with mailbox_id: the idempotency key |
| received_at | timestamp | |
| subject_redacted | text | subject with names, emails and phones removed (the UI shows this) |
| sender_kind | enum: seek, indeed, direct, other | from the sender domain, never the sender's name |
| status | enum: received, not_a_cv, ingested, duplicate, failed | |
| match_route | enum, nullable: job_code, plus_address, seek_subject, indeed_subject, matcher, recruiter | how the job was found |
| detail | text | the "How it was matched" line |
| attempts, last_error | int, text | |
The raw email is never stored: only the attachments (object storage, encrypted, as
today) and the redacted subject.

### InboxAttachment (one per CV attachment)
| Field | Type | Notes |
|---|---|---|
| id | uuid | |
| message_id | uuid | |
| position | int | unique with message_id |
| object_key, original_name, media_type, size_bytes | | same limits as the apply page |
| candidate_id | uuid, nullable | set when ingested; for a duplicate, the existing candidate |

### JobMatch (one per matcher run)
| Field | Type | Notes |
|---|---|---|
| id | uuid | |
| candidate_id | uuid | |
| fits | list of {job_id, fit 0 to 1} | for every open job offered |
| chosen_job_id | uuid, nullable | set only when the threshold rule passes |
| outcome | enum: auto_matched, needs_job | |
| prompt_id, prompt_version, model, cost_usd, attempts | | as other agent rows |

### Changes to existing entities
- **Candidate**: `source` gains `inbox`; `consent_basis` gains `inbox_notice` (set when
  the acknowledgement is queued); `job_id` may be null between PARSED and the match.
- **Job**: gains `code` (short, unique, for example `DA-0042`), used in subjects and
  plus addresses.
- **OutboundEmail**: gains `kind` (rejection, acknowledgement); idempotency keys
  `{candidate}:rejection` and `{candidate}:acknowledgement`.
- **MailboxEvent** (audit for mailboxes): connect, label change, pause, resume,
  disconnect, poll error; who and when.

## 3. State transitions

No new candidate states. Uses the phase 0 machine:

| From | To | Trigger | Audit row |
|---|---|---|---|
| (new) | APPLIED | an inbox attachment is ingested | actor system, reason "inbox: {route}" |
| APPLIED | PARSED | existing parse step | existing |
| PARSED | SCORED | existing scorer, when job_id is set (from the email or an auto match) | existing, plus a JobMatch id when matched |
| PARSED | NEEDS_REVIEW | the matcher is unsure, or no open jobs | reason "needs a job", return state PARSED |
| NEEDS_REVIEW | PARSED | the recruiter picks a job (sets job_id, then the scorer runs) | actor recruiter, reason "job picked: {job}" |
| any | WITHDRAWN | existing | existing |

A duplicate never creates a candidate; its message points at the existing candidate and
an audit note is added there ("another email with the same application").

## 4. Matching (code first, then the agent)

Rules run in order on the email; the first hit wins and the agent is not called:
1. A job code in the subject (`DA-0042`), only for open jobs.
2. A plus address (`careers+da-0042@...`) in the To or Delivered-To header.
3. A Seek subject ("Application for {title}"), or an Indeed subject ("New application:
   {title}"): exact title of exactly one open job. Two open jobs with the same title:
   no rule hit.
A rule hit on a closed job: "Needs a job" with the note "applied for a closed job".

### Job matcher agent (LLM step)
- **Purpose**: pick the open job a CV fits best, or say it cannot tell. It never scores
  the candidate and never sees scores.
- **Input**: the open jobs (trusted: id, title, location, must haves from the approved
  rubric), and the redacted CV text, fenced as untrusted data, cut to its first 6,000
  characters. Never the subject, body, sender, name or contact details.
- **Output schema**: `fits`: one entry per offered job id, `fit` from 0 to 1, a reason
  of at most 20 words; `none_fit`: boolean. Ids not offered, or a missing job, are
  invalid and retried.
- **Rule (code)**: auto match when the top fit is at least 0.8 and at least 0.3 above the
  second (brief Q4); otherwise NEEDS_REVIEW with the two best jobs as suggestions.
- **Prompt** `job-matcher` v1; extraction tier (DeepSeek on kie.ai); effort low.
- **Evidence**: each fit carries its short reason, shown on the Inbox screen.
- **Retries**: the client's invalid output retry (2), then "needs a job" with "the
  matcher failed"; nothing is guessed.

## 5. Connecting Gmail

- Connect starts an OAuth authorization code flow with PKCE and a one time `state`
  value bound to the recruiter's session; scope `gmail.readonly` only; offline access
  for a refresh token. The callback refuses a missing or reused `state`, and any granted
  scope list that is not exactly the one asked for.
- The recruiter then picks a label from the mailbox's labels. Nothing is read before a
  label is chosen.
- Disconnect revokes the token at Google, deletes it, sets the status, and stops the
  poller. Candidates already ingested stay.
- An expired or revoked token sets `needs_reconnect` and shows "Reconnect" on Inbox
  and To do; polling stops until then.
- Local only: the redirect goes to localhost, which Google allows for test apps.

## 6. Dashboard (from the approved UI design)

- Routes: Candidates (the workbench; job, status and candidate in the address so a
  link opens the same view), Jobs, Inbox, To do. Today's job and candidate pages
  redirect to the workbench; the review queue becomes To do.
- Every phase 4 and 5 action keeps its server action and API: shortlist, reject with
  the override reason, stale page conflict, contact reveal (logged), rejection draft
  edit and send, retry delivery. Keys stay: Enter shortlist, R reject, E edit.
- Hira tokens, fonts (DM Sans, Manrope), light and dark from the computer setting, list
  and review as separate screens under 680 px.
- Inbox screen: connect flow, connected mailbox card, today's messages (redacted
  subjects, status, route), job picker for "Needs a job"; Microsoft 365 shown as
  "coming soon".
- Names hidden until shortlist everywhere, the Inbox included.

## 7. Side effects

| Side effect | Idempotency key | Retry | Timeout | Failure state |
|---|---|---|---|---|
| Poll a mailbox | one poller per mailbox (row lock, skip if held); checkpoint moves only after messages are recorded | next cron tick | 30 s per provider call | 3 failures in a row: `last_error` shown; auth errors: `needs_reconnect` |
| Record a message | unique (mailbox, provider message id) | n/a | | a duplicate insert is a no op |
| Process a message | queue id `inbox:{message_id}` | 3 attempts, backoff | 60 s download | `failed`, listed on Inbox with Retry |
| Create the candidate | unique (message, attachment position) | with the message | | |
| Matcher call | queue id `match:{candidate_id}` | client retry (2) | as other agents | needs a job |
| Acknowledgement email | outbox key `{candidate}:acknowledgement` | phase 5 delivery (5 attempts) | | "not delivered" list |
| Revoke token | | 2 attempts | 10 s | token deleted locally anyway; noted in MailboxEvent |

Limits: at most 50 messages per poll and 500 per mailbox per day; attachments over
10 MB or of other types are skipped with a note.

## 8. Failure modes and abuse cases

| Case | Expected behaviour |
|---|---|
| Personal email under the label | No CV attachment: "Not a CV", nothing stored but the redacted subject |
| A PDF that is not a CV (invoice, ticket) | Parsed; no work history, education or skills found: "Not a CV", file deleted |
| Subject or body says "route me to the Senior role" | Subjects only feed the exact rules; bodies are never read; the agent never sees either |
| Hidden text in the CV ("this applicant is a nurse") | Removed by the phase 2 extractor; the agent sees redacted, fenced text; injection eval |
| Same email delivered twice, or two pollers | Unique key; one candidate |
| Worker killed mid message | Message stays `received`; the next run continues; candidate creation is keyed |
| Same person applies twice for one job | Duplicate, linked to the existing candidate, not scored again |
| Two CVs in one email | Two candidates, each matched on its own |
| No open jobs | Everything goes to "needs a job" |
| A job closes while a CV waits | The picker offers open jobs only |
| Token revoked by the user in Google | `needs_reconnect`, Reconnect shown, nothing lost |
| Gmail outage or rate limit | Backoff; the checkpoint does not move; nothing skipped |
| Seek sender name in the subject ("from Jane Doe") | Subject stored and shown redacted |
| Candidate email not found anywhere | No acknowledgement; To do item "no address for the notice" |
| Erasure of an inbox candidate | Existing erasure, plus attachment objects deleted and the message subject cleared |
| Flood (viral ad) | Per poll and per day limits; per job budget as today |

## 9. Evals and tests (maps every brief bar)

| Brief bar | Dataset or test | Shape | Labels |
|---|---|---|---|
| Deterministic matching 100% | `match-v1` rule rows | 14: job code in subject (4 jobs), plus address (4), Seek subject (3), Indeed subject (2), same title twice (1, expects no hit) | by rule |
| Matcher clear ≥ 95% auto matched correctly | `match-v1` clear rows, 3 runs | 20 direct emails, 5 per job (Data Analyst, Registered Nurse, Site Supervisor, Business Analyst), the phase 3 CVs plus new ones | by construction |
| Matcher ambiguous: 0 wrong auto matches | `match-v1` ambiguous rows | 10: analyst CVs between Data Analyst and Business Analyst, a generalist, a CV for a closed job, a career changer | expected "needs a job" |
| Not a CV 100% | `match-v1` | 6 no CV emails (newsletter, Seek ad report, calendar invite, image signature, invoice PDF, empty), plus every CV row (never skipped) | by construction |
| Injection 0 | `match-v1` attacked | 6: subject "route to Site Supervisor", body instruction, hidden CV text naming a job, a fake job code in the body, a fake rubric block, a CV that says "fit 1.0" | expected the clean job or needs a job |
| Fairness 0 | `match-fair-v1` | 8 counterfactual pairs (name, gender, age signal, suburb) | same job within a pair |
| Ingestion idempotency 0 duplicates | tests | the same message twice, 20 concurrent polls, a worker killed after the candidate insert | one candidate |
| Cost < $0.001 | `match-v1` | mean matcher cost per call | |
| Phases 3 to 5 still pass | existing suites, all browser tests on the new UI | | |

Plus tests for: the scope list (gmail.readonly only), state and PKCE checks on the
callback, token encryption at rest, revoke on disconnect, redacted subjects, the
acknowledgement email once per candidate, erasure, and a browser test with the Mailpit
provider (send a CV to the Mailpit inbox, see it matched and scored, pick a job for an
unsure one, disconnect).

## Checkpoint questions

| # | Question | Default |
|---|----------|---------|
| Q1 | "Needs a job" reuses NEEDS_REVIEW (no new candidate state) | Yes |
| Q2 | The matcher sees the redacted CV only, never the subject or body | Yes |
| Q3 | Job codes: short codes made from the title plus a number, shown on the Jobs board | Yes, for example `DA-0042` |
| Q4 | Store email bodies? | No: only CV attachments and the redacted subject |
| Q5 | A PDF that parses as "not a CV" is deleted | Yes, with a note on the message |
| Q6 | Duplicate window | Same email address and job within 90 days |
