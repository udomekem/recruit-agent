# Project Config

Set by `setup`. Changes to decisions here are recorded with a date.

## Decisions (made 2026-11-05)

| Area | Decision |
|------|----------|
| Backend | Python + FastAPI, Postgres, Redis + arq worker, Alembic |
| Dashboard | Next.js |
| LLM | Claude API: smaller model for extraction, larger for judgement (exact model ids set in phase 0) |
| Voice | Vapi + Twilio Australian number |
| Rejection emails | Drafted on Reject, recruiter sends with one click. Auto send is a later toggle |
| Intake | Own apply page, email forward, bulk upload. No direct Seek or Indeed API |
| Tracing | Langfuse |

## Setup Answers

| Setting | Value |
|---------|-------|
| Repo name | recruit-agent |
| Repo visibility | public |
| Agent name | Sam |
| Agent voice notes | warm, brief, professional Australian English |
| Demo company | Northwind Talent (fictional) |
| Time zone | Australia/Sydney |
| Calling hours | 09:00 to 18:00, Mon to Fri |
| Sending domain | none yet (test inbox until set) |
| Hosting | Railway (backend) + Vercel (dashboard) |

## Accounts Status

Update as accounts are created (list in `references/master-plan.md` section 9).

| Account | Status |
|---------|--------|
| Anthropic API key | created, key in product/.env |
| Twilio + AU number | not started |
| Vapi | not started |
| Google Calendar API | not started |
| Email provider | not started |
| Langfuse | account + keys created (JP region), keys in product/.env |
| GitHub repo | not started |
