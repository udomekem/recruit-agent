"""Answer scorer, form input rules and the score formula (phase 3 design sections 3 and 4)."""

from typing import Any

import pytest

from app.domain.questions import coerce_answer, standard_questions
from app.scoring.answers import QuestionInput, score_answers
from app.scoring.formula import score_card, total_score

BAND_MAX = 120_000


def qs(**values: Any) -> list[QuestionInput]:
    out = []
    for spec in standard_questions("Sydney", "hybrid"):
        rule = spec.knockout_rule.model_dump() if spec.knockout_rule else None
        out.append(
            QuestionInput(spec.key, spec.prompt, spec.answer_type.value, rule, values.get(spec.key))
        )
    return out


GOOD = {
    "right_to_work": True,
    "expected_salary": 110_000,
    "notice_period": "1 to 2 weeks",
    "location_fit": "yes",
    "current_role": "Analyst",
}


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("95000", 95000),
        ("$95,000", 95000),
        ("95k", 95000),
        ("95K AUD", 95000),
        (95000, 95000),
        ("$95k to $110k", {"min": 95000, "max": 110000, "text": "$95k to $110k"}),
        ("95,000 - 110,000", {"min": 95000, "max": 110000, "text": "95,000 - 110,000"}),
        ("95 to 110k", {"min": 95000, "max": 110000, "text": "95 to 110k"}),
    ],
)
def test_salary_inputs_accepted(raw: Any, expected: Any) -> None:
    assert coerce_answer("number", None, raw) == expected


@pytest.mark.parametrize("raw", ["negotiable", "market rate", "110k to 95k", "-5"])
def test_salary_inputs_refused(raw: str) -> None:
    with pytest.raises(ValueError):
        coerce_answer("number", None, raw)


@pytest.mark.parametrize("raw", ["PR pending", "applying", "maybe", "soon"])
def test_right_to_work_must_be_a_clear_yes_or_no(raw: str) -> None:
    with pytest.raises(ValueError, match="yes or no"):
        coerce_answer("yes_no", None, raw)


def outcomes(**values: Any) -> dict[str, str]:
    return {a.key: a.outcome for a in score_answers(qs(**values), salary_max=BAND_MAX)}


def test_good_answers_pass_and_free_text_is_not_scored() -> None:
    o = outcomes(**GOOD)
    assert o == {
        "right_to_work": "pass",
        "expected_salary": "pass",
        "notice_period": "not_scored",
        "location_fit": "pass",
        "current_role": "not_scored",
    }


def test_knockouts() -> None:
    assert outcomes(**{**GOOD, "right_to_work": False})["right_to_work"] == "fail"
    assert outcomes(**{**GOOD, "expected_salary": 130_000})["expected_salary"] == "flag"
    assert outcomes(**{**GOOD, "expected_salary": 120_000})["expected_salary"] == "pass"
    assert outcomes(**{**GOOD, "location_fit": "no"})["location_fit"] == "flag"
    assert outcomes(**{**GOOD, "location_fit": "yes with relocation"})["location_fit"] == "pass"


def test_salary_range_uses_the_lower_end() -> None:
    within = {"min": 115_000, "max": 135_000, "text": "115k to 135k"}
    above = {"min": 125_000, "max": 140_000, "text": "125k to 140k"}
    assert outcomes(**{**GOOD, "expected_salary": within})["expected_salary"] == "pass"
    res = score_answers(qs(**{**GOOD, "expected_salary": above}), salary_max=BAND_MAX)
    salary = next(a for a in res if a.key == "expected_salary")
    assert salary.outcome == "flag" and "125k to 140k" in salary.note


def test_bulk_upload_has_no_answers() -> None:
    assert set(outcomes().values()) == {"not_answered"}


CRITERIA = [
    {"id": "sql", "kind": "must_have", "text": "SQL", "weight": 5},
    {"id": "python", "kind": "must_have", "text": "Python", "weight": 4},
    {"id": "bi", "kind": "nice_to_have", "text": "Power BI", "weight": 2},
    {"id": "cloud", "kind": "nice_to_have", "text": "Cloud", "weight": 1},
]


def answers(**over: Any) -> Any:
    return score_answers(qs(**{**GOOD, **over}), salary_max=BAND_MAX)


def test_total_is_weighted_points() -> None:
    v = {"sql": "met", "python": "partly_met", "bi": "not_met", "cloud": "met"}
    # (5*100 + 4*50 + 0 + 1*100) / 12 = 66.666...
    assert total_score(CRITERIA, v) == 66.7


def test_changing_a_weight_moves_the_total_exactly() -> None:
    v = {"sql": "met", "python": "partly_met", "bi": "not_met", "cloud": "met"}
    heavier = [dict(c, weight=2) if c["id"] == "bi" else c for c in CRITERIA]
    lighter = [dict(c, weight=1) if c["id"] == "bi" else c for c in CRITERIA]
    assert total_score(heavier, v) == round(800 / 12, 1)
    assert total_score(lighter, v) == round(800 / 11, 1)


def test_bands() -> None:
    all_met = dict.fromkeys(["sql", "python", "bi", "cloud"], "met")
    assert score_card(CRITERIA, all_met, answers()).band == "advance"

    must_missed = {**all_met, "python": "not_met"}  # (5+2+1)*100/12 = 66.7
    card = score_card(CRITERIA, must_missed, answers())
    assert card.band == "maybe" and "Must have not met: Python" in card.reasons

    weak = {"sql": "partly_met", "python": "not_met", "bi": "met", "cloud": "not_met"}
    assert score_card(CRITERIA, weak, answers()).band == "reject"  # 37.5


def test_must_have_missed_with_a_high_total_is_maybe() -> None:
    crit = [
        {"id": "a", "kind": "must_have", "text": "A", "weight": 5},
        {"id": "b", "kind": "must_have", "text": "B", "weight": 5},
        {"id": "c", "kind": "must_have", "text": "C", "weight": 5},
        {"id": "d", "kind": "must_have", "text": "D", "weight": 3},
    ]
    v = {"a": "met", "b": "met", "c": "met", "d": "not_met"}  # 83.3
    card = score_card(crit, v, answers())
    assert card.total > 75 and card.band == "maybe"


def test_no_right_to_work_rejects_whatever_the_score() -> None:
    all_met = dict.fromkeys(["sql", "python", "bi", "cloud"], "met")
    card = score_card(CRITERIA, all_met, answers(right_to_work=False))
    assert card.total == 100.0 and card.band == "reject"
    assert card.reasons[0] == "No right to work in Australia (application answer)"


def test_flags_show_but_do_not_change_the_band() -> None:
    all_met = dict.fromkeys(["sql", "python", "bi", "cloud"], "met")
    card = score_card(
        CRITERIA,
        all_met,
        answers(expected_salary=150_000, location_fit="no"),
        injection_suspected=True,
        hidden_chars=42,
    )
    assert card.band == "advance"
    kinds = {f.kind for f in card.flags}
    assert kinds == {"salary_above_band", "location_no", "injection_suspected", "hidden_text"}


def test_missing_answers_hold_a_strong_cv_at_maybe() -> None:
    all_met = dict.fromkeys(["sql", "python", "bi", "cloud"], "met")
    card = score_card(CRITERIA, all_met, score_answers(qs(), salary_max=BAND_MAX))
    assert card.band == "maybe"
    assert any(f.kind == "answers_missing" for f in card.flags)
    weak = dict.fromkeys(["sql", "python", "bi", "cloud"], "not_met")
    assert score_card(CRITERIA, weak, score_answers(qs(), salary_max=BAND_MAX)).band == "reject"
