"""Recruiter score views (phase 3 design section 7). Read only: scores are
recommendations; shortlist and reject stay recruiter decisions on the candidate API."""

import uuid
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from app.db.models import Candidate, Decision, Job, Rubric, Score
from app.scoring.agreement import agreement

BAND_ORDER = {"advance": 0, "maybe": 1, "reject": 2}


async def _latest_approved_version(s: Any, job_id: uuid.UUID) -> int | None:
    v = await s.scalar(
        select(func.max(Rubric.version)).where(
            Rubric.job_id == job_id, Rubric.approved_at.is_not(None)
        )
    )
    return int(v) if v is not None else None


def _flags(score: Score, current_version: int | None) -> list[dict[str, Any]]:
    flags = list(score.flags)
    if current_version is not None and current_version > score.rubric_version:
        flags.append(
            {
                "kind": "rubric_outdated",
                "text": f"Scored on rubric v{score.rubric_version}; v{current_version} "
                "is now approved",
            }
        )
    return flags


def _knockouts(score: Score) -> list[dict[str, Any]]:
    return [
        {"key": a["key"], "outcome": a["outcome"]}
        for a in score.answer_results
        if a.get("rule") is not None
    ]


def register(app: FastAPI, Recruiter: Any, Pl: Any) -> None:  # noqa: N803
    @app.get("/jobs/{job_id}/candidates")
    async def ranked_candidates(job_id: uuid.UUID, _: Recruiter, p: Pl) -> JSONResponse:
        """Scored candidates by total (highest first, ties by apply time), then the rest."""
        async with p.sessions() as s:
            if await s.get(Job, job_id) is None:
                return JSONResponse(
                    status_code=404, content={"error": "not_found", "detail": "no such job"}
                )
            current = await _latest_approved_version(s, job_id)
            cands = (
                (await s.execute(select(Candidate).where(Candidate.job_id == job_id)))
                .scalars()
                .all()
            )
            scores = (
                (
                    await s.execute(
                        select(Score)
                        .join(Candidate, Candidate.id == Score.candidate_id)
                        .where(Candidate.job_id == job_id)
                        .order_by(Score.created_at)
                    )
                )
                .scalars()
                .all()
            )
            decisions = (
                (
                    await s.execute(
                        select(Decision)
                        .join(Candidate, Candidate.id == Decision.candidate_id)
                        .where(Candidate.job_id == job_id)
                        .order_by(Decision.created_at)
                    )
                )
                .scalars()
                .all()
            )
        latest: dict[uuid.UUID, Score] = {}
        for sc in scores:  # ordered by time, so the last one wins
            latest[sc.candidate_id] = sc
        last_decision: dict[uuid.UUID, Decision] = {d.candidate_id: d for d in decisions}
        summary = agreement((d.recommended, d.decision) for d in last_decision.values())

        scored, unscored = [], []
        for c in cands:
            base = {
                "id": str(c.id),
                "label": c.display_label,
                "state": c.state,
                "applied_at": c.created_at.isoformat(),
                "erased": c.erased_at is not None,
                "state_version": c.state_version,
            }
            d = last_decision.get(c.id)
            if d is not None:
                base["decision"] = {
                    "decision": d.decision,
                    "recommended": d.recommended,
                    "override": d.override,
                }
            sc = latest.get(c.id)
            if sc is None:
                unscored.append(base)
                continue
            scored.append(
                {
                    **base,
                    "total": sc.total,
                    "band": sc.band,
                    "flags": _flags(sc, current),
                    "knockouts": _knockouts(sc),
                    "rubric_version": sc.rubric_version,
                }
            )
        scored.sort(key=lambda r: (-r["total"], r["applied_at"]))
        unscored.sort(key=lambda r: (r["state"], r["applied_at"]))
        for i, r in enumerate(scored, start=1):
            r["rank"] = i
        return JSONResponse(
            content={
                "job_id": str(job_id),
                "rubric_version": current,
                "outdated": sum(
                    1
                    for r in scored
                    if r["state"] == "SCORED"
                    and current is not None
                    and r["rubric_version"] < current
                ),
                "agreement": summary.as_dict(),
                "scored": scored,
                "unscored": unscored,
            }
        )

    @app.get("/candidates/{candidate_id}/score")
    async def candidate_score(candidate_id: uuid.UUID, _: Recruiter, p: Pl) -> JSONResponse:
        """Latest score with the evidence behind every criterion."""
        async with p.sessions() as s:
            sc = (
                await s.execute(
                    select(Score)
                    .where(Score.candidate_id == candidate_id)
                    .order_by(Score.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if sc is None:
                return JSONResponse(
                    status_code=404, content={"error": "not_found", "detail": "no score yet"}
                )
            rubric = await s.get(Rubric, sc.rubric_id)
            assert rubric is not None
            current = await _latest_approved_version(s, rubric.job_id)
        by_id = {c["id"]: c for c in rubric.criteria}
        criteria = []
        for j in sc.judgements:
            c = by_id.get(j["criterion_id"], {})
            criteria.append(
                {
                    "criterion_id": j["criterion_id"],
                    "text": c.get("text"),
                    "kind": c.get("kind"),
                    "weight": c.get("weight"),
                    "verdict": j["verdict"],
                    "points": j["points"],
                    "reason": j.get("reason"),
                    "quote": j.get("quote"),
                }
            )
        return JSONResponse(
            content={
                "candidate_id": str(candidate_id),
                "total": sc.total,
                "band": sc.band,
                "recommendation_only": True,
                "reasons": sc.reasons,
                "flags": _flags(sc, current),
                "criteria": criteria,
                "answers": sc.answer_results,
                "rubric_version": sc.rubric_version,
                "prompt_id": sc.prompt_id,
                "prompt_version": sc.prompt_version,
                "model": sc.model,
                "cost_usd": sc.cost_usd,
                "erased": sc.erased,
                "created_at": sc.created_at.isoformat(),
            }
        )

    _ = (ranked_candidates, candidate_score)
