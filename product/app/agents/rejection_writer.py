"""Rejection writer (phase 5 design section 4): job and missed requirements in, the parts
of a short rejection email out. Code assembles the email and runs the hard rule checks.

The model never sees the name, contact details, CV text, quotes, scores, band or rank, or
the recruiter's reason. The scorer's notes are fenced as untrusted data (they came from a
model that read the CV). A draft that fails a check is retried with every failure listed
(the client's invalid output retry); if it still fails, the caller uses the template.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from pydantic import BaseModel, Field

from app.llm.client import LLMClient, LLMResult, ModelTier
from app.llm.prompts import PromptRef
from app.rejection.checks import failures, run_checks
from app.rejection.compose import ReasonSource, assemble_body

# v2 (phase 5 evals): code picks the reasons (top three) and the writer explains each
# one; no added job facts. v1 let the model pick, which differed within fairness pairs.
PROMPT = PromptRef("rejection-writer", "v2")
EFFORT = "medium"  # design Q1: raise to high only if the judge bar misses
MAX_REASONS = 3


class WriterReason(BaseModel):
    source_id: str
    sentence: str = Field(max_length=200)


class WriterOutput(BaseModel):
    opening: str = Field(max_length=300)
    reasons: list[WriterReason]
    closing: str = Field(max_length=300)

    def body(self) -> str:
        return assemble_body(self.opening, [r.sentence for r in self.reasons], self.closing)


def check_draft(out: WriterOutput, sources: Sequence[ReasonSource], cv_text: str) -> None:
    """Raise ValueError naming every problem, so one retry can fix them all."""
    problems: list[str] = []
    given = [s.id for s in sources]
    got = [r.source_id for r in out.reasons]
    missing = [i for i in given if i not in got]
    if missing:
        problems.append(f"explain every requirement given; missing: {', '.join(missing)}")
    if len(got) > MAX_REASONS:
        problems.append(f"at most {MAX_REASONS} reasons, not {len(got)}")
    results = run_checks(
        out.body(),
        reason_ids=[r.source_id for r in out.reasons],
        allowed_ids=[s.id for s in sources],
        cv_text=cv_text,
    )
    problems += [f"{r.rule}: {r.detail}" for r in failures(results)]
    if problems:
        raise ValueError("; ".join(problems))


async def write_rejection(
    client: LLMClient,
    *,
    job_title: str,
    company: str,
    sources: Sequence[ReasonSource],
    cv_text: str,
    candidate_id: str,
) -> LLMResult[WriterOutput]:
    if not sources:
        raise ValueError("no missed requirements to explain")
    trusted = json.dumps([s.for_model() for s in sources], ensure_ascii=False, indent=1)
    notes = json.dumps(
        {s.id: s.scorer_note for s in sources if s.kind == "criterion" and s.scorer_note},
        ensure_ascii=False,
        indent=1,
    )
    return await client.run(
        prompt=PROMPT,
        tier=ModelTier.EXTRACTION,
        output_schema=WriterOutput,
        instructions=(
            f"Job: {job_title}\nCompany: {company}\n"
            "Requirements this applicant did not meet, from the recruiter's approved "
            f"requirements (use only these ids as source_id):\n{trusted}"
        ),
        untrusted={"screening_notes": notes},
        candidate_id=candidate_id,
        check=lambda out: check_draft(out, sources, cv_text),
        effort=EFFORT,
        trace_fields={"agent": "rejection_writer", "sources": len(sources)},
        trace_output=False,
    )
