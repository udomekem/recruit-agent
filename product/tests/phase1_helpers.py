"""Shared fixtures data for phase 1 tests: a job ad, a valid rubric for it, CV files."""

from __future__ import annotations

import io
import json
import zipfile
from typing import Any

AD = (
    "Harbourline Insurance is looking for a Business Analyst to join our claims "
    "transformation program.\n\nEssential:\n- At least 3 years of experience as a Business "
    "Analyst\n- Working knowledge of SQL\n- Strong stakeholder management with senior "
    "business leaders\n\nDesirable:\n- Insurance or financial services background\n\n"
    "Hybrid: three days a week in our Sydney CBD office."
)

JOB = {
    "title": "Business Analyst",
    "description": AD,
    "location": "Sydney NSW",
    "work_arrangement": "hybrid",
    "salary_min": 110000,
    "salary_max": 130000,
}

RUBRIC: dict[str, Any] = {
    "criteria": [
        {
            "id": "ba_experience",
            "kind": "must_have",
            "category": "experience",
            "text": "At least 3 years as a Business Analyst",
            "weight": 5,
            "years": 3,
            "evidence": "At least 3 years of experience as a Business Analyst",
        },
        {
            "id": "sql",
            "kind": "must_have",
            "category": "skill",
            "text": "Working knowledge of SQL",
            "weight": 4,
            "years": None,
            "evidence": "Working knowledge of SQL",
        },
        {
            "id": "stakeholders",
            "kind": "must_have",
            "category": "skill",
            "text": "Stakeholder management with senior leaders",
            "weight": 4,
            "years": None,
            "evidence": "Strong stakeholder management with senior business leaders",
        },
        {
            "id": "insurance",
            "kind": "nice_to_have",
            "category": "experience",
            "text": "Insurance or financial services background",
            "weight": 2,
            "years": None,
            "evidence": "Insurance or financial services background",
        },
    ],
    "flags": [],
}
RUBRIC_JSON = json.dumps(RUBRIC)


def score_json(**verdicts: str) -> str:
    """A scripted cv-scorer reply for the phase 2 test CV against RUBRIC (phase 3).
    Default: BA experience partly met, SQL met, the rest not met = 43.3, reject."""
    quotes = {
        "ba_experience": "Senior Data Analyst, Molonglo Analytics",
        "sql": "SQL, Tableau, Python",
        "stakeholders": "Senior Data Analyst, Molonglo Analytics",
        "insurance": "Senior Data Analyst, Molonglo Analytics",
    }
    v = {
        "ba_experience": "partly_met",
        "sql": "met",
        "stakeholders": "not_met",
        "insurance": "not_met",
        **verdicts,
    }
    return json.dumps(
        {
            "judgements": [
                {
                    "criterion_id": cid,
                    "verdict": verdict,
                    "reason": (
                        "Analyst work shown, role is related."
                        if verdict != "not_met"
                        else "Not shown in the CV."
                    ),
                    "quote": quotes[cid] if verdict != "not_met" else "",
                }
                for cid, verdict in v.items()
            ],
            "injection_suspected": False,
            "injection_note": "",
        }
    )


SCORE_JSON = score_json()

PDF = b"%PDF-1.7\n1 0 obj << /Type /Catalog >> endobj\ntrailer << >>\n%%EOF\n"


def docx(macros: bool = False) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        main = (
            "application/vnd.ms-word.document.macroEnabled.main+xml"
            if macros
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
        )
        z.writestr(
            "[Content_Types].xml",
            f'<Types><Override PartName="/word/document.xml" ContentType="{main}"/></Types>',
        )
        z.writestr("word/document.xml", "<w:document><w:body><w:p>CV</w:p></w:body></w:document>")
        if macros:
            z.writestr("word/vbaProject.bin", b"\x00" * 10)
    return buf.getvalue()


def answers(**over: str) -> dict[str, str]:
    base = {
        "q_right_to_work": "yes",
        "q_expected_salary": "120000",
        "q_notice_period": "3 to 4 weeks",
        "q_location_fit": "yes",
        "q_current_role": "Senior Analyst",
    }
    base.update(over)
    return base
