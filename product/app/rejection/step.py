"""The real draft step (phase 5 design sections 3 and 4): REJECTED to REJECTION_DRAFTED.

Returns a decision; the pipeline applies it (the move and draft version 1 in one
transaction). The plain template is used, marked for the recruiter, when there is no
score (a reject from NEEDS_REVIEW), when the recruiter overrode an advance (the scores
do not support a reject, so no reason is invented), when nothing was missed, when no
model is configured, and when the writer's drafts keep failing the checks.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select

from app.agents.rejection_writer import write_rejection
from app.db.models import Candidate, CvParse, Decision, Job, Rubric, Score, ScreeningQuestion
from app.db.session import SessionMaker
from app.domain.states import CandidateState
from app.llm.client import LLMClient, LLMError
from app.rejection.checks import all_passed, run_checks
from app.rejection.compose import ReasonSource, assemble_body, reason_sources, template_parts
from app.workflow.decisions import latest_score

S = CandidateState


@dataclass
class DraftDecision:
    to_state: CandidateState
    reason: str
    row: dict[str, Any] | None = None  # RejectionDraft fields (version 1)
    trace: dict[str, Any] = field(default_factory=dict)
    use_stub: bool = False


def _template_row(
    title: str, company: str, cv_text: str, fallback: str, score_id: uuid.UUID | None
) -> dict[str, Any]:
    opening, closing = template_parts(title, company)
    body = assemble_body(opening, [], closing)
    checks = run_checks(body, reason_ids=[], allowed_ids=[], cv_text=cv_text)
    return {
        "version": 1,
        "source": "template",
        "score_id": score_id,
        "opening": opening,
        "closing": closing,
        "reasons": [],
        "body": body,
        "checks": [c.as_dict() for c in checks],
        "fallback_reason": fallback,
        "needs_edit": True,
        "actor_id": "system",
    }


async def run_draft(
    sessions: SessionMaker,
    llm: LLMClient | None,
    candidate_id: uuid.UUID,
    *,
    company: str,
    production: bool,
) -> DraftDecision:
    async with sessions() as s:
        cand = await s.get(Candidate, candidate_id)
        if cand is None:
            return DraftDecision(S.NEEDS_REVIEW, "candidate not found")
        if cand.job_id is None:
            if production:
                return DraftDecision(S.NEEDS_REVIEW, "no job to write a rejection for")
            return DraftDecision(S.REJECTION_DRAFTED, "", use_stub=True)  # phase 0 test candidates
        job = await s.get(Job, cand.job_id)
        if job is None:
            return DraftDecision(S.NEEDS_REVIEW, "no job to write a rejection for")
        title, location, arrangement = job.title, job.location, job.work_arrangement
        decision = (
            await s.execute(
                select(Decision)
                .where(Decision.candidate_id == candidate_id, Decision.decision == "reject")
                .order_by(Decision.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        score: Score | None = None
        if decision is not None and decision.score_id is not None:
            score = await s.get(Score, decision.score_id)  # the score the recruiter saw
        if score is None and decision is None:
            score = await latest_score(s, candidate_id)
        overrode_advance = (
            decision is not None and decision.override and decision.recommended == "advance"
        )
        parse = (
            await s.execute(
                select(CvParse)
                .where(CvParse.candidate_id == candidate_id, CvParse.status == "parsed")
                .order_by(CvParse.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        cv_text = (parse.redacted_text or "") if parse is not None else ""
        sources: list[ReasonSource] = []
        if score is not None and not score.erased:
            rubric = await s.get(Rubric, score.rubric_id)
            questions = {
                q.key: q.prompt
                for q in (
                    await s.execute(
                        select(ScreeningQuestion).where(ScreeningQuestion.job_id == job.id)
                    )
                ).scalars()
            }
            sources = reason_sources(
                list(rubric.criteria) if rubric is not None else [],
                list(score.judgements),
                list(score.answer_results),
                questions,
                location=location,
                arrangement=arrangement,
            )
        score_id = score.id if score is not None else None
        score_state = "none" if score is None else ("erased" if score.erased else "ok")

    return await compose_draft(
        llm,
        title=title,
        company=company,
        sources=sources,
        cv_text=cv_text,
        score_state=score_state,
        overrode_advance=overrode_advance,
        score_id=score_id,
        candidate_id=str(candidate_id),
    )


async def compose_draft(
    llm: LLMClient | None,
    *,
    title: str,
    company: str,
    sources: list[ReasonSource],
    cv_text: str,
    score_state: str,  # ok | none | erased
    overrode_advance: bool,
    score_id: uuid.UUID | None = None,
    candidate_id: str = "eval",
) -> DraftDecision:
    """The routing and the writer, with no database: the draft step and the evals both use
    this, so the evals measure the code that runs."""

    def template(fallback: str, **trace: Any) -> DraftDecision:
        row = _template_row(title, company, cv_text, fallback, score_id)
        return DraftDecision(
            S.REJECTION_DRAFTED,
            f"template: {fallback}",
            row=row,
            trace={"outcome": "template", "fallback": fallback, **trace},
        )

    if score_state == "none":
        return template("no score to explain")
    if score_state == "erased":
        return template("the score was erased")
    if overrode_advance:
        return template("the recruiter overrode an advance recommendation")
    if not sources:
        return template("no missed requirements to explain")
    if llm is None:
        return template("no language model configured (provider key not set)")
    try:
        result = await write_rejection(
            llm,
            job_title=title,
            company=company,
            sources=sources,
            cv_text=cv_text,
            candidate_id=str(candidate_id),
        )
    except LLMError as exc:
        return template(
            f"the writer's drafts failed the checks or the model failed ({type(exc).__name__})",
            error=type(exc).__name__,
        )

    out = result.output
    body = out.body()
    checks = run_checks(
        body,
        reason_ids=[r.source_id for r in out.reasons],
        allowed_ids=[x.id for x in sources],
        cv_text=cv_text,
    )
    if not all_passed(checks):  # cannot happen (the client ran the same checks); belt and braces
        return template("the draft failed the checks")
    by_id = {x.id: x for x in sources}
    reasons = [
        {
            "source_id": r.source_id,
            "kind": by_id[r.source_id].kind,
            "requirement": by_id[r.source_id].requirement,
            "sentence": r.sentence,
        }
        for r in out.reasons
    ]
    return DraftDecision(
        S.REJECTION_DRAFTED,
        f"drafted by {result.prompt_id} {result.prompt_version} "
        f"({len(reasons)} reasons, all checks passed)",
        row={
            "version": 1,
            "source": "agent",
            "score_id": score_id,
            "opening": out.opening,
            "closing": out.closing,
            "reasons": reasons,
            "body": body,
            "checks": [c.as_dict() for c in checks],
            "fallback_reason": None,
            "needs_edit": False,
            "prompt_id": result.prompt_id,
            "prompt_version": result.prompt_version,
            "model": result.model,
            "cost_usd": result.cost_usd,
            "attempts": result.attempts,
            "actor_id": "system",
        },
        trace={
            "outcome": "drafted",
            "prompt_version": f"{result.prompt_id}-{result.prompt_version}",
            "model": result.model,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "cost_usd": result.cost_usd,
            "attempts": result.attempts,
            "reasons": len(reasons),
            "sources": len(sources),
        },
    )
