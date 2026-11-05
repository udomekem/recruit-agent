# Recruit Agent (ICM workspace)

An AI recruiter screening agent, built as a production grade, eval-driven system.
This folder is a self-contained ICM (Interpretable Context Methodology) workspace.
It is not connected to any other workspace. Do not read or write outside this folder.

ICM here runs the BUILD PROCESS. The product itself is code in `product/`.

## Folder Map

```
recruit-agent/
├── CLAUDE.md               (you are here)
├── CONTEXT.md              (task routing: start here)
├── README.md               (human overview)
├── setup/questionnaire.md  (one-time project config)
├── shared/
│   ├── project-config.md   (decisions made at setup: stack, models, voice, hours)
│   └── phase-tracker.md    (which build phase is active, what is done)
├── references/
│   ├── master-plan.md      (canonical plan: rules, journey, scoring, agents, evals, phases)
│   └── icm/                (ICM conventions + licence, for portability)
├── stages/                 (the build loop, run once per phase)
│   ├── 01-brief/           (phase goal, done criteria, eval bars)
│   ├── 02-design/          (schemas, prompts, failure modes, eval cases)
│   ├── 03-build/           (code in product/, tests, build log)
│   ├── 04-evals/           (run evals, gate the phase)
│   └── 05-ship/            (readiness check, demo, LinkedIn post brief)
└── product/                (the application code: API, worker, dashboard, evals)
```

## Triggers

| Keyword | Action |
|---------|--------|
| `setup` | Run `setup/questionnaire.md`, write answers into `shared/project-config.md` |
| `status` | Read `shared/phase-tracker.md`, then scan `stages/*/output/` and render the pipeline for the active phase |
| `next phase` | Archive the active phase outputs to `stages/*/output/phase-N/`, update the tracker, start stage 01 for the next phase |

### How `status` works

For the active phase, a stage is COMPLETE if its `output/` holds a `phase-N-*` file
(ignore `.gitkeep` and archived `phase-*/` folders). Render:

```
Recruit Agent, Phase N: <name>
  [01-brief] --> [02-design] --> [03-build] --> [04-evals] --> [05-ship]
     STATUS        STATUS         STATUS         STATUS         STATUS
```

Also print the eval gate result from `04-evals/output/phase-N-eval-report.md` if present.

## Routing

| Task | Go To |
|------|-------|
| Start or scope a phase | `stages/01-brief/CONTEXT.md` |
| Design a phase | `stages/02-design/CONTEXT.md` |
| Implement a phase | `stages/03-build/CONTEXT.md` |
| Run evals and gate a phase | `stages/04-evals/CONTEXT.md` |
| Ship, demo, write the post brief | `stages/05-ship/CONTEXT.md` |

## What to Load

| Task | Load These | Do NOT Load |
|------|-----------|-------------|
| Brief | `shared/*`, `references/master-plan.md` (sections named by stage), `stages/01-brief/references/*` | `product/`, other stages |
| Design | `stages/01-brief/output/`, `stages/02-design/references/*`, `references/master-plan.md` (sections named by stage) | `stages/03-build/` onward |
| Build | `stages/02-design/output/`, `stages/03-build/references/*`, `shared/project-config.md`, relevant files in `product/` | `references/master-plan.md` in full, `stages/01-brief/` |
| Evals | `stages/01-brief/output/` (pass bars), `stages/03-build/output/`, `stages/04-evals/references/*`, `product/evals/` | `stages/02-design/` unless a case needs it |
| Ship | `stages/04-evals/output/`, `stages/05-ship/references/*`, `shared/phase-tracker.md` | `product/` source unless checking a rule |

## Stage Handoffs

Each stage writes to its own `output/` as `phase-N-<artifact>.md`. The next stage reads
that file. Edit any output between stages and the next stage uses your edit.
Stages 03 and 04 also touch `product/`; that is the one place outside `output/` they write.

## Hard Rules

- A phase is not done until stage 04 reports every eval bar for that phase as PASS.
- Humans make consequential decisions in the product (reject, advance). Never build
  an unreviewed path around that without a decision recorded in `shared/project-config.md`.
- Never put real candidate data, real keys, or `.env` contents in this folder or in git.
  Datasets are synthetic. Keys live in `product/.env` (gitignored).
- Never place real phone calls or send real emails from tests. Use sandbox numbers,
  test inboxes, and web calls until the phase says otherwise.
- One canonical home per fact. Stage files point to `references/master-plan.md`
  sections; they do not copy them.
