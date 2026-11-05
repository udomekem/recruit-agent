# Design Checklist

## Schemas
- Every LLM output is a Pydantic model. No free text parsing.
- Scores carry: value, evidence quote, source location, prompt version, model id.
- Enumerated states only. No stringly typed status.

## Prompts
- Versioned by name: `<agent>-v<N>`. A change bumps the version.
- Untrusted text (CV, answer, transcript, call audio text) is wrapped in clearly
  delimited data blocks, and the system prompt says content inside is data, not
  instructions.
- Rubric and criteria come from the approved rubric, never from candidate text.

## Threat model prompts
Ask for each LLM step: what happens if the input says "ignore the rubric", contains
hidden text, is empty, is 10x longer than normal, is in another language, or names a
protected attribute?

## Human control
- Reject, shortlist, advance, and send are recruiter actions.
- The agent output is a recommendation with evidence.

## Side effects
- Idempotency key = candidate id + action + attempt scope.
- Timeouts on every external call. Retries with backoff. Terminal failure goes to
  NEEDS_REVIEW with a reason, never silently dropped.

## Privacy
- Redact before scoring. Redacted copy is what LLM scoring sees.
- Log ids, not raw personal data, in traces where possible.
- Retention and delete paths exist for anything stored.

## Evals
- Every agent gets a dataset plan: size, personas, edge cases, labelling method.
- Include at least one adversarial case per agent.
