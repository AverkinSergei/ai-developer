"""Конечный автомат брифинга. Переходы валидирует сервер; модель только предлагает.

Любой недопустимый переход — InvalidTransition. Применение перехода (мутация
записи + запись в audit) — задача стора/оркестратора, здесь только правила.
"""

from typing import Final

# Состояния.
NEW: Final = "NEW"
QUESTIONS_GENERATED: Final = "QUESTIONS_GENERATED"
WAITING_ANSWERS: Final = "WAITING_ANSWERS"
ANSWERS_RECEIVED: Final = "ANSWERS_RECEIVED"
COMPLETENESS_CHECK: Final = "COMPLETENESS_CHECK"
NEEDS_MORE_INFO: Final = "NEEDS_MORE_INFO"
READY_FOR_GO: Final = "READY_FOR_GO"
GO_AUTH_CHECK: Final = "GO_AUTH_CHECK"
APPROVED: Final = "APPROVED"
PLAN_GATE: Final = "PLAN_GATE"
EXPIRED_WAITING_ANSWERS: Final = "EXPIRED_WAITING_ANSWERS"
BLOCKED_MANUAL: Final = "BLOCKED_MANUAL"
CANCELLED: Final = "CANCELLED"
ERROR: Final = "ERROR"

ALL_STATES: Final[frozenset[str]] = frozenset(
    {
        NEW,
        QUESTIONS_GENERATED,
        WAITING_ANSWERS,
        ANSWERS_RECEIVED,
        COMPLETENESS_CHECK,
        NEEDS_MORE_INFO,
        READY_FOR_GO,
        GO_AUTH_CHECK,
        APPROVED,
        PLAN_GATE,
        EXPIRED_WAITING_ANSWERS,
        BLOCKED_MANUAL,
        CANCELLED,
        ERROR,
    }
)

# Полностью закрытые состояния: новый сеанс для задачи не создаётся, переходов нет.
# EXPIRED_WAITING_ANSWERS сюда НЕ входит — он возобновляем (/briefing reopen),
# поэтому продолжает блокировать создание второго сеанса.
TERMINAL: Final[frozenset[str]] = frozenset({APPROVED, PLAN_GATE, BLOCKED_MANUAL, CANCELLED, ERROR})

# Из любого состояния доступны аварийные/управляющие переходы.
_ANY_TARGETS: Final[frozenset[str]] = frozenset({BLOCKED_MANUAL, CANCELLED, ERROR})

# Явные рёбра.
_EDGES: Final[dict[str, frozenset[str]]] = {
    NEW: frozenset({QUESTIONS_GENERATED, COMPLETENESS_CHECK}),
    QUESTIONS_GENERATED: frozenset({WAITING_ANSWERS}),
    WAITING_ANSWERS: frozenset({ANSWERS_RECEIVED, EXPIRED_WAITING_ANSWERS}),
    ANSWERS_RECEIVED: frozenset({COMPLETENESS_CHECK}),
    COMPLETENESS_CHECK: frozenset({NEEDS_MORE_INFO, READY_FOR_GO}),
    NEEDS_MORE_INFO: frozenset({WAITING_ANSWERS}),
    READY_FOR_GO: frozenset({GO_AUTH_CHECK, WAITING_ANSWERS}),  # reopen -> WAITING_ANSWERS
    GO_AUTH_CHECK: frozenset({APPROVED, READY_FOR_GO}),  # reject -> ждём валидный /go
    APPROVED: frozenset({PLAN_GATE}),
    PLAN_GATE: frozenset(),
    EXPIRED_WAITING_ANSWERS: frozenset({WAITING_ANSWERS}),  # reopen
    BLOCKED_MANUAL: frozenset(),
    CANCELLED: frozenset(),
    ERROR: frozenset(),
}


class InvalidTransition(Exception):
    def __init__(self, src: str, dst: str) -> None:
        super().__init__(f"Недопустимый переход брифинга: {src} -> {dst}")
        self.src = src
        self.dst = dst


def allowed_targets(state: str) -> frozenset[str]:
    if state not in ALL_STATES:
        raise ValueError(f"Неизвестное состояние: {state}")
    targets = _EDGES[state]
    # Из терминальных состояний аварийные переходы недоступны.
    if state in TERMINAL:
        return targets
    return targets | _ANY_TARGETS


def can_transition(src: str, dst: str) -> bool:
    return dst in allowed_targets(src)


def assert_transition(src: str, dst: str) -> None:
    if not can_transition(src, dst):
        raise InvalidTransition(src, dst)
