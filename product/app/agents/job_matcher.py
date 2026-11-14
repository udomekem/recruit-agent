"""Job matcher (phase 5B design section 4): which open job does this CV fit, if any.

Input: the open jobs (trusted: id, title, location, must haves from the approved rubric)
and the redacted CV, fenced as untrusted data. Never the email subject, body, sender,
name or contact details. Output: one fit per offered job (0 to 1) with a short reason.
Code decides: auto match only when the best fit clears the threshold and leads the next
job by the gap; otherwise the recruiter picks. The matcher never scores the candidate.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from pydantic import BaseModel, Field

from app.llm.client import LLMClient, LLMResult, ModelTier
from app.llm.prompts import PromptRef

# v2 (phase 5B evals): fit is the kind of job, not the strength of the applicant; v1 rated
# "maybe" CVs 0.6 to 0.75 and left half the clear CVs for the recruiter.
PROMPT = PromptRef("job-matcher", "v2")
EFFORT = "low"
CV_CHARS = 6000


class Fit(BaseModel):
    job_id: str
    fit: float = Field(ge=0, le=1)
    reason: str = Field(max_length=200)


class MatcherOutput(BaseModel):
    fits: list[Fit]
    none_fit: bool


@dataclass(frozen=True)
class JobForMatch:
    id: uuid.UUID
    title: str
    location: str
    must_haves: list[str]

    def for_model(self) -> dict[str, object]:
        return {
            "id": str(self.id),
            "title": self.title,
            "location": self.location,
            "must_haves": self.must_haves,
        }


def check_fits(out: MatcherOutput, offered: list[str]) -> None:
    got = [f.job_id for f in out.fits]
    if sorted(got) != sorted(offered):
        raise ValueError(
            "give exactly one fit for each offered job id and no other ids "
            f"(offered {offered}, got {got})"
        )


@dataclass(frozen=True)
class MatchChoice:
    job_id: uuid.UUID | None
    top: list[tuple[str, float]]  # best two (job id, fit)
    why: str


def choose(out: MatcherOutput, *, threshold: float, gap: float) -> MatchChoice:
    ranked = sorted(((f.job_id, f.fit) for f in out.fits), key=lambda x: -x[1])
    top = ranked[:2]
    if not ranked or out.none_fit:
        return MatchChoice(None, top, "the CV does not clearly fit any open job")
    best, second = ranked[0][1], (ranked[1][1] if len(ranked) > 1 else 0.0)
    if best < threshold:
        return MatchChoice(None, top, f"the best fit ({best:.2f}) is below {threshold:.2f}")
    if best - second < gap:
        return MatchChoice(None, top, f"two jobs are close ({best:.2f} and {second:.2f})")
    return MatchChoice(uuid.UUID(ranked[0][0]), top, f"fit {best:.2f}, next {second:.2f}")


async def match_job(
    client: LLMClient, *, jobs: list[JobForMatch], cv_text: str, candidate_id: str
) -> LLMResult[MatcherOutput]:
    if not jobs:
        raise ValueError("no open jobs to match")
    offered = [str(j.id) for j in jobs]
    return await client.run(
        prompt=PROMPT,
        tier=ModelTier.EXTRACTION,
        output_schema=MatcherOutput,
        instructions=(
            "Open jobs (from the recruiter; use only these ids):\n"
            + json.dumps([j.for_model() for j in jobs], ensure_ascii=False, indent=1)
        ),
        untrusted={"cv": cv_text[:CV_CHARS]},
        candidate_id=candidate_id,
        check=lambda out: check_fits(out, offered),
        effort=EFFORT,
        trace_fields={"agent": "job_matcher", "jobs": len(jobs)},
        trace_output=True,
    )
