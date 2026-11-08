"""CV scorer: redacted CV + approved rubric in, one judgement per criterion out
(phase 3 design section 2).

The model judges; code checks and code scores. A result is rejected (and retried with
every reason at once) when a criterion is missing, repeated or unknown, a met or partly
met judgement has no quote, a quote is not in the redacted copy or is only placeholders,
or a reason uses protected attribute wording. The model is given criterion ids, kinds,
text and years, never the weights or the band thresholds.
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.domain.guard import find_reason_terms
from app.intake.redact import normalise
from app.llm.client import LLMClient, LLMResult, ModelTier
from app.llm.prompts import PromptRef

# v2 (phase 3 evals): explicit rules for years, listed skills and partly_met, and today's
# date in the instructions (v1 could not count months up to "Present"). v1 kept.
PROMPT = PromptRef("cv-scorer", "v2")
MONTH_NAMES = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]


def today_sydney() -> tuple[int, int]:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo("Australia/Sydney"))
    return now.year, now.month


# Phase 3 brief Q5: medium unless consistency or agreement miss the bars. Prompt v2 at
# medium met every bar except consistency (2 of 45 CVs moved 10 points in one of three
# runs, 2026-11-08), so raised to high.
EFFORT = "high"
MAX_CV_CHARS = 40_000

Verdict = Literal["met", "partly_met", "not_met"]
_PLACEHOLDER = re.compile(r"\[[A-Z ]+\]")

# Common injection phrasing, caught by code as well as the model (phase 3 design 5).
_INJECTION = re.compile(
    r"\b(ignore|disregard|forget)\s+(all\s+|any\s+)?(the\s+|your\s+|my\s+)?"
    r"(previous|prior|above|earlier|system|scoring|screening)?\s*"
    r"(instructions?|prompts?|rubric|criteria|scoring\s+rules)\b"
    r"|\b(note|message|instructions?)\s+(to|for)\s+(the\s+)?(ai|assistant|model|llm|"
    r"recruiter\s+bot|screening\s+system|reviewer)\b"
    r"|\b(rate|score|rank|mark)\s+(this|the|me)\b.{0,40}\b(100|top|highest|perfect|"
    r"best|all\s+criteria)\b"
    r"|\bsystem\s+prompt\b"
    r"|\b(screening|scoring)\s+rubric\b|\brubric\s*\((updated|override|new)\)"
    r"|\byou\s+are\s+(now\s+)?(an?\s+)?(ai|assistant|language\s+model)\b",
    re.IGNORECASE | re.DOTALL,
)


class Judgement(BaseModel):
    criterion_id: str
    verdict: Verdict
    reason: str = Field(max_length=300)
    quote: str = Field(max_length=300)


class ScoreOutput(BaseModel):
    judgements: list[Judgement]
    injection_suspected: bool
    injection_note: str = Field(max_length=200)


def injection_phrases(text: str) -> bool:
    return _INJECTION.search(text) is not None


def criteria_for_model(criteria: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """What the model may see: no weights."""
    return [
        {"id": c["id"], "kind": c["kind"], "text": c["text"], "years": c.get("years")}
        for c in criteria
    ]


def check_score(out: ScoreOutput, criteria: list[dict[str, Any]], text: str) -> None:
    """Raise ValueError listing every problem, so one retry can fix them all."""
    problems: list[str] = []
    t = normalise(text)
    ids = [c["id"] for c in criteria]
    got = [j.criterion_id for j in out.judgements]
    for missing in [i for i in ids if i not in got]:
        problems.append(f"missing a judgement for criterion {missing}")
    for unknown in sorted({g for g in got if g not in ids}):
        problems.append(f"{unknown} is not a criterion in the rubric; use only the given ids")
    for rep in sorted({g for g in got if got.count(g) > 1}):
        problems.append(f"criterion {rep} is judged more than once")
    for j in out.judgements:
        if j.verdict != "not_met":
            q = j.quote.strip()
            if not q:
                problems.append(f"{j.criterion_id}: {j.verdict} needs a quote from the CV")
            elif not _PLACEHOLDER.sub("", q).strip(" .,;:-|"):
                problems.append(f"{j.criterion_id}: the quote is only placeholders")
            elif normalise(q) not in t:
                problems.append(
                    f"{j.criterion_id}: the quote is not in the CV; copy it word for word"
                )
        found = find_reason_terms(j.reason)
        if found:
            problems.append(
                f"{j.criterion_id}: the reason mentions {', '.join(found)}; judge the work only"
            )
    if problems:
        raise ValueError("; ".join(problems[:25]))


async def score_cv(
    client: LLMClient,
    *,
    redacted_text: str,
    criteria: list[dict[str, Any]],
    candidate_id: str,
    today: tuple[int, int] | None = None,
) -> LLMResult[ScoreOutput]:
    """`today` (year, month) defaults to now in Sydney; evals pass their dataset's date."""
    if len(redacted_text) > MAX_CV_CHARS:
        raise ValueError("CV too long to score")
    year, month = today or today_sydney()
    rubric = json.dumps(criteria_for_model(criteria), ensure_ascii=False, indent=1)
    return await client.run(
        prompt=PROMPT,
        tier=ModelTier.JUDGEMENT,
        output_schema=ScoreOutput,
        instructions=(
            f"Today is {MONTH_NAMES[month - 1]} {year}. Judge the CV in the data block "
            f"against each of these criteria from the approved rubric:\n{rubric}"
        ),
        untrusted={"cv": redacted_text},
        candidate_id=candidate_id,
        check=lambda out: check_score(out, criteria, redacted_text),
        effort=EFFORT,
        trace_fields={"agent": "cv_scorer", "criteria": len(criteria)},
        trace_output=False,
    )
