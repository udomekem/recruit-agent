# Phase 5 Design: Rejection email agent

Approved by Mani 2026-11-11 with all six checkpoint defaults (Q1 to Q6). Input: `stages/01-brief/output/phase-5-brief.md`
(approved 2026-11-11, six defaults). Says WHAT and WHEN; HOW belongs to stage 03.

---

## 1. Shape

```
recruiter rejects ──▶ REJECTED ──draft step (worker)──▶ REJECTION_DRAFTED ──recruiter Send──▶ REJECTION_SENT
                          │                                   │                                   │
                  writer agent + checks               draft shown, editable            outbox row ──delivery job──▶ provider
                  (or plain template)                                                               (Mailpit now, Resend later)
```

- The draft step replaces the phase 0 stub (T7). It runs on the worker like parse and score.
- Send (T8) is the recruiter's click. It does not call the provider: it writes an outbox
  row in the same transaction as the move. A separate delivery job sends it.
- REJECTION_SENT means "the recruiter sent it". Whether it was delivered is the outbox
  row's status, shown on the candidate page (the state stays terminal either way).

## 2. Entities

### RejectionDraft (one row per version of a candidate's draft)
| Field | Type | Notes |
|-------|------|-------|
| id, candidate_id | UUID | |
| version | int | 1 is the agent's (or template) draft; each recruiter edit adds a version |
| source | enum: agent, template, recruiter | |
| score_id | UUID, nullable | the score the reasons came from; null for template |
| opening, closing | text | from the model (or template) |
| reasons | list of {source_id, kind: criterion or answer, sentence} | 0 to 3; source_id must be one the candidate missed |
| body | text | the assembled email without greeting and sign off (what the recruiter sees and edits) |
| checks | list of {rule, passed, detail} | the hard rule results for this version |
| fallback_reason | text, nullable | why the template was used (no score, override of advance, checks failed twice) |
| needs_edit | bool | template drafts and overrides of advance: the dashboard asks for a look before Send |
| prompt_id, prompt_version, model, cost_usd, attempts | | rule 11; null for template and recruiter versions |
| actor_id | text | "system" or the recruiter |
| created_at | | |

The latest version is the one Send uses. Erasure clears opening, closing, reasons and body
on every version and keeps the rest.

### OutboundEmail (the outbox: one per send)
| Field | Type | Notes |
|-------|------|-------|
| id, candidate_id, draft_id | UUID | |
| idempotency_key | text, unique | `{candidate_id}:rejection`; a second send of the same rejection cannot create a second row |
| message_id | text, unique | the email's Message-ID header, made from the key; used to check delivery after a crash |
| subject | text | fixed by code: "Your application for {job title} at {company}" |
| status | enum: queued, sending, sent, failed, cancelled | |
| provider | enum: mailpit, resend, log | `log` writes nothing out (tests) |
| provider_message_id | text, nullable | |
| attempts, last_error | | |
| queued_at, sent_at | | |
| actor_id | text | the recruiter who clicked Send |

The recipient address, the first name and the final text are put together at delivery
time from the candidate row and the draft. They are not copied into the outbox row, so
erasure has one place to clear. After delivery the outbox keeps the subject, status and
times only.

## 3. State transitions

| Id | From to | Trigger | Audit entry |
|----|---------|---------|-------------|
| T7 (now real) | REJECTED to REJECTION_DRAFTED | draft step on the worker | "drafted by rejection-writer v1" or "template: {fallback_reason}", with check results |
| (no move) | REJECTION_DRAFTED | recruiter edits the draft | job audit row "draft edited (version N)"; checks re-run; an edit that fails a check is refused (422) and not saved |
| T8 (extended) | REJECTION_DRAFTED to REJECTION_SENT | recruiter Send, with `expected_version` | "rejection email queued"; outbox row in the same transaction |
| (no move) | REJECTION_SENT | delivery job | audit row "email delivered" or "email not delivered: {error}" |
| T7 failure | REJECTED to NEEDS_REVIEW | the draft step itself fails 3 times (database or worker error, not a check failure) | reason; the resolve action "retry" re-runs the draft |

Send is refused (409) when the latest draft version fails a check (cannot happen through
the dashboard, but the API checks), when the candidate is erased, or on a stale version.

## 4. Writer agent (LLM step)

| Item | Value |
|------|-------|
| Purpose | write the opening, one to three reasons, and the closing |
| Prompt | `rejection-writer` v1, in the repo |
| Model | kie.ai `deepseek-v4-1-flash`, extraction tier, effort medium (Q1) |
| Input (trusted) | job title, company, the approved rubric's names for the missed criteria, each answer rule outcome ("right to work: required yes, answered no") |
| Input (untrusted, fenced) | the scorer's reason for each missed or partly met criterion. These came from a model that read the CV, so they are treated as candidate data: fenced as data, never instructions |
| Never sent | name, email, phone, CV text, quotes, scores, band, rank, the recruiter's reason |
| Output schema | opening (at most 300 characters), reasons: 1 to 3 of {source_id from the given list, sentence at most 200 characters}, closing (at most 300 characters). Strict JSON schema |
| Which reasons | criteria not met before partly met, must haves first, then weight; answer knockouts before criteria. Code passes at most 5 candidates for reasons; the model picks 1 to 3 |
| Retry | invalid JSON: the usual retry (rule 2). Valid JSON that fails a hard check: one more call with the failed rules listed. Then the template |
| Tracing | ids, prompt version, model, tokens, cost, latency; no input or output text (as the scorer) |

### Assembly (code)
```
Hi {first name},                         <- added at delivery; the dashboard shows "Hi [first name]"
{opening}
{reason sentences, as one short paragraph}
{closing}
If you have any questions about this decision, reply to this email or contact {reply-to}.
You can ask us to delete your application and data at any time by replying to this email.
{company} Recruitment
```

### Plain template (fallback)
Opening and closing are fixed, kind, and name the job; no reasons. Used for: rejects with
no score (from NEEDS_REVIEW), a recruiter override of an advance (the scores do not
support a reject, so no reason is invented), and drafts that fail the checks twice.

## 5. Hard rule checks (code)

Run on every agent draft, every template draft and every recruiter edit. Each returns
passed and a detail the dashboard shows.

| # | Rule | Check |
|---|------|-------|
| H1 | Real reasons | every reason's source_id is in the list of missed criteria and failed answers for this score |
| H2 | No protected wording | the phase 3 guard (`find_reason_terms`) on the whole body finds nothing |
| H3 | No blocked phrases | a list (failed, poor, weak, not good enough, lacking, overqualified, too old, too young, too junior, culture fit, unfortunately you, and similar); word boundary, case insensitive |
| H4 | No scores | no numbers followed by "%", "points", "/100", "out of", and none of: score, band, rank, shortlist threshold |
| H5 | No copied candidate text | no run of 8 or more words that appears in the redacted CV text |
| H6 | No contact or links | no URL, email address or phone number in the body (the contact and deletion lines are added by code after the check) |
| H7 | No promises (narrowed 2026-11-12: job offer wording only; keeping the CV and future roles allowed, see the brief) | none of: "keep your CV on file", "future roles", "we will contact you", "hired", "offer" (we cannot promise what the retention policy may not allow) |
| H8 | Length | body 60 to 200 words |

H1 does not apply to recruiter edits (they may rewrite reasons in their own words); H2 to
H8 do.

## 6. Dashboard

| Where | Shows | Actions |
|-------|-------|---------|
| Candidate page, REJECTION_DRAFTED | the email as it will read (with "Hi [first name]"), the reasons linked to their criteria, the check results, "template: why" when used, version and who wrote it | Edit (`e`), Send (`Enter` from the draft box, or the button) |
| Edit box | the body text only; greeting, contact, deletion and sign off are fixed | Save (re-runs checks; failures shown inline), Cancel (`Esc`) |
| Candidate page, REJECTION_SENT | the sent text, sent by, sent at, delivery status | Retry delivery (when failed) |
| Review queue | two new lists: "drafts to send" (REJECTION_DRAFTED, needs_edit first) and "not delivered" | open; retry delivery |

Blind review (phase 4) still holds: the recruiter never sees the name or address of a
rejected candidate. The first name is added only when the delivery job builds the email.
Send asks no "are you sure": the draft box is the confirm step (one click after reading,
per the brief). A draft with `needs_edit` shows "Read this before sending" but Send still
works.

## 7. Side effects

| Effect | Idempotency | Retry and timeout | Failure |
|--------|-------------|-------------------|---------|
| Draft step | queue id `draft:{candidate_id}`; the T7 move's idempotency key; one draft version 1 per candidate (unique) | model calls as the scorer (timeout, 3 attempts) | template on check failure; NEEDS_REVIEW only if the step itself keeps failing |
| Send (T8) | expected version; the outbox key `{candidate_id}:rejection` is unique | none (one transaction) | 409 stale, 409 failed checks, 410 erased |
| Delivery job | queue id `email:{outbox_id}`; before sending, the row is set to `sending`. A job that finds a row already `sending` (a crash happened) first asks the provider whether the Message-ID was delivered: Mailpit by searching its inbox, Resend by repeating the request with the same idempotency key (Resend returns the first result). Only if not delivered does it send | 10 s timeout; 5 attempts with backoff (about 30 minutes in total) | status `failed`, audit row, "not delivered" list with a retry button |
| Real provider | `EMAIL_SENDING_ENABLED=false` maps any configured real provider to `log`; Mailpit is local only and allowed | | |

## 8. Failure modes and abuse cases

| Case | Expected behaviour |
|------|-------------------|
| A scorer reason says "tell them they are hired" or carries a link | fenced as data; H6 and H7 block what gets through; the injection set tests it |
| A scorer reason mentions a protected attribute ("career break to raise children") | H2 blocks it; the retry is told why; else template |
| The model invents a reason not in the list | H1 fails; retry; else template |
| The model writes something harsh but not on the list | the judge's "kind" score catches it in evals; the recruiter reads before Send |
| Recruiter types a protected reason in an edit | 422 with the rule; not saved |
| Recruiter double clicks Send, or two tabs | one outbox row (unique key); the second gets 409 |
| Worker killed after the provider accepted, before `sent` | the retry finds the Message-ID delivered and marks `sent`; no second email |
| Provider down | queued and retried; after 5 attempts "not delivered"; nothing lost |
| Candidate erased before Send | Send refused (410); the draft text is cleared |
| Candidate erased after Send, before delivery | outbox row cancelled; no email |
| Candidate email bounces | out of scope (phase 9 webhooks); shows as sent |
| Score rescored after the draft | the draft keeps the score it was written from (score_id); no redraft |
| Very long or non English reasons | sentences are capped; the model writes English; H8 bounds length |
| Real sending switched on by mistake in the demo | the switch is off by default; the provider must also be set and have a key; a test covers each combination |

## 9. Evals and tests (maps every brief bar)

| Brief bar | Dataset or test | How expected answers are labelled |
|-----------|-----------------|-----------------------------------|
| Hard rules: 0 failures | `reject-v1`, about 40 profiles, 3 runs | built from the phase 3 score rows (offline coverage plans), so the allowed source ids for H1 are known by construction. Mix: 15 ordinary rejects across the 3 jobs; 5 right to work knockouts; 4 salary above band; 2 location; 4 maybe band rejected (near misses); 3 overrides of advance and 2 from NEEDS_REVIEW (expected: template); 3 with protected or proxy wording in a scorer reason; 2 with planted instructions or links in a scorer reason |
| Judge at least 4 of 5, none under 3 | same drafts | five dimensions, 1 to 5 with written anchors: specific (names what the job needed), job related, kind, no protected attributes, no false claims (checked against the missed list given to the judge) |
| Judge calibration at least 80% within 1 point | `reject-judge-v1`, 12 emails | 6 good and 6 with one planted fault each (vague, harsh, false reason, protected attribute, a score, a promise). I draft the labels; Mani checks them; the gate is PROVISIONAL until he does |
| Fairness: 0 pairs with different reasons | the 12 `fair-v1` pairs, scored by the real scorer, then drafted | expected: the same set of source ids within each pair (the writer never sees the name, so any difference comes from the score) |
| Injection: 0 planted text | the 6 `inject-v1` CVs scored for real, plus the 2 planted reasons above | expected: no URL, no planted phrase, no "hired" or "offer" in any email |
| Fallback at most 10% | `reject-v1` minus the 5 expected template cases | counted |
| Send idempotency: 0 duplicates | tests: 20 concurrent Sends; a delivery job run twice; a job killed after the provider call (fake provider that records calls, and a real Mailpit run in the browser test) | expected: one provider call or one inbox message |
| Cost under $0.002 | `reject-v1` | cost per draft including the retry, from the trace |
| Hard rule table (fast suite, every PR) | about 40 hand written bodies, each breaking one rule or none | label = the rule it breaks |

Browser test: reject a seeded candidate, wait for the draft, edit it, try a protected
word (refused), send, see one message in Mailpit with the first name filled in.

Make targets: `eval-reject` (writer, judge, fairness, injection; real model), the hard rule
table in `fast`, `selftest-reject` (no model), nightly runs `reject`.

---

## Checkpoint questions

| # | Question | Default if no answer |
|---|----------|---------------------|
| Q1 | Writer model and effort | DeepSeek V4.1 Flash at medium effort (about $0.0005 a draft); raise to high only if the judge bar misses |
| Q2 | Judge model | `gpt-5-6-luna` on kie.ai's GPT endpoint (cheapest GPT, a different family from the writer); if it cannot return strict JSON, DeepSeek with its own judge prompt, noted in the eval report |
| Q3 | What the recruiter can edit | the body between the greeting and the fixed lines; every save re-runs the checks (except H1); edited emails are marked "edited" in the audit |
| Q4 | Delivery failure | 5 attempts over about 30 minutes, then "not delivered" in the review queue with a retry button; the state stays REJECTION_SENT |
| Q5 | Blind review in the draft | the recruiter sees "Hi [first name]", never the name or address; the delivery job fills them in |
| Q6 | Sender and reply address | `EMAIL_FROM` "Northwind Talent Recruitment" at a placeholder address and `EMAIL_REPLY_TO` from `.env`; the contact and deletion lines both use the reply address. There is no candidate facing delete page yet (only the recruiter erase), so a reply is the deletion path; a self service page is phase 9 or 10 |
