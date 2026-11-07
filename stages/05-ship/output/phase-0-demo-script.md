# Phase 0 Demo Script

All data is synthetic. Before recording: hide `product/.env`, and blank the recruiter
token in any terminal shown (use the `$TOKEN` variable, never print it).

## Setup (off camera)

```bash
cd ~/code/recruit-agent/product
make up
TOKEN=$(grep '^RECRUITER_TOKEN=' .env | cut -d= -f2- | tr -d '"')
H="Authorization: Bearer $TOKEN"; J="Content-Type: application/json"
```

## Full demo (about 5 minutes)

1. **The stack is up.** `curl -s localhost:8000/health`
   Expect: `{"status":"ok","database":"ok","redis":"ok"}`
2. **The rules live in one table.** Open `app/domain/states.py`, scroll the transition
   table. Point out: recruiter decisions have no system row.
3. **Add a candidate.**
   `ID=$(curl -s -H "$H" -H "$J" -d '{"display_label":"Demo candidate 1"}' localhost:8000/candidates | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')`
4. **The worker runs, then stops at the human.**
   `curl -s -H "$H" localhost:8000/candidates/$ID | python3 -m json.tool | head -20`
   Expect: state `SCORED`, 3 audit rows. It waits for a recruiter.
5. **Try to skip a step.**
   `curl -s -H "$H" -H "$J" -d '{"reason":"skip"}' localhost:8000/candidates/$ID/advance`
   Expect: 409 `illegal_transition`.
6. **Shortlist, then advance.** `.../shortlist` with a reason, wait 2 s, check state
   `SCREEN_SCORED`; then `.../advance`, check `INTERVIEW_BOOKED` with 11 audit rows.
7. **Double click.** Repeat the last `advance` call. Expect: 409, nothing written.
8. **Failure goes to review, not silence.** In tests: `uv run pytest -q tests/test_journeys.py -k review -v`.
9. **The eval gate.** `make eval` (PASS, exit 0), then `make eval-selftest`: the planted
   bug is caught and the 3 broken cases are named.
10. **The trace.** `make smoke`, open the printed Langfuse link: model, prompt v1, tokens,
    cost ($0.00006), latency.
11. **CI.** Open the latest green run on GitHub Actions.

## 60 to 90 second cut

| Seconds | On screen | Line |
|---------|-----------|------|
| 0 to 8 | Transition table in the editor | "Before I wrote a single prompt, I wrote this table." |
| 8 to 20 | Create candidate, state SCORED | "The worker scores a candidate, then stops. Only a recruiter can move it on." |
| 20 to 30 | 409 illegal_transition | "Try to skip a step: refused. Nothing written." |
| 30 to 42 | Audit trail JSON, 11 rows | "Every move has a row: who, why, when." |
| 42 to 60 | `make eval-selftest` output | "I planted a bug to check my tests can fail. They caught it." |
| 60 to 75 | Langfuse trace | "Every model call is traced: model, prompt version, cost. This one cost six thousandths of a cent." |
| 75 to 90 | Green CI run | "54 tests, evals and a secret scan on every push. Phase 0 done." |
