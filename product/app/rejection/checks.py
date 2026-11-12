"""Hard rule checks on a rejection email body (phase 5 design section 5).

Run on every agent draft, every template draft and every recruiter edit. Each rule
returns passed plus a detail the dashboard shows. H1 (real reasons) needs the reasons the
writer chose, so it is skipped for recruiter edits, which may reword reasons freely.

The contact line, the deletion line, the greeting and the sign off are added by code
after these checks, so H6 can forbid every link, address and number in the body.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from typing import Any

from app.domain.guard import find_reason_terms

MIN_WORDS = 60
MAX_WORDS = 200
COPY_RUN = 8  # words in a row that may not be copied from the CV

# H3: harsh or loaded wording. Word boundaries, case insensitive. Change with a test.
BLOCKED_PHRASES: tuple[str, ...] = (
    r"fail(ed|s|ure)?",
    r"poor(ly)?",
    r"weak(ness|nesses)?",
    r"not good enough",
    r"lack(s|ed|ing)?",
    r"inadequate",
    r"insufficient",
    r"unqualified",
    r"overqualified",
    r"too (old|young|junior|senior|experienced|inexperienced)",
    r"culture fit",
    r"cultural fit",
    r"unfortunately,? you",
    r"you (were|are) not (suitable|a fit|right)",
    r"disappointing",
    r"subpar",
    r"below (the )?(standard|bar|par)",
)
_BLOCKED = re.compile(r"\b(" + "|".join(BLOCKED_PHRASES) + r")\b", re.IGNORECASE)

# H4: no numbers presented as a score, and no scoring words.
_SCORE_NUMBER = re.compile(
    r"\b\d+(\.\d+)?\s*(%|percent\b|points?\b|/\s*\d+|out of\b)", re.IGNORECASE
)
_SCORE_WORDS = re.compile(
    r"\b(scor(e|ed|es|ing)|band(s|ed)?|rank(ed|ing|s)?|threshold|rubric)\b",
    re.IGNORECASE,
)

# H6: links, email addresses, phone numbers.
_URL = re.compile(
    r"https?://|\bwww\.|\b[\w-]+\.(com|au|net|org|io|co|ly|me|info|biz|app)\b", re.IGNORECASE
)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
_PHONE = re.compile(r"(\+?\d[\d ()-]{7,}\d)")

# H7: anything that reads as a job offer. Keeping the CV on file and future roles or
# contact are allowed (Mani, 2026-11-12); they were blocked before.
_PROMISE = re.compile(
    r"\bhired\b|\boffer\b|\bcongratulations\b|\bsuccessful (applicant|candidate)\b|"
    r"\byou (got|have got|have been given) the (job|role|position)\b",
    re.IGNORECASE,
)

# H2 extra: an email speaks to the candidate, so "your children" and similar. The phase 3
# guard covers third person forms ("her children") and the protected word list.
# Found in the phase 5 build: "with your young children" passed the guard alone.
_SECOND_PERSON = re.compile(
    r"\byour (own )?(young |little |small )?(children|kids|family|baby|partner|husband|wife|"
    r"spouse|pregnancy|health|illness|condition|disability|age|religion|faith|beliefs|"
    r"accent|cultural background|culture|nationality|ethnicity|heritage|home|suburb|commute)\b"
    r"|\b(mum|mom|mother|father|dad)\b|\b(as a|being a) (parent|carer|mother|father)\b",
    re.IGNORECASE,
)

_WORD = re.compile(r"[a-z0-9']+")


@dataclass(frozen=True)
class CheckResult:
    rule: str
    passed: bool
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def words(text: str) -> list[str]:
    return _WORD.findall(text.lower().replace("’", "'"))


def _ngrams(ws: Sequence[str], n: int) -> set[tuple[str, ...]]:
    return {tuple(ws[i : i + n]) for i in range(len(ws) - n + 1)}


def _found(rx: re.Pattern[str], text: str) -> list[str]:
    return sorted({m.group(0).strip().lower() for m in rx.finditer(text)})


def run_checks(
    body: str,
    *,
    reason_ids: Iterable[str] | None,
    allowed_ids: Iterable[str],
    cv_text: str,
) -> list[CheckResult]:
    """All eight rules. `reason_ids=None` skips H1 (recruiter edits)."""
    out: list[CheckResult] = []
    if reason_ids is None:
        out.append(CheckResult("H1", True, "not checked on a recruiter edit"))
    else:
        ids = list(reason_ids)
        allowed = set(allowed_ids)
        bad = sorted({i for i in ids if i not in allowed})
        dup = sorted({i for i in ids if ids.count(i) > 1})
        detail = []
        if bad:
            detail.append(f"not a missed requirement: {', '.join(bad)}")
        if dup:
            detail.append(f"used twice: {', '.join(dup)}")
        out.append(CheckResult("H1", not detail, "; ".join(detail) or "every reason is real"))

    protected = sorted(set(find_reason_terms(body)) | set(_found(_SECOND_PERSON, body)))
    out.append(
        CheckResult(
            "H2",
            not protected,
            f"protected or proxy wording: {', '.join(protected)}" if protected else "none found",
        )
    )

    harsh = _found(_BLOCKED, body)
    out.append(
        CheckResult(
            "H3", not harsh, f"blocked wording: {', '.join(harsh)}" if harsh else "none found"
        )
    )

    scores = _found(_SCORE_NUMBER, body) + _found(_SCORE_WORDS, body)
    out.append(
        CheckResult(
            "H4",
            not scores,
            f"mentions scoring: {', '.join(sorted(set(scores)))}" if scores else "none found",
        )
    )

    copied = sorted(
        " ".join(g) for g in _ngrams(words(body), COPY_RUN) & _ngrams(words(cv_text), COPY_RUN)
    )
    out.append(
        CheckResult(
            "H5",
            not copied,
            f'copied from the CV: "{copied[0]}"' if copied else "nothing copied from the CV",
        )
    )

    contact = _found(_URL, body) + _found(_EMAIL, body) + _found(_PHONE, body)
    out.append(
        CheckResult(
            "H6",
            not contact,
            f"link, email or phone number: {', '.join(sorted(set(contact)))}"
            if contact
            else "none found",
        )
    )

    promises = _found(_PROMISE, body)
    out.append(
        CheckResult(
            "H7",
            not promises,
            f"job offer wording: {', '.join(promises)}" if promises else "none found",
        )
    )

    n = len(words(body))
    out.append(
        CheckResult(
            "H8",
            MIN_WORDS <= n <= MAX_WORDS,
            f"{n} words (allowed {MIN_WORDS} to {MAX_WORDS})",
        )
    )
    return out


def failures(results: Iterable[CheckResult]) -> list[CheckResult]:
    return [r for r in results if not r.passed]


def all_passed(results: Iterable[dict[str, Any]] | Iterable[CheckResult]) -> bool:
    for r in results:
        passed = r["passed"] if isinstance(r, dict) else r.passed
        if not passed:
            return False
    return True
