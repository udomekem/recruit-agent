# Recruit Agent

An AI screening agent for recruiters: scores every CV against the job, scores
screening answers, drafts personalised rejection emails, phones shortlisted
candidates, scores the call, then calls finalists back and books the interview.

Built as a showcase of production grade agent engineering: a deterministic workflow
with bounded LLM steps, human decisions at every consequential point, evals in CI,
fairness and injection tests, idempotent side effects, tracing, and an audit log.

## How this repo is organised

This is an [ICM](https://github.com/RinDig/Interpretable-Context-Methodology)
workspace. The folder structure drives the build process, one phase at a time:

```
stages/01-brief -> 02-design -> 03-build -> 04-evals -> 05-ship
```

The application itself lives in `product/`. The full plan is
`references/master-plan.md`.

## Working in it

Open this folder in Claude Code. Type `setup` once, then `status` to see where the
build is. Say "start phase 0" to begin.

## Credit

Workspace method: Interpretable Context Methodology by Jake Van Clief and
contributors (MIT licence, copy in `references/icm/LICENSE-icm`).
