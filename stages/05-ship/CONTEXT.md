# Stage 05: Ship

Close the phase: production readiness check, demo script, docs, and a brief for the
LinkedIn post. Nothing is published from here.

## Inputs

| Source | File/Location | Section/Scope | Why |
|--------|--------------|---------------|-----|
| Previous stage | `../04-evals/output/phase-N-eval-report.md` | Full file | Gate result and numbers |
| Brief | `../01-brief/output/phase-N-brief.md` | Goal and done criteria | What was promised |
| Build | `../03-build/output/phase-N-build-log.md` | Known gaps | Honest limits |
| Plan | `../../references/master-plan.md` | Section 8 row, post angle column | Post angle |
| Reference | `references/production-readiness-checklist.md` | Full file | The gate list |
| Reference | `references/linkedin-post-brief.md` | Full file | Post brief shape |
| Shared | `../../shared/phase-tracker.md` | Full file | Update on close |

## Process

1. Refuse to proceed if the eval gate is not PASS.
2. Run the readiness checklist for this phase; mark each item pass, fail, or not
   applicable yet, with evidence.
3. Write the demo script: exact steps, commands, expected output, a 60 to 90 second
   version for video.
4. Write the post brief: angle, the one number or surprise, what broke, what the eval
   showed, what is honestly not done. Include screenshots or clips to capture.
5. **[Checkpoint]** Present readiness, demo script, and post brief. Ask the user
   what to change and whether to close the phase.
6. On approval: tick the phase done in the tracker with date and eval gate.
   Commit the phase in `product/` if the user asks.

## Checkpoints

| After Step | Agent Presents | Human Decides |
|------------|---------------|---------------|
| 4 | Readiness result, demo script, post brief | Close the phase, or fix gaps first |

## Audit

| Check | Pass Condition |
|-------|---------------|
| Gate | Eval report overall status is PASS |
| Evidence | Every checklist pass cites a test, eval, or file |
| Honesty | Known gaps and limits are stated in the post brief |
| No secrets | Demo script and screenshots plan expose no keys or real personal data |

## Outputs

| Artifact | Location | Format |
|----------|----------|--------|
| Readiness report | `output/phase-N-readiness.md` | Checklist with evidence |
| Demo script | `output/phase-N-demo-script.md` | Steps and 60 to 90 second cut |
| Post brief | `output/phase-N-post-brief.md` | Per post brief reference |
