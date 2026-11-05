# Stage 04: Evals

Create the datasets, run the evals, compare against the phase's bars, and gate the
phase. No pass, no ship.

## Inputs

| Source | File/Location | Section/Scope | Why |
|--------|--------------|---------------|-----|
| Brief | `../01-brief/output/phase-N-brief.md` | Eval bars table | Metrics and thresholds |
| Design | `../02-design/output/phase-N-design.md` | Eval case plan | Dataset plans |
| Build | `../03-build/output/phase-N-build-log.md` | How to run | Entry points |
| Plan | `../../references/master-plan.md` | Section 7 rows for agents this phase touches | Pass bars and personas |
| Reference | `references/eval-harness-spec.md` | Full file | Dataset and report formats |
| Code | `../../product/evals/` | Runners and datasets for this phase | Existing harness |

## Process

1. Build or extend datasets in `product/evals/datasets/` per the design's plan.
   Synthetic data only. Label expected outputs and record how they were labelled.
2. Write or extend runners. For LLM judges, first check the judge against a small
   human labelled set.
3. Run `make eval` (and `make eval-full` when calls or simulations are in scope),
   three runs where consistency is a metric.
4. Compare each metric to its threshold. Mark PASS or FAIL. Include run to run spread.
5. For each FAIL, list failing cases and a likely cause. Do not change thresholds
   to pass; changing a bar needs a user decision recorded in the brief.
6. If FAIL: return to stage 03 with the failure list. Re-run after fixes.
7. **[Checkpoint]** Present the report. Ask the user to review failing and borderline
   cases and confirm the gate.
8. Save the report and update the tracker's eval gate column.

## Checkpoints

| After Step | Agent Presents | Human Decides |
|------------|---------------|---------------|
| 5 | Report with PASS/FAIL per bar, failing cases, causes | Accept gate, send back to build, or change a bar (recorded) |

## Audit

| Check | Pass Condition |
|-------|---------------|
| Coverage | Every bar in the brief appears in the report |
| Real runs | Numbers come from a run in this session, with command and date |
| Adversarial | Each agent has injection or edge cases in its dataset |
| No leakage | Datasets contain no real candidate data |
| Honest gate | Overall gate is PASS only if every bar is PASS |

## Outputs

| Artifact | Location | Format |
|----------|----------|--------|
| Eval report | `output/phase-N-eval-report.md` | Markdown per harness spec |
| Datasets and runners | `../../product/evals/` | JSONL and Python |
