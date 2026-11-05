# Onboarding Questionnaire: Recruit Agent

Read this file when the user types "setup". Ask ALL questions in one pass. These
configure the project, not a single phase. Write answers into `shared/project-config.md`
by replacing the placeholders. Accept defaults for anything skipped.

---

### Q1: GitHub repo name and visibility?
- Placeholder: `{{REPO_NAME}}`, `{{REPO_VISIBILITY}}`
- Default: `recruit-agent`, public
- Files: `shared/project-config.md`

### Q2: Agent name and voice persona for phone calls?
- Placeholder: `{{AGENT_NAME}}`, `{{AGENT_VOICE_NOTES}}`
- Default: "Sam", warm, brief, professional Australian English
- Files: `shared/project-config.md`

### Q3: Company name the agent calls on behalf of (demo company is fine)?
- Placeholder: `{{DEMO_COMPANY}}`
- Default: "Northwind Talent" (fictional)
- Files: `shared/project-config.md`

### Q4: Time zone and allowed calling hours?
- Placeholder: `{{TIMEZONE}}`, `{{CALL_HOURS}}`
- Default: Australia/Sydney, 09:00 to 18:00 Mon to Fri
- Files: `shared/project-config.md`

### Q5: Sending email domain (or "none yet")?
- Placeholder: `{{EMAIL_DOMAIN}}`
- Default: none yet (use a test inbox until set)
- Files: `shared/project-config.md`

### Q6: Hosting preference for the public demo?
- Placeholder: `{{HOSTING}}`
- Options: Railway + Vercel (default), Fly + Vercel, undecided
- Files: `shared/project-config.md`

---

## After Onboarding

Tell the user what was set, which accounts in `references/master-plan.md` section 9
are still missing, and that the next step is "start phase 0". Then scan
`shared/project-config.md` for remaining `{{` patterns and ask for any gaps.
