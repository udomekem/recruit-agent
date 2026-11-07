"""Pure tests of the transition table (no database)."""

import itertools

from app.domain.states import (
    DECISION_POINTS,
    NON_TERMINAL,
    SYSTEM_STEPS,
    TERMINAL,
    TRANSITIONS,
    ActorType,
    CandidateState,
    find_transition,
)

S = CandidateState
LEGAL = {
    (t.from_state, t.to_state, t.actor) for t in TRANSITIONS if t.to_state != "RETURN_TO_SAVED"
}


def test_every_illegal_pair_is_refused() -> None:
    """Generated from the table: every (from, to, actor) not listed must be refused."""
    refused = 0
    for from_state, to_state, actor in itertools.product([None, *S], list(S), list(ActorType)):
        if (from_state, to_state, actor) in LEGAL:
            assert find_transition(from_state, to_state, actor) is not None
            continue
        # resolve-retry (T20) is legal only to the saved state; with no saved state it is refused
        assert find_transition(from_state, to_state, actor) is None, (from_state, to_state, actor)
        refused += 1
    assert refused > 500  # 18 x 17 x 2 = 612 combinations minus the legal ones


def test_terminal_states_have_no_exits() -> None:
    for t in TRANSITIONS:
        assert t.from_state not in TERMINAL


def test_decision_points_have_no_system_exit_except_failure_rules() -> None:
    """The worker can never pass a recruiter decision point on its own."""
    for t in TRANSITIONS:
        if t.from_state in {S.SCORED, S.SCREEN_SCORED, S.REJECTION_DRAFTED}:
            assert t.actor == ActorType.RECRUITER or t.to_state == S.NEEDS_REVIEW, t
    for state in DECISION_POINTS:
        assert state not in SYSTEM_STEPS


def test_resolve_retry_goes_only_to_the_saved_state() -> None:
    assert find_transition(S.NEEDS_REVIEW, S.PARSED, ActorType.RECRUITER, S.PARSED) is not None
    assert find_transition(S.NEEDS_REVIEW, S.SCORED, ActorType.RECRUITER, S.PARSED) is None


def test_withdraw_allowed_from_every_non_terminal_state() -> None:
    for s in NON_TERMINAL:
        assert find_transition(s, S.WITHDRAWN, ActorType.RECRUITER) is not None
        assert find_transition(s, S.WITHDRAWN, ActorType.SYSTEM) is None


def test_every_system_step_state_can_fail_into_review() -> None:
    for s in SYSTEM_STEPS:
        assert find_transition(s, S.NEEDS_REVIEW, ActorType.SYSTEM) is not None, s


def test_transition_ids_unique_per_pair() -> None:
    pairs = [(t.from_state, t.to_state, t.actor) for t in TRANSITIONS]
    assert len(pairs) == len(set(pairs))
