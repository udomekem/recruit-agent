"""Reason sources, email assembly and the plain template (phase 5 design section 4).

- `reason_sources` picks what the writer may explain: failed or flagged screening answers
  first (code written notes, trusted), then criteria not met before partly met, must
  haves before nice to haves, heavier weights first. At most five go to the model; it
  picks one to three. The criterion's name comes from the approved rubric (trusted); the
  scorer's reason came from a model that read the CV, so it is passed as untrusted data.
- The body is what the recruiter sees and edits. The greeting, the contact and deletion
  lines and the sign off are fixed and added around it; the first name is filled in only
  at delivery, so the dashboard shows "[first name]" (blind review).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

MAX_SOURCES = (
    3  # code picks the reasons (phase 5 evals: model picks differed within fairness pairs)
)
NAME_PLACEHOLDER = "[first name]"

_VERDICT_ORDER = {"not_met": 0, "partly_met": 1}
_KIND_ORDER = {"must_have": 0, "nice_to_have": 1}


@dataclass(frozen=True)
class ReasonSource:
    id: str
    kind: Literal["criterion", "answer"]
    requirement: str  # trusted: the rubric criterion text, or the question's requirement
    status: str  # trusted: not_met, partly_met, or the answer note written by code
    scorer_note: str = ""  # untrusted: the scorer's reason (criteria only)

    def for_model(self) -> dict[str, str]:
        return {
            "id": self.id,
            "kind": self.kind,
            "requirement": self.requirement,
            "status": self.status,
        }


def _answer_requirement(key: str, prompt: str, *, location: str, arrangement: str) -> str:
    if key == "right_to_work":
        return "The right to work in Australia"
    if key == "expected_salary":
        return "A salary expectation within the range for this role"
    if key == "location_fit":
        return f"Able to work in {location} ({arrangement})"
    return prompt


def reason_sources(
    criteria: Sequence[dict[str, Any]],
    judgements: Sequence[dict[str, Any]],
    answer_results: Sequence[dict[str, Any]],
    questions: dict[str, str],
    *,
    location: str,
    arrangement: str,
) -> list[ReasonSource]:
    """`questions` maps question key to its prompt."""
    out: list[ReasonSource] = []
    answers = [a for a in answer_results if a.get("outcome") in ("fail", "flag")]
    answers.sort(key=lambda a: (a.get("outcome") != "fail", a.get("key", "")))
    for a in answers:
        key = str(a["key"])
        out.append(
            ReasonSource(
                id=f"answer:{key}",
                kind="answer",
                requirement=_answer_requirement(
                    key, questions.get(key, key), location=location, arrangement=arrangement
                ),
                # Not the code's answer note: it holds figures such as the band maximum
                # ("$140,000 is above the band maximum $120,000"), which the writer quoted
                # and which an employer may not publish (found in the 2026-11-12 run).
                status="not_met",
            )
        )
    by_id = {c["id"]: c for c in criteria}
    missed = [
        j for j in judgements if j.get("verdict") in _VERDICT_ORDER and j["criterion_id"] in by_id
    ]
    missed.sort(
        key=lambda j: (
            _VERDICT_ORDER[j["verdict"]],
            _KIND_ORDER.get(by_id[j["criterion_id"]].get("kind", ""), 2),
            -float(by_id[j["criterion_id"]].get("weight") or 0),
            j["criterion_id"],
        )
    )
    for j in missed:
        c = by_id[j["criterion_id"]]
        out.append(
            ReasonSource(
                id=f"criterion:{c['id']}",
                kind="criterion",
                requirement=str(c["text"]),
                status=str(j["verdict"]),
                scorer_note=str(j.get("reason") or ""),
            )
        )
    return out[:MAX_SOURCES]


def assemble_body(opening: str, reason_sentences: Sequence[str], closing: str) -> str:
    parts = [opening.strip()]
    reasons = " ".join(s.strip() for s in reason_sentences if s.strip())
    if reasons:
        parts.append(reasons)
    parts.append(closing.strip())
    return "\n\n".join(p for p in parts if p)


def template_parts(job_title: str, company: str) -> tuple[str, str]:
    """The plain template: kind, names the job, gives no reasons (nothing is invented)."""
    opening = (
        f"Thank you for applying for the {job_title} role at {company}, and for the time "
        "you put into your application. We have now reviewed the applications for this "
        "role, and we will not be taking yours further this time."
    )
    closing = (
        "We know this is not the news you were hoping for. We read every application "
        "carefully, and we appreciate your interest in working with us. We wish you all "
        "the best with your search."
    )
    return opening, closing


def subject(job_title: str, company: str) -> str:
    return f"Your application for {job_title} at {company}"


def full_text(body: str, *, first_name: str | None, company: str, reply_to: str) -> str:
    """The email as sent. `first_name=None` gives the dashboard preview."""
    name = first_name.strip() if first_name and first_name.strip() else None
    greeting = (
        f"Hi {name}," if name else (f"Hi {NAME_PLACEHOLDER}," if first_name is None else "Hi,")
    )
    return (
        f"{greeting}\n\n{body.strip()}\n\n"
        f"If you have any questions about this decision, reply to this email or contact "
        f"{reply_to}.\n"
        "You can ask us to delete your application and data at any time by replying to "
        "this email.\n\n"
        f"{company} Recruitment"
    )


def first_name_of(full_name: str | None) -> str:
    """The first word of the name, or "" (the greeting then reads "Hi,")."""
    return (full_name or "").strip().split(" ")[0] if full_name and full_name.strip() else ""
