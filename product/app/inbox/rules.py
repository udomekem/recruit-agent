"""Code rules for inbox emails (phase 5B design section 4). No model involved.

Matching, in order; the first hit wins:
  1. a job code in the subject (DA-0042), open jobs only
  2. a plus address (careers+da-0042@...) in To, Cc or Delivered-To
  3. a Seek subject ("Application for {title}") or an Indeed subject ("New application:
     {title}"): the exact title of exactly one open job
A hit on a closed job is not a match ("applied for a closed job"). Subjects are
untrusted: they only ever select among the jobs that exist; they never reach a model.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

SEEK_DOMAINS = ("seek.com.au", "seek.co.nz", "seek.com")
INDEED_DOMAINS = ("indeed.com", "indeed.com.au", "indeedemail.com")

_CODE = re.compile(r"\b([A-Z]{2}-\d{4})\b", re.IGNORECASE)
_PLUS = re.compile(r"^[^@+]+\+([a-z]{2}-\d{4})@", re.IGNORECASE)
_PREFIX = re.compile(r"^\s*((fwd?|fw|re)\s*:\s*)+", re.IGNORECASE)
_SEEK = re.compile(
    r"^application for\s+(?:the\s+)?(.+?)(?:\s+(?:role|position|job))?(?:\s+from\s+.+)?$", re.I
)
_INDEED = re.compile(
    r"^(?:new application|indeed application)\s*[:\-]\s*(.+?)(?:\s+from\s+.+)?$", re.I
)
_FROM_NAME = re.compile(r"\bfrom\s+([A-Z][a-zA-Z'\-]+(?:\s+[A-Z][a-zA-Z'\-]+){0,3})\s*$")
_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(\+?\d[\d ()\-]{7,}\d)")
_NAME_LINE = re.compile(r"^[A-Z][a-zA-Z'\-]+(?:\s+[A-Z][a-zA-Z'\-]+){1,3}$")
_NOT_NAMES = {"curriculum", "vitae", "resume", "résumé", "cv", "profile", "summary", "contact"}


@dataclass(frozen=True)
class OpenJob:
    id: uuid.UUID
    title: str
    code: str | None
    open: bool


@dataclass(frozen=True)
class RuleMatch:
    job_id: uuid.UUID | None
    route: str | None  # job_code | plus_address | seek_subject | indeed_subject
    detail: str


def sender_kind(address: str) -> str:
    domain = address.rsplit("@", 1)[-1].lower() if "@" in address else ""
    if domain.endswith(SEEK_DOMAINS):
        return "seek"
    if domain.endswith(INDEED_DOMAINS):
        return "indeed"
    return "direct" if domain else "other"


def strip_prefixes(subject: str) -> str:
    return _PREFIX.sub("", subject).strip()


def name_from_subject(subject: str) -> str | None:
    m = _FROM_NAME.search(strip_prefixes(subject))
    return m.group(1) if m else None


def redact_subject(subject: str, names: list[str | None]) -> str:
    """The subject as stored and shown: no names, emails or phone numbers."""
    s = " ".join(subject.split())[:300]
    s = _EMAIL.sub("[email]", s)
    s = _PHONE.sub("[phone]", s)
    for n in [x for x in names if x]:
        for part in sorted({n, *n.split()}, key=len, reverse=True):
            if len(part) > 1:
                s = re.sub(rf"\b{re.escape(part)}\b", "[name]", s, flags=re.IGNORECASE)
    m = _FROM_NAME.search(s)
    if m:
        s = s[: m.start(1)] + "[name]"
    return s


def _by_code(code: str, jobs: list[OpenJob]) -> OpenJob | None:
    return next((j for j in jobs if j.code and j.code.lower() == code.lower()), None)


def _decide(job: OpenJob | None, route: str, label: str) -> RuleMatch | None:
    if job is None:
        return None
    if not job.open:
        return RuleMatch(None, None, f"{label} points to a closed job ({job.title})")
    return RuleMatch(job.id, route, label)


def match_rules(subject: str, to: list[str], kind: str, jobs: list[OpenJob]) -> RuleMatch:
    subj = strip_prefixes(subject)
    m = _CODE.search(subj)
    if m:
        hit = _decide(
            _by_code(m.group(1), jobs), "job_code", f"Job code {m.group(1).upper()} in the subject"
        )
        if hit:
            return hit
    for addr in to:
        p = _PLUS.match(addr.strip())
        if p:
            hit = _decide(
                _by_code(p.group(1), jobs), "plus_address", "Sent to the job's own address"
            )
            if hit:
                return hit
    for pattern, route, label in (
        (_SEEK, "seek_subject", "Seek subject line"),
        (_INDEED, "indeed_subject", "Indeed subject line"),
    ):
        t = pattern.match(subj)
        if not t:
            continue
        title = " ".join(t.group(1).split()).casefold()
        same = [j for j in jobs if " ".join(j.title.split()).casefold() == title]
        live = [j for j in same if j.open]
        if len(live) == 1:
            return RuleMatch(live[0].id, route, label)
        if len(live) > 1:
            return RuleMatch(None, None, f"{label}: more than one open job has this title")
        if same:
            return RuleMatch(None, None, f"{label} points to a closed job ({same[0].title})")
    return RuleMatch(None, None, "No job code or known subject")


def guess_contact(
    *, kind: str, sender_name: str, sender_address: str, subject: str, cv_text: str
) -> tuple[str | None, str | None]:
    """Best guess at the applicant's name and email, for redaction and the notice.
    Direct emails: the sender. Seek and Indeed: the subject's "from" name and the first
    email address in the CV (the job board's own address is never the applicant's)."""
    email: str | None = None
    name: str | None = None
    if kind == "direct" and sender_address:
        email = sender_address
        if _NAME_LINE.match(sender_name.strip() or "x"):
            name = sender_name.strip()
    if email is None:
        for found in _EMAIL.findall(cv_text[:4000]):
            if sender_kind(found) not in ("seek", "indeed"):
                email = found
                break
    name = name or name_from_subject(subject)
    if name is None:
        for line in cv_text.splitlines()[:8]:
            line = line.strip()
            if _NAME_LINE.match(line) and not ({w.lower() for w in line.split()} & _NOT_NAMES):
                name = line
                break
    return name, email
