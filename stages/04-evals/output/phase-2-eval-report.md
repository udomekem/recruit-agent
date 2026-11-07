# Phase 2 Eval Report

Date 2026-11-08 · Ubuntu 24.04 (WSL2) · agent `cv_parser`, prompt `cv-parser` v2, model
`deepseek-v4-1-flash` via kie.ai (reported `deepseek-v4.1-flash`), effort low.
Dataset `cv-v1`: 30 synthetic CVs rendered to real files (9 single column PDF, 6 two
column PDF, 5 Word with tables, 4 Word with header and footer contact, 2 hidden injection
PDFs, 2 image only PDFs, plus 4 with stated protected attributes and 6 with referees),
3 runs each. Labels are `rule`: exact by construction from the source data, so the gate
is not blocked on a human label review (unlike phase 1).

**Status: gate PASS, awaiting Mani's confirmation at the stage 04 checkpoint.**

## Commands run

| Where | Command | When |
|-------|---------|------|
| Local, real model | `python -m evals run --suite cv` | 2026-11-07 13:01 UTC, report `cv-20261107T130109Z` (code as committed with this report) |
| Local | full test suite with real MinIO | 2026-11-08, 173 passed |
| Live stack | two applications parsed by the real worker | 2026-11-08 |

Langfuse experiment: https://jp.cloud.langfuse.com/project/cmw3jw4qd000mad0em81dw2so/experiments/results?baseline=37c02eaba62ccbe1

## Bars (84 parses of 28 text CVs plus 6 image only checks, $0.055 total)

| Bar | Metric | Threshold | Result (worst of 3, spread) | Status |
|-----|--------|-----------|------------------------------|--------|
| Identifiers | strings left in the redacted copy | 0 | 0 | PASS |
| Protected attributes | stated values left in the redacted copy | 0 | 0 | PASS |
| Data minimisation | intake name, email, phone in text sent to the model | 0 | 0 | PASS |
| Fields | field accuracy | ≥ 0.95 | 0.985 (0.015) | PASS |
| Valid output | parsed, retries allowed | 100% | 100% | PASS |
| Consistency | identical work history across runs | ≥ 90% of CVs | 100% | PASS |
| Over redaction | job terms lost | ≤ 2% | 0% | PASS |
| Injection | planted terms in the profile | 0 | 0 | PASS |
| Image only | to review with no model call | 2 of 2 | 6 of 6 (2 CVs x 3 runs) | PASS |
| Cost | mean per parsed CV | ≤ $0.01 | $0.00066 | PASS |

## History (same dataset)

| Run (UTC) | Change | Field accuracy | Protected leaks | Other |
|-----------|--------|----------------|-----------------|-------|
| 12:30 | prompt v1 | 0.890 | 0 | study year blank on every CV |
| 12:41 | prompt v2 (study year) | 0.934 | 0 | two runs returned empty profiles |
| 12:50 | empty profile rejected | 0.956 | 1 | model missed "Proud mum of three" once |
| 13:01 | family phrases removed by code | **0.985** | **0** | all bars pass |

## Phase 2 done criteria

| Done criterion (brief) | Evidence | Status |
|------------------------|----------|--------|
| Text extracted from every text PDF and DOCX, incl. two column, tables, header and footer | extraction check on all 28 text CVs; `test_docx_header_table_footer_in_order` | PASS |
| Known and pattern identifiers removed before the model; the exact text sent is inspected | minimisation bar 0; `test_model_never_receives_the_applicants_identifiers` | PASS |
| Schema valid profile; values not in the text rejected; failure to review with a reason | `test_values_must_come_from_the_cv`, `test_invalid_parser_output_goes_to_review_without_personal_data`; valid 100% | PASS |
| Image only PDF to review, no model call | bar 6 of 6; `test_scanned_cv_goes_to_review_without_a_model_call` | PASS |
| Redacted copy and profile stored; neither in traces or logs | `test_parse_stores_redacted_copy_and_profile`, `test_no_personal_data_in_traces_or_logs` | PASS |
| Live application APPLIED to PARSED to SCORED on the Docker stack | live check 2026-11-08 | PASS |
| Erasure clears profile and redacted copy | `test_erase_deletes_parse` | PASS |
| Parser and redaction evals meet every bar, real model, three runs | table above | PASS |
| Recruiter API reads the redacted copy and profile | `GET /candidates/{id}/parse` | PASS |

## Gate

**PASS.** To be confirmed by Mani. Stage 05 (readiness, demo, post brief) follows.
