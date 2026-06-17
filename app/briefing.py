"""Генерация уточняющих вопросов, completeness-проверка и рендер раунда.

Модуль не принимает решений о переходах состояния и правах — только готовит
вопросы и текст. Переходы валидирует FSM, права — go_authorizer.
"""

import json

from app.clients.protocols import LLMClient
from app.contracts import TaskCard

# Шаблонные вопросы по незаполненному полю — fallback без модели.
_FIELD_QUESTIONS: dict[str, str] = {
    "business_goal": "Какова бизнес-цель и ожидаемый результат задачи?",
    "acceptance_criteria": "Какие критерии успешной приёмки?",
    "affected_area": "Какие области затрагиваются (backend/frontend/API/DB/...)?",
    "reviewer": "Кто проводит ревью результата?",
    "target_repo": "В каком репозитории выполняется задача?",
    "target_branch": "Какая базовая ветка?",
    "constraints": (
        "Что нельзя менять и какие интерфейсы критичны и не могут быть изменены без согласования?"
    ),
    "verification": "Как проверить результат — тестовые сценарии?",
}

_GEN_SYSTEM = (
    "Ты ведёшь брифинг задачи разработки. По пробелам в постановке сформулируй "
    "короткие конкретные вопросы (по одному на пробел). Верни JSON-массив строк. "
    "Не задавай вопросов по уже заполненным данным."
)


def template_questions(missing_fields: list[str]) -> list[str]:
    """Вопросы по шаблону для незаполненных полей."""
    return [_FIELD_QUESTIONS.get(f, f"Уточните: {f}") for f in missing_fields]


async def generate_questions(
    card: TaskCard,
    missing_fields: list[str],
    llm: LLMClient | None,
    max_questions: int,
) -> list[str]:
    """Вопросы для текущего раунда. Модель уточняет формулировки, иначе — шаблон."""
    if llm is None:
        return template_questions(missing_fields)[:max_questions]

    resp = await llm.complete(
        system=_GEN_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": (
                    f"task_type={card.task_type}, business_goal={card.business_goal!r}, "
                    f"acceptance_criteria={card.acceptance_criteria!r}, "
                    f"пробелы={missing_fields}"
                ),
            }
        ],
    )
    try:
        questions = json.loads(resp.text)
        if isinstance(questions, list) and questions:
            return [str(q) for q in questions][:max_questions]
    except (json.JSONDecodeError, TypeError):
        pass
    return template_questions(missing_fields)[:max_questions]


def completeness_ready(missing_fields: list[str], open_questions: list[str]) -> bool:
    """READY_FOR_GO достижимо, когда не осталось блокирующих пробелов и вопросов."""
    return not missing_fields and not open_questions


def render_round_comment(
    session_id: str,
    round_label: str,
    questions: list[str],
    status: str = "WAITING_ANSWERS",
) -> str:
    """Текст комментария бота с машинным идентификатором раунда."""
    lines = [
        "[AI_BRIEFING]",
        f"session_id: {session_id}",
        f"round_id: {round_label}",
        f"status: {status}",
        f"Ответьте командой: /briefing answer {round_label}",
    ]
    for i, q in enumerate(questions, start=1):
        lines.append(f"Q{i}: {q}")
    return "\n".join(lines)
