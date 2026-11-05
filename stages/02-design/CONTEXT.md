# Stage 02: Design

Design the phase before any code: data shapes, state transitions, prompts, failure
modes, and the eval cases that will judge it. Specs say WHAT and WHEN, not HOW.

## Inputs

| Source | File/Location | Section/Scope | Why |
|--------|--------------|---------------|-----|
| Previous stage | `../01-brief/output/phase-N-brief.md` | Full file | Scope, bars, done criteria |
| Plan | `../../references/master-plan.md` | Section 2 (journey), section 3 (scoring), section 4 (agents) rows for this phase | Contracts to honour |
| Plan | `../../references/master-plan.md` | Section 6 (compliance) when the phase touches candidate data, calls, or email | Legal constraints |
| Reference | `references/design-checklist.md` | Full file | Threat model, schema, and prompt rules |

## Process

1. Read the brief.
2. List the data entities and fields this phase adds or changes (Pydantic schema
   level: names, types, constraints, who writes, who reads).
3. State transitions: which candidate states are added or touched, what triggers
   each, and the audit log entry for each.
4. For each LLM step: purpose, input (what is fenced as untrusted), output schema,
   prompt version label, model tier, evidence requirement.
5. For each side effect (email, call, calendar, storage): idempotency key, retry
   policy, timeout, failure state.
6. Failure modes and abuse cases: prompt injection, malformed input, provider
   outage, duplicate events, consent refused. State the expected behaviour for each.
7. Eval cases: for every eval bar in the brief, describe the dataset shape (count,
   personas, edge cases) and how expected answers are labelled. Do not write the data yet.
8. **[Checkpoint]** Present the design. Ask: schemas right? any missing failure modes?
   eval cases cover what could hurt a candidate or recruiter?
9. Run the audit. Save to output.

## Checkpoints

| After Step | Agent Presents | Human Decides |
|------------|---------------|---------------|
| 7 | Entities, transitions, LLM and side effect specs, failure table, eval case plan | Approve to build, or revise |

## Audit

| Check | Pass Condition |
|-------|---------------|
| Schemas | Every LLM output has a typed schema and a retry/fail path |
| Human control | No consequential decision is made without a recruiter action |
| Idempotency | Every side effect has a key and a duplicate behaviour |
| Hostile input | Every untrusted input is named and fenced |
| Eval coverage | Every brief bar maps to a dataset plan |
| No HOW | No code, file paths inside `product/`, or library calls beyond naming the tool |

## Outputs

| Artifact | Location | Format |
|----------|----------|--------|
| Phase design | `output/phase-N-design.md` | Markdown: entities, transitions, LLM specs, side effects, failure table, eval case plan |
