# Stage 01: Brief

Turn one phase row of the master plan into a precise brief: goal, scope, done
criteria, and the eval bars that gate it.

## Inputs

| Source | File/Location | Section/Scope | Why |
|--------|--------------|---------------|-----|
| Shared | `../../shared/phase-tracker.md` | Full file | Which phase is next |
| Shared | `../../shared/project-config.md` | Decisions table | Stack and constraints |
| Plan | `../../references/master-plan.md` | Section 8 row for this phase; section 7.1 rows for agents this phase touches; section 1 rules this phase most exercises | Scope, bars, rules |
| Reference | `references/brief-template.md` | Full file | Brief shape |
| Previous phase | `../../shared/phase-tracker.md` | Notes column | Carry over any debt |

## Process

1. Confirm the phase number with the user (default: next not started in the tracker).
2. Read the phase row, related eval rows, and the production rules it exercises.
3. Fill `references/brief-template.md`: goal, in scope, out of scope, done criteria,
   eval bars with metric and threshold, accounts or keys needed, risks.
4. List open questions from master-plan section 10 that this phase must answer.
5. **[Checkpoint]** Present the brief. Ask: right scope? bars right? answer the open questions?
6. Run the audit. Save to output.
7. Set the phase to "in progress" in the tracker.

## Checkpoints

| After Step | Agent Presents | Human Decides |
|------------|---------------|---------------|
| 4 | Full brief with scope, bars, open questions | Scope cuts, bar changes, answers to open questions |

## Audit

| Check | Pass Condition |
|-------|---------------|
| Testable | Every done criterion can be checked by a command or an eval |
| Bars explicit | Every agent touched has a metric and a numeric threshold |
| Scope tight | Nothing from a later phase is in scope |
| Blockers named | Any missing account or key is listed |

## Outputs

| Artifact | Location | Format |
|----------|----------|--------|
| Phase brief | `output/phase-N-brief.md` | Markdown following the brief template |
