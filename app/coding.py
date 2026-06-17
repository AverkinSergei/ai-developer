"""Генерация кода/документации по плану и локальный self-check.

Запрещено отключать тесты, менять thresholds или удалять security-проверки —
такие действия не входят в автоматический контур.
"""

import json
from dataclasses import dataclass, field

from app.clients.protocols import LLMClient
from app.context_engine import is_safe_repo_path
from app.contracts import RiskPlanGate, TaskCard

_CODE_SYSTEM = (
    "Ты генерируешь изменения по утверждённому плану. Верни JSON-объект "
    "{путь: содержимое_файла} только для action create|update. Публичные функции/классы "
    "снабжай docstring. Не добавляй файлы вне плана."
)


@dataclass
class CodingResult:
    files: dict[str, str] = field(default_factory=dict)
    deletions: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


def self_check(files: dict[str, str], gate: RiskPlanGate) -> list[str]:
    """Сверка сгенерированного с планом: покрытие и отсутствие лишних файлов."""
    planned = {c.path for c in gate.changes if c.action in ("create", "update")}
    produced = set(files)
    issues: list[str] = []
    missing = planned - produced
    extra = produced - planned
    if missing:
        issues.append(f"missing planned files: {sorted(missing)}")
    if extra:
        issues.append(f"unplanned files: {sorted(extra)}")
    empty = [p for p, c in files.items() if not c.strip()]
    if empty:
        issues.append(f"empty files: {sorted(empty)}")
    unsafe = [p for p in produced if not is_safe_repo_path(p)]
    if unsafe:
        issues.append(f"unsafe paths: {sorted(unsafe)}")
    return issues


async def generate_changes(card: TaskCard, gate: RiskPlanGate, llm: LLMClient) -> CodingResult:
    targets = [c for c in gate.changes if c.action in ("create", "update")]
    deletions = [c.path for c in gate.changes if c.action == "delete"]

    prompt = json.dumps(
        {
            "task_id": card.task_id,
            "acceptance_criteria": card.acceptance_criteria,
            "changes": [
                {"path": c.path, "action": c.action, "rationale": c.rationale} for c in targets
            ],
        },
        ensure_ascii=False,
    )
    resp = await llm.complete(system=_CODE_SYSTEM, messages=[{"role": "user", "content": prompt}])
    try:
        files = json.loads(resp.text)
        if not isinstance(files, dict):
            files = {}
    except (json.JSONDecodeError, TypeError):
        files = {}

    files = {str(k): str(v) for k, v in files.items()}
    issues = self_check(files, gate)
    return CodingResult(files=files, deletions=deletions, issues=issues)
