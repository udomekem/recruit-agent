"""Screening answers for scorer eval cases: the five standard questions with raw answers
coerced exactly as the apply form does. Shared by the dataset builder and the eval agent."""

from __future__ import annotations

from typing import Any

from app.domain.questions import coerce_answer, standard_questions
from app.scoring.answers import QuestionInput


def questions(answers: dict[str, Any] | None) -> list[QuestionInput]:
    """None means a bulk upload: every question unanswered."""
    out = []
    for spec in standard_questions("Sydney NSW", "onsite"):
        raw = (answers or {}).get(spec.key)
        value = None if raw is None else coerce_answer(spec.answer_type.value, spec.choices, raw)
        rule = spec.knockout_rule.model_dump() if spec.knockout_rule else None
        out.append(QuestionInput(spec.key, spec.prompt, spec.answer_type.value, rule, value))
    return out
