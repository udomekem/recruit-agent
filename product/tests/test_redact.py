"""Redaction steps 1 to 6 (no model)."""

from app.intake.redact import final_redact, normalise, pre_redact

CV = """Imogen Quillfeather-Hale
Senior Business Analyst
12 Wattle Street, Parramatta NSW
2150
Phone: 0491 570 101 | Email: imogen.q@example.test | linkedin.com/in/imogenq
Personal Details
Date of birth: 14/03/1986
Gender: Female
Marital status: Married
Visa: Permanent resident, full work rights
Profile
Proud mum of three. QUILLFEATHER-HALE, Imogen is my legal name order.
Experience
Senior Business Analyst, Christian Brothers College
Mar 2021 to Present
Skills
SQL, Rose Gardening Systems, Hunter Valley logistics
Referees
Desmond Varga, Operations Manager, 0491 570 299
Bartholomew Cardew, 0412 345 678
"""


def red() -> str:
    return pre_redact(
        CV, name="Imogen Quillfeather-Hale", email="imogen.q@example.test", phone="+61 491 570 101"
    ).text


def test_known_identifiers_removed() -> None:
    t = red()
    assert "Imogen" not in t and "Quillfeather" not in t and "QUILLFEATHER" not in t
    assert "imogen.q@example.test" not in t
    assert "570 101" not in t and "0491570101" not in t.replace(" ", "")


def test_patterns_removed_even_across_line_breaks() -> None:
    t = red()
    assert "Wattle Street" not in t and "Parramatta" not in t and "2150" not in t
    assert "linkedin.com" not in t
    assert "14/03/1986" not in t


def test_protected_lines_keep_label_drop_value() -> None:
    t = red()
    assert "Gender: [PROTECTED]" in t and "Female" not in t
    assert "Marital status: [PROTECTED]" in t and "Married" not in t


def test_referees_section_dropped() -> None:
    t = red()
    assert "[REFERENCES REMOVED]" in t
    assert "Desmond Varga" not in t and "0412 345 678" not in t and "Cardew" not in t


def test_job_relevant_words_kept() -> None:
    t = red()
    for keep in [
        "Senior Business Analyst",
        "Christian Brothers College",
        "SQL",
        "Rose Gardening Systems",
        "Hunter Valley logistics",
        "Mar 2021 to Present",
        "Permanent resident, full work rights",
    ]:
        assert keep in t, keep


def test_counts_recorded() -> None:
    r = pre_redact(
        CV, name="Imogen Quillfeather-Hale", email="imogen.q@example.test", phone="0491 570 101"
    )
    assert r.counts["[NAME]"] >= 2 and r.counts["[EMAIL]"] == 1 and r.counts["[PROTECTED]"] >= 2
    assert r.counts["[REFERENCES REMOVED]"] == 1


def test_free_text_needs_the_model_step() -> None:
    cv = CV.replace(
        "Experience\n",
        "I manage my ADHD with routines that make me very organised.\nExperience\n",
        1,
    )
    pre = pre_redact(cv, name="Imogen Quillfeather-Hale", email=None, phone=None)
    assert "Proud mum of three" not in pre.text  # common family phrasing: removed by code
    assert "my ADHD" in pre.text  # free text health statement: code cannot know this
    final = final_redact(
        pre,
        [
            ("I manage my ADHD with routines that make me very organised.", "health"),
            ("Gender: [PROTECTED]", "gender"),
        ],
    )
    assert "ADHD" not in final.text
    assert "Gender: [PROTECTED]" in final.text  # placeholder spans are skipped


def test_other_patterns() -> None:
    t = pre_redact(
        "Call (02) 9876 5432 or +44 20 7946 0958. Born on 2 June 1979. Age: 41. "
        "See https://example.test/me and github.com/someone",
        name=None,
        email=None,
        phone=None,
    ).text
    for gone in ["9876 5432", "7946 0958", "2 June 1979", "Age: 41", "https://", "github.com"]:
        assert gone not in t, gone


def test_normalise() -> None:
    assert normalise("Torrens & Gilbert Pty. Ltd.") == normalise("torrens  &  gilbert pty ltd")


def test_family_statements_removed_by_code() -> None:
    """Regression: the model missed 'Proud mum of three' in 1 of 3 eval runs."""
    for text in [
        "Proud mum of three, I balance family life with my career.",
        "Husband and father of two young boys.",
        "Single dad who loves coaching.",
        "Married with two kids.",
    ]:
        out = pre_redact(f"Profile\n{text}\nSkills\nSQL", name=None, email=None, phone=None).text
        assert "[PROTECTED]" in out and "SQL" in out, (text, out)
    keep = (
        "Mentored a team of three analysts. Father's Day campaign lead. "
        "Mother Duck Childcare (employer)."
    )
    assert pre_redact(keep, name=None, email=None, phone=None).text == keep


def test_qualifications_and_employers_with_a_state_and_year_are_kept() -> None:
    """Regression (phase 4 demo seed): "TAFE NSW, 2012" looked like a suburb and postcode."""
    for line in [
        "Certificate IV in Building and Construction, TAFE NSW, 2012",
        "Diploma of Nursing, TAFE Queensland QLD 2015",
        "Graduate Nurse, Health NSW 2021",
        "Data Officer, Transport for NSW 2019 to 2022",
        "Bachelor of Commerce, Charles Sturt University NSW 2014",
    ]:
        out = pre_redact(line, name=None, email=None, phone=None).text
        assert out == line, (line, out)
    for home in ["Parramatta NSW 2150", "Blacktown NSW, 2148", "South Yarra VIC 3141"]:
        out = pre_redact(f"Lives at {home}", name=None, email=None, phone=None).text
        assert "[ADDRESS]" in out and home.split()[0] not in out, (home, out)
