"""Protected attribute guard (phase 1 design section 5).

A reviewed list of words that must never be the basis of a criterion or a screening
question: age, sex or gender, race or nationality (as origin), disability, family or
carer status, religion, sexuality. The rubric builder runs this after the model; a hit
makes the output invalid so it is retried, and the model is also asked to flag such
wording in the ad.

Deliberately NOT on the list:
- "right to work", "work rights", "visa": lawful eligibility questions
- "citizenship", "citizen", "security clearance": lawful where a clearance requires it
  (rubric-009); the model may flag them, the guard does not block them
- "years" on its own: "5 years of experience" is fine; only age phrasing is blocked
- "English": language skill is lawful; "native English speaker" is blocked
- "native" alone: "native mobile development" is a skill
- "single" alone: "Single Touch Payroll" is the ATO payroll reporting system
- "young people": working with young people is a lawful duty (youth work)
- "straight": too many ordinary meanings ("straight to work")

Change this list only with a test showing the case it fixes and that the false positive
cases below still pass.
"""

from __future__ import annotations

import re

PROTECTED_PATTERNS: dict[str, str] = {
    # age
    r"\byoung(er)?\b(?! (people|persons?|adults?|children|clients?|offenders?|carers?))": "age",
    r"\byouthful\b": "age",
    r"\bmature[- ]aged?\b": "age",
    r"\bunder \d{2}\b": "age",
    r"\baged? \d{2}": "age",
    r"\b\d{2} ?(years old|yo)\b": "age",
    r"\bdigital native\b": "age",
    r"\brecent(ly)? graduat": "age",
    r"\bretire(e|d)\b": "age",
    # sex, gender, sexuality
    r"\b(fe)?male\b": "sex_or_gender",
    r"\b(wo)?m[ae]n only\b": "sex_or_gender",
    r"\bgentlem[ae]n\b": "sex_or_gender",
    r"\bladies\b": "sex_or_gender",
    r"\b(gay|lesbian|heterosexual|sexual orientation)\b": "sexuality",
    # race, nationality (as origin), language as origin
    r"\bnative[- ](english )?speakers?\b": "race_or_nationality",
    r"\bnative[- ]born\b": "race_or_nationality",
    r"\bnationality\b": "race_or_nationality",
    r"\bethnic(ity)?\b": "race_or_nationality",
    r"\b(born in|country of birth)\b": "race_or_nationality",
    r"\b(caucasian|white|asian|african|aboriginal|indigenous) "
    r"(candidates?|applicants?|people)\b": "race_or_nationality",
    r"\bno accents?\b": "race_or_nationality",
    # family, carer, marital, pregnancy
    r"\bfamily commitments?\b": "family_or_carer",
    r"\bno (kids|children)\b": "family_or_carer",
    r"\b(childless|married|marital status)\b": "family_or_carer",
    r"\bsingle (people|persons?|applicants?|candidates?|parents?)\b": "family_or_carer",
    r"\bpregnan(t|cy)\b": "family_or_carer",
    r"\bcarer('s)? (status|responsibilities)\b": "family_or_carer",
    # religion
    r"\b(christian|muslim|jewish|hindu|buddhist|religio(n|us))\b": "religion",
    # disability and health (not job specific physical requirements, which are worded as tasks)
    r"\b(able[- ]bodied|no disabilit(y|ies)|disabled)\b": "disability",
}

_COMPILED = [(re.compile(p, re.IGNORECASE), cat) for p, cat in PROTECTED_PATTERNS.items()]


def find_protected_terms(text: str) -> list[str]:
    """Return the matched phrases (lowercased), empty if none."""
    hits: list[str] = []
    for rx, _cat in _COMPILED:
        for m in rx.finditer(text):
            hits.append(m.group(0).lower())
    return sorted(set(hits))


def protected_categories(text: str) -> list[str]:
    return sorted({cat for rx, cat in _COMPILED if rx.search(text)})
