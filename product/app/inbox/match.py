"""The matching step (phase 5B design sections 3 and 4): a PARSED candidate with no job
gets one before scoring. The job matcher reads only the redacted CV. When it is sure, code
sets the job and scoring goes on; otherwise the candidate goes to NEEDS_REVIEW "needs a
job" with the best two suggestions, and the recruiter picks."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select

from app.agents.job_matcher import PROMPT, JobForMatch, choose, match_job
from app.config import Settings
from app.db.models import Candidate, CvParse, Job, Rubric
from app.db.session import SessionMaker
from app.domain.jobs import JobState
from app.llm.client import LLMClient, LLMError


@dataclass
class MatchDecision:
    job_id: uuid.UUID | None
    reason: str
    row: dict[str, Any]
    titles: dict[str, str] = field(default_factory=dict)


async def open_jobs_for_match(sessions: SessionMaker) -> list[JobForMatch]:
    async with sessions() as s:
        jobs = list(
            (
                await s.execute(
                    select(Job).where(
                        Job.state == JobState.OPEN, Job.approved_rubric_version.is_not(None)
                    )
                )
            ).scalars()
        )
        out = []
        for j in jobs:
            rubric = (
                await s.execute(
                    select(Rubric).where(
                        Rubric.job_id == j.id, Rubric.version == j.approved_rubric_version
                    )
                )
            ).scalar_one_or_none()
            musts = [
                str(c.get("text", ""))
                for c in (rubric.criteria if rubric else [])
                if c.get("kind") == "must_have"
            ]
            out.append(JobForMatch(j.id, j.title, j.location, musts[:8]))
    return out


async def run_match(
    sessions: SessionMaker, llm: LLMClient | None, candidate_id: uuid.UUID, *, settings: Settings
) -> MatchDecision:
    jobs = await open_jobs_for_match(sessions)
    titles = {str(j.id): j.title for j in jobs}
    base: dict[str, Any] = {"fits": [], "chosen_job_id": None, "outcome": "needs_job"}
    if not jobs:
        return MatchDecision(
            None,
            "needs a job: there are no open jobs with an approved rubric",
            {**base, "reason": "no open jobs"},
            titles,
        )
    async with sessions() as s:
        parse = (
            await s.execute(
                select(CvParse)
                .where(CvParse.candidate_id == candidate_id)
                .order_by(CvParse.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        cand = await s.get(Candidate, candidate_id)
    text = (parse.redacted_text if parse else None) or ""
    if cand is None or not text.strip():
        return MatchDecision(
            None,
            "needs a job: the CV text could not be read",
            {**base, "reason": "no CV text"},
            titles,
        )
    if llm is None:
        return MatchDecision(
            None,
            "needs a job: no language model configured",
            {**base, "reason": "no model"},
            titles,
        )
    try:
        result = await match_job(llm, jobs=jobs, cv_text=text, candidate_id=str(candidate_id))
    except LLMError as exc:
        return MatchDecision(
            None,
            f"needs a job: the matcher failed ({type(exc).__name__})",
            {**base, "reason": "matcher failed"},
            titles,
        )
    pick = choose(result.output, threshold=settings.match_threshold, gap=settings.match_gap)
    fits = [f.model_dump() for f in result.output.fits]
    row = {
        "fits": fits,
        "chosen_job_id": pick.job_id,
        "outcome": "auto_matched" if pick.job_id else "needs_job",
        "reason": pick.why,
        "prompt_id": PROMPT.id,
        "prompt_version": PROMPT.version,
        "model": result.model,
        "cost_usd": result.cost_usd,
        "attempts": result.attempts,
    }
    if pick.job_id is not None:
        return MatchDecision(
            pick.job_id,
            f"matched to {titles[str(pick.job_id)]} by the AI ({pick.why})",
            row,
            titles,
        )
    suggest = ", ".join(f"{titles.get(j, j)} ({fit:.2f})" for j, fit in pick.top)
    return MatchDecision(None, f"needs a job: {pick.why}; suggested: {suggest}", row, titles)
