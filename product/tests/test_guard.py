"""The protected attribute guard: blocks what it must, and only that."""

import json
from pathlib import Path

import pytest

from app.domain.guard import find_protected_terms

BLOCK = [
    "Join our young, energetic team",
    "Would suit someone under 30",
    "Native English speaker",
    "Female applicants preferred",
    "No family commitments",
    "Recent graduates only",
    "Mature aged candidates welcome",
    "Must not be pregnant",
    "Christian values essential",
    "Able-bodied workers only",
    "Single applicants preferred",
    "aged 25 to 35",
]

ALLOW = [
    "At least 5 years of experience as a Business Analyst",
    "Over 10 years of experience in payroll",
    "Single Touch Payroll (STP) reporting",
    "Native mobile development (iOS and Android)",
    "Experience working with young people",
    "Excellent written English",
    "Australian citizenship and a Baseline security clearance",
    "Right to work in Australia",
    "A current White Card (construction induction)",
    "Leading a team of 15 pickers and packers",
    "40,000 square metre distribution centre",
    "Available until 7pm on Tuesdays and Thursdays",
    "Postgraduate qualification in emergency nursing",
]


@pytest.mark.parametrize("text", BLOCK)
def test_blocks_protected_wording(text: str) -> None:
    assert find_protected_terms(text), text


@pytest.mark.parametrize("text", ALLOW)
def test_allows_lawful_wording(text: str) -> None:
    assert find_protected_terms(text) == [], text


def test_must_have_phrases_in_the_eval_labels_never_trip_the_guard() -> None:
    """Every accepted phrasing in rubric-v1 must be usable as a criterion."""
    path = Path(__file__).resolve().parents[1] / "evals/datasets/rubric-v1.jsonl"
    for line in path.read_text().splitlines():
        case = json.loads(line)
        for group in ("must_haves", "nice_to_haves"):
            for crit in case["expected"][group]:
                for phrase in crit["phrases"]:
                    assert find_protected_terms(phrase) == [], (case["id"], phrase)
