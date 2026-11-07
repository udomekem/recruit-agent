# Phase Tracker

Active phase: none (phase 0 done 2026-11-07; next: "start phase 1")

Phase names and goals live in `references/master-plan.md` section 8. This file only
tracks progress.

| Phase | Name | Status | Eval gate | Date done | Notes |
|-------|------|--------|-----------|-----------|-------|
| 0 | Foundations + eval harness | done | PASS (2026-11-07, ac091bd) | 2026-11-07 | Design approved 2026-11-07. Dev setup done 2026-11-07: Ubuntu 24.04 (WSL2), Docker Engine + Compose, make, gh, uv, Python 3.12; working copy ~/code/recruit-agent. Build done 2026-11-07: 53 tests, lint clean, smoke call and evals run; CI green on ac091bd. Ship: readiness, demo script and post brief in stages/05-ship/output; clean clone check fixed blank secrets (54 tests). Repo still private; making it public is a separate decision |
| 1 | Jobs and intake | not started | | | |
| 2 | CV parsing + PII redaction | not started | | | |
| 3 | Scoring engine + fairness + injection | not started | | | |
| 4 | Recruiter dashboard | not started | | | |
| 5 | Rejection email agent | not started | | | |
| 6 | Screening call agent | not started | | | |
| 7 | Transcript scoring | not started | | | |
| 8 | Booking call + calendar | not started | | | |
| 9 | Hardening + online evals | not started | | | |
| 10 | Public demo mode | not started | | | |
