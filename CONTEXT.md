# Recruit Agent

Build loop for a production grade recruiter screening agent. Run the five stages once
per build phase (phases 0 to 10 live in `references/master-plan.md`, section 8).

## Task Routing

| Task Type | Go To | Description |
|-----------|-------|-------------|
| Scope a phase | `stages/01-brief/CONTEXT.md` | Turn the plan's phase row into a brief with done criteria and eval bars |
| Design a phase | `stages/02-design/CONTEXT.md` | Schemas, prompts, state transitions, failure modes, eval cases |
| Build a phase | `stages/03-build/CONTEXT.md` | Write code and tests in `product/` |
| Evaluate a phase | `stages/04-evals/CONTEXT.md` | Run evals, compare to bars, gate the phase |
| Ship a phase | `stages/05-ship/CONTEXT.md` | Production readiness check, demo script, LinkedIn post brief |

## Shared Resources

| Resource | Location | Contains |
|----------|----------|----------|
| Project config | `shared/project-config.md` | Stack, models, voice, calling hours, accounts status |
| Phase tracker | `shared/phase-tracker.md` | Active phase and history |
| Master plan | `references/master-plan.md` | Rules, journey, scoring, agents, compliance, evals, phases |
| ICM conventions | `references/icm/conventions.md` | How this workspace is structured |
