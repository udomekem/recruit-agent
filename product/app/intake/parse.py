"""The real parse step (phase 2 design section 4): CV object to redacted copy and profile.

Returns a decision; the pipeline applies it (state move and CvParse row in one
transaction). Reasons never quote CV content: audit reasons hold no personal data.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.agents.cv_parser import parse_cv
from app.db.models import Candidate
from app.db.session import SessionMaker
from app.domain.states import CandidateState
from app.intake.extract import extract
from app.intake.redact import final_redact, pre_redact
from app.integrations.storage import Storage, StorageError
from app.llm.client import LLMClient, LLMError

S = CandidateState


@dataclass
class ParseDecision:
    to_state: CandidateState
    reason: str
    row: dict[str, Any] | None = None  # CvParse fields to store with the move
    trace: dict[str, Any] = field(default_factory=dict)
    use_stub: bool = False


async def run_parse(
    sessions: SessionMaker,
    storage: Storage,
    llm: LLMClient | None,
    candidate_id: uuid.UUID,
    *,
    production: bool,
) -> ParseDecision:
    async with sessions() as s:
        cand = await s.get(Candidate, candidate_id)
        if cand is None:
            return ParseDecision(S.NEEDS_REVIEW, "candidate not found")
        key, media = cand.cv_object_key, cand.cv_media_type
        name, email, phone = cand.full_name, cand.email, cand.phone

    if not key or not media:
        if production:
            return ParseDecision(S.NEEDS_REVIEW, "no CV stored for this candidate")
        return ParseDecision(S.PARSED, "", use_stub=True)  # phase 0 test candidates

    data: bytes | None = None
    for _attempt in range(3):
        try:
            data = await storage.get(key)
            break
        except StorageError:
            continue
    if data is None:
        return ParseDecision(S.NEEDS_REVIEW, "could not read the stored CV")

    ex = await extract(data, media)
    if ex.status == "no_text_layer":
        return ParseDecision(
            S.NEEDS_REVIEW,
            "no text layer (scanned CV): needs a person or OCR",
            row={"status": "no_text_layer", "text_layer": False, "redaction_counts": {}},
            trace={"outcome": "no_text_layer", "model_calls": 0},
        )
    if ex.status == "failed":
        return ParseDecision(
            S.NEEDS_REVIEW,
            ex.detail,
            row={"status": "failed", "text_layer": False, "redaction_counts": {}},
            trace={"outcome": "extract_failed"},
        )

    pre = pre_redact(ex.text, name=name, email=email, phone=phone)
    if llm is None:
        return ParseDecision(S.NEEDS_REVIEW, "no language model configured (provider key not set)")
    try:
        result = await parse_cv(llm, pre_redacted_text=pre.text, candidate_id=str(candidate_id))
    except LLMError as exc:
        return ParseDecision(
            S.NEEDS_REVIEW,
            f"cv parser failed: {type(exc).__name__}",
            row={"status": "failed", "text_layer": True, "redaction_counts": dict(pre.counts)},
            trace={"outcome": "parser_failed", "error": type(exc).__name__},
        )
    final = final_redact(pre, [(sp.text, sp.kind) for sp in result.output.personal_spans])
    profile = result.output.model_dump(mode="json", exclude={"personal_spans"})
    counts = dict(final.counts)
    redactions = sum(counts.values())
    if ex.hidden_chars:
        counts["hidden_text"] = ex.hidden_chars  # removed before redaction (phase 3 design 5)
    return ParseDecision(
        S.PARSED,
        f"cv parsed: {len(result.output.work_history)} roles, {len(result.output.skills)} skills, "
        f"{redactions} redactions",
        row={
            "status": "parsed",
            "text_layer": True,
            "redacted_text": final.text,
            "profile": profile,
            "redaction_counts": counts,
            "prompt_id": result.prompt_id,
            "prompt_version": result.prompt_version,
            "model": result.model,
            "cost_usd": result.cost_usd,
            "attempts": result.attempts,
        },
        trace={
            "outcome": "parsed",
            "prompt_version": f"{result.prompt_id}-{result.prompt_version}",
            "model": result.model,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "cost_usd": result.cost_usd,
            "attempts": result.attempts,
            "roles": len(result.output.work_history),
            "redactions": redactions,
            "hidden_chars": ex.hidden_chars,
        },
    )
