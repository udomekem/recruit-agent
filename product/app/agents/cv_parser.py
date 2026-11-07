"""CV parser: pre redacted CV text in, structured profile out (phase 2 design sections 1, 4).

The model proposes; code checks. A profile is rejected (and retried with the reasons) when
an employer, title, institution, qualification, skill, certification, licence or personal
span is not in the text, or a date is malformed or out of order. The parser's output never
goes to traces (it is personal data); only counts, tokens, cost and latency do.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.intake.redact import normalise
from app.llm.client import LLMClient, LLMResult, ModelTier
from app.llm.prompts import PromptRef

PROMPT = PromptRef("cv-parser", "v2")
EFFORT = "low"

SpanKind = Literal[
    "name",
    "address",
    "dob",
    "gender",
    "marital_or_family",
    "nationality_or_ethnicity",
    "religion",
    "health",
    "other_personal",
]
_DATE = re.compile(r"^(?:\d{4}(?:-(?:0[1-9]|1[0-2]))?|present)$")


class Role(BaseModel):
    title: str = Field(min_length=2, max_length=150)
    employer: str = Field(min_length=2, max_length=150)
    start: str | None = None
    end: str | None = None
    highlights: list[str] = Field(default_factory=list, max_length=3)


class Study(BaseModel):
    qualification: str = Field(min_length=2, max_length=200)
    institution: str = Field(min_length=2, max_length=200)
    end: str | None = Field(
        default=None,
        description="Completion year as four digits, e.g. '2016'. A year on the same line as "
        "the qualification is the completion year. Null only if no year is written.",
    )

    @field_validator("end", mode="before")
    @classmethod
    def _year_as_text(cls, value: object) -> object:
        return str(value) if isinstance(value, int) else value


class Certification(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    year: int | None = None


_KIND_HINTS: list[tuple[str, str]] = [
    ("name", "name"),
    ("person", "name"),
    ("referee", "name"),
    ("address", "address"),
    ("location", "address"),
    ("birth", "dob"),
    ("dob", "dob"),
    ("age", "dob"),
    ("gender", "gender"),
    ("sex", "gender"),
    ("pronoun", "gender"),
    ("marital", "marital_or_family"),
    ("family", "marital_or_family"),
    ("parent", "marital_or_family"),
    ("carer", "marital_or_family"),
    ("child", "marital_or_family"),
    ("nation", "nationality_or_ethnicity"),
    ("ethnic", "nationality_or_ethnicity"),
    ("citizen", "nationality_or_ethnicity"),
    ("race", "nationality_or_ethnicity"),
    ("relig", "religion"),
    ("faith", "religion"),
    ("health", "health"),
    ("medical", "health"),
    ("disab", "health"),
]


class PersonalSpan(BaseModel):
    text: str = Field(min_length=2, max_length=300)
    kind: SpanKind

    @field_validator("kind", mode="before")
    @classmethod
    def _closest_kind(cls, value: object) -> object:
        """DeepSeek does not always keep to the enum ('marital_status', 'family_status').
        Map near misses to the closest allowed kind instead of failing the whole parse."""
        if not isinstance(value, str):
            return value
        v = value.strip().lower()
        if v in SpanKind.__args__:  # type: ignore[attr-defined]
            return v
        for hint, kind in _KIND_HINTS:
            if hint in v:
                return kind
        return "other_personal"


class CvProfile(BaseModel):
    headline: str | None = None
    summary: str | None = None
    work_history: list[Role] = Field(default_factory=list, max_length=30)
    education: list[Study] = Field(default_factory=list, max_length=15)
    skills: list[str] = Field(default_factory=list, max_length=60)
    certifications: list[Certification] = Field(default_factory=list, max_length=30)
    licences: list[str] = Field(default_factory=list, max_length=20)
    personal_spans: list[PersonalSpan] = Field(default_factory=list, max_length=60)


def _key(d: str | None) -> str:
    if d is None or d == "present":
        return "9999"
    return d


def check_profile(p: CvProfile, text: str) -> None:
    """Raise ValueError listing every problem, so one retry can fix them all."""
    t = " " + normalise(text) + " "
    problems: list[str] = []

    def must_appear(label: str, value: str) -> None:
        v = normalise(value)
        if v and f" {v} " not in t and v not in t:
            problems.append(
                f"{label} '{value[:60]}' is not in the CV text; copy it exactly or leave it out"
            )

    for i, r in enumerate(p.work_history):
        must_appear(f"work_history[{i}].title", r.title)
        must_appear(f"work_history[{i}].employer", r.employer)
        for name, d in (("start", r.start), ("end", r.end)):
            if d is not None and not _DATE.match(d):
                problems.append(f"work_history[{i}].{name} '{d}' must be YYYY-MM, YYYY or present")
        if (
            r.start
            and r.end
            and _DATE.match(r.start)
            and _DATE.match(r.end)
            and _key(r.start) > _key(r.end)
        ):
            problems.append(f"work_history[{i}] starts after it ends")
    for i, s in enumerate(p.education):
        must_appear(f"education[{i}].qualification", s.qualification)
        must_appear(f"education[{i}].institution", s.institution)
    for skill in p.skills:
        must_appear("skill", skill)
    for c in p.certifications:
        must_appear("certification", c.name)
    for lic in p.licences:
        must_appear("licence", lic)
    for sp in p.personal_spans:
        must_appear("personal span", sp.text)
    if not (p.work_history or p.education or p.skills):
        # Found in phase 2 evals: DeepSeek sometimes returned an empty profile, which passed
        # every "must appear" check because there was nothing to check.
        problems.append(
            "the profile is empty; extract the roles, education and skills the CV lists"
        )
    if problems:
        raise ValueError("; ".join(problems[:25]))


async def parse_cv(
    client: LLMClient, *, pre_redacted_text: str, candidate_id: str
) -> LLMResult[CvProfile]:
    return await client.run(
        prompt=PROMPT,
        tier=ModelTier.EXTRACTION,
        output_schema=CvProfile,
        instructions="Return the structured profile for the CV in the data block below.",
        untrusted={"cv": pre_redacted_text},
        candidate_id=candidate_id,
        check=lambda prof: check_profile(prof, pre_redacted_text),
        effort=EFFORT,
        trace_fields={"agent": "cv_parser"},
        trace_output=False,
    )
