"""Phase 4 backend: decisions and overrides, the agreement rate, blind review contact
details with the access log, the review queue, rescoring, erasure and list speed."""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy import func, select

from app.config import Settings
from app.db.models import AccessEvent, Candidate, Decision, Score
from app.db.session import SessionMaker
from app.scoring.agreement import agreement, is_override
from tests.phase1_helpers import RUBRIC, answers, score_json
from tests.test_parse_step import AUTH, PROFILE, Env, cv_docx, make_env

STRONG = score_json(ba_experience="met", stakeholders="met")  # 86.7 advance
WEAK = score_json()  # 43.3 reject

# ---- agreement table (no database) -----------------------------------------------------

TABLE = [
    ("advance", "shortlist", False),
    ("advance", "reject", True),
    ("reject", "reject", False),
    ("reject", "shortlist", True),
    ("maybe", "shortlist", False),
    ("maybe", "reject", False),
    ("none", "shortlist", False),
    ("none", "reject", False),
]


@pytest.mark.parametrize("rec,dec,override", TABLE)
def test_override_table(rec: str, dec: str, override: bool) -> None:
    assert is_override(rec, dec) is override


def test_agreement_rate_counts_only_advance_and_reject() -> None:
    pairs = [
        ("advance", "shortlist"),
        ("advance", "shortlist"),
        ("advance", "reject"),
        ("reject", "reject"),
        ("reject", "reject"),
        ("reject", "reject"),
        ("reject", "shortlist"),
        ("maybe", "shortlist"),
        ("maybe", "reject"),
        ("none", "reject"),
    ]
    a = agreement(pairs)
    assert (a.decided, a.counted, a.agreed, a.overrides, a.maybe_or_none) == (10, 7, 5, 2, 3)
    assert a.rate == round(5 / 7, 3)
    assert agreement([]).rate is None


# ---- API -------------------------------------------------------------------------------

pytestmark_db = pytest.mark.integration


async def apply_as(env: Env, n: int, **ans: str) -> str:
    data = {
        "full_name": f"Zephyrine Quoll{n}",
        "email": f"zq{n}@example.test",
        "phone": f"0491 570 {600 + n}",
        "consent": "yes",
        **answers(**ans),
    }
    r = await env.c.post(
        f"/apply/{env.job_id}", data=data, files={"cv": ("cv.docx", cv_docx(), "x")}
    )
    assert r.status_code == 201, r.text
    await env.p.drain()
    async with env.p.sessions() as s:
        cid = (
            await s.execute(
                select(Candidate.id).where(Candidate.email_normalised == f"zq{n}@example.test")
            )
        ).scalar_one()
    return str(cid)


@pytest.fixture
async def env(sessions: SessionMaker, settings: Settings) -> AsyncIterator[Env]:
    async for e in make_env(sessions, settings, [PROFILE, STRONG, PROFILE, WEAK]):
        yield e


async def two(env: Env) -> tuple[str, str]:
    return await apply_as(env, 1), await apply_as(env, 2)


async def version(env: Env, cid: str) -> int:
    return int((await env.state(cid))["state_version"])


async def post(env: Env, cid: str, action: str, reason: str, **extra: Any) -> Any:
    return await env.c.post(
        f"/candidates/{cid}/{action}",
        json={"reason": reason, "expected_version": await version(env, cid), **extra},
        headers=AUTH,
    )


@pytest.mark.integration
async def test_agreeing_decisions_are_recorded(env: Env) -> None:
    strong, weak = await two(env)
    assert (
        await post(env, strong, "shortlist", "Agrees with the recommendation")
    ).status_code == 200
    assert (await post(env, weak, "reject", "Agrees with the recommendation")).status_code == 200
    async with env.p.sessions() as s:
        rows = {str(d.candidate_id): d for d in (await s.execute(select(Decision))).scalars()}
    assert (rows[strong].recommended, rows[strong].decision, rows[strong].override) == (
        "advance",
        "shortlist",
        False,
    )
    assert (rows[weak].recommended, rows[weak].override) == ("reject", False)
    ranked = (await env.c.get(f"/jobs/{env.job_id}/candidates", headers=AUTH)).json()
    assert ranked["agreement"] == {
        "decided": 2,
        "counted": 2,
        "agreed": 2,
        "overrides": 0,
        "maybe_or_none": 0,
        "rate": 1.0,
    }
    assert ranked["scored"][0]["decision"]["decision"] == "shortlist"


@pytest.mark.integration
@pytest.mark.parametrize("reason", ["ok", "x", "too short"])
async def test_override_needs_a_real_reason(env: Env, reason: str) -> None:
    _strong, weak = await two(env)
    r = await post(env, weak, "shortlist", reason)
    assert r.status_code == 422 and "reason of at least 10" in r.json()["detail"]
    assert (await env.state(weak))["state"] == "SCORED"  # nothing moved
    async with env.p.sessions() as s:
        assert (await s.execute(select(func.count()).select_from(Decision))).scalar() == 0


@pytest.mark.integration
async def test_override_with_a_reason_is_logged(env: Env) -> None:
    strong, weak = await two(env)
    assert (
        await post(env, weak, "shortlist", "Strong portfolio not reflected in the CV text")
    ).status_code == 200
    assert (
        await post(env, strong, "reject", "Already interviewed for this team in May")
    ).status_code == 200
    ranked = (await env.c.get(f"/jobs/{env.job_id}/candidates", headers=AUTH)).json()
    assert ranked["agreement"]["overrides"] == 2 and ranked["agreement"]["rate"] == 0.0
    jobs = (await env.c.get("/jobs", headers=AUTH)).json()["jobs"]
    assert jobs[0]["agreement"]["overrides"] == 2 and jobs[0]["undecided"] == 0


@pytest.mark.integration
async def test_stale_page_cannot_decide_twice(env: Env) -> None:
    strong, _weak = await two(env)
    v = await version(env, strong)
    body = {"reason": "Agrees with the recommendation", "expected_version": v}
    assert (
        await env.c.post(f"/candidates/{strong}/shortlist", json=body, headers=AUTH)
    ).status_code == 200
    again = await env.c.post(f"/candidates/{strong}/reject", json=body, headers=AUTH)
    assert again.status_code == 409
    async with env.p.sessions() as s:
        assert (await s.execute(select(func.count()).select_from(Decision))).scalar() == 1


@pytest.mark.integration
async def test_contact_details_only_after_shortlist_and_logged(env: Env) -> None:
    strong, weak = await two(env)
    before = await env.c.get(f"/candidates/{strong}/contact", headers=AUTH)
    assert before.status_code == 403 and before.json()["error"] == "blind_review"
    for path in (
        f"/candidates/{strong}",
        f"/candidates/{strong}/score",
        f"/jobs/{env.job_id}/candidates",
    ):
        body = (await env.c.get(path, headers=AUTH)).text
        assert "Quoll1" not in body and "zq1@example.test" not in body and "570 601" not in body
    await post(env, strong, "shortlist", "Agrees with the recommendation")
    after = await env.c.get(f"/candidates/{strong}/contact", headers=AUTH)
    assert after.status_code == 200 and after.json()["email"] == "zq1@example.test"
    log = (await env.c.get(f"/candidates/{strong}/access", headers=AUTH)).json()["events"]
    assert [e["what"] for e in log] == ["contact"]
    async with env.p.sessions() as s:
        assert (await s.execute(select(func.count()).select_from(AccessEvent))).scalar() == 1
    assert (await env.c.get(f"/candidates/{weak}/contact", headers=AUTH)).status_code == 403


@pytest.mark.integration
async def test_review_queue_lists_needs_review_with_reason(
    sessions: SessionMaker, settings: Settings
) -> None:
    bad = '{"judgements": [], "injection_suspected": false, "injection_note": ""}'
    async for e in make_env(sessions, settings, [PROFILE, bad, bad, bad]):
        cid = await apply_as(e, 1)
        q = (await e.c.get("/review-queue", headers=AUTH)).json()
        assert [c["id"] for c in q["candidates"]] == [cid]
        assert q["candidates"][0]["reason"] == "cv scorer failed: LLMOutputInvalid"
        r = await post(e, cid, "reject", "Could not be scored, CV unreadable to us")
        assert r.status_code == 200
        async with e.p.sessions() as s:
            d = (await s.execute(select(Decision))).scalar_one()
        assert d.recommended == "none" and d.override is False


@pytest.mark.integration
async def test_rescore_on_a_new_rubric_keeps_state_and_old_score(
    sessions: SessionMaker, settings: Settings
) -> None:
    async for e in make_env(sessions, settings, [PROFILE, WEAK, STRONG]):
        cid = await apply_as(e, 1)
        jid = e.job_id
        assert (await e.c.post(f"/jobs/{jid}/rescore", headers=AUTH)).json()["queued"] == 0
        await e.c.post(f"/jobs/{jid}/close", json={"reason": "revise"}, headers=AUTH)
        r = await e.c.post(
            f"/jobs/{jid}/rubric",
            json={"criteria": RUBRIC["criteria"], "flags": [], "reason": "tightened wording"},
            headers=AUTH,
        )
        assert r.status_code == 200, r.text
        r = await e.c.post(
            f"/jobs/{jid}/approve", json={"version": 2, "reason": "ok"}, headers=AUTH
        )
        assert r.status_code == 200, r.text
        ranked = (await e.c.get(f"/jobs/{jid}/candidates", headers=AUTH)).json()
        assert ranked["outdated"] == 1
        assert any(f["kind"] == "rubric_outdated" for f in ranked["scored"][0]["flags"])
        assert (await e.c.post(f"/jobs/{jid}/rescore", headers=AUTH)).json()["queued"] == 1
        await e.p.drain()
        async with e.p.sessions() as s:
            rows = list((await s.execute(select(Score).order_by(Score.created_at))).scalars())
        assert [r.rubric_version for r in rows] == [1, 2]
        assert (await e.state(cid))["state"] == "SCORED"
        ranked = (await e.c.get(f"/jobs/{jid}/candidates", headers=AUTH)).json()
        assert ranked["outdated"] == 0 and ranked["scored"][0]["band"] == "advance"
        assert (await e.c.post(f"/jobs/{jid}/rescore", headers=AUTH)).json()["queued"] == 0
        audit = (await e.c.get(f"/jobs/{jid}", headers=AUTH)).json()["audit"]
        assert any("rescore requested: 1 candidates" in a["reason"] for a in audit)


@pytest.mark.integration
async def test_erase_clears_the_decision_reason(env: Env) -> None:
    strong, _ = await two(env)
    await post(env, strong, "shortlist", "Met her at the Brisbane meetup, very strong")
    assert (await env.c.post(f"/candidates/{strong}/erase", headers=AUTH)).status_code == 200
    async with env.p.sessions() as s:
        d = (await s.execute(select(Decision))).scalar_one()
    assert d.reason == "" and d.decision == "shortlist" and d.recommended == "advance"
    assert (await env.c.get(f"/candidates/{strong}/contact", headers=AUTH)).status_code == 410


@pytest.mark.integration
async def test_ranked_list_with_200_candidates_is_fast(env: Env) -> None:
    from app.db.models import CvParse, Rubric

    async with env.p.sessions() as s, s.begin():
        rubric_id = str(
            (
                await s.execute(select(Rubric.id).where(Rubric.job_id == uuid.UUID(env.job_id)))
            ).scalar_one()
        )
        for i in range(200):
            cid = uuid.uuid4()
            s.add(
                Candidate(
                    id=cid,
                    state="SCORED",
                    state_version=3,
                    display_label=f"Applicant {i}",
                    job_id=uuid.UUID(env.job_id),
                )
            )
            await s.flush()
            parse = CvParse(
                candidate_id=cid,
                status="parsed",
                text_layer=True,
                redacted_text="x",
                redaction_counts={},
            )
            s.add(parse)
            await s.flush()
            s.add(
                Score(
                    candidate_id=cid,
                    rubric_id=uuid.UUID(rubric_id),
                    rubric_version=1,
                    cv_parse_id=parse.id,
                    judgements=[],
                    answer_results=[],
                    total=float(i % 100),
                    band="maybe",
                    reasons=[],
                    flags=[],
                    injection_suspected=False,
                    prompt_id="cv-scorer",
                    prompt_version="v2",
                    model="m",
                )
            )
    times = []
    for _ in range(50):
        t = time.perf_counter()
        r = await env.c.get(f"/jobs/{env.job_id}/candidates", headers=AUTH)
        times.append(time.perf_counter() - t)
        assert r.status_code == 200 and len(r.json()["scored"]) == 200
    times.sort()
    p95 = times[int(len(times) * 0.95) - 1]
    assert p95 < 0.3, f"p95 {p95:.3f} s"
