"""The collection notice shown on the apply page (Privacy Act, APP 5).

Versioned: the version a candidate agreed to is stored with their consent. A wording
change is a new version; old versions stay so past consent stays explainable.
Not legal advice; reviewed by an employment lawyer before real use (master plan phase 10).
"""

NOTICE_VERSION = "v1"
RETENTION_MONTHS = 12


def notice_text(company: str) -> list[str]:
    return [
        f"{company} collects your name, contact details, answers and CV to assess your "
        "application for this role.",
        "An AI assisted system helps screen applications: it compares your CV and answers "
        "with the job's requirements and suggests a rating. A person makes every decision "
        "to progress or decline an application.",
        "Shortlisted applicants may receive a phone call from an AI assistant, which will "
        "tell you it is an AI and ask before recording.",
        "Your information is seen only by the hiring team and the services that run this "
        "system. It is not sold or used to train AI models.",
        f"We keep your application for {RETENTION_MONTHS} months after the role closes, then "
        "delete it. You can ask us to delete it sooner, or to see or correct it, at any time.",
        "You do not have to apply, but we cannot consider your application without this "
        "information.",
    ]


CONSENT_LABEL = (
    "I have read this notice and agree to my application being assessed with AI assistance "
    "as described."
)
