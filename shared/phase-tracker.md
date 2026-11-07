# Phase Tracker

Active phase: 1 (Jobs and intake), 01-brief, 02-design done; 03-build done except the real model eval run (blocked: Anthropic credit, label review)

Phase names and goals live in `references/master-plan.md` section 8. This file only
tracks progress.

| Phase | Name | Status | Eval gate | Date done | Notes |
|-------|------|--------|-----------|-----------|-------|
| 0 | Foundations + eval harness | done | PASS (2026-11-07, ac091bd) | 2026-11-07 | Design approved 2026-11-07. Dev setup done 2026-11-07: Ubuntu 24.04 (WSL2), Docker Engine + Compose, make, gh, uv, Python 3.12; working copy ~/code/recruit-agent. Build done 2026-11-07: 53 tests, lint clean, smoke call and evals run; CI green on ac091bd. Ship: readiness, demo script and post brief in stages/05-ship/output; clean clone check fixed blank secrets (54 tests). Repo made public 2026-11-07 |
| 1 | Jobs and intake | in progress | | | Brief and design approved 2026-11-07. Build 2026-11-07: 133 tests, live stack verified, CV encrypted in MinIO. Waiting: Anthropic credit, label review, GitHub secret |
| 2 | CV parsing + PII redaction | not started | | | |
| 3 | Scoring engine + fairness + injection | not started | | | |
| 4 | Recruiter dashboard | not started | | | |
| 5 | Rejection email agent | not started | | | |
| 6 | Screening call agent | not started | | | |
| 7 | Transcript scoring | not started | | | |
| 8 | Booking call + calendar | not started | | | |
| 9 | Hardening + online evals | not started | | | |
| 10 | Public demo mode | not started | | | |
