# Phase 5B Production Readiness

Date 2026-11-17 · closed by Mani 2026-11-18 · on top of `d8cccaa` · checked against
`stages/05-ship/references/production-readiness-checklist.md`.
Eval gate: PASS on every bar, accepted by Mani 2026-11-17
(`stages/04-evals/output/phase-5b-eval-report.md`).

| # | Check | Status | Evidence |
|---|-------|--------|----------|
| 1 | Workflow deterministic; LLM steps bounded | PASS | One new model step, the job matcher, between PARSED and scoring; code rules run first and code decides from its fit numbers (0.8 and a 0.3 gap). New transition T24 (system creates an inbox candidate) in `app/domain/states.py`, covered by the state machine tests |
| 2 | LLM output validated; failures go to review | PASS | The matcher's output is a schema; an invalid or unsure answer means "needs a job" (NEEDS_REVIEW with return state PARSED). `tests/test_inbox.py` (matcher sure and unsure). The inbox demo found a phase 2 parser bug here, fixed (see below) |
| 3 | No consequential action without a recruiter | PASS | Reading an inbox creates a candidate and scores it; nothing is shortlisted, rejected or sent except the acknowledgement (a receipt, not a decision). Unsure matches wait for the recruiter's pick (`/candidates/{id}/pick-job`, stale pick refused in tests) |
| 4 | Evidence exists in the source | PASS | Unchanged scorer; the matcher gives a short reason, never quotes, and its reason is not shown as evidence |
| 5 | Evals pass in CI | PASS (from the next push) | `match-rules` added to the fast suite (CI); the real model `match` suite is local (`make eval-match`, report `match-20261117T110232Z`). Browser tests in CI include the inbox and list tests |
| 6 | Fairness | PASS | Matcher sees the redacted CV only; 12 counterfactual pairs (name, gender, age signal, suburb): 0 matched differently (3 runs). Inbox subjects are stored redacted; the sender's name never reaches the dashboard (browser test) |
| 7 | Injection does not move outputs | PASS | 6 attacked CVs and subjects: 0 moved to another job. Subjects only select among existing jobs by code or exact title and never reach a model |
| 8 | Side effects idempotent | PASS | Unique (mailbox, provider message id); a message is claimed before fetching; two pollers at once and the same message twice at once give one candidate (tests). Acknowledgements go through the phase 5 outbox (one per candidate) |
| 9 | Retries, timeouts, dead letter; kill test | PARTIAL | Poll lease per mailbox, failed messages retried by the next poll (`attempts`), revoked access moves the mailbox to "needs reconnect". Dead letter and kill test stay in phase 9 |
| 10 | Traces with version, model, tokens, cost, latency | PASS | Matcher calls traced like every agent (Langfuse experiment links in the eval report); CV text not traced |
| 11 | Prompt and version stored with outputs | PASS | `job_matches.prompt_version` (`job-matcher-v2`) and the fit numbers stored with every match; test checks the version |
| 12 | Audit row per transition | PASS | T24 audit row with the route ("job from job code"), mailbox events for connect, label, pause, disconnect; picks are audited (tests) |
| 13 | Cost measured, limits set | PASS | $0.00037 per email for the matcher; per poll (50) and per day (500) limits per mailbox (`INBOX_MAX_PER_POLL`, `INBOX_MAX_PER_DAY`) |
| 14 | Compliance items | PASS (with open items) | Gmail scope is exactly `gmail.readonly` (a wider grant is refused and revoked), one label only, bodies never read, token encrypted (Fernet) and revoked on disconnect; collection notice in every acknowledgement (Privacy Act APP 5). Open: Google app verification before real recruiters; data location decision before real data |
| 15 | Defaults safe | PASS | No inbox connected by default; Gmail refused unless the OAuth client is set (test); Mailpit only on the local stack; real email sending still off |
| 16 | README and demo work from a clean checkout | PASS | Clean copy of the tree (no `.env`, `.venv`, `node_modules`): `make local-env` fills 9 secrets incl. `INBOX_TOKEN_KEY`; settings load; Compose config valid; ruff, mypy clean; 332 passed, 2 skipped; fast suite PASS; dashboard check PASS. README has the inbox section, `make demo-inbox` and `make eval-match` |
| 17 | No secrets or real personal data in git | PASS (CI confirms on push) | Scan of the 5 unpushed commits for key patterns (OpenAI, Google client secret and token, AWS, private keys): 0; no `.env` tracked; demo and eval CVs are synthetic |

## Found during ship: the CV parser refused CVs that leave out an employer or university

Running the inbox demo with the real model sent all three demo CVs to review: "cv parser
failed: LLMOutputInvalid". Cause (phase 2): `employer` and `institution` were required, so
for "Bachelor of Nursing" with no university, or "Seven years supervising sites" with no
employer, the model wrote "Not stated"; the check that every value appears in the CV
refused it, three times, and the candidate went to review. Real CVs do this often. The
offline demo seed never runs the parser, so only 7 real parses ever hit it.

Fix in `app/agents/cv_parser.py`: both fields may be null, placeholders ("Not stated",
"Unknown", "N/A") become null, and the check skips a null. Regression tests in
`tests/test_extract_and_parser.py`. Real model parser evals rerun (`make eval-cv`,
`cv-20261117T124003Z`): every bar PASS, field accuracy 99.6%, 0 leaks, $0.0007 per CV.

Demo rerun after the fix (API and worker rebuilt, real model, `make demo-inbox`): the
analyst CV matched by job code and scored; the nurse CV matched by plus address and
scored; the site CV with no job went to the matcher, which gave the Site Supervisor job
0.97 but found two open Site Supervisor jobs tied at 0.97, so it waited under "Needs a
job" with both suggested, as designed. Three acknowledgements delivered to Mailpit.
Backend tests 340 passed, 2 skipped (8 new parser cases); fast suite PASS; ruff, mypy
clean.

## Open items

1. Live Gmail: Mani's Google Cloud OAuth client and a test Gmail account (steps given
   2026-11-14). Then one live run: connect, label, email a CV, see it scored.
2. Push: the phase 5 and 5B commits (5 so far, plus this ship commit) wait for Mani's go ahead; CI runs on push.
3. Phase 5 gate still waits on Mani's review of the grader labels (judge-10 note).
4. Google app verification (phase 10) before any recruiter outside the test users.
5. Older: phase 3 CV spot check, phase 1 rubric labels, kie.ai spend cap, key rotation,
   data location decision.
