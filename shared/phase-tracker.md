# Phase Tracker

Active phase: 2 (CV parsing + PII redaction): stages 01 to 03 done, 04 gate PASS awaiting Mani confirmation, 05 next.
Phase 1 still open: gate PROVISIONAL (all bars met on draft labels), 05 drafted; closes after Mani reviews the rubric-v1 labels.

Phase names and goals live in `references/master-plan.md` section 8. This file only
tracks progress.

| Phase | Name | Status | Eval gate | Date done | Notes |
|-------|------|--------|-----------|-----------|-------|
| 0 | Foundations + eval harness | done | PASS (2026-11-07, ac091bd) | 2026-11-07 | Design approved 2026-11-07. Dev setup done 2026-11-07: Ubuntu 24.04 (WSL2), Docker Engine + Compose, make, gh, uv, Python 3.12; working copy ~/code/recruit-agent. Build done 2026-11-07: 53 tests, lint clean, smoke call and evals run; CI green on ac091bd. Ship: readiness, demo script and post brief in stages/05-ship/output; clean clone check fixed blank secrets (54 tests). Repo made public 2026-11-07 |
| 1 | Jobs and intake | in progress | PROVISIONAL (2026-11-07, cbb5907: all 8 rubric bars met on draft labels) | | Brief and design approved 2026-11-07. Build 2026-11-07: live stack verified, CV encrypted in MinIO; provider switched to kie.ai DeepSeek; prompt v2; 145 tests, CI green. To close: label review, KIE_API_KEY secret, clean clone check, kie.ai spend cap |
| 2 | CV parsing + PII redaction | in progress | PASS pending confirmation (2026-11-08: all 10 bars) | | Brief and design approved 2026-11-07. Build done 2026-11-08: 173 tests, live parse verified, prompt cv-parser v2. Disk full incident recovered (temp cleared, WSL restart, Docker cache pruned) |
| 3 | Scoring engine + fairness + injection | not started | | | |
| 4 | Recruiter dashboard | not started | | | |
| 5 | Rejection email agent | not started | | | |
| 6 | Screening call agent | not started | | | |
| 7 | Transcript scoring | not started | | | |
| 8 | Booking call + calendar | not started | | | |
| 9 | Hardening + online evals | not started | | | |
| 10 | Public demo mode | not started | | | |
