"""The answer scorer (phase 3 design section 4): knockout rules stored in phase 1, run as code.

No model is involved. Outcomes:
- pass / fail: a rule was checked (fail on a hard rule = reject band)
- flag: a soft rule fired (salary above band, location "no"); shown, never decides
- not_scored: no rule on the question (notice period, current role, free text)
- not_answered: no stored answer (bulk uploads)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

Outcome = Literal["pass", "fail", "flag", "not_scored", "not_answered"]


@dataclass(frozen=True)
class QuestionInput:
    key: str
    prompt: str
    answer_type: str
    knockout_rule: dict[str, Any] | None
    value: Any  # None when not answered


@dataclass(frozen=True)
class AnswerResult:
    key: str
    value: Any
    rule: str | None
    outcome: Outcome
    hard: bool
    note: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _money(n: float) -> str:
    return f"${n:,.0f}"


def _words(value: Any) -> str:
    """Plain words for a recruiter: yes and no, not Python's True and False."""
    if isinstance(value, bool):
        return "yes" if value else "no"
    return repr(value) if isinstance(value, str) else str(value)


def _lower(value: Any) -> float | None:
    if isinstance(value, dict) and "min" in value:
        return float(value["min"])
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def score_answer(q: QuestionInput, *, salary_max: int) -> AnswerResult:
    rule = q.knockout_rule or None
    kind = rule.get("kind") if rule else None
    hard = bool(rule.get("hard_fail")) if rule else False
    if q.value is None:
        return AnswerResult(q.key, None, kind, "not_answered", hard, "not answered")
    if rule is None:
        return AnswerResult(q.key, q.value, None, "not_scored", False, "recorded, not scored")

    bad: Outcome = "fail" if hard else "flag"
    if kind == "must_equal":
        ok = q.value == rule.get("value")
        note = (
            "as required"
            if ok
            else f"answered {_words(q.value)}, required {_words(rule.get('value'))}"
        )
        outcome: Outcome = "pass" if ok else bad
        return AnswerResult(q.key, q.value, kind, outcome, hard, note)
    if kind == "max_number_vs_band":
        low = _lower(q.value)
        if low is None:
            return AnswerResult(q.key, q.value, kind, "not_scored", hard, "not a number")
        if low > salary_max:
            shown = q.value["text"] if isinstance(q.value, dict) else _money(low)
            note = f"expected {shown}, above the band maximum {_money(salary_max)}"
            return AnswerResult(q.key, q.value, kind, bad, hard, note)
        return AnswerResult(q.key, q.value, kind, "pass", hard, "within the band")
    if kind == "not_in":
        blocked = rule.get("value") or []
        if q.value in blocked:
            return AnswerResult(q.key, q.value, kind, bad, hard, f"answered {q.value!r}")
        return AnswerResult(q.key, q.value, kind, "pass", hard, "as required")
    return AnswerResult(q.key, q.value, kind, "not_scored", hard, f"unknown rule {kind}")


def score_answers(questions: list[QuestionInput], *, salary_max: int) -> list[AnswerResult]:
    return [score_answer(q, salary_max=salary_max) for q in questions]
