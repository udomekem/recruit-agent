# Phase 5B Demo Script: the agent reads its own inbox

All data is synthetic. Before recording: hide `product/.env` and the terminal; never show
the password, the token or a real inbox. Browser zoom 110%, light mode for the recording.
The demo uses the local test inbox (Mailpit); live Gmail is not connected yet.

## Setup (off camera)

```bash
cd ~/code/recruit-agent/product
make up
make demo-seed-offline        # jobs with codes, candidates (no model)
```

Sign in at http://localhost:3000 with `DASHBOARD_PASSWORD` from `.env`. Open the Inbox
page and press "Connect the test inbox" if it is not connected yet. The job matcher needs
`KIE_API_KEY` in `.env` for the third email.

## Full demo (about 5 minutes)

1. **The new look.** Candidates page: "Your next great hire.", counts, status tabs, the
   ranked list on the left (100 at a time, "Show more"), the open candidate on the right.
   Still "Applicant 12", never a name, until shortlist.
2. **The job board.** Each job has a code (`DA-0042` style). That code is how an emailed
   CV finds its job without any AI.
3. **The inbox.** Inbox page: the connected test inbox, its label ("Applications"), pause,
   "Check now", disconnect. "Connect Gmail" (read only, one label) sits beside it.
4. **Send three applications.** In a terminal: `make demo-inbox`. Open
   http://localhost:8025 to show the three emails arriving, each with a PDF CV.
5. **Check now.** Back on the Inbox page, press "Check now", refresh after a few seconds.
   Recent emails, with redacted subjects ("from [name]"):
   - the analyst CV: "Job code ... in the subject", added to Data Analyst;
   - the nurse CV: matched by the plus address `careers+rn-....@`;
   - the site CV with no job in the email: the AI looked, and with several open site jobs
     it was not sure, so it waits under **Needs a job**.
6. **Pick the job.** In "Needs a job", pick the Site Supervisor job: the candidate is
   scored for it and joins that job's ranked list.
7. **The acknowledgement.** In Mailpit: each new candidate got an email saying the CV was
   received, with the collection notice (Privacy Act). Sent through the phase 5 outbox.
8. **One email, one candidate.** Press "Check now" again: nothing new. The same email is
   never read twice.
9. **The evals.** `phase-5b-eval-report.md`: clear CVs filed 96.3%, wrong auto matches 0,
   fairness and injection 0, $0.00037 per email.

## 60 to 90 second cut

| Seconds | On screen | Line |
|---------|-----------|------|
| 0 to 10 | Inbox page, connected | "My recruiting agent now reads its own inbox." |
| 10 to 25 | `make demo-inbox`, three emails in the test inbox | "Three CVs arrive. One has a job code, one a job's email address, one says nothing." |
| 25 to 40 | "Check now", the three rows with routes | "The first two never touch AI. Plain code reads the code and the address." |
| 40 to 55 | The third row under "Needs a job" | "The third goes to the AI. It is not sure, so it does not guess. It asks me." |
| 55 to 70 | Pick a job, candidate scored, still "Applicant" | "I pick the job. It is scored, and I still cannot see a name." |
| 70 to 90 | Eval table | "Tested on 53 synthetic CVs, three runs: zero sent to the wrong job." |
