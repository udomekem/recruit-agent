"""Screening questions: the five standard confirm questions and custom question rules.

Knockout rules are stored as data in phase 1 and evaluated in phase 3.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.domain.guard import find_protected_terms


class AnswerType(StrEnum):
    YES_NO = "yes_no"
    NUMBER = "number"
    CHOICE = "choice"
    TEXT = "text"


class KnockoutRule(BaseModel):
    kind: Literal["must_equal", "max_number_vs_band", "not_in"]
    value: Any = None
    hard_fail: bool = False


class QuestionSpec(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,59}$")
    prompt: str = Field(min_length=3, max_length=500)
    answer_type: AnswerType
    choices: list[str] | None = None
    required: bool = True
    knockout_rule: KnockoutRule | None = None

    @model_validator(mode="after")
    def _check(self) -> QuestionSpec:
        if self.answer_type is AnswerType.CHOICE and not self.choices:
            raise ValueError("a choice question needs choices")
        if self.answer_type is not AnswerType.CHOICE and self.choices:
            raise ValueError("only choice questions have choices")
        found = find_protected_terms(" ".join([self.prompt, *(self.choices or [])]))
        if found:
            raise ValueError(f"question mentions protected attributes: {', '.join(found)}")
        return self


NOTICE_CHOICES = ["immediate", "1 to 2 weeks", "3 to 4 weeks", "more than 4 weeks"]
LOCATION_CHOICES = ["yes", "yes with relocation", "no"]
STANDARD_KEYS = (
    "right_to_work",
    "expected_salary",
    "notice_period",
    "location_fit",
    "current_role",
)


def standard_questions(location: str, work_arrangement: str) -> list[QuestionSpec]:
    """The five confirm questions every job gets (decided 2026-11-07)."""
    return [
        QuestionSpec(
            key="right_to_work",
            prompt="Do you have the right to work in Australia?",
            answer_type=AnswerType.YES_NO,
            knockout_rule=KnockoutRule(kind="must_equal", value=True, hard_fail=True),
        ),
        QuestionSpec(
            key="expected_salary",
            prompt="What is your expected annual salary (AUD)?",
            answer_type=AnswerType.NUMBER,
            knockout_rule=KnockoutRule(kind="max_number_vs_band", hard_fail=False),
        ),
        QuestionSpec(
            key="notice_period",
            prompt="What is your notice period?",
            answer_type=AnswerType.CHOICE,
            choices=NOTICE_CHOICES,
        ),
        QuestionSpec(
            key="location_fit",
            prompt=f"Can you work in {location} ({work_arrangement})?",
            answer_type=AnswerType.CHOICE,
            choices=LOCATION_CHOICES,
            knockout_rule=KnockoutRule(kind="not_in", value=["no"], hard_fail=False),
        ),
        QuestionSpec(
            key="current_role",
            prompt="What is your current or most recent role?",
            answer_type=AnswerType.TEXT,
        ),
    ]


_NUM = r"\$?\s*(\d[\d,]*(?:\.\d+)?)\s*(k)?"
_RANGE_SEP = r"\s*(?:-|–|to)\s*"


def _check_number(value: float) -> int | float:
    if value < 0 or value > 10_000_000:
        raise ValueError("number out of range")
    return int(value) if value.is_integer() else value


def _to_number(digits: str, k: str | None) -> int | float:
    value = float(digits.replace(",", ""))
    return _check_number(value * 1000 if k else value)


def _number_or_range(raw: str) -> int | float | dict[str, Any]:
    """ "95000", "$95,000", "95k" give a number; "$95k to $110k" gives a range
    {min, max, text} (phase 3 design Q3). Anything else ("negotiable") is refused."""
    s = raw.strip().lower().replace("aud", "").strip()
    one = re.fullmatch(_NUM, s)
    if one:
        return _to_number(one.group(1), one.group(2))
    rng = re.fullmatch(_NUM + _RANGE_SEP + _NUM, s)
    if rng:
        lo = _to_number(rng.group(1), rng.group(2) or rng.group(4))  # "95 to 110k"
        hi = _to_number(rng.group(3), rng.group(4))
        if lo > hi:
            raise ValueError("put the lower number first")
        return {"min": lo, "max": hi, "text": raw.strip()[:60]}
    raise ValueError("answer with a number")


def coerce_answer(spec_type: str, choices: list[str] | None, raw: Any) -> Any:
    """Turn a submitted value into the question's type, or raise ValueError."""
    t = AnswerType(spec_type)
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    if t is AnswerType.YES_NO:
        if isinstance(raw, bool):
            return raw
        s = str(raw).strip().lower()
        if s in {"yes", "y", "true", "1"}:
            return True
        if s in {"no", "n", "false", "0"}:
            return False
        raise ValueError("answer yes or no")
    if t is AnswerType.NUMBER:
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            return _check_number(float(raw))
        return _number_or_range(str(raw))
    if t is AnswerType.CHOICE:
        s = str(raw).strip()
        if choices is None or s not in choices:
            raise ValueError("pick one of the listed options")
        return s
    s = str(raw).strip()
    if len(s) > 2000:
        raise ValueError("answer is too long (2000 characters max)")
    return s
