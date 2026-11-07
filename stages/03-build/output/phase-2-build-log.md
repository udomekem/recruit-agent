# Phase 2 Build Log: CV parsing and PII redaction

Built 2026-11-07 to 2026-11-08 in `~/code/recruit-agent`. Inputs: `phase-2-brief.md` and
`phase-2-design.md` (both approved, all defaults).

## What was built

| Area | Files |
|------|-------|
| Text extraction: PDF via pdfminer.six (MIT, layout aware), DOCX via python-docx (header, body, tables, footer in order); no text layer detection; time and page limits | `app/intake/extract.py` |
| Redaction steps 1 to 6: referees, own name (whole words, hyphenated, "SURNAME, First"), own email and phone (digits), patterns (email, phone, link, street, suburb + state + postcode across line breaks, DOB and age), labelled protected lines, family statements, model spans | `app/intake/redact.py` |
| CV parser agent + prompt v2 (v1 kept): values must appear in the text, date format and order checks, empty profile rejected, kind near misses mapped, output never traced | `app/agents/cv_parser.py`, `app/prompts/cv-parser/` |
| LLM client: every schema field required (nulls allowed), defaults stripped; `trace_output=False` switch | `app/llm/client.py` |
| Real parse step: decision object, CvParse row stored in the same transaction as the move (`extra` hook on `apply_transition`); audit reasons never quote CV content | `app/intake/parse.py`, `app/workflow/pipeline.py`, `app/workflow/machine.py` |
| CvParse table (redacted copy, profile, redaction counts, prompt, model, cost; no raw text) + migration 0003 | `app/db/models.py`, `migrations/versions/0003_cv_parses.py` |
| Storage read (`get`) | `app/integrations/storage.py` |
| API: `GET /candidates/{id}/parse` (redacted copy only); erasure deletes parse rows | `app/api/intake_api.py`, `machine.py` |
| Worker and API pass storage to the pipeline | `app/workers/worker.py`, `app/api/main.py` |
| Eval set `cv-v1`: 30 CVs rendered to real PDF and DOCX from structured source data (labels exact by construction), 5 samples for a spot check | `evals/datasets/build_cv_v1.py`, `cv-v1/`, `cv-v1.jsonl`, `cv-v1-samples/` |
| CV metrics and suite (10 bars), nightly real model run | `evals/cv_metrics.py`, `evals/agents.py`, `evals/suites.toml`, `.github/workflows/nightly.yml` |
| Tests (173 total) | `tests/test_redact.py`, `test_extract_and_parser.py`, `test_parse_step.py` |

## Verified (2026-11-08)

| Check | Result |
|-------|--------|
| `make lint` (ruff, format, mypy strict, 49 files) | clean |
| `make test` with real MinIO | 173 passed |
| Migration 0003 up, down, up; `alembic check` | ok |
| Code only redaction across the 26 text CVs | 0 identifiers left before the model, 0 of 238 job terms lost |
| Real model CV suite, 3 runs (`cv-20261107T130109Z`) | all 10 bars PASS (below) |
| Live stack: job, rubric, two applications (Word table, two column PDF), real worker parse | both PARSED then SCORED; roles, dates, skills exact; no identity in the redacted copy; $0.0004 and $0.0016 |

| Bar | Threshold | Result |
|-----|-----------|--------|
| Identifier leaks | 0 | 0 |
| Protected attribute leaks | 0 | 0 |
| Identifiers sent to the model | 0 | 0 |
| Field accuracy (worst of 3) | ≥ 0.95 | 0.985 |
| Valid output | 100% | 100% |
| Work history consistency | ≥ 0.90 | 1.0 |
| Over redaction | ≤ 2% | 0% |
| Injection effects | 0 | 0 |
| Image only to review, no model call | 2 of 2 | 2 of 2 |
| Cost per CV | ≤ $0.01 | $0.00066 |

## Found while building, and fixed

1. **My own generator split emails mid word** in narrow columns (`...@exa / mple.test`), which would have been an unfair leak test. Real CVs wrap between words; fixed.
2. **DeepSeek skipped optional list fields** (skills, personal spans came back null). The schema sent to the model now marks every field required (nulls allowed). Applies to all agents.
3. **Enum near misses** (`marital_status`, `family_status`): mapped to the closest allowed kind instead of failing the parse.
4. **Study year always blank** (all 28 CVs): prompt v2 says a year on the qualification line is the completion year; field description added. Field accuracy 0.89 to 0.93.
5. **Empty profiles passed every check** (nothing to check): an empty profile is now invalid and retried. Field accuracy 0.93 to 0.96.
6. **The model missed "Proud mum of three" in 1 of 3 runs**: common family and carer phrasings are now removed by code first; the model is the second line. Protected leaks 1 to 0; field accuracy 0.985.
7. **Validation errors could carry CV text into traces and audit reasons**: parser failures record only the error type.
8. **Disk full**: Docker rebuilds grew the WSL disk until C: had 0 MB and Ubuntu hit I/O errors. Recovered by clearing the Windows temp folder (2.72 GB, with Mani's approval), a WSL restart, and pruning the Docker build cache (2 GB inside Ubuntu). Repo checked with `git fsck`; all tests passed after. WSL sparse mode is refused by WSL ("potential data corruption"); not forced. A manual compact attempt did not run. C: now 2.13 GB free.

## Deviations from the design

- Step 5 gained free text family and carer phrases (finding 6); the design had them in step 6 (model) only.
- `Study.end` accepts a number and stores it as text.

## Known gaps

- Scanned CVs go to review; no OCR (by design, Q1).
- Dates kept on purpose (age proxy risk measured by phase 3 fairness tests).
- C: disk space is tight for further Docker work; a manual WSL disk compact or Windows Disk Cleanup is recommended.
- Data location decision for real candidate data (kie.ai processing) still open before phase 6.
