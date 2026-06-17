"""Классификация репозиториев задачи: где нужны изменения (MR), а где только контекст.

Бот сверяет постановку с указанными постановщиком списками и возвращает несоответствия.
Результат — advisory: он не меняет молча scope (это решение человека), а публикуется
комментарием в задачу. Нераспознанный вывод модели трактуется как «без несоответствий».
"""

import json
from dataclasses import dataclass, field

from app.clients.protocols import LLMClient
from app.contracts import TaskCard

_SYSTEM = (
    "Ты анализируешь постановку задачи и список репозиториев. Определи, в каких репозиториях "
    "нужны изменения (MR), а какие нужны только как контекст (read-only). Сверь со списками, "
    "указанными постановщиком, и перечисли несоответствия. Верни JSON "
    "{change_repos:[], context_repos:[], mismatches:[]}. mismatches — короткие строки: "
    "репозиторий помечен как контекст, но требует изменений; помечен под изменения, но не "
    "затрагивается; упомянут в цели, но не указан в списках."
)


@dataclass
class RepoClassification:
    change_repos: list[str] = field(default_factory=list)
    context_repos: list[str] = field(default_factory=list)
    mismatches: list[str] = field(default_factory=list)


async def classify_repos(card: TaskCard, llm: LLMClient) -> RepoClassification:
    payload = json.dumps(
        {
            "business_goal": card.business_goal,
            "acceptance_criteria": card.acceptance_criteria,
            "stated_change_repos": card.all_repos,
            "stated_context_repos": card.context_only_repos,
        },
        ensure_ascii=False,
    )
    resp = await llm.complete(system=_SYSTEM, messages=[{"role": "user", "content": payload}])
    try:
        data = json.loads(resp.text)
    except (json.JSONDecodeError, TypeError):
        return RepoClassification()
    if not isinstance(data, dict):
        return RepoClassification()
    return RepoClassification(
        change_repos=[str(r) for r in data.get("change_repos", [])],
        context_repos=[str(r) for r in data.get("context_repos", [])],
        mismatches=[str(m) for m in data.get("mismatches", [])],
    )
