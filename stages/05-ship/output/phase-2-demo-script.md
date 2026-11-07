# Phase 2 Demo Script

All data is synthetic. Before recording: hide `product/.env`; never print the token.

## Setup (off camera)

```bash
cd ~/code/recruit-agent/product
make up
TOKEN=$(grep '^RECRUITER_TOKEN=' .env | cut -d= -f2- | tr -d '"')
H="Authorization: Bearer $TOKEN"
```

Create and open a job as in the phase 1 demo. Pick two CVs from
`evals/datasets/cv-v1/`: `cv-010.pdf` (two column, states nationality, religion and age)
and `cv-003.pdf` (states gender, marital status, "Proud mum of three").

## Full demo (about 5 minutes)

1. **The original.** Open `cv-010.pdf`: name, phone, email, address, LinkedIn,
   "Nationality", "Religion", "Age" in the sidebar.
2. **Apply** with it on the apply page.
3. **Watch the worker.** `make logs`: parse runs, about 20 seconds, then SCORED.
4. **What the scorer will read.** `curl -s -H "$H" localhost:8000/candidates/$CID/parse`
   and show `redacted_text`: `[NAME]`, `[ADDRESS]`, `[PHONE]`, `[EMAIL]`, `[LINK]`,
   `Nationality: [PROTECTED]`, `Religion: [PROTECTED]`, `[DOB]`; employers, titles, dates and
   skills untouched.
5. **What the model never saw.** In `tests/test_parse_step.py`, the test that inspects the
   exact text sent to the model: no name, email or phone.
6. **The profile.** `profile.work_history`: titles, employers, dates exactly as the CV.
7. **Free text.** Repeat with `cv-003.pdf`: "Proud mum of three" becomes `[PROTECTED]`.
8. **A scanned CV.** Apply with `cv-027.pdf`: NEEDS_REVIEW "no text layer", no model call.
9. **The eval.** `make eval-cv`: 30 CVs x 3 runs, 0 leaks, 98.5% field accuracy,
   about 6 cents for the whole run.
10. **Erase.** `POST /candidates/$CID/erase`: the parse is gone too.

## 60 to 90 second cut

| Seconds | On screen | Line |
|---------|-----------|------|
| 0 to 10 | The original CV, sidebar visible | "This CV has a name, address, age, nationality and religion on it." |
| 10 to 25 | Redacted text side by side | "My agent never scores this. It scores this." |
| 25 to 40 | Test showing the text sent to the model | "Even the AI that reads the CV never sees the name, email or phone. Code strips them first." |
| 40 to 55 | "Proud mum of three" to `[PROTECTED]` | "The model caught this, but only two times in three. So now code catches it every time, and the model is the backup." |
| 55 to 75 | Eval table | "Thirty test CVs, three runs: zero leaks, 98.5% of fields right, six cents for the whole test." |
| 75 to 90 | Scanned CV to review | "A scanned CV it cannot read goes to a person, not a guess." |
