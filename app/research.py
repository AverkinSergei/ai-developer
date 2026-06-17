"""Research-контур: markdown-отчёт в задачу Битрикс24. Без ветки и MR."""

from app.clients.protocols import BitrixClient, LLMClient
from app.contracts import TaskCard

_RESEARCH_SYSTEM = (
    "Ты проводишь исследование по задаче разработки. Сформируй markdown-отчёт: выводы, "
    "риски, варианты решений и рекомендацию. Если нужны актуальные внешние данные — "
    "фиксируй источник. Не выдумывай факты."
)


async def run_research(card: TaskCard, llm: LLMClient, bitrix: BitrixClient) -> str:
    """Готовит отчёт и публикует его в задачу. Возвращает текст отчёта."""
    prompt = (
        f"Задача: {card.business_goal}\n"
        f"Критерии достаточности: {card.acceptance_criteria}\n"
        f"Контекст: {', '.join(card.context_keywords)}"
    )
    resp = await llm.complete(
        system=_RESEARCH_SYSTEM, messages=[{"role": "user", "content": prompt}]
    )
    report = resp.text
    await bitrix.add_comment(card.task_id, f"[AI_RESEARCH]\n{report}")
    return report
