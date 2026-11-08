# Phase 3 Build Log: Scoring engine, fairness and injection

Built 2026-11-08 in `~/code/recruit-agent`. Inputs: `phase-3-brief.md` (approved, five
defaults) and `phase-3-design.md` (approved, six defaults).

## What was built

| Area | Files |
|------|-------|
| Hidden text removal: PDF white text (unless on a dark filled shape) and text under 3 pt; DOCX hidden (vanish) and white runs; counted as `hidden_text` | `app/intake/extract.py`, `app/intake/parse.py` |
| Answer scorer (code only): right to work hard fail, salary above band flag (lower end of a range), location "no" flag, free text not scored, bulk uploads not answered | `app/scoring/answers.py` |
| Form input: salary accepts "95k" and ranges ("$95k to $110k"); "negotiable" and "PR pending" refused; salary field is now a text box with a hint | `app/domain/questions.py`, `app/templates/apply.html` |
| Score formula and band (code only): weighted points, reject / advance / maybe in the design's order, reasons and flags in plain words | `app/scoring/formula.py` |
| CV scorer agent + prompt v2 (v1 kept): one judgement per criterion; quotes must be in the redacted copy and not only placeholders; ids checked; reasons checked against protected wording; weights never sent; today's date in the instructions; output never traced | `app/agents/cv_scorer.py`, `app/prompts/cv-scorer/` |
| Reason guard: wording about a person (age, own family, gaps, illness, suburb, name) blocked in reasons; "aged care", "children's ward", "health sector" allowed | `app/domain/guard.py` |
| Injection phrases caught by code as well as the model | `app/agents/cv_scorer.py` |
| Score table + migration 0004 (one row per candidate per rubric; parse link set null on erasure) | `app/db/models.py`, `migrations/versions/0004_scores.py` |
| Real score step: PARSED to SCORED with the Score row in the same transaction; failures to NEEDS_REVIEW with no CV text | `app/scoring/step.py`, `app/workflow/pipeline.py` |
| Erasure clears quotes, reasons, answer values and flag text; keeps total, band, versions | `app/workflow/machine.py` |
| API: `GET /jobs/{id}/candidates` (ranked, flags, knockouts, `rubric_outdated` on read), `GET /candidates/{id}/score` (evidence per criterion) | `app/api/scores_api.py` |
| Eval sets: 3 fixed rubrics; `score-v1` 45 CVs from coverage plans; `fair-v1` 12 pairs; `inject-v1` 6 pairs; `answers-v1` 22 rows; 5 samples and a 10 CV review sheet | `evals/datasets/build_score_v1.py` and outputs |
| Metrics, suites (`score`, answer rules in `fast`, `selftest-score`), planted lift regression, nightly | `evals/score_metrics.py`, `evals/agents.py`, `evals/suites.toml`, `Makefile`, `.github/workflows/nightly.yml` |
| Tests (251) | `test_hidden_text.py`, `test_scoring_rules.py`, `test_cv_scorer.py`, `test_score_step.py`, parse step tests now score for real |

## Verified (2026-11-08)

| Check | Result |
|-------|--------|
| ruff, format, mypy strict (57 files) | clean |
| `make test` | 251 passed |
| Migration 0004 up, down, up | ok |
| Fast suite (no model): answer rules 22 of 22 | PASS |
| Self tests: dummy regression and the planted lift scorer (lift 50, 0% flagged) | gate FAIL as required |
| Phase 2 CV suite rerun after the extractor change | all 10 bars PASS (field accuracy 0.983) |
| Live stack, real model: BA job, two applications | BA CV 86.7 advance, quotes from the CV; nurse CV with right to work "no" 0.0 reject, that reason first; $0.0008 per score; ranked list correct |
| Real model score suite, 3 runs | all 11 bars PASS (run 3 below) |

## Eval runs

| Run | Prompt, effort | Result |
|-----|----------------|--------|
| 1 (`20261108T051324Z`) | v1, medium | 7 of 11 bars. Score within 10: 0.71; spread: 100 (two invalid outputs); injection lift 8.3 |
| 2 (`20261108T054338Z`) | v2, medium | 10 of 11 bars: bands, criteria and scores 100%, fairness 0, injection lift 0 and 100% flagged, $0.002 per candidate. Consistency: 2 CVs moved 10 points in one of three runs |
| 3 (`20261108T061010Z`) | v2, high (brief Q5) | **all 11 bars PASS**: bands 100%, criteria 99.7%, scores within 10 points 100%, largest spread 2.5 points, quotes 100% genuine, valid output 100%, fairness mean and worst pair difference 0, injection lift 0 and 100% flagged, $0.0025 per candidate (parse + score); suite spend $0.62 |

## Found while building, and fixed

1. **The model did not know today's date**, so a role "Sep 2023 to Present" could not be counted to 3 years; borderline CVs were marked partly met. The date now goes in the instructions (evals pass the dataset's own date, so labels do not drift).
2. **Experience in a different kind of role counted as partly met** (a customer service lead who ran SQL reports, a carpenter for "years supervising sites"). Prompt v2 says only that kind of role counts.
3. **A tool in the skills list was only partly met** ("Snowflake" for "experience with a cloud data warehouse"). Prompt v2: a listed skill, certificate or licence meets a criterion asking for it; partly met only for a related but different thing.
4. **Injection "lift" in run 1 was run to run noise**: hidden text is removed, so the clean and attacked copies the model read were identical. Fixed by the consistency work, not by an injection rule.
5. **The ad guard was the wrong tool for reasons about a person**: "close to retirement age" passed. A reason guard adds wording about the person; its false positive cases ("children's ward", "aged care") have tests.
6. **"Ignore ... rules" flagged ordinary CV lines** ("trained staff not to ignore safety rules"). The pattern now needs instruction words.
7. **A test line planted after the Referees heading was removed by redaction**, which also made the phase 2 sentinel test weaker. The extra line now sits before Referees.
8. **Erasure would have failed**: the score referenced the parse that erasure deletes. The link is now nullable and cleared.
9. **The salary box was a number field**, so a range could not be typed. Now a text box with a hint.

## Deviations from the design

- Prompt `cv-scorer` v2 replaces v1 (design named v1); v1 is kept for comparison.
- Effort raised to high under brief Q5 (consistency missed at medium).
- Clean twins of injection pairs and fairness pairs use good answers, not the base CV's edge case answers.
- `score_spread_max` bar written as at most 4.9 ("under 5 points", totals have one decimal); `fairness_mean_diff` as at most 1.99 ("under 2").

## Known gaps

- Rescoring when a new rubric is approved: phase 4 (flag shown).
- CV labels are built by design; Mani's spot check of 10 (`evals/datasets/score-v1-review.md`) is still to do (brief Q1).
- The scorer flags injection but does not detect text rendered as images or in PDF annotations.
- Data location decision for real candidate data still open before phase 6.
