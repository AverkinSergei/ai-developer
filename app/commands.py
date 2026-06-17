"""Разбор управляющих команд из комментариев Битрикс24.

Команды распознаются только в начале строки комментария. Обычный текст командой
не считается — это отдельный источник контекста, не ответ на брифинг.

Пример реального брифинга (комментарии бота и постановщика по очереди):

    [бот, раунд r1]
    [AI_BRIEFING] session_id: brf_1  round_id: r1  status: WAITING_ANSWERS
    Ответьте командой: /briefing answer r1
    Q1: Какой критерий успешной приёмки?
    Q2: Какие роли пользователей должны иметь доступ?
    Q3: Нужна ли интеграция с 1С?

    [постановщик]
    /briefing answer r1
    A1: Успех — пользователь видит статус заказа без перезагрузки страницы.
    A2: Доступ только у менеджера и администратора.

    [постановщик — отказ по нерелевантному вопросу]
    /briefing skip brf_1:r1:q3 интеграция с 1С вне scope

    [бот, уточняющий раунд r2]
    [AI_BRIEFING] session_id: brf_1  round_id: r2  status: WAITING_ANSWERS
    Q1: Где хранить историю смены статусов?

    [постановщик]
    /briefing answer r2
    A1: В отдельной таблице order_status_history.

    [постановщик — проверка состояния и старт]
    /briefing status
    /go

    [участники — команды по ходу работы]
    @ai status                    # узнать фазу и блокеры
    @ai redteam                   # принудительно запустить security-ревью
    @ai fix                       # поправить замечания в MR
    @ai resolve                   # разрешить конфликт MR

    [после READY_FOR_GO, если нужно]
    /briefing reopen уточнили требования к ролям
    /briefing cancel постановка снята
"""

import re

from app.contracts import BriefingCommand

_AI_ACTIONS = {"status", "stop", "retry", "resolve", "fix", "redteam"}


def parse_command(text: str) -> BriefingCommand | None:
    """Возвращает команду по первой строке текста или None."""
    if not text:
        return None
    first = text.strip().splitlines()[0].strip() if text.strip() else ""
    low = first.lower()

    if low == "/go" or low.startswith("/go "):
        return BriefingCommand(kind="go", raw=text)

    if low.startswith("/briefing"):
        return _parse_briefing(first, text)

    if low.startswith("@ai"):
        parts = first.split()
        if len(parts) >= 2 and parts[1].lower() in _AI_ACTIONS:
            return BriefingCommand(kind=f"ai_{parts[1].lower()}", raw=text)
        return None

    return None


def _parse_briefing(first: str, raw: str) -> BriefingCommand | None:
    # /briefing answer <round_id> | status | reopen <reason> | cancel <reason> | skip <qid> <reason>
    m = re.match(r"/briefing\s+(\w+)\s*(.*)", first, re.IGNORECASE)
    if not m:
        return None
    sub = m.group(1).lower()
    rest = m.group(2).strip()

    if sub == "answer":
        round_id = rest.split()[0] if rest else None
        if not round_id:
            return None
        return BriefingCommand(kind="briefing_answer", round_id=round_id, raw=raw)
    if sub == "status":
        return BriefingCommand(kind="briefing_status", raw=raw)
    if sub == "reopen":
        return BriefingCommand(kind="briefing_reopen", args=rest, raw=raw)
    if sub == "cancel":
        return BriefingCommand(kind="briefing_cancel", args=rest, raw=raw)
    if sub == "skip":
        tokens = rest.split(maxsplit=1)
        if not tokens:
            return None
        question_id = tokens[0]
        reason = tokens[1] if len(tokens) > 1 else ""
        return BriefingCommand(kind="briefing_skip", question_id=question_id, args=reason, raw=raw)
    return None
