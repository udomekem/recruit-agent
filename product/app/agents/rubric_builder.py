"""Rubric builder: job advertisement in, draft rubric out (phase 1 design section 5).

The model proposes; code checks. A draft is rejected (and retried with the reasons) when
any evidence or flag quote is not in the ad, ids repeat, counts or weights are out of
range, or a criterion contains protected attribute wording (app/domain/guard.py).
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from app.domain.guard import find_protected_terms
from app.llm.client import LLMClient, LLMResult, ModelTier
from app.llm.prompts import PromptRef

PROMPT = PromptRef("rubric-builder", "v2")
EFFORT = "medium"  # phase 1 design Q3: raise only if evals miss the bars
MAX_CRITERIA = 25

Kind = Literal["must_have", "nice_to_have"]
Category = Literal["skill", "experience", "qualification", "licence", "other"]
Concern = Literal[
    "age",
    "sex_or_gender",
    "sexuality",
    "race_or_nationality",
    "disability",
    "family_or_carer",
    "religion",
    "other",
]
WEIGHTS = {"must_have": range(3, 6), "nice_to_have": range(1, 3)}


class Criterion(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,59}$")
    kind: Kind
    category: Category
    text: str = Field(min_length=3, max_length=300)
    weight: int = Field(ge=1, le=5)
    years: int | None = Field(default=None, ge=0, le=40)
    evidence: str = Field(min_length=2, max_length=500)


class WordingFlag(BaseModel):
    quote: str = Field(min_length=2, max_length=300)
    concern: Concern
    suggestion: str = Field(min_length=2, max_length=300)


class RubricDraft(BaseModel):
    criteria: list[Criterion]
    flags: list[WordingFlag]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def check_rubric(draft: RubricDraft, ad: str) -> None:
    """Raise ValueError listing every problem, so the retry can fix them all at once."""
    problems: list[str] = []
    ad_n = _norm(ad)
    if not 1 <= len(draft.criteria) <= MAX_CRITERIA:
        problems.append(f"return between 1 and {MAX_CRITERIA} criteria (got {len(draft.criteria)})")
    if not any(c.kind == "must_have" for c in draft.criteria):
        problems.append("at least one criterion must be a must_have")
    ids = [c.id for c in draft.criteria]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        problems.append(f"criterion ids must be unique (repeated: {', '.join(dupes)})")
    for c in draft.criteria:
        if c.weight not in WEIGHTS[c.kind]:
            lo, hi = WEIGHTS[c.kind][0], WEIGHTS[c.kind][-1]
            problems.append(f"{c.id}: {c.kind} weight must be {lo} to {hi} (got {c.weight})")
        if _norm(c.evidence) not in ad_n:
            problems.append(f"{c.id}: evidence must be an exact quote from the ad")
        hits = find_protected_terms(c.text)
        if hits:
            problems.append(
                f"{c.id}: criterion uses protected attribute wording ({', '.join(hits)}); "
                "remove it and flag the ad wording instead"
            )
    for f in draft.flags:
        if _norm(f.quote) not in ad_n:
            problems.append(f"flag quote '{f.quote[:60]}' must be an exact quote from the ad")
    if problems:
        raise ValueError("; ".join(problems))


async def build_rubric(
    client: LLMClient,
    *,
    title: str,
    location: str,
    work_arrangement: str,
    salary_min: int,
    salary_max: int,
    description: str,
    job_id: str | None = None,
) -> LLMResult[RubricDraft]:
    instructions = (
        f"Build the rubric for this job.\nTitle: {title}\nLocation: {location} "
        f"({work_arrangement})\nSalary band: AUD {salary_min:,} to {salary_max:,} per year\n"
        "The advertisement text is in the data block below."
    )
    return await client.run(
        prompt=PROMPT,
        tier=ModelTier.JUDGEMENT,
        output_schema=RubricDraft,
        instructions=instructions,
        untrusted={"job_advertisement": description},
        check=lambda d: check_rubric(d, description),
        effort=EFFORT,
        trace_fields={"job_id": job_id or "none", "agent": "rubric_builder"},
    )
