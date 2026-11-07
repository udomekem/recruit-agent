# Phase 1 Demo Script (draft)

All data is synthetic. Before recording: hide `product/.env`; never print the token or keys.

## Setup (off camera)

```bash
cd ~/code/recruit-agent/product
make up
TOKEN=$(grep '^RECRUITER_TOKEN=' .env | cut -d= -f2- | tr -d '"')
H="Authorization: Bearer $TOKEN"; J="Content-Type: application/json"
```

Have two ads ready as JSON: the Business Analyst ad (`rubric-001`) and the sales ad with
age wording (`rubric-011`) from `evals/datasets/rubric-v1.jsonl`.

## Full demo (about 6 minutes)

1. **Create a job.** `POST /jobs` with the sales ad. Response: `DRAFT`.
2. **The rubric builder runs.** After a few seconds `GET /jobs/{id}`: `RUBRIC_READY`,
   rubric v1 from `deepseek-v4.1-flash`, prompt v2. Show the criteria, each with its quote
   from the ad, and the two **flags**: "young, energetic" and "under 30", with neutral
   rewording. No age criterion exists.
3. **The guard.** Try to save a rubric with a criterion "Young and energetic":
   `POST /jobs/{id}/rubric` returns 422 "protected attribute wording". Try a custom
   question "Are you under 30?": refused.
4. **Human approval.** Edit one weight (new version v2), then try to approve v1: 409
   (stale). Approve v2: job `OPEN`. Try to edit the rubric while open: 409.
5. **The apply page.** Open `http://localhost:8000/apply/{id}` in a browser: job, five
   questions, CV upload, the collection notice, consent box not ticked.
6. **Apply.** Fill the form with a synthetic person and a PDF. "Your application is in".
7. **Behind the scenes.** `GET /candidates/{cid}`: `Applicant 1`, audit row T23 with
   actor `candidate`; the worker moves it on (stub scoring until phase 3).
8. **What gets refused.** Apply again with the same email in capitals: "already have your
   application". Rename a text file to `cv.pdf`: refused by content. Untick consent: refused.
9. **Encrypted CV.** Show the stored object reporting server side encryption (MinIO).
10. **Delete my data.** `POST /candidates/{cid}/erase`: CV gone, name, email, phone
    cleared, audit trail still there without personal data.
11. **The evals.** `make eval-rubric`: 15 ads x 3 runs, recall 0.986, 0 protected
    criteria, 9 of 9 flagged, 0 injected criteria, about $0.05 for the whole run. Open the
    Langfuse experiment.
12. **CI.** Latest green run.

## 60 to 90 second cut

| Seconds | On screen | Line |
|---------|-----------|------|
| 0 to 10 | The age wording ad | "This job ad says 'young team, suit someone under 30'. Watch what my agent does with it." |
| 10 to 25 | Rubric JSON: criteria with quotes, two flags | "It turns the ad into a scoring rubric, quotes every line it used, and flags the age wording instead of scoring on it." |
| 25 to 35 | 422 on "Young and energetic" | "Even if the model tried, code blocks it." |
| 35 to 48 | Approve v2, apply page | "A recruiter approves the rubric. Only then does the job open." |
| 48 to 62 | Refused fake PDF, duplicate, encrypted CV | "Fake files refused. Duplicates caught. CVs encrypted." |
| 62 to 80 | Eval table | "Tested on 15 ads, 3 runs each: 98.6% of requirements found, zero discriminatory criteria. About 5 cents for the whole test." |
| 80 to 90 | Erase call | "And one call deletes a candidate's data." |
