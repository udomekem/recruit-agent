"""The real score step (phase 3 design section 6): PARSED to SCORED.

Returns a decision; the pipeline applies it (state move and Score row in one transaction).
The scorer reads only the stored redacted copy. Reasons in the audit log hold no CV text.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select

from app.agents.cv_scorer import injection_phrases, score_cv
from app.db.models import Answer, Candidate, CvParse, Job, Rubric, ScreeningQuestion
from app.db.session import SessionMaker
from app.domain.states import CandidateState
from app.llm.client import LLMClient, LLMError
from app.scoring.answers import QuestionInput, score_answers
from app.scoring.formula import POINTS, score_card

S = CandidateState


@dataclass
class ScoreDecision:
    to_state: CandidateState
    reason: str
    row: dict[str, Any] | None = None  # Score fields to store with the move
    trace: dict[str, Any] = field(default_factory=dict)
    use_stub: bool = False


async def run_score(
    sessions: SessionMaker,
    llm: LLMClient | None,
    candidate_id: uuid.UUID,
    *,
    production: bool,
) -> ScoreDecision:
    async with sessions() as s:
        cand = await s.get(Candidate, candidate_id)
        if cand is None:
            return ScoreDecision(S.NEEDS_REVIEW, "candidate not found")
        parse = (
            await s.execute(
                select(CvParse)
                .where(CvParse.candidate_id == candidate_id, CvParse.status == "parsed")
                .order_by(CvParse.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if parse is None or cand.job_id is None:
            if production:
                return ScoreDecision(S.NEEDS_REVIEW, "no parsed CV to score")
            return ScoreDecision(S.SCORED, "", use_stub=True)  # phase 0 test candidates
        job = await s.get(Job, cand.job_id)
        rubric = (
            await s.execute(
                select(Rubric)
                .where(Rubric.job_id == cand.job_id, Rubric.approved_at.is_not(None))
                .order_by(Rubric.version.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if job is None or rubric is None:
            return ScoreDecision(S.NEEDS_REVIEW, "no approved rubric for this job")
        rows = (
            await s.execute(
                select(ScreeningQuestion, Answer)
                .outerjoin(
                    Answer,
                    (Answer.question_id == ScreeningQuestion.id)
                    & (Answer.candidate_id == candidate_id),
                )
                .where(ScreeningQuestion.job_id == cand.job_id)
                .order_by(ScreeningQuestion.position)
            )
        ).all()
        questions = [
            QuestionInput(q.key, q.prompt, q.answer_type, q.knockout_rule, a.value if a else None)
            for q, a in rows
        ]
        criteria = list(rubric.criteria)
        redacted = parse.redacted_text or ""
        hidden = int((parse.redaction_counts or {}).get("hidden_text", 0))
        parse_id, rubric_id, rubric_version = parse.id, rubric.id, rubric.version
        salary_max = job.salary_max

    answers = score_answers(questions, salary_max=salary_max)
    if llm is None:
        return ScoreDecision(S.NEEDS_REVIEW, "no language model configured (provider key not set)")
    try:
        result = await score_cv(
            llm, redacted_text=redacted, criteria=criteria, candidate_id=str(candidate_id)
        )
    except ValueError as exc:  # too long to score
        return ScoreDecision(S.NEEDS_REVIEW, str(exc), trace={"outcome": "too_long"})
    except LLMError as exc:
        return ScoreDecision(
            S.NEEDS_REVIEW,
            f"cv scorer failed: {type(exc).__name__}",
            trace={"outcome": "scorer_failed", "error": type(exc).__name__},
        )

    out = result.output
    verdicts = {j.criterion_id: j.verdict for j in out.judgements}
    injection = out.injection_suspected or injection_phrases(redacted)
    card = score_card(
        criteria, verdicts, answers, injection_suspected=injection, hidden_chars=hidden
    )
    judgements = [
        {
            "criterion_id": j.criterion_id,
            "verdict": j.verdict,
            "points": POINTS[j.verdict],
            "reason": j.reason,
            "quote": j.quote if j.verdict != "not_met" else "",
        }
        for j in out.judgements
    ]
    counts = {v: sum(j["verdict"] == v for j in judgements) for v in POINTS}
    return ScoreDecision(
        S.SCORED,
        f"scored {card.total:.1f} against rubric v{rubric_version}: {card.band} "
        "(recommendation only)",
        row={
            "rubric_id": rubric_id,
            "rubric_version": rubric_version,
            "cv_parse_id": parse_id,
            "judgements": judgements,
            "answer_results": [a.as_dict() for a in answers],
            "total": card.total,
            "band": card.band,
            "reasons": card.reasons,
            "flags": [f.as_dict() for f in card.flags],
            "injection_suspected": injection,
            "prompt_id": result.prompt_id,
            "prompt_version": result.prompt_version,
            "model": result.model,
            "cost_usd": result.cost_usd,
            "attempts": result.attempts,
        },
        trace={
            "outcome": "scored",
            "prompt_version": f"{result.prompt_id}-{result.prompt_version}",
            "model": result.model,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "cost_usd": result.cost_usd,
            "attempts": result.attempts,
            "criteria": len(criteria),
            "met": counts["met"],
            "partly_met": counts["partly_met"],
            "not_met": counts["not_met"],
            "total": card.total,
            "band": card.band,
            "injection_suspected": injection,
            "hidden_chars": hidden,
        },
    )
