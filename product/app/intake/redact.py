"""Redaction (phase 2 design section 2). Order matters.

Before any model call (`pre_redact`):
  1. referees or references section dropped
  2. the applicant's own name (from intake): whole words only
  3. the applicant's own email and phone (phone compared by digits)
  4. patterns: emails, phone numbers, links, street addresses, suburb + state + postcode,
     date of birth and age statements
  5. labelled protected attribute lines (Gender:, Marital status:, Nationality: ...)
After the model (`final_redact`):
  6. personal spans the parser found (other names, free text such as "proud mum of three")

Kept on purpose: employers, titles, schools, skills, employment and study dates, visa or
work rights statements.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

NAME, EMAIL, PHONE, LINK, ADDRESS, DOB, PROTECTED, REFS = (
    "[NAME]",
    "[EMAIL]",
    "[PHONE]",
    "[LINK]",
    "[ADDRESS]",
    "[DOB]",
    "[PROTECTED]",
    "[REFERENCES REMOVED]",
)

KNOWN_HEADINGS = {
    "profile",
    "summary",
    "professional summary",
    "about me",
    "objective",
    "experience",
    "work experience",
    "work history",
    "employment",
    "employment history",
    "career history",
    "education",
    "qualifications",
    "skills",
    "key skills",
    "technical skills",
    "certifications",
    "certifications and licences",
    "licences",
    "licenses",
    "personal details",
    "personal",
    "contact",
    "contact details",
    "projects",
    "awards",
    "achievements",
    "interests",
    "hobbies",
    "languages",
    "volunteering",
    "training",
    "professional development",
    "memberships",
}
REFEREE_HEADINGS = {"referees", "references", "referee", "reference"}

_EMAIL = re.compile(r"[A-Za-z0-9._%+'-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(
    r"(?<![\w])(?:\+?61[\s-]?\(?0?\)?[\s-]?[2-478](?:[\s-]?\d){8}"  # +61 ...
    r"|\(?0[2-478]\)?(?:[\s-]?\d){8}"  # 04xx xxx xxx, (02) xxxx xxxx
    r"|1[38]00(?:[\s-]?\d){6}"  # 1300 / 1800
    r"|\+\d{1,3}(?:[\s-]?\d){6,12})(?![\w])"  # other international
)
_LINK = re.compile(
    r"(?i)\b(?:https?://\S+|www\.\S+|(?:[a-z]{2,3}\.)?linkedin\.com/\S+|github\.com/\S+"
    r"|gitlab\.com/\S+|behance\.net/\S+|dribbble\.com/\S+|medium\.com/@?\S+)"
)
_STREET_TYPES = (
    r"Street|St|Road|Rd|Avenue|Ave|Place|Pl|Drive|Dr|Court|Ct|Lane|Ln|Crescent|Cres|Parade|Pde"
    r"|Terrace|Tce|Way|Close|Cl|Boulevard|Blvd|Highway|Hwy|Circuit|Cct|Grove|Gr"
)
_STREET = re.compile(
    rf"\b(?:(?:Unit|Apt|Apartment|Level)\s+\d+[A-Za-z]?[,/ ]\s*)?"
    rf"\d{{1,5}}[A-Za-z]?(?:/\d{{1,5}})?\s+"
    rf"(?:[A-Z][A-Za-z'-]+\s+){{1,3}}(?:{_STREET_TYPES})\b\.?,?"
)
_SUBURB = re.compile(
    r"\b(?:[A-Z][A-Za-z'-]+[ \t]+){1,3}(?:NSW|VIC|QLD|WA|SA|TAS|ACT|NT)[\s,]+\d{4}\b"
)
_DOB = re.compile(
    r"(?i)\b(?:date\s+of\s+birth|d\.?o\.?b\.?)\s*[:\-]?\s*[^\n|]{0,40}"
    r"|\bborn(?:\s+on)?\s*[:\-]?\s*\d{1,2}[\s/.-]+(?:\d{1,2}|[A-Za-z]{3,9})[\s/.-]+\d{2,4}"
    r"|\bborn\s+in\s+\d{4}\b"
    r"|\bage\s*[:\-]\s*\d{1,3}\b|\b\d{2}\s+years\s+old\b"
)
# Free text family and carer statements. Found in phase 2 evals: the model missed "Proud mum
# of three" in 1 of 3 runs, so the common phrasings are removed by code first and the model
# is the second line. Matches up to the end of the sentence or line.
_FAMILY = re.compile(
    r"(?i)\b(?:proud\s+)?(?:mum|mom|mother|father|dad|parent|grandmother|grandfather|grandparent)"
    r"\s+(?:of|to)\s+(?:\w+\s+){0,2}(?:children|kids|boys|girls|sons?|daughters?|"
    r"one|two|three|four|five|six|\d+)\b[^.\n]*\.?"
    r"|\b(?:husband|wife|partner)\s+and\s+(?:father|mother|dad|mum|mom|parent)\s+of\b[^.\n]*\.?"
    r"|\b(?:married|divorced|widowed|separated)\s+(?:with|and)\s+(?:\w+\s+){0,3}"
    r"(?:children|kids|boys|girls|sons?|daughters?)\b[^.\n]*\.?"
    r"|\bsingle\s+(?:mum|mom|mother|father|dad|parent)\b[^.\n]*\.?"
)

_PROTECTED_LINE = re.compile(
    r"(?im)^(?P<label>[ \t]*(?:gender|sex|marital\s+status|relationship\s+status|nationality"
    r"|citizenship|ethnicity|ethnic\s+background|race|religion|faith|health|medical\s+conditions?"
    r"|disability|pronouns|dependants|dependents|children)\s*:)[ \t]*(?P<value>[^\n|]+)"
)


@dataclass
class Redaction:
    text: str
    counts: Counter[str] = field(default_factory=Counter)


def _sub(rx: re.Pattern[str], placeholder: str, r: Redaction) -> None:
    r.text, n = rx.subn(placeholder, r.text)
    r.counts[placeholder] += n


def _is_heading(line: str) -> bool:
    s = line.strip().rstrip(":").strip().lower()
    return s in KNOWN_HEADINGS or s in REFEREE_HEADINGS


def drop_referees(r: Redaction) -> None:
    lines = r.text.split("\n")
    out, skipping = [], False
    for line in lines:
        key = line.strip().rstrip(":").strip().lower()
        if (
            key in REFEREE_HEADINGS
            or key.startswith("references available")
            or key.startswith("referees available")
        ):
            skipping = True
            r.counts[REFS] += 1
            out.append(REFS)
            continue
        if skipping and _is_heading(line):
            skipping = False
        if not skipping:
            out.append(line)
    r.text = "\n".join(out)


def _name_patterns(full_name: str) -> list[re.Pattern[str]]:
    parts = [p for p in re.split(r"\s+", full_name.strip()) if p]
    pieces = set(parts)
    for p in parts:
        pieces.update(x for x in p.split("-") if len(x) >= 3)
    pieces = {p for p in pieces if len(p.strip(".'-")) >= 3}
    pats = []
    if len(parts) >= 2:
        first, last = parts[0], parts[-1]
        pats.append(re.compile(rf"(?i)\b{re.escape(last)}\s*,\s*{re.escape(first)}\b"))
        pats.append(re.compile(rf"(?i)\b{r'[\s]+'.join(re.escape(p) for p in parts)}\b"))
    for p in sorted(pieces, key=len, reverse=True):  # longest first: hyphenated surnames
        pats.append(
            re.compile(
                rf"(?i)(?<![\w-]){re.escape(p)}(?![\w-])"
                if "-" in p
                else rf"(?i)(?<![\w]){re.escape(p)}(?![\w])"
            )
        )
    return pats


def _phone_pattern(phone: str) -> re.Pattern[str] | None:
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 8:
        return None
    local = digits[-9:]  # national significant number without the trunk 0
    sep = r"[\s().-]*"
    body = sep.join(local)
    return re.compile(rf"(?:\+?61{sep}|0{sep})?{body}(?!\d)")


def pre_redact(text: str, *, name: str | None, email: str | None, phone: str | None) -> Redaction:
    r = Redaction(text)
    drop_referees(r)
    if email:
        _sub(re.compile(re.escape(email.strip()), re.IGNORECASE), EMAIL, r)
    if phone:
        rx = _phone_pattern(phone)
        if rx is not None:
            _sub(rx, PHONE, r)
    if name:
        for rx in _name_patterns(name):
            _sub(rx, NAME, r)
    _sub(_EMAIL, EMAIL, r)
    _sub(_LINK, LINK, r)
    _sub(_PHONE, PHONE, r)
    _sub(_STREET, ADDRESS, r)
    _sub(_SUBURB, ADDRESS, r)
    _sub(_DOB, DOB, r)
    r.text, n = _PROTECTED_LINE.subn(lambda m: f"{m.group('label')} {PROTECTED}", r.text)
    r.counts[PROTECTED] += n
    _sub(_FAMILY, PROTECTED, r)
    return r


_KIND_PLACEHOLDER = {"name": NAME, "address": ADDRESS, "dob": DOB}


def final_redact(pre: Redaction, spans: list[tuple[str, str]]) -> Redaction:
    """Step 6: replace each (text, kind) span the parser found. Whitespace tolerant."""
    r = Redaction(pre.text, Counter(pre.counts))
    for text, kind in sorted(spans, key=lambda s: len(s[0]), reverse=True):
        t = text.strip()
        if (
            len(t) < 2
            or "[" in t
            and "]" in t
            and not re.sub(r"\[[A-Z ]+\]|[\W_]", "", t.split(":")[-1])
        ):
            continue  # already a placeholder ("Gender: [PROTECTED]")
        rx = re.compile(r"\s+".join(re.escape(w) for w in t.split()), re.IGNORECASE)
        _sub(rx, _KIND_PLACEHOLDER.get(kind, PROTECTED), r)
    return r


def normalise(s: str) -> str:
    """For 'appears in the text' checks: lowercase, punctuation and spacing collapsed."""
    return " ".join(re.sub(r"[^\w&+#/]+", " ", s.lower()).split())
