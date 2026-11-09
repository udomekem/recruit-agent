"""Demo data for the recruiter dashboard (phase 4 design section 9). Synthetic people only.

    uv run python -m scripts.demo_seed --offline     # no model, no key (tests, CI, demos)
    uv run python -m scripts.demo_seed --real        # through the running API: real model

Both create the three phase 3 jobs (data analyst, registered nurse, site supervisor) with
the fixed phase 3 rubrics and their 45 CVs, plus a "review drill" job of 50 analyst
candidates for the keyboard flow.

--offline runs the real job service and the real intake (CV stored in MinIO, answers
coerced), then writes each parse and score from the CV's coverage plan: redacted text by
the real code redaction, judgements and quotes from the plan, total and band by the real
formula. Moves go through the state machine, so the audit trail is real.

--real creates jobs through the API, replaces the drafted rubric with the fixed one,
approves it, and applies through the apply page: the worker parses and scores with the
real model (about $0.15). Needs `make up` and a KIE_API_KEY.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATASETS = ROOT / "evals" / "datasets"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
DRILL_SIZE = 50

ADS = {
    "analyst": (
        "Northwind Talent is hiring a Data Analyst for a Sydney based client in logistics. "
        "You will write SQL for analysis and reporting, use Python (pandas) to automate "
        "reports, build Power BI dashboards and present findings to senior stakeholders. "
        "Essential: at least 3 years as a data analyst, SQL, Python. Desirable: Power BI, "
        "a quantitative degree, a cloud data warehouse such as Snowflake or BigQuery."
    ),
    "nurse": (
        "Northwind Talent is hiring a Registered Nurse for a surgical ward at a Sydney "
        "hospital. Essential: current AHPRA registration as a Registered Nurse, at least 2 "
        "years of acute care nursing, safe medication administration including S8 drugs. "
        "Desirable: Advanced Life Support, electronic medical records such as Cerner or Epic, "
        "emergency triage, a Working with Children Check."
    ),
    "site": (
        "Northwind Talent is hiring a Site Supervisor for residential construction in "
        "Western Sydney. Essential: at least 5 years supervising construction sites, a White "
        "Card, and running WHS on site: inductions, SWMS and incident reporting. Desirable: a "
        "driver's licence, a first aid certificate, Procore, and a Certificate IV in "
        "Building and Construction."
    ),
}


def load() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rubrics = json.loads((DATASETS / "score-rubrics-v1.json").read_text())
    rows = [json.loads(line) for line in (DATASETS / "score-v1.jsonl").read_text().splitlines()]
    return rubrics, rows


def form_answers(answers: dict[str, Any] | None) -> dict[str, str]:
    return {f"q_{k}": str(v) for k, v in (answers or {}).items()}


def cases_for(job: str, rows: list[dict[str, Any]], drill: bool) -> list[dict[str, Any]]:
    """The 15 CVs of a job; for the drill, the analyst CVs repeated to 50 with new people."""
    base = [r for r in rows if r["input"]["job"] == job]
    if not drill:
        return base
    out = []
    for i in range(DRILL_SIZE):
        r = json.loads(json.dumps(base[i % len(base)]))
        # same person as the CV (so redaction removes the name printed in it); a new email
        # and phone so each copy is its own application
        it = r["input"]["intake"]
        user, domain = it["email"].split("@")
        it["email"] = f"{user}+drill{i:02d}@{domain}"
        it["phone"] = f"0491 570 {800 + i:03d}"
        r["input"]["answers"] = r["input"]["answers"] or {
            "right_to_work": "yes",
            "expected_salary": "100000",
            "notice_period": "3 to 4 weeks",
            "location_fit": "yes",
            "current_role": "see CV",
        }
        out.append(r)
    return out


# ---- offline -------------------------------------------------------------------------


def _quote(job: str, cid: str, verdict: str, text: str) -> str:
    """A line of the redacted CV that shows the criterion, from the plan's fragments."""
    from app.intake.redact import normalise
    from evals.datasets.build_score_v1 import FRAGS, ROLES, SYNONYM

    t = normalise(text)
    if cid == "years":
        roles = ROLES[job]
        titles = [r for r in [*roles["main"], roles["junior"]]]
        for title, employer in titles:
            line = f"{title}, {employer}"
            if normalise(line) in t:
                return line
        return ""
    options = [frag for _place, frag in FRAGS[job].get(cid, {}).get(verdict, [])]
    if SYNONYM[job][0] == cid:
        options.append(SYNONYM[job][1][1])
    for frag in options:
        if normalise(frag) in t:
            return frag
    return ""


def _adder(table: Any, /, **fields: Any) -> Any:
    """An `extra` hook for apply_transition that adds one row in the move's transaction."""

    def add(s: Any, _c: Any) -> None:
        s.add(table(**fields))

    return add


async def seed_offline() -> None:
    from sqlalchemy import select

    from app.config import get_settings
    from app.db.models import Candidate, CvParse, Rubric, Score
    from app.db.session import make_engine, make_sessionmaker
    from app.domain.jobs import JobState, WorkArrangement
    from app.domain.states import ActorType, CandidateState
    from app.intake.extract import extract
    from app.intake.redact import pre_redact
    from app.intake.service import Application, submit
    from app.integrations.storage import make_storage
    from app.observability.tracing import RecordingTracer
    from app.scoring.answers import score_answers
    from app.scoring.formula import POINTS, score_card
    from app.workflow import jobs as J
    from app.workflow.dispatch import InlineDispatcher
    from app.workflow.machine import apply_transition, get_candidate
    from app.workflow.pipeline import Pipeline
    from evals.score_inputs import questions

    settings = get_settings()
    engine = make_engine(settings.database_url)
    sessions = make_sessionmaker(engine)
    storage = make_storage(settings)
    ensure = getattr(storage, "ensure_bucket", None)
    if ensure is not None:
        await ensure()
    pipeline = Pipeline(sessions, InlineDispatcher(), RecordingTracer(), settings)
    rubrics, rows = load()

    plan_jobs = [("analyst", False), ("nurse", False), ("site", False), ("analyst", True)]
    for job, drill in plan_jobs:
        spec = rubrics[job]
        title = spec["title"] + (" (review drill)" if drill else "")
        snap = await J.create_job(
            sessions,
            J.JobFields(
                title=title,
                description=ADS[job] + " " + ADS[job],
                location="Sydney NSW",
                work_arrangement=WorkArrangement.ONSITE,
                salary_min=int(spec["salary_max"] * 0.8),
                salary_max=int(spec["salary_max"]),
            ),
            [],
            actor_id="seed",
        )
        snap, version = await J.save_rubric(
            sessions,
            snap.id,
            criteria=spec["criteria"],
            flags=[],
            source="recruiter",
            actor_type=ActorType.SYSTEM,
            actor_id="seed",
            to=JobState.RUBRIC_READY,
            reason="phase 3 fixed rubric (demo seed)",
            expected_state=JobState.DRAFT,
            expected_version=snap.state_version,
        )
        await J.approve_and_open(
            sessions, snap.id, version=version, actor_id="seed", reason="demo seed"
        )
        async with sessions() as s:
            rubric = (await s.execute(select(Rubric).where(Rubric.job_id == snap.id))).scalar_one()
        made = 0
        for case in cases_for(job, rows, drill):
            inp, exp = case["input"], case["expected"]
            path = DATASETS / inp["file"]
            it = inp["intake"]
            res = await submit(
                pipeline,
                storage,
                Application(
                    job_id=snap.id,
                    source="bulk_upload" if inp["answers"] is None else "apply_page",
                    full_name=it["name"],
                    email=it["email"],
                    phone=it["phone"],
                    cv_bytes=path.read_bytes(),
                    cv_filename=path.name,
                    answers=dict(inp["answers"] or {}),
                    candidate_consented=inp["answers"] is not None,
                    recruiter_attested=inp["answers"] is None,
                    attested_by="seed" if inp["answers"] is None else None,
                    original_platform="Seek (demo)" if inp["answers"] is None else None,
                ),
                cv_max_bytes=settings.cv_max_bytes,
            )
            cid = res.candidate_id
            applied = await get_candidate(sessions, cid)
            media = "application/pdf" if path.suffix == ".pdf" else DOCX
            ex = await extract(path.read_bytes(), media)
            pre = pre_redact(ex.text, name=it["name"], email=it["email"], phone=it["phone"])
            parse_id = uuid.uuid4()
            counts = {**pre.counts, **({"hidden_text": ex.hidden_chars} if ex.hidden_chars else {})}
            add_parse = _adder(
                CvParse,
                id=parse_id,
                candidate_id=cid,
                status="parsed",
                text_layer=True,
                redacted_text=pre.text,
                profile=None,
                redaction_counts=counts,
                prompt_id="seed",
                prompt_version="offline",
                model="none",
                cost_usd=0.0,
                attempts=0,
            )
            snap_c = await apply_transition(
                sessions,
                candidate_id=cid,
                to_state=CandidateState.PARSED,
                actor_type=ActorType.SYSTEM,
                actor_id="worker:parse",
                reason="cv parsed (offline demo seed: code redaction only)",
                expected_state=CandidateState.APPLIED,
                expected_version=applied.state_version,
                extra=add_parse,
            )
            verdicts: dict[str, str] = exp["verdicts"]
            answers = score_answers(questions(inp["answers"]), salary_max=int(spec["salary_max"]))
            card = score_card(spec["criteria"], verdicts, answers, hidden_chars=ex.hidden_chars)
            judgements = []
            for c in spec["criteria"]:
                v = verdicts[c["id"]]
                q = _quote(job, c["id"], v, pre.text) if v != "not_met" else ""
                judgements.append(
                    {
                        "criterion_id": c["id"],
                        "verdict": v,
                        "points": POINTS[v],
                        "reason": "Shown in the CV."
                        if v == "met"
                        else "Partly shown in the CV."
                        if v == "partly_met"
                        else "Not shown in the CV.",
                        "quote": q,
                    }
                )
            row = {
                "rubric_id": rubric.id,
                "rubric_version": rubric.version,
                "cv_parse_id": parse_id,
                "judgements": judgements,
                "answer_results": [a.as_dict() for a in answers],
                "total": card.total,
                "band": card.band,
                "reasons": card.reasons,
                "flags": [f.as_dict() for f in card.flags],
                "injection_suspected": False,
                "prompt_id": "seed",
                "prompt_version": "offline",
                "model": "none",
                "cost_usd": 0.0,
                "attempts": 0,
            }

            add_score = _adder(Score, candidate_id=cid, **row)

            await apply_transition(
                sessions,
                candidate_id=cid,
                to_state=CandidateState.SCORED,
                actor_type=ActorType.SYSTEM,
                actor_id="worker:score",
                reason=f"scored {card.total:.1f} against rubric v{rubric.version}: {card.band} "
                "(recommendation only; offline demo seed)",
                expected_state=CandidateState.PARSED,
                expected_version=snap_c.state_version,
                extra=add_score,
            )
            made += 1
        print(f"{title}: {made} candidates")
    async with sessions() as s:
        from sqlalchemy import func

        n = (await s.execute(select(func.count()).select_from(Candidate))).scalar()
    print(f"done: {n} candidates in the database")
    await engine.dispose()


# ---- real ----------------------------------------------------------------------------


def seed_real(base_url: str) -> None:
    import time

    import httpx

    from app.config import get_settings

    token = get_settings().recruiter_token
    if token is None:
        sys.exit("RECRUITER_TOKEN is not set: run make local-env")
    h = {"Authorization": f"Bearer {token.get_secret_value()}"}
    c = httpx.Client(base_url=base_url, timeout=60)
    rubrics, rows = load()
    for job in ("analyst", "nurse", "site"):
        spec = rubrics[job]
        r = c.post(
            "/jobs",
            headers=h,
            json={
                "title": spec["title"],
                "description": ADS[job] + " " + ADS[job],
                "location": "Sydney NSW",
                "work_arrangement": "onsite",
                "salary_min": int(spec["salary_max"] * 0.8),
                "salary_max": int(spec["salary_max"]),
            },
        )
        r.raise_for_status()
        jid = r.json()["id"]
        for _ in range(90):
            st = c.get(f"/jobs/{jid}", headers=h).json()
            if st["state"] in ("RUBRIC_READY", "NEEDS_REVIEW"):
                break
            time.sleep(2)
        r = c.post(
            f"/jobs/{jid}/rubric",
            headers=h,
            json={
                "criteria": spec["criteria"],
                "flags": [],
                "reason": "phase 3 fixed rubric (demo seed)",
            },
        )
        r.raise_for_status()
        version = max(x["version"] for x in c.get(f"/jobs/{jid}", headers=h).json()["rubrics"])
        c.post(
            f"/jobs/{jid}/approve", headers=h, json={"version": version, "reason": "demo seed"}
        ).raise_for_status()
        for case in cases_for(job, rows, drill=False):
            inp = case["input"]
            path = DATASETS / inp["file"]
            it = inp["intake"]
            data = {
                "full_name": it["name"],
                "email": it["email"],
                "phone": it["phone"],
                "consent": "yes",
                **form_answers(
                    inp["answers"]
                    or {
                        "right_to_work": "yes",
                        "expected_salary": "100000",
                        "notice_period": "3 to 4 weeks",
                        "location_fit": "yes",
                        "current_role": "see CV",
                    }
                ),
            }
            r = c.post(
                f"/apply/{jid}",
                data=data,
                files={"cv": (path.name, path.read_bytes(), "application/octet-stream")},
            )
            print(job, case["id"], r.status_code)
    print("applications sent; the worker parses and scores them (watch make logs)")


def main() -> None:
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--offline", action="store_true")
    mode.add_argument("--real", action="store_true")
    ap.add_argument("--api", default="http://localhost:8000")
    args = ap.parse_args()
    if args.offline:
        asyncio.run(seed_offline())
    else:
        seed_real(args.api)


if __name__ == "__main__":
    main()
