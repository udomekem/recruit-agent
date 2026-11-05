# Eval Harness Spec

## Dataset format (JSONL, one case per line)

```json
{"id": "cv-017", "agent": "cv_scorer", "tags": ["career-gap", "injection"],
 "input": {"...": "..."}, "expected": {"band": "strong", "must_flag": ["injection"]},
 "label_source": "hand", "notes": "why this case exists"}
```

- `label_source`: `hand`, `rule`, or `judge` (judge labels are never ground truth).
- Datasets are versioned; a changed label bumps the dataset version.
- Counterfactual pairs share a `pair_id` and differ in exactly one attribute.

## Runner contract

A runner takes a dataset and an agent version and returns per-case results plus
aggregate metrics. It records prompt version, model id, dataset version, git sha.

## Report format

```markdown
# Phase N Eval Report
Date, git sha, commands run, agent and prompt versions.

| Bar | Metric | Threshold | Result (3 run spread) | Status |
|-----|--------|-----------|-----------------------|--------|

## Failing and borderline cases
Case id, expected, got, likely cause.

## Compared with last run
Regressions and improvements.

## Gate
PASS only if every bar is PASS.
```

## Simulated calls
An LLM plays the candidate from a persona card (goal, behaviour, quirks). Score
the run on: all required confirmations captured, consent handled correctly, stays
in scope, ends cleanly, duration. Run text-loop simulations first; real Vapi web
calls only for the release set.

## Judges
Rubric based, score 1 to 5 with a written reason. Calibrate against a human labelled
set before use and report agreement.
