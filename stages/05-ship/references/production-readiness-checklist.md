# Production Readiness Checklist

Mark each: PASS (with evidence), FAIL, or N/A for this phase. Rule numbers refer to
`references/master-plan.md` section 1.

| # | Check | Evidence to cite |
|---|-------|------------------|
| 1 | Workflow is deterministic; LLM steps are bounded (rule 1) | State machine module and tests |
| 2 | Every LLM output validated against a schema; failures go to review (rule 2) | Schema tests |
| 3 | No consequential action without a recruiter action (rule 3) | Route tests |
| 4 | Scores cite evidence that exists in the source text (rule 4) | Evidence check in evals |
| 5 | Evals pass in CI for this phase (rule 5) | Eval report |
| 6 | Fairness counterfactuals pass where scoring is touched (rule 6) | Fairness results |
| 7 | Injection cases do not move scores or actions (rule 7) | Injection results |
| 8 | Side effects idempotent; duplicate event test passes (rule 8) | Outbox tests |
| 9 | Jobs retry, time out, and dead letter; kill test recovers (rule 9) | Chaos or worker tests |
| 10 | Traces show prompt version, model, tokens, cost, latency (rule 10) | Langfuse trace link |
| 11 | Prompt and rubric versions stored with outputs (rule 11) | DB field and test |
| 12 | Audit log entry for every transition (rule 12) | Audit tests |
| 13 | Cost per candidate measured; limits set (rule 13) | Cost report |
| 14 | Compliance items for this phase done (rule 14, section 6) | Notice text, consent flow, hours check |
| 15 | Defaults safe: no real send or call unless explicitly enabled | Config and tests |
| 16 | README and demo steps work from a clean clone | Fresh clone run |
| 17 | No secrets or real personal data in git | Secret scan |
