"""Независимый AI-review диффа.

Ревьюер получает только задачу, acceptance criteria, diff, результаты тестов и
docs — но НЕ внутренний ход рассуждений Coder Agent. Нераспознанный вывод модели
трактуется fail-closed как NEED_HUMAN_REVIEW (блокирует merge).
"""

import json

from app.clients.protocols import LLMClient
from app.contracts import AIReviewVerdict, TaskCard

_REVIEW_SYSTEM = (
    "Ты независимый ревьюер кода. Проверь соответствие требованиям и acceptance "
    "criteria, edge cases, тесты, архитектурные ограничения, документацию и лишние "
    "изменения вне scope. Верни JSON {verdict, comments:[{file,line,severity,body}]}. "
    "verdict: PASS|PASS_WITH_NOTES|FAIL|NEED_HUMAN_REVIEW. severity: low|medium|high|blocker."
)

_FAIL_CLOSED = AIReviewVerdict(
    verdict="NEED_HUMAN_REVIEW",
    comments=[],
)


async def review_diff(
    card: TaskCard,
    diff: str,
    test_results: str,
    docs: str,
    llm: LLMClient,
) -> AIReviewVerdict:
    payload = json.dumps(
        {
            "task_type": card.task_type,
            "acceptance_criteria": card.acceptance_criteria,
            "diff": diff,
            "test_results": test_results,
            "docs": docs,
        },
        ensure_ascii=False,
    )
    resp = await llm.complete(
        system=_REVIEW_SYSTEM, messages=[{"role": "user", "content": payload}]
    )
    try:
        data = json.loads(resp.text)
        return AIReviewVerdict(**data)
    except (json.JSONDecodeError, TypeError, ValueError):
        return _FAIL_CLOSED


def autofixable(verdict: AIReviewVerdict) -> list:
    """Замечания, которые Coder может попытаться исправить (не блокеры по людям)."""
    if verdict.verdict == "NEED_HUMAN_REVIEW":
        return []
    return [c for c in verdict.comments if c.severity in ("high", "blocker")]
