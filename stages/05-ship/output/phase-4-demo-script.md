# Phase 4 Demo Script (the demo video)

All data is synthetic. Before recording: hide `product/.env` and the terminal; never show
the password or token. Browser zoom 110%, light mode for the recording.

## Setup (off camera)

```bash
cd ~/code/recruit-agent/product
make up
make demo-seed-offline        # or make demo-seed for real model scores (about $0.15)
```

Sign in at http://localhost:3000 with `DASHBOARD_PASSWORD` from `.env`. Use the newest
copy of each job (top of the jobs list).

## Full demo (about 5 minutes)

1. **Jobs.** Four jobs, candidates to decide, agreement with the AI.
2. **The ranked list** (Data Analyst). Scores, recommendation badges, flags ("Salary above
   band"), knockouts ("right to work: fail"). Filter by band: Reject.
3. **A candidate.** "Applicant 5": no name anywhere. Left: each requirement, the AI's
   judgement, the reason, the quote. Click a quote: it lights up in the CV on the right.
   The CV shows `[NAME]`, `[ADDRESS]`, `[PHONE]`, `[EMAIL]`.
4. **Why it says reject.** Score 80, but "No right to work in Australia (application
   answer)" first. Code decides that, not the AI.
5. **Disagree with the AI.** Press `s` on a reject: the box says this goes against the
   recommendation. `Enter` with no reason: refused. Type a real reason, `Enter`: saved, the
   next candidate opens. Back on the job page: agreement drops and the row says override.
6. **The keyboard drill.** Review drill job, "Review next undecided": `s`/`r`, `Enter`,
   ten candidates in about 15 seconds.
7. **Contact after shortlist.** Open a shortlisted candidate: the contact panel appears,
   and the history now says "Contact details viewed".
8. **Two tabs.** Decide in one tab, try the other: "This candidate changed since you opened
   it."
9. **The tests.** `make e2e` output: 9 tests, "decided 50 candidates with 100 actions".

## 60 to 90 second cut

| Seconds | On screen | Line |
|---------|-----------|------|
| 0 to 10 | Ranked list | "This is where my AI recruiter hands over to a human." |
| 10 to 25 | Candidate page, click a quote | "Every judgement points at the line in the CV. Click it, it lights up." |
| 25 to 35 | Header "Applicant 5", `[NAME]` in the CV | "No names until you shortlist. You judge the work, not the person." |
| 35 to 50 | Override refused, then accepted with a reason | "Disagree with the AI? Fine. Say why. That is how I measure if the AI is any good." |
| 50 to 70 | Drill, fast keys | "Fifty candidates, two keys each. Under half a minute." |
| 70 to 90 | Agreement rate, test output | "Every decision is logged against the AI's recommendation. That number is the real eval." |
