# Phase 3 Demo Script

All data is synthetic. Before recording: hide `product/.env`; never print the token.

## Setup (off camera)

```bash
cd ~/code/recruit-agent/product
make up
TOKEN=$(grep '^RECRUITER_TOKEN=' .env | cut -d= -f2- | tr -d '"')
H="Authorization: Bearer $TOKEN"
```

Create the Business Analyst job from the phase 1 demo, wait for RUBRIC_READY, approve
version 1. Files: `evals/datasets/cv-v1/cv-001.pdf` (a business analyst at an insurer),
`cv-v1/cv-002.pdf` (a nurse), and one injection pair from `evals/datasets/inject-v1/`
(`inject-02-a.pdf` clean, `inject-02-b.pdf` with hidden white text claiming skills; use
the nurse job from `score-rubrics-v1.json` if you want that pair on camera, or show it
from the eval report).

## Full demo (about 6 minutes)

1. **The rubric.** `GET /jobs/$JID`: the approved criteria with their weights (must haves
   3 to 5, nice to haves 1 to 2). "The AI never sees these weights."
2. **Apply twice** on the apply page: cv-001 with salary "120k to 135k"; cv-002 with
   right to work "no".
3. **Watch the worker.** `make logs`: parse, then score, about 30 seconds each.
4. **The ranked list.** `curl -s -H "$H" localhost:8000/jobs/$JID/candidates`: rank 1,
   86.7, advance; rank 2, 0.0, reject.
5. **The evidence.** `GET /candidates/$CID/score`: each criterion with met, partly met
   or not met, a reason, and a quote copied from the CV. "Stakeholder management" is
   partly met, quoting only the skills line.
6. **Code, not the model, decides the band.** Show `app/scoring/formula.py`: weighted
   points, then the band rules in order. "No right to work" is the first reason on
   cv-002 whatever its score.
7. **A recommendation only.** The candidate is SCORED; the pipeline stops; shortlist and
   reject are recruiter buttons (phase 4).
8. **The attack.** Open `inject-02-b.pdf`: looks identical to the clean one. Select all
   to reveal the white text. The scorer never read it: hidden text removed, flagged with
   a character count.
9. **The fairness test.** Eval report: same CV with a different name, gender, graduation
   year 20 years apart, suburb, or reason for a career gap: 0.0 points difference over
   three runs.
10. **The eval.** `make eval-score` result table: all 11 bars, $0.0025 a candidate.

## 60 to 90 second cut

| Seconds | On screen | Line |
|---------|-----------|------|
| 0 to 10 | Ranked list | "My AI recruiter ranked these two applicants. It did not decide anything." |
| 10 to 25 | Evidence view with quotes | "Every judgement quotes the CV. If the quote is not really in the CV, code throws it out." |
| 25 to 40 | `formula.py` | "The AI says met, partly met or not met. Code adds it up. The AI never sees the weights." |
| 40 to 55 | White text revealed in the PDF | "This CV hides 'expert, ten years' in white text. The scorer never reads it, and it gets flagged." |
| 55 to 75 | Fairness rows | "Same CV, different name, gender, age, suburb, or reason for a career gap. Zero point difference." |
| 75 to 90 | Eval table and history | "The first version passed 7 of 11 tests. It did not know today's date." |
