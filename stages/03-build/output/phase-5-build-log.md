# Phase 5 Build Log: Rejection email agent

Built 2026-11-11 in `~/code/recruit-agent`. Inputs: `phase-5-brief.md` (approved, six
defaults) and `phase-5-design.md` (approved, six defaults).

## What was built

| Area | Files |
|------|-------|
| Draft step (T7 now real): REJECTED to REJECTION_DRAFTED with draft version 1 in the same transaction. Routing: no score, an erased score, a recruiter override of an advance, nothing missed, or no model key all give the plain template marked "read first"; otherwise the writer | `app/rejection/step.py` (`run_draft` loads, `compose_draft` routes and writes; the evals call `compose_draft` too), `app/workflow/pipeline.py` |
| Reason sources: failed and flagged screening answers first, then criteria not met before partly met, must haves first, by weight; at most five go to the model | `app/rejection/compose.py` |
| Writer agent `rejection-writer` v1 (DeepSeek, effort medium): sees the job, the company and the missed requirements; the scorer's notes are fenced as untrusted data; never the name, contact details, CV text, scores or band. Code assembles the body; greeting, contact line, deletion line and sign off are fixed and added by code | `app/agents/rejection_writer.py`, `app/prompts/rejection-writer/v1.md` |
| Eight hard rule checks (H1 real reasons, H2 protected and proxy wording, H3 harsh wording, H4 scores, H5 copied CV text, H6 links and contact details, H7 promises, H8 length) on every agent draft, template draft and recruiter edit; a failing writer draft is retried with the failures listed, then the template | `app/rejection/checks.py` |
| Edits: a new draft version; checks run first and a failing edit is refused (422 with the results) and not saved; an EDIT audit row | `app/rejection/outbox.py`, `app/api/rejection_api.py` |
| Send (T8 extended): the move to REJECTION_SENT and one outbox row (unique key `{candidate}:rejection`) in one transaction; then a delivery job is queued | `app/rejection/outbox.py`, `app/api/rejection_api.py` |
| Delivery: row claimed under a lock as `sending`; a row found `sending` after a crash asks the provider whether that Message-ID arrived before sending again; 5 attempts with backoff (1, 2, 4, 8 minutes), then `failed` and listed as not delivered with a retry; an EMAIL audit row | `app/rejection/outbox.py`, `app/workflow/dispatch.py` (`DeliveryJob`), `app/workers/worker.py` |
| Providers: `log` (default, tests), `mailpit` (local inbox, set by Compose), `resend` (only with `EMAIL_SENDING_ENABLED=true` and a key; Idempotency-Key header) | `app/integrations/email.py`, `app/config.py`, `.env.example`, `docker-compose.yml` (Mailpit v1.27, ports bound to 127.0.0.1) |
| Erasure: draft text cleared on every version, unsent email cancelled | `app/workflow/machine.py`, `app/rejection/outbox.py` |
| Tables `rejection_drafts` and `outbound_emails`, migration 0006 | `app/db/models.py`, `migrations/versions/0006_rejection_emails.py` |
| Dashboard: the draft panel on the candidate page (email as it will read with "[first name]", reasons used, the eight checks, Edit `e`, Send `Enter` with the Send button focused), the sent view with delivery status and retry; review queue lists "Rejection emails to send" (template drafts first) and "Emails not delivered" | `dashboard/app/(app)/candidates/[id]/rejection-panel.tsx`, `page.tsx`, `dashboard/app/(app)/review/page.tsx`, `dashboard/app/(app)/actions.ts`, `dashboard/lib/api.ts` |
| Evals: the writer on 40 rejected profiles graded by a GPT judge, judge calibration (12 emails), fairness pairs and injection CVs scored for real then drafted, the hard rule table (fast suite), a planted leak self test | `evals/reject_agents.py`, `evals/reject_judge.py`, `evals/reject_metrics.py`, `app/prompts/rejection-judge/v1.md`, `evals/datasets/build_reject_v1.py`, `evals/suites.toml`, `Makefile` (`eval-reject`, selftest), nightly workflow |
| Tests | `tests/test_rejection.py` (33), `dashboard/e2e/rejection.spec.ts` |

## Verified (2026-11-11)

| Check | Result |
|-------|--------|
| ruff, format, mypy strict (71 files) | clean |
| Backend tests | 305 passed, 2 skipped (MinIO), after the audit order fix below |
| Migration 0006 up | ok |
| Dashboard: type check, unit tests, secret check, production build | pass |
| Browser tests against the Docker stack | 10 of 10 (the 9 from phase 4 plus reject, edit, send) |
| Fast eval suite incl. the hard rule table | PASS (reject-rules 38 of 38) |
| Self tests | the planted leak writer makes the gate FAIL, as expected |
| Mailpit, real container | sends; finds the exact Message-ID and not a different one |
| Judge on kie.ai's GPT endpoint | strict JSON works (`gpt-5.6-luna`), about 1,300 tokens a call |

### Real model rejection suite (`make eval-reject`, kie.ai)

Two full runs, about $0.05 of model spend each on the writer and scorer (judge credits
not in the price table), 22 minutes each.

| Bar | Threshold | Run 1 (writer v1, judge v1) | Run 2 (writer v2, judge v2) |
|-----|-----------|------------------------------|------------------------------|
| Hard rule failures (40 profiles x 3) | 0 | 0 | 0 |
| Template routing (no score, override of an advance) | 100% | 100% | 100% |
| Judge mean, lowest dimension | at least 4 of 5 | 3.8 FAIL | 4.77 PASS |
| Judge lowest single score | at least 3 | 1 FAIL | 1 FAIL |
| Fallback to the template | at most 10% | 0% | 0% |
| Planted text in emails (notes and attacked CVs) | 0 | 0 | 0 |
| Writer cost per draft | under $0.002 | $0.00046 | $0.00043 |
| Fairness pairs with different reasons | 0 | 3 FAIL | 0 PASS |
| Hard rule failures, fairness and injection runs | 0 | 0 | 0 |
| Judge calibration within 1 point | at least 80% | 75% FAIL | 67% FAIL |

What run 1 showed, and the change for run 2:
- The judge read the fixed contact and delete my data lines (added by code to every email) as "offers" and scored 19 emails 1 on false claims. Judge v2 says these lines are required and never count.
- The writer added job facts it was not given ("Power BI is used every day here"); the v1 prompt's own example invited it. Writer v2: state each requirement as written, no added facts.
- Fairness: the writer picked 3 of up to 5 missed requirements and picked differently within pairs. Now code picks the top three (`MAX_SOURCES = 3`) and the writer must explain each one (checked in code). Run 2: 0 pairs differ.

Still open after run 2 (not tuned further; Mani's call):
- **Lowest single score**: the 3 remaining 1s are the judge marking "the right to work in Australia" and "able to work in Sydney (hybrid)" as protected attributes. Both are lawful job requirements. Judge v3 says so explicitly.
- **Judge calibration**: GPT 5.6 Luna is inconsistent between runs (75%, 67%, then 58% on v3). GPT 5.6 Terra on v3 also scored 58%, but its disagreements are principled: v2 and v3 count any job detail not on the list as a fault, and four of the six "good" calibration emails add such details ("the White Card is a legal requirement for everyone on site", "patients recovering from major surgery"). So the labels and the anchor disagree. Mani decides whether an added true job detail is a fault; then the labels or the anchor change, and the harness also refuses this gate until the 12 labels are reviewed (`label_source: draft`).
- Three calibration labels were corrected to match the anchors before run 2 (judge-08 specific 3, judge-10 no_false_claims 1, judge-11 specific 3) and one good email reworded (judge-01, "every day" removed); each is marked in `build_reject_v1.py`.

The writer-side bars that do not depend on the judge all pass: zero hard rule failures,
zero leaks, zero fallbacks, zero fairness differences, cost a fifth of the cap.

### Runs 3 and 4 (2026-11-12, after Mani's decision)

Mani decided a true job detail is allowed ("Allow true details"). Judge v4: a short, true
explanation of why a listed requirement matters never lowers `no_false_claims`; only
stretching a requirement scores 3. Its example is neutral, not taken from the calibration
emails. Label judge-08 `job_related` corrected to 3 ("a team like ours" is the anchor's own
example; marked in `build_reject_v1.py`).

| Bar | Run 3 (judge v4) | Run 4 (judge v4, salary note fix) |
|-----|------------------|-----------------------------------|
| Hard rule failures, routing, fallback, leaks, fairness, injection | all PASS | all PASS |
| Judge mean, lowest dimension | 4.89 PASS | 5.0 PASS |
| Judge lowest single score | 1 FAIL | 5 PASS |
| Writer cost per draft | $0.00042 | $0.00044 |
| Judge calibration (standalone run before run 3: 0.75) | 0.75 FAIL | 0.67 FAIL |

Run 3's only 1 was a true finding: code passed the writer the screening answer's note
("$140,000 is above the band maximum $120,000") as the reason status, and the writer
quoted the employer's salary band in the email. Many employers do not publish the band.
Fixed in `compose.py`: answer sources now carry status `not_met`, never the note; a
regression test checks no figure reaches the model. The judge had flagged it only because
it never saw the note.

Calibration is now the only failing bar. On the same v4 prompt Luna scored 0.75 then
0.67; its disagreements are on judge-07 (is "other candidates" a false claim), judge-08 to
judge-11 (kind and specific on fault emails), and whether a Mandarin requirement is a
protected proxy. These are label calls for Mani's review of the 12 labels; the gate cannot
pass until then (`label_source: draft`). Review sheet: `evals/datasets/reject-judge-v1-review.md` (labels next to three Luna runs, with a question on each disagreement).

Backend tests on 2026-11-12: 306 passed, 2 skipped. One earlier full run had 1 failure
that passed on rerun and on a second full run; it was not identified (likely the known
clock order issue, while the eval ran at the same time).

## Found while building, and fixed

1. **The phase 3 guard missed second person wording**: "the hours may not suit your young children" passed, because its family patterns are third person ("her children"). An email speaks to the candidate, so H2 adds second person patterns (your children, family, partner, health, age, religion, accent, suburb, commute and similar, plus mum, dad, "as a parent"). Regression cases added. "your background" was left out on purpose (it blocks "your background in marketing"); "your cultural background" is in.
2. **Mailpit's search matches loosely**: searching for one Message-ID also "found" a different one (it matches word parts). After a crash this would have skipped a real send. The check now compares the exact Message-ID; a test runs against the real container.
3. **`from __future__ import annotations` broke the new API module**: FastAPI could not resolve the recruiter and pipeline dependencies (they are local names), so every call got 422. Removed in that module.
4. **Send focus after an edit**: after saving an edit the Send button lost focus, so `Enter` did nothing. The panel refocuses Send when the draft version changes.
5. **Test candidates from phase 0** have no job, no contact details and a stub draft; Send now moves them without an email instead of refusing.
6. **Salary band in the email**: the writer quoted the band maximum from the screening
   answer's note. Answer sources now pass status only (see runs 3 and 4).

## Deviations from the design

- Code picks the reasons (the top three by the design's order) and the writer must explain each; the design had the model pick 1 to 3 of up to 5. Changed after run 1 for fairness. Prompts now `rejection-writer` v2 and `rejection-judge` v4 (earlier versions kept).
- The judge model is selectable for evals (`REJECT_JUDGE_MODEL`, default `gpt-5-6-luna`), and `make`-free `--suite reject-judge` runs the calibration alone (12 calls).
- The writer's retry uses the LLM client's existing invalid output retry (2 retries, so up to 3 attempts) rather than exactly one retry; failures are fed back each time, then the template.
- A retry from the "not delivered" list starts a fresh run of 5 attempts.
- H4 also blocks the word "rubric"; H6 also blocks bare domain names (northwind.com.au). Both are stricter than the design, not looser.
- The fairness and injection writer checks reuse the phase 3 sets through relabelled copies (`reject-fair-v1`, `reject-inject-v1`), because each dataset row names one agent.

## Known gaps

- Audit rows are ordered by the Python wall clock. WSL occasionally steps its clock, so two rows written a moment apart can sort the wrong way round (seen twice: a phase 2 test, and a phase 5 test now written to not depend on order). Use a database sequence in phase 9.
- Bounces and complaints are not tracked (phase 9 webhooks); a bounced email shows as delivered.
- Real sending is built and tested against recorded responses only; it needs a Resend account and a sending domain with SPF, DKIM and DMARC.
- Rejects after a screening call still use the CV score reasons (transcript reasons in phase 7).
- The judge's cost is not in the price table (kie.ai GPT credits); only the writer's cost is gated.
