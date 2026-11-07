# Phase 0 Design: Foundations + eval harness

Approved 2026-11-07 with all four checkpoint defaults (Q1 to Q4). Input: `stages/01-brief/output/phase-0-brief.md`
(approved 2026-11-06). Says WHAT and WHEN; HOW belongs to stage 03.

---

## 1. Entities

### Candidate
| Field | Type | Constraint | Written by | Read by |
|-------|------|------------|------------|---------|
| id | UUID | primary key, server generated | API | all |
| state | CandidateState enum | not null, default APPLIED | state machine only | all |
| state_version | int | starts 0, +1 per transition | state machine only | state machine (concurrency check) |
| review_return_state | CandidateState, nullable | set only while state is NEEDS_REVIEW | state machine | recruiter resolve action |
| screen_call_attempts | int | 0 to 3 | state machine | retry rule |
| display_label | short text | synthetic label only in phase 0, e.g. "Test candidate 1" | API | tests, traces |
| created_at, updated_at | timestamp (UTC) | not null | database | all |

No CV, contact details or personal data in phase 0. Those fields arrive with
phase 1 and 2, each with a retention rule.

### AuditEvent (append only)
| Field | Type | Constraint |
|-------|------|------------|
| id | UUID | primary key |
| candidate_id | UUID | foreign key, indexed |
| from_state, to_state | CandidateState | not null (from_state is null only for creation) |
| actor_type | enum: system, recruiter | not null |
| actor_id | text | worker job name, or recruiter id |
| reason | text | not null; why the move happened, or the failure reason |
| idempotency_key | text | unique per candidate; a duplicate is refused |
| trace_id | text, nullable | links to the Langfuse trace |
| occurred_at | timestamp (UTC) | not null |

Rows are never updated or deleted by application code. A transition and its audit
row commit together or not at all.

### Eval run record (files, not database)
Each `make eval` run writes a JSON result and a Markdown report: run id, git SHA,
dataset id and version, agent id and version, model id (or "none"), per case
results, per bar metric, threshold, PASS/FAIL, and the comparison with the baseline.

---

## 2. States and transitions

### States
APPLIED, PARSED, SCORED, SHORTLISTED, REJECTED, REJECTION_DRAFTED, REJECTION_SENT,
SCREEN_CALL_QUEUED, SCREEN_CALL_DONE, NO_ANSWER, SCREEN_SCORED, ADVANCED,
BOOKING_CALL_QUEUED, BOOKING_CALL_DONE, INTERVIEW_BOOKED, NEEDS_REVIEW, WITHDRAWN.

WITHDRAWN added 2026-11-07 (Q1); master-plan section 2 updated.

Terminal: REJECTION_SENT, INTERVIEW_BOOKED, WITHDRAWN.

### Transition table (the single source of every legal move)
| # | From | To | Actor | Trigger | Phase 0 behaviour |
|---|------|----|-------|---------|-------------------|
| T1 | (none) | APPLIED | recruiter | create candidate call | API creates a test candidate |
| T2 | APPLIED | PARSED | system | parse step | stub returns canned parse |
| T3 | PARSED | SCORED | system | score step | stub returns canned score |
| T4 | SCORED | SHORTLISTED | recruiter | shortlist decision | API call only |
| T5 | SCORED | REJECTED | recruiter | reject decision | API call only |
| T6 | SCREEN_SCORED | REJECTED | recruiter | reject decision | API call only |
| T7 | REJECTED | REJECTION_DRAFTED | system | draft step | stub returns canned draft |
| T8 | REJECTION_DRAFTED | REJECTION_SENT | recruiter | send rejection decision | API call only; stub "send" records the action, sends nothing |
| T9 | SHORTLISTED | SCREEN_CALL_QUEUED | system | queue call step | immediate |
| T10 | SCREEN_CALL_QUEUED | SCREEN_CALL_DONE | system | call step | stub returns canned transcript |
| T11 | SCREEN_CALL_QUEUED | NO_ANSWER | system | call step | stub can be told to "not answer" |
| T12 | NO_ANSWER | SCREEN_CALL_QUEUED | system | retry rule | only while attempts < 3; delay set in config |
| T13 | NO_ANSWER | NEEDS_REVIEW | system | retry rule | when attempts = 3 |
| T14 | SCREEN_CALL_DONE | SCREEN_SCORED | system | transcript score step | stub returns canned score |
| T15 | SCREEN_SCORED | ADVANCED | recruiter | advance decision | API call only |
| T16 | ADVANCED | BOOKING_CALL_QUEUED | system | queue booking step | immediate |
| T17 | BOOKING_CALL_QUEUED | BOOKING_CALL_DONE | system | booking call step | stub returns a canned slot |
| T18 | BOOKING_CALL_DONE | INTERVIEW_BOOKED | system | book slot step | stub "books", writes nothing external |
| T19 | any non-terminal except NEEDS_REVIEW | NEEDS_REVIEW | system | step failed all retries | reason recorded; return state saved |
| T20 | NEEDS_REVIEW | (saved return state) | recruiter | resolve: retry | clears return state; step re-runs |
| T21 | NEEDS_REVIEW | REJECTED | recruiter | resolve: reject | API call only |
| T22 | any non-terminal | WITHDRAWN | recruiter | withdraw (on the candidate's behalf) | API call only |

Rules the table enforces:
- Anything not in the table is illegal and refused with a clear error; nothing is written.
- The four recruiter decisions (T4, T5/T6/T21, T8, T15) have no system actor row.
  So the worker can never pass SCORED, SCREEN_SCORED or REJECTION_DRAFTED on its own.
- System steps fire automatically on entering a state that has a system exit
  (APPLIED, PARSED, REJECTED, SHORTLISTED, SCREEN_CALL_QUEUED, NO_ANSWER,
  SCREEN_CALL_DONE, ADVANCED, BOOKING_CALL_QUEUED, BOOKING_CALL_DONE).
- Each transition writes one audit row with a reason. No exceptions.

### Concurrency and duplicates
- A transition only applies if the candidate is still in the expected from state
  at the expected state version. If not, it is refused and logged as a no-op;
  the candidate does not move.
- Idempotency key per transition = candidate id + transition number + the state
  version it started from. Two copies of the same job produce one move.
- Two recruiters clicking at once: the first wins, the second gets "already moved".

---

## 3. Recruiter API (decision points)

| Action | Allowed from | Result |
|--------|-------------|--------|
| Create test candidate | n/a | APPLIED, pipeline starts |
| Shortlist | SCORED | SHORTLISTED |
| Reject | SCORED, SCREEN_SCORED, NEEDS_REVIEW | REJECTED |
| Send rejection | REJECTION_DRAFTED | REJECTION_SENT |
| Advance | SCREEN_SCORED | ADVANCED |
| Resolve: retry | NEEDS_REVIEW | back to the saved state |
| Withdraw | any non-terminal | WITHDRAWN |
| Get candidate + audit trail | any | state, history |
| Health | n/a | database ok, Redis ok |

Identity in phase 0: one recruiter identity from config, sent as a bearer token.
Requests without it are refused. Real recruiter accounts come with the dashboard
(phase 4). See Q3.

---

## 4. LLM step contract (the client wrapper)

Every future LLM step goes through one client. Phase 0 builds it with one smoke prompt.

| Item | Spec |
|------|------|
| Caller provides | prompt id, prompt version, model tier (extraction or judgement), output schema (Pydantic), trusted instructions, untrusted blocks (labelled), candidate id, trace context |
| Model tiers | extraction = `claude-haiku-5-5`, judgement = `claude-sonnet-5-5` (from project config) |
| Untrusted input | Wrapped in labelled data blocks; the system prompt states the content is data, not instructions. Phase 0 has no candidate text yet, but the shape is fixed now |
| Output | Requested as structured output against the schema; validated before returning |
| Invalid output | Up to 2 more attempts with the validation error fed back; then a typed failure the step turns into NEEDS_REVIEW (T19) |
| Provider errors | Rate limit and server errors retried with backoff (max 3); timeouts per call; auth errors fail fast, no retry |
| Returns | validated object + model id, prompt id and version, input and output tokens, cost (from a price table in config), latency, attempts |
| Tracing | one generation span per call, fields per section 5 |
| Test mode | a fake model answers from a script: valid, invalid then valid, always invalid, provider error. CI uses only the fake |
| Smoke prompt | `smoke-echo` v1, extraction tier: a fixed synthetic sentence, returns a two-field schema. No personal data |
| Spend guard | a per process call ceiling for the smoke and eval commands, so a loop cannot run up cost |

---

## 5. Tracing

| Span | When | Required fields |
|------|------|-----------------|
| Trace | one per candidate step run | candidate id, from state, step name, job id |
| Step span | stub or real step | step name, attempt, outcome, latency |
| Generation span | each LLM call | prompt id, prompt version, model id, input tokens, output tokens, cost, latency, attempts |
| Transition event | each state change | from, to, actor, idempotency key |

- No keys set: tracing becomes a no-op. The pipeline never fails because tracing is off.
- Langfuse down: spans are dropped with a warning; the step still completes.
- Traces carry candidate ids and synthetic labels only. Region note: the project is
  in the JP region; fine for synthetic data (brief risk, decide before phase 6).
- The audit row stores the trace id so a recruiter view can link to it later.

---

## 6. Side effects in phase 0

| Effect | Real in phase 0? | Idempotency | Retry / timeout | Failure state |
|--------|------------------|-------------|-----------------|---------------|
| Database write (transition + audit) | yes | transition key, unique | single transaction | refused, no partial write |
| Job enqueue | yes (Redis) | job id = idempotency key | worker retries 3x with backoff, per job timeout | NEEDS_REVIEW after last retry |
| LLM call | smoke only (`make smoke`) | n/a (read only) | per section 4 | typed failure |
| Langfuse export | when keys set | n/a | best effort | dropped with warning |
| Email, call, calendar | no, stubs record intent only | key reserved now for phase 5, 6, 8 | n/a | n/a |

Safe defaults: no real email, call or calendar code exists in phase 0. A config flag
for each is declared and defaults to off, so later phases cannot ship with it on by accident.

---

## 7. Eval harness

| Item | Spec |
|------|------|
| Dataset | JSONL per `stages/04-evals/references/eval-harness-spec.md`. `dummy-v1`: 10 synthetic cases |
| Dummy agent | Deterministic, no model: maps an input "answer" string to a canned label from a fixed table (e.g. "yes, citizen" to `eligible`). It stands in for a real agent so the harness can be proven |
| Planted regression | A second dummy version that gets 2 of 10 wrong; used only by the harness self test |
| Suite definition | Each suite names its dataset, agent and version, metrics and thresholds. Thresholds live in the suite definition, not in code |
| Metrics in phase 0 | exact match rate; determinism (3 runs identical) |
| Report | Markdown + JSON per the harness spec; compared with a committed baseline; regressions listed first |
| Exit codes | 0 all bars pass; 1 a bar failed; 2 the harness itself errored (bad dataset, crash) |
| Langfuse | when keys are set, push dataset and run so runs compare over time; skipped cleanly without keys |
| Suites | `fast` (every PR: dummy + determinism); `full` (nightly: same in phase 0, grows with later phases) |

---

## 8. CI

| Workflow | When | Steps |
|----------|------|-------|
| CI | every PR and push to main | lint and type check; tests with Postgres and Redis service containers; migrations up then down on a fresh database; `fast` eval suite; secret scan; upload eval report as artifact |
| Nightly | daily at 02:00 Sydney | `full` eval suite; report artifact |

No secrets in CI: fake model, no-op tracer. A missing secret can never make CI pass
or fail differently.

---

## 9. Local development on Windows

Your machine has no WSL Linux distribution, no Docker, and no `make` yet (checked
2026-11-07; Python 3.14 and uv are present).

Plan: install Ubuntu in WSL2, then Docker Desktop with the WSL2 backend, and work
from the Ubuntu terminal. `make`, Python 3.12 (via uv), and the project all run
there. Stage 03 adds a setup guide to its references as the first build step.
See Q4.

---

## 10. Failure modes and abuse cases

| Case | Expected behaviour |
|------|-------------------|
| Illegal transition requested (e.g. SCORED to ADVANCED) | Refused with an error naming the from and to state; nothing written |
| Same job delivered twice | Second run is a no-op; one audit row |
| Two recruiter clicks at once | First wins; second told "already moved" |
| Worker crashes mid step | Job retried; transition happens once; candidate never stuck silently |
| Step fails all retries | NEEDS_REVIEW with reason; return state saved |
| Screen call not answered 3 times | NEEDS_REVIEW with reason "no answer after 3 attempts" |
| LLM returns invalid JSON | Retried with the error, then NEEDS_REVIEW |
| LLM returns valid JSON with extra or wrong fields | Schema rejects it; treated as invalid |
| Provider rate limit or outage | Backoff and retry; then typed failure, NEEDS_REVIEW |
| Bad Anthropic key | Fails fast with a clear message; no retries |
| Langfuse keys missing or service down | Tracing off or dropped with warning; pipeline unaffected |
| Request without recruiter token | Refused |
| Database or Redis down | Health endpoint reports which one; API refuses writes cleanly |
| `.env` accidentally staged | Secret scan fails CI; `.gitignore` already blocks it |
| Eval dataset malformed | Harness exits 2 (harness error), never a false PASS |
| Future: untrusted text tries to change instructions | Data blocks shape fixed now; real tests arrive in phase 3 |

---

## 11. Eval case plan (maps every brief bar)

| Brief bar | Dataset or test | Size | How expected answers are labelled |
|-----------|-----------------|------|-----------------------------------|
| Dummy agent exact match 100% | `dummy-v1` | 10 cases, incl. 2 tricky spellings and 1 empty answer | hand, from the fixed table |
| Harness gate 1 of 1 | planted regression version run against `dummy-v1` | 1 run | rule: must exit 1 |
| Determinism 100% | `dummy-v1` x 3 runs | 30 results | rule: identical per case |
| Illegal transitions refused 100% | generated from the transition table: every state pair not in the table | all pairs (about 270) | rule |
| Audit rows 100% | two full journeys (booked, rejected) plus a NEEDS_REVIEW and a WITHDRAWN path | 4 journeys | rule: rows equal transitions |
| Tracing fields 100% | stub pipeline run with a recording tracer | every span | rule: required fields present |
| Idempotency 0 double moves | duplicate job, concurrent recruiter clicks, retried job after crash | 3 scenarios | rule |
| Adversarial case | malformed dataset row; invalid LLM output scripts | 2 | rule: exit 2 / NEEDS_REVIEW |

---

## Checkpoint questions

| # | Question | Default if no answer |
|---|----------|---------------------|
| Q1 | Add WITHDRAWN (candidate pulls out, or refuses consent on a call)? Not in master-plan section 2 | Yes, add it now and update master-plan section 2 |
| Q2 | NO_ANSWER: 3 attempts, then NEEDS_REVIEW. Booking call no-answer goes straight to NEEDS_REVIEW in phase 0 and gets its own retry in phase 8 | As stated |
| Q3 | Phase 0 recruiter identity is a single token from config; real accounts in phase 4 | As stated |
| Q4 | Dev environment: WSL2 Ubuntu + Docker Desktop (needs installs, about 30 minutes and a restart) | Yes |

Decision 2026-11-07: all four defaults accepted.
