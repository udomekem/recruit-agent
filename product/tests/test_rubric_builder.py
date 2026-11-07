"""Code checks on the rubric builder's output (no model)."""

import pytest

from app.agents.rubric_builder import RubricDraft, check_rubric
from tests.phase1_helpers import AD, RUBRIC


def draft(**over: object) -> RubricDraft:
    return RubricDraft.model_validate({**RUBRIC, **over})


def crit(i: int = 0, **over: object) -> dict[str, object]:
    return {**RUBRIC["criteria"][i], **over}


def test_valid_rubric_passes() -> None:
    check_rubric(draft(), AD)


def test_evidence_must_be_in_the_ad_whitespace_and_case_ignored() -> None:
    check_rubric(
        draft(criteria=[crit(evidence="at least 3 years of   experience as a business analyst")]),
        AD,
    )
    with pytest.raises(ValueError, match="exact quote"):
        check_rubric(draft(criteria=[crit(evidence="10 years of Python")]), AD)


def test_weights_follow_kind() -> None:
    with pytest.raises(ValueError, match="weight"):
        check_rubric(draft(criteria=[crit(weight=2)]), AD)
    with pytest.raises(ValueError, match="weight"):
        check_rubric(draft(criteria=[crit(0), crit(3, weight=4)]), AD)


def test_needs_a_must_have_and_unique_ids() -> None:
    with pytest.raises(ValueError, match="must_have"):
        check_rubric(draft(criteria=[crit(3)]), AD)
    with pytest.raises(ValueError, match="unique"):
        check_rubric(draft(criteria=[crit(0), crit(1, id="ba_experience")]), AD)


def test_protected_wording_blocked_even_if_model_produces_it() -> None:
    with pytest.raises(ValueError, match="protected attribute"):
        check_rubric(draft(criteria=[crit(text="Young, under 30, energetic")]), AD)


def test_flag_quotes_must_be_in_the_ad() -> None:
    flags = [{"quote": "only men", "concern": "sex_or_gender", "suggestion": "remove"}]
    with pytest.raises(ValueError, match="flag quote"):
        check_rubric(draft(flags=flags), AD)


def test_all_problems_reported_together() -> None:
    with pytest.raises(ValueError) as exc:
        check_rubric(draft(criteria=[crit(weight=1, evidence="nope", text="young")]), AD)
    msg = str(exc.value)
    assert "weight" in msg and "exact quote" in msg and "protected" in msg
