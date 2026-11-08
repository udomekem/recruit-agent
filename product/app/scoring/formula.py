"""Score, band, reasons and flags (phase 3 design section 3). Code only: the model never
outputs a total, and never sees the weights or the thresholds.

Total = sum(weight x points) / sum(weight), one decimal; met 100, partly 50, not 0.
Band, in order: right to work no -> reject; total under 50 -> reject; total at least 75 with
no must have not met and answers present -> advance; otherwise maybe.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from app.scoring.answers import AnswerResult

Verdict = Literal["met", "partly_met", "not_met"]
Band = Literal["advance", "maybe", "reject"]

POINTS: dict[str, int] = {"met": 100, "partly_met": 50, "not_met": 0}
ADVANCE_AT = 75.0
REJECT_BELOW = 50.0


@dataclass(frozen=True)
class Flag:
    kind: str
    text: str

    def as_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "text": self.text}


@dataclass
class ScoreCard:
    total: float
    band: Band
    reasons: list[str] = field(default_factory=list)
    flags: list[Flag] = field(default_factory=list)


def total_score(criteria: list[dict[str, Any]], verdicts: Mapping[str, str]) -> float:
    weights = sum(int(c["weight"]) for c in criteria)
    if weights <= 0:
        raise ValueError("rubric has no weight")
    points = sum(int(c["weight"]) * POINTS[verdicts[c["id"]]] for c in criteria)
    return round(points / weights, 1)


def _answer_flags(answers: list[AnswerResult]) -> list[Flag]:
    flags: list[Flag] = []
    for a in answers:
        if a.outcome != "flag":
            continue
        if a.key == "expected_salary":
            flags.append(Flag("salary_above_band", f"Expected salary: {a.note}"))
        elif a.key == "location_fit":
            flags.append(Flag("location_no", "Answered no to the job's location or arrangement"))
        else:
            flags.append(Flag("answer_flag", f"{a.key}: {a.note}"))
    return flags


def score_card(
    criteria: list[dict[str, Any]],
    verdicts: Mapping[str, str],
    answers: list[AnswerResult],
    *,
    injection_suspected: bool = False,
    hidden_chars: int = 0,
) -> ScoreCard:
    total = total_score(criteria, verdicts)
    met = sum(verdicts[c["id"]] == "met" for c in criteria)
    partly = sum(verdicts[c["id"]] == "partly_met" for c in criteria)
    missed_must = [
        c for c in criteria if c["kind"] == "must_have" and verdicts[c["id"]] == "not_met"
    ]
    hard_fails = [a for a in answers if a.outcome == "fail" and a.hard]
    missing = [a for a in answers if a.outcome == "not_answered" and a.rule is not None]

    summary = f"Meets {met} of {len(criteria)} criteria"
    if partly:
        summary += f", partly meets {partly}"
    reasons = [f"{summary} (score {total:.1f})"]
    reasons += [f"Must have not met: {c['text']}" for c in missed_must]

    flags = _answer_flags(answers)
    if missing:
        flags.append(Flag("answers_missing", "Screening answers missing (bulk upload)"))
    if injection_suspected:
        flags.append(Flag("injection_suspected", "The CV may contain instructions aimed at the AI"))
    if hidden_chars:
        flags.append(Flag("hidden_text", f"{hidden_chars} characters of hidden text removed"))

    band: Band
    if any(a.key == "right_to_work" for a in hard_fails):
        band = "reject"
        reasons.insert(0, "No right to work in Australia (application answer)")
    elif hard_fails:
        band = "reject"
        reasons[:0] = [f"Knockout question failed: {a.key}" for a in hard_fails]
    elif total < REJECT_BELOW:
        band = "reject"
    elif total >= ADVANCE_AT and not missed_must and not missing:
        band = "advance"
    else:
        band = "maybe"
        if total >= ADVANCE_AT and missing and not missed_must:
            reasons.append("Screening answers missing, so held at maybe")
    return ScoreCard(total, band, reasons, flags)
