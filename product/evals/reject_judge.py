"""The rejection email judge (phase 5 design section 9, Q2). Evals only, never in the
request path.

A different model family from the writer (DeepSeek writes; a GPT model on kie.ai's GPT
endpoint grades), so the judge does not go easy on its own kind of writing. It is checked
against hand labels (`reject-judge-v1`) before its scores gate anything.
"""

from __future__ import annotations

import json
import os
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.llm.client import LLMClient, LLMResult, ModelTier
from app.llm.prompts import PromptRef

# v5: keeping the CV on file and future contact are allowed (Mani, 2026-11-12).
# v4: a true explanation of a listed requirement is not a false claim (Mani, 2026-11-12).
# v2 (phase 5 evals): the fixed contact and deletion lines are never offers; each
# dimension scored on its own; harsh words anchored. v1 kept.
PROMPT = PromptRef("rejection-judge", "v5")
JUDGE_MODEL = os.environ.get("REJECT_JUDGE_MODEL", "gpt-5-6-luna")  # eval only
JUDGE_URL = "https://api.kie.ai/codex/v1/responses"
DIMENSIONS = ("specific", "job_related", "kind", "no_protected", "no_false_claims")

Score = Literal[1, 2, 3, 4, 5]


class JudgeOutput(BaseModel):
    specific: Score
    job_related: Score
    kind: Score
    no_protected: Score
    no_false_claims: Score
    note: str = Field(max_length=300)

    def scores(self) -> dict[str, int]:
        return {d: int(getattr(self, d)) for d in DIMENSIONS}


def make_judge_client(max_calls: int, model: str = JUDGE_MODEL) -> tuple[LLMClient, Any]:
    from app.config import get_settings
    from app.llm.providers import KieProvider
    from app.observability.tracing import make_tracer
    from evals.harness import HarnessError

    base = get_settings()
    if base.kie_api_key is None:
        raise HarnessError("the rejection judge needs KIE_API_KEY (real model)")
    settings = base.model_copy(
        update={
            "llm_max_calls_per_process": max_calls,
            "model_judgement": model,
            "effort_judgement": "low",
        }
    )
    tracer = make_tracer(settings)
    provider = KieProvider(
        base.kie_api_key.get_secret_value(), settings.llm_timeout_seconds, JUDGE_URL
    )
    return LLMClient(provider, tracer, settings), tracer


async def judge_email(
    client: LLMClient, *, job_title: str, requirements: list[str], email: str
) -> LLMResult[JudgeOutput]:
    return await client.run(
        prompt=PROMPT,
        tier=ModelTier.JUDGEMENT,
        output_schema=JudgeOutput,
        instructions=(
            f"Job: {job_title}\nRequirements the applicant did not meet (the only allowed "
            f"reasons):\n{json.dumps(requirements, ensure_ascii=False, indent=1)}"
        ),
        untrusted={"email": email},
        candidate_id="eval",
        trace_fields={"agent": "rejection_judge"},
    )
