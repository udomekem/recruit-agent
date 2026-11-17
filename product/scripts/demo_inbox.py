"""Demo emails for the connected inbox (phase 5B). Synthetic people only.

    uv run python -m scripts.demo_inbox        # = make demo-inbox (needs make up)

Sends three applications to the local test inbox (Mailpit), tagged "Applications" (the
tag stands in for a Gmail label). Connect the test inbox on the dashboard's Inbox page
first, then press "Check now" or wait for the 2 minute poll:

  1. a Data Analyst CV with the job's code in the subject   -> matched by code
  2. a Registered Nurse CV sent to the job's plus address   -> matched by plus address
  3. a Site Supervisor CV with no job in the email          -> the job matcher decides;
     with several open jobs of the same kind it is unsure, so it waits in "Needs a job"

Each CV is a small PDF. The job codes come from the newest approved job of each kind.
"""

from __future__ import annotations

import base64
import io
import os
import random
import sys
from typing import Any

MAILPIT = os.environ.get("MAILPIT_URL", "http://localhost:8025")
API = os.environ.get("API_URL", "http://localhost:8000")
TO = "careers@northwind.example"

CVS: dict[str, list[str]] = {
    "analyst": [
        "Data Analyst",
        "Profile: data analyst with five years of reporting work in freight and retail.",
        "Experience: Data Analyst, Harbourline Freight, 2020 to present.",
        "Wrote SQL for weekly delivery reporting; automated reports with Python and pandas.",
        "Built Power BI dashboards and presented findings to the operations leadership team.",
        "Education: Bachelor of Science (Statistics). Skills: SQL, Python, Power BI, Snowflake.",
    ],
    "nurse": [
        "Registered Nurse",
        "Current AHPRA registration as a Registered Nurse.",
        "Experience: Registered Nurse, surgical ward, Westmead area hospital, 2021 to present.",
        "Acute post operative care; safe medication administration including S8 drugs.",
        "Advanced Life Support certificate; daily use of Cerner electronic medical records.",
        "Education: Bachelor of Nursing.",
    ],
    "site": [
        "Site Supervisor",
        "Seven years supervising residential construction sites in Western Sydney.",
        "Ran WHS on site: inductions, SWMS reviews and incident reporting.",
        "White Card, first aid certificate, driver's licence; Procore daily.",
        "Certificate IV in Building and Construction.",
    ],
}
TITLES = {
    "analyst": "Data Analyst",
    "nurse": "Registered Nurse",
    "site": "Site Supervisor",
}


def pdf(lines: list[str]) -> str:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 800
    for line in lines:
        c.drawString(50, y, line)
        y -= 18
    c.save()
    return base64.b64encode(buf.getvalue()).decode()


def jobs() -> dict[str, dict[str, Any]]:
    import httpx

    from app.config import get_settings

    token = get_settings().recruiter_token
    if token is None:
        sys.exit("RECRUITER_TOKEN is not set; run make local-env")
    r = httpx.get(
        f"{API}/jobs", headers={"Authorization": f"Bearer {token.get_secret_value()}"}, timeout=30
    )
    r.raise_for_status()
    out: dict[str, dict[str, Any]] = {}
    for j in r.json()["jobs"]:  # newest first
        for kind, title in TITLES.items():
            if (
                kind not in out
                and j["title"].startswith(title)
                and j.get("code")
                and j.get("approved_rubric_version")
            ):
                out[kind] = j
    missing = [k for k in TITLES if k not in out]
    if missing:
        sys.exit(f"no approved job for {missing}; run make demo-seed-offline first")
    return out


def send(sender: tuple[str, str], subject: str, to: str, kind: str) -> None:
    import httpx

    name, email = sender
    body = {
        "From": {"Email": email, "Name": name},
        "To": [{"Email": to}],
        "Subject": subject,
        "Text": "Hello, please find my CV attached. Kind regards.",
        "Tags": ["Applications"],
        "Attachments": [{"Filename": "cv.pdf", "Content": pdf([name, *CVS[kind]])}],
    }
    r = httpx.post(f"{MAILPIT}/api/v1/send", json=body, timeout=30)
    r.raise_for_status()
    print(f"sent: {subject!r} to {to}")


def main() -> None:
    js = jobs()
    run = random.randint(100, 999)
    a, n = js["analyst"]["code"], js["nurse"]["code"]
    send(("Priya Demo", f"priya.{run}@example.test"), f"Application {a}", TO, "analyst")
    send(
        ("Tom Demo", f"tom.{run}@example.test"),
        "My application",
        f"careers+{n.lower()}@northwind.example",
        "nurse",
    )
    send(("Lena Demo", f"lena.{run}@example.test"), "CV attached", TO, "site")
    print("Now press Check now on the Inbox page (or wait up to 2 minutes).")


if __name__ == "__main__":
    main()
