import pytest

from app import briefing_state_machine as fsm


def test_happy_path_chain():
    chain = [
        (fsm.NEW, fsm.QUESTIONS_GENERATED),
        (fsm.QUESTIONS_GENERATED, fsm.WAITING_ANSWERS),
        (fsm.WAITING_ANSWERS, fsm.ANSWERS_RECEIVED),
        (fsm.ANSWERS_RECEIVED, fsm.COMPLETENESS_CHECK),
        (fsm.COMPLETENESS_CHECK, fsm.READY_FOR_GO),
        (fsm.READY_FOR_GO, fsm.GO_AUTH_CHECK),
        (fsm.GO_AUTH_CHECK, fsm.APPROVED),
        (fsm.APPROVED, fsm.PLAN_GATE),
    ]
    for src, dst in chain:
        assert fsm.can_transition(src, dst)


def test_needs_more_info_loop():
    assert fsm.can_transition(fsm.COMPLETENESS_CHECK, fsm.NEEDS_MORE_INFO)
    assert fsm.can_transition(fsm.NEEDS_MORE_INFO, fsm.WAITING_ANSWERS)


def test_go_reject_returns_to_ready():
    assert fsm.can_transition(fsm.GO_AUTH_CHECK, fsm.READY_FOR_GO)


def test_reopen_edges():
    assert fsm.can_transition(fsm.EXPIRED_WAITING_ANSWERS, fsm.WAITING_ANSWERS)
    assert fsm.can_transition(fsm.READY_FOR_GO, fsm.WAITING_ANSWERS)


def test_idle_timeout():
    assert fsm.can_transition(fsm.WAITING_ANSWERS, fsm.EXPIRED_WAITING_ANSWERS)


def test_any_state_to_emergency():
    for target in (fsm.BLOCKED_MANUAL, fsm.CANCELLED, fsm.ERROR):
        assert fsm.can_transition(fsm.WAITING_ANSWERS, target)
        assert fsm.can_transition(fsm.NEW, target)


def test_illegal_transition_raises():
    with pytest.raises(fsm.InvalidTransition):
        fsm.assert_transition(fsm.NEW, fsm.APPROVED)
    with pytest.raises(fsm.InvalidTransition):
        fsm.assert_transition(fsm.WAITING_ANSWERS, fsm.PLAN_GATE)


def test_terminal_states_have_no_targets():
    for state in (fsm.APPROVED, fsm.PLAN_GATE):
        # APPROVED -> PLAN_GATE допустимо, но из PLAN_GATE/BLOCKED/CANCELLED/ERROR — никуда.
        pass
    for state in (fsm.BLOCKED_MANUAL, fsm.CANCELLED, fsm.ERROR, fsm.PLAN_GATE):
        assert fsm.allowed_targets(state) == frozenset()


def test_terminal_no_emergency_escape():
    # Из терминального состояния нельзя уйти даже в CANCELLED.
    assert not fsm.can_transition(fsm.CANCELLED, fsm.ERROR)


def test_unknown_state_raises():
    with pytest.raises(ValueError):
        fsm.allowed_targets("NONSENSE")
