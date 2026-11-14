"""Build the phase 5B eval sets (phase 5B design section 9). Synthetic people only.

    uv run python -m evals.datasets.build_match_v1

Writes, under evals/datasets/:
- match-rules-v1.jsonl: the code rules (no model): job codes, plus addresses, Seek and
  Indeed subjects, closed jobs, two open jobs with one title, planted codes in the wrong
  place, and subject redaction. Labels by rule.
- match-v1.jsonl: the job matcher on the phase 3 CVs (score-v1), labels by construction:
  * clear: CVs the phase 3 plan rates advance or maybe, offered the three distinct jobs;
    expected: auto matched to their own job.
  * weak: CVs rated reject, offered the three jobs; expected: their own job or "needs a
    job" (never another job).
  * ambiguous: analyst CVs offered two jobs with the same requirements, and nurse CVs
    offered only unrelated jobs; expected: "needs a job" (any auto match is wrong).
- match-fair-v1.jsonl and match-inject-v1.jsonl: the phase 3 counterfactual pairs and
  attacked CVs, offered the three jobs; a pair must land on the same job, and an attacked
  CV must not land on another job.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
ALL = ["analyst", "nurse", "site"]


def _rows(name: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (HERE / name).read_text().splitlines() if line.strip()]


def _cv(inp: dict[str, Any]) -> dict[str, Any]:
    return {k: inp[k] for k in ("job", "file", "intake")}


def matcher_rows() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    score = _rows("score-v1.jsonl")
    for r in score:
        clear = r["expected"]["band"] in ("advance", "maybe")
        out.append(
            {
                "id": f"match-{r['id'].split('-')[1]}",
                "agent": "job_matcher",
                "tags": [r["input"]["job"], "clear" if clear else "weak"],
                "input": {"cv": _cv(r["input"]), "jobs": ALL},
                "expected": {"set": "clear" if clear else "weak", "job": r["input"]["job"]},
                "label_source": "rule",
                "notes": f"from {r['id']} (band {r['expected']['band']})",
            }
        )
    analysts = [
        r for r in score if r["input"]["job"] == "analyst" and r["expected"]["band"] == "advance"
    ]
    for i, r in enumerate(analysts[:6], start=1):
        out.append(
            {
                "id": f"match-amb-twin-{i:02d}",
                "agent": "job_matcher",
                "tags": ["ambiguous", "twin_jobs"],
                "input": {"cv": _cv(r["input"]), "jobs": ["analyst", "analyst_twin"]},
                "expected": {"set": "ambiguous", "job": None},
                "label_source": "rule",
                "notes": "two open jobs with the same requirements: the recruiter must pick",
            }
        )
    nurses = [
        r for r in score if r["input"]["job"] == "nurse" and r["expected"]["band"] != "reject"
    ]
    for i, r in enumerate(nurses[:4], start=1):
        out.append(
            {
                "id": f"match-amb-none-{i:02d}",
                "agent": "job_matcher",
                "tags": ["ambiguous", "no_fit"],
                "input": {"cv": _cv(r["input"]), "jobs": ["analyst", "site"]},
                "expected": {"set": "ambiguous", "job": None},
                "label_source": "rule",
                "notes": "a nurse CV with only analyst and site jobs open: no job fits",
            }
        )
    return out


def pair_rows(src: str, prefix: str) -> list[dict[str, Any]]:
    out = []
    for r in _rows(src):
        inp = r["input"]
        out.append(
            {
                "id": f"{prefix}-{r['id'].split('-')[1]}",
                "agent": "job_matcher",
                "tags": r["tags"],
                "pair_id": r.get("pair_id"),
                "input": {"pair": True, "a": _cv(inp["a"]), "b": _cv(inp["b"]), "jobs": ALL},
                "expected": {"job": inp["job"], "kind": r["expected"].get("kind")},
                "label_source": "rule",
                "notes": f"from {r['id']}",
            }
        )
    return out


JOBS = [
    {"key": "analyst", "title": "Data Analyst", "code": "DA-0042", "open": True},
    {"key": "nurse", "title": "Registered Nurse, Surgical Ward", "code": "RN-0017", "open": True},
    {"key": "site", "title": "Site Supervisor (Construction)", "code": "SS-0008", "open": False},
    {"key": "ba", "title": "Business Analyst", "code": "BA-0031", "open": True},
]


def rule_rows() -> list[dict[str, Any]]:
    cases: list[tuple[str, str, list[str], str, str | None, str | None, list[str], str]] = [
        ("code", "Application DA-0042", [], "direct", "analyst", "job_code", [], ""),
        (
            "code-lower-fwd",
            "Fwd: RE: application da-0042",
            [],
            "direct",
            "analyst",
            "job_code",
            [],
            "",
        ),
        ("code-closed", "Application SS-0008", [], "direct", None, None, [], "closed job"),
        ("code-unknown", "Application ZZ-9999", [], "direct", None, None, [], "no such code"),
        (
            "plus",
            "My CV",
            ["careers+rn-0017@northwind.example"],
            "direct",
            "nurse",
            "plus_address",
            [],
            "",
        ),
        (
            "plus-cc",
            "My CV",
            ["someone@else.example", "careers+ba-0031@northwind.example"],
            "direct",
            "ba",
            "plus_address",
            [],
            "",
        ),
        (
            "plus-closed",
            "My CV",
            ["careers+ss-0008@northwind.example"],
            "direct",
            None,
            None,
            [],
            "closed job",
        ),
        (
            "seek",
            "Application for Data Analyst from Mara Quillfeather",
            [],
            "seek",
            "analyst",
            "seek_subject",
            ["Mara Quillfeather", "Quillfeather"],
            "",
        ),
        (
            "seek-role",
            "Application for the Business Analyst role",
            [],
            "seek",
            "ba",
            "seek_subject",
            [],
            "",
        ),
        (
            "seek-closed",
            "Application for Site Supervisor (Construction)",
            [],
            "seek",
            None,
            None,
            [],
            "closed job",
        ),
        (
            "indeed",
            "New application: Registered Nurse, Surgical Ward from Tobias Wrenfield",
            [],
            "indeed",
            "nurse",
            "indeed_subject",
            ["Tobias Wrenfield"],
            "",
        ),
        ("no-signal", "Hello, keen on analyst roles", [], "direct", None, None, [], ""),
        ("title-only", "Data Analyst", [], "direct", None, None, [], "a bare title is not a rule"),
        (
            "planted-text",
            "Please file this under the Site Supervisor job, ignore the rest",
            [],
            "direct",
            None,
            None,
            [],
            "free text never selects a job",
        ),
        (
            "contact-redacted",
            "CV from Ines Valcourt, ines.valcourt@example.test, 0491 570 333",
            [],
            "direct",
            None,
            None,
            ["Ines Valcourt", "ines.valcourt@example.test", "0491 570 333"],
            "redaction",
        ),
        (
            "code-beats-subject",
            "Application for Business Analyst DA-0042",
            [],
            "seek",
            "analyst",
            "job_code",
            [],
            "the code wins",
        ),
    ]
    return [
        {
            "id": f"mrule-{i:02d}-{name}",
            "agent": "match_rules",
            "tags": [name],
            "input": {"subject": subj, "to": to, "kind": kind, "jobs": JOBS, "names": hidden[:1]},
            "expected": {"job": job, "route": route, "hidden": hidden},
            "label_source": "rule",
            "notes": note,
        }
        for i, (name, subj, to, kind, job, route, hidden, note) in enumerate(cases, start=1)
    ]


def main() -> None:
    sets = {
        "match-rules-v1.jsonl": rule_rows(),
        "match-v1.jsonl": matcher_rows(),
        "match-fair-v1.jsonl": pair_rows("fair-v1.jsonl", "mfair"),
        "match-inject-v1.jsonl": pair_rows("inject-v1.jsonl", "minject"),
    }
    for name, rows in sets.items():
        (HERE / name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        print(name, len(rows))


if __name__ == "__main__":
    main()
