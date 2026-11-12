# Phase 5B UI Design: Hira style + connected inbox

Approved by Mani 2026-11-12 with the six defaults (Q1 to Q6). The prototype is
`phase-5b-ui-design.html` in this folder: one interactive page with fictional data.
Nothing is sent and no mailbox is connected. Design source:
`references/design/hira/` (copied from Mani's Codex outputs, 2026-11-12).

## Screens

| Screen | What it holds | Replaces today |
|--------|---------------|----------------|
| Candidates | Hira workbench: header stats, status filters (All, To decide, Shortlisted, Rejected), job selector, number search, ranked queue (score, recommendation, source, received), review panel with tabs Requirements, CV, Rejection email (once rejected), Notes, Activity; Shortlist and Reject with Undo; keys Enter and R | job page ranked table + candidate page |
| Jobs | Job board: each open job with its plus address for email applications, to decide, shortlisted, agreement with the AI, rubric status; click opens Candidates filtered to the job | jobs list |
| Inbox (new) | Connect Gmail or Microsoft 365 (provider, sign in, pick a label, done); connected view with what is read, how jobs are matched, privacy; today's emails with status Matched, Needs a job (pick a job, suggestions first), Duplicate, Not a CV; pause and disconnect | new |
| To do | One list of everything waiting on the recruiter: unreadable CVs, CVs that need a job, rejection emails not sent, rubrics that failed | review queue |

Top navigation tabs in the header, no sidebar (the brief rules out a permanent
sidebar). Below 680 px the list and the review are separate screens with a back
control, as in Hira.

## Where it departs from the Hira brief, and why

1. **Names hidden until shortlist.** Hira shows names and initials. Our scoring is blind
   (production rule 6), so rows show "Candidate 0042" and the number's last digits in
   the avatar; the name appears after Shortlist ("Show contact details", logged). The
   inbox list hides sender names too.
2. **Scores stay, with evidence.** Hira says no artificial match scores. Our product's
   point is a score you can check: the score and recommendation are shown small, and
   the default tab is Requirements, each verdict quoting the CV line it came from.
3. **Shortlist and Reject** instead of Approve and Decline, matching the state machine.
   Reject drafts the rejection email; the reason list holds job related reasons only.
4. **Rejection email tab** with the eight checks shown, Edit and Send (phase 5).

## Matching CVs from the inbox to jobs (shown in the Inbox screen)

Job code or plus address, then the Seek or Indeed subject line, then the AI matcher.
When the AI is unsure or two jobs are close, the CV waits in "Needs a job" with the
suggested jobs first. Full rules in `references/master-plan.md`, section 5.

## Checked

In the browser (Chromium, scripted, 2026-11-12): no console errors; candidate select,
CV tab, status and job filters, empty search, reject form, reject then undo, shortlist,
jobs to candidates, inbox job pick, disconnect and reconnect, to do links. No sideways
scrolling at 1280, 375 and 320 px; mobile list to review to back works. Screenshots were
not possible (the browser pane was hidden), so the look has not been checked by eye
here.

## Questions for Mani

| # | Question | Default |
|---|----------|---------|
| Q1 | Product name in the header: "hira" as in the design, or Recruit Agent? | hira |
| Q2 | Keep names hidden until shortlist (blind review)? | yes |
| Q3 | Keep the score and recommendation visible in the list? | yes, small, evidence first |
| Q4 | Inbox: Gmail first, Microsoft 365 second? | Gmail first |
| Q5 | Inbox reads one label (for example "Applications"), not the whole mailbox? | one label |
| Q6 | Dark mode follows the computer's setting, as in Hira? | yes |
