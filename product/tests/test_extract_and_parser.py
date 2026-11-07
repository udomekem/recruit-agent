"""Text extraction and the CV parser's code checks (no model)."""

import io

import pytest

from app.agents.cv_parser import CvProfile, PersonalSpan, check_profile
from app.intake.extract import extract_sync
from app.llm.client import strict_json_schema

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def docx_with_header_and_table() -> bytes:
    from docx import Document

    d = Document()
    d.sections[0].header.paragraphs[0].text = "Header Person | 0491 570 155"
    d.add_paragraph("Experience " + "lorem ipsum " * 15)
    t = d.add_table(rows=1, cols=2)
    t.rows[0].cells[0].text, t.rows[0].cells[1].text = "2021 to Present", "Analyst, Kookaburra Labs"
    d.sections[0].footer.paragraphs[0].text = "Footer Street address"
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def test_docx_header_table_footer_in_order() -> None:
    ex = extract_sync(docx_with_header_and_table(), DOCX)
    assert ex.status == "ok"
    lines = ex.text.splitlines()
    assert lines[0].startswith("Header Person")
    assert "2021 to Present | Analyst, Kookaburra Labs" in ex.text
    assert lines[-1] == "Footer Street address"


def test_image_only_and_broken_files() -> None:
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.rect(10, 10, 100, 100)  # a page with no text
    c.save()
    assert extract_sync(buf.getvalue(), "application/pdf").status == "no_text_layer"
    assert extract_sync(b"%PDF-1.7 broken", "application/pdf").status in ("failed", "no_text_layer")
    assert extract_sync(b"PK\x03\x04 junk", DOCX).status == "failed"
    assert extract_sync(b"x", "text/plain").status == "failed"


TEXT = """[NAME]
Experience
Senior Data Analyst, Molonglo Analytics
Mar 2021 to Present
Skills
SQL, Tableau, Python
Certifications: AWS Certified Developer (2019)
Licences: Driver's Licence
Education: Bachelor of Science (Statistics), Australian National University, 2016
Proud mum of three."""


def profile(**over: object) -> CvProfile:
    base = {
        "headline": None,
        "summary": None,
        "work_history": [
            {
                "title": "Senior Data Analyst",
                "employer": "Molonglo Analytics",
                "start": "2021-03",
                "end": "present",
                "highlights": [],
            }
        ],
        "education": [
            {
                "qualification": "Bachelor of Science (Statistics)",
                "institution": "Australian National University",
                "end": "2016",
            }
        ],
        "skills": ["SQL", "Tableau", "Python"],
        "certifications": [{"name": "AWS Certified Developer", "year": 2019}],
        "licences": ["Driver's Licence"],
        "personal_spans": [{"text": "Proud mum of three.", "kind": "marital_or_family"}],
    }
    base.update(over)
    return CvProfile.model_validate(base)


def test_valid_profile_passes() -> None:
    check_profile(profile(), TEXT)


@pytest.mark.parametrize(
    ("over", "msg"),
    [
        ({"skills": ["SQL", "Quantum Computing"]}, "skill 'Quantum Computing'"),
        (
            {
                "work_history": [
                    {
                        "title": "CEO",
                        "employer": "Google DeepMind",
                        "start": "2021-03",
                        "end": "present",
                    }
                ]
            },
            "not in the CV",
        ),
        (
            {
                "work_history": [
                    {
                        "title": "Senior Data Analyst",
                        "employer": "Molonglo Analytics",
                        "start": "March 2021",
                        "end": "present",
                    }
                ]
            },
            "YYYY-MM",
        ),
        (
            {
                "work_history": [
                    {
                        "title": "Senior Data Analyst",
                        "employer": "Molonglo Analytics",
                        "start": "2023-01",
                        "end": "2021-01",
                    }
                ]
            },
            "starts after",
        ),
        ({"personal_spans": [{"text": "Never said this", "kind": "health"}]}, "personal span"),
    ],
)
def test_values_must_come_from_the_cv(over: dict[str, object], msg: str) -> None:
    with pytest.raises(ValueError, match=msg):
        check_profile(profile(**over), TEXT)


def test_kind_near_misses_map_to_allowed_kinds() -> None:
    assert PersonalSpan(text="x y", kind="marital_status").kind == "marital_or_family"  # type: ignore[arg-type]
    assert PersonalSpan(text="x y", kind="family_status").kind == "marital_or_family"  # type: ignore[arg-type]
    assert PersonalSpan(text="x y", kind="Date of Birth").kind == "dob"  # type: ignore[arg-type]
    assert PersonalSpan(text="x y", kind="something odd").kind == "other_personal"  # type: ignore[arg-type]


def test_schema_sent_to_model_requires_every_field() -> None:
    """Regression: DeepSeek skipped optional list fields (skills came back empty)."""
    schema = strict_json_schema(CvProfile)
    assert set(schema["required"]) == set(schema["properties"])
    role = schema["$defs"]["Role"]
    assert set(role["required"]) == set(role["properties"])
    assert all("default" not in p for p in schema["properties"].values())


def test_empty_profile_is_invalid() -> None:
    """Regression: an empty profile passed every check because there was nothing to check."""
    empty = profile(
        work_history=[], education=[], skills=[], certifications=[], licences=[], personal_spans=[]
    )
    with pytest.raises(ValueError, match="profile is empty"):
        check_profile(empty, TEXT)


def test_study_year_given_as_a_number_is_accepted() -> None:
    p = profile(
        education=[
            {
                "qualification": "Bachelor of Science (Statistics)",
                "institution": "Australian National University",
                "end": 2016,
            }
        ]
    )
    assert p.education[0].end == "2016"
