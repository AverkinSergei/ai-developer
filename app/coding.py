"""Генерация кода/документации с итеративной верификацией.

Цикл: сгенерировать файлы по плану → self-check → записать в checkout → прогнать проверки
репо (lint/typecheck/test) в песочнице → отдать падения модели → повторить до
MAX_CODE_ITERATIONS. Так MR становится верифицированным, а не угаданным. Если проверок нет
или изоляция не подтверждена — MR помечается unverified (его смотрит человек).

Запрещено отключать тесты, менять thresholds или удалять security-проверки.
"""

import json
import os
from dataclasses import dataclass, field

from app.clients.protocols import LLMClient
from app.config import settings
from app.context_engine import is_safe_repo_path
from app.contracts import RiskPlanGate, TaskCard
from app.repo_config import RepoConfig
from app.sandbox_exec import run_checks

_CODE_SYSTEM = (
    "Ты генерируешь изменения по утверждённому плану. Верни JSON-объект "
    "{путь: содержимое_файла} только для action create|update. Публичные функции/классы "
    "снабжай docstring. Не добавляй файлы вне плана. Если приложены ошибки проверок — "
    "исправь их, сохранив исходную задачу."
)


@dataclass
class CodingResult:
    files: dict[str, str] = field(default_factory=dict)
    deletions: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    verified: bool = False  # прогнаны и зелены исполняемые проверки репо
    iterations: int = 0
    checks: dict[str, str] = field(default_factory=dict)  # имя -> статус


def self_check(files: dict[str, str], gate: RiskPlanGate) -> list[str]:
    """Сверка сгенерированного с планом: покрытие, отсутствие лишних/пустых/небезопасных."""
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


def _enabled_commands(repo_config: RepoConfig) -> dict[str, str | None]:
    commands = {
        "lint": repo_config.commands.lint,
        "typecheck": repo_config.commands.typecheck,
        "test": repo_config.commands.test,
    }
    return {name: cmd for name, cmd in commands.items() if cmd}


async def _generate(card: TaskCard, targets: list, llm: LLMClient, feedback: str) -> dict[str, str]:
    payload: dict = {
        "task_id": card.task_id,
        "acceptance_criteria": card.acceptance_criteria,
        "changes": [
            {"path": c.path, "action": c.action, "rationale": c.rationale} for c in targets
        ],
    }
    if feedback:
        payload["check_failures"] = feedback
    resp = await llm.complete(
        system=_CODE_SYSTEM,
        messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
    )
    try:
        files = json.loads(resp.text)
        if not isinstance(files, dict):
            files = {}
    except (json.JSONDecodeError, TypeError):
        files = {}
    return {str(k): str(v) for k, v in files.items()}


def _write_files(checkout_root: str, files: dict[str, str]) -> None:
    """Пишет файлы в checkout (только безопасные пути — повторный guard к self_check)."""
    for path, content in files.items():
        if not is_safe_repo_path(path):
            continue
        full = os.path.join(checkout_root, path)
        os.makedirs(os.path.dirname(full) or checkout_root, exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(content)


def _format_failures(results: dict) -> str:
    parts = []
    for name, res in results.items():
        if res.status in ("failed", "timeout"):
            parts.append(f"[{name} {res.status}]\n{res.output[-1500:]}")
    return "\n\n".join(parts)


async def generate_changes(
    card: TaskCard,
    gate: RiskPlanGate,
    llm: LLMClient,
    *,
    checkout_root: str,
    repo_config: RepoConfig,
    max_iterations: int | None = None,
) -> CodingResult:
    """Итеративно генерирует и верифицирует изменения проверками репо."""
    max_iter = max_iterations or settings.max_code_iterations
    targets = [c for c in gate.changes if c.action in ("create", "update")]
    deletions = [c.path for c in gate.changes if c.action == "delete"]
    commands = _enabled_commands(repo_config)

    files: dict[str, str] = {}
    feedback = ""
    last_checks: dict[str, str] = {}

    for attempt in range(1, max_iter + 1):
        files = await _generate(card, targets, llm, feedback)
        issues = self_check(files, gate)
        if issues:
            feedback = "Исправь self-check: " + "; ".join(issues)
            continue

        _write_files(checkout_root, files)
        results = await run_checks(commands, checkout_root)
        last_checks = {name: res.status for name, res in results.items()}
        runnable = [r for r in results.values() if r.status in ("passed", "failed", "timeout")]
        failed = [r for r in runnable if r.status in ("failed", "timeout")]

        if not failed:
            return CodingResult(
                files=files,
                deletions=deletions,
                issues=[],
                verified=bool(runnable),  # есть прогнанные проверки и все зелёные
                iterations=attempt,
                checks=last_checks,
            )
        feedback = _format_failures(results)

    # Лимит исчерпан: либо self-check, либо проверки не зелёные -> fail-closed (нужен человек).
    issues = self_check(files, gate) or ["repo checks failing after iterations"]
    return CodingResult(
        files=files,
        deletions=deletions,
        issues=issues,
        verified=False,
        iterations=max_iter,
        checks=last_checks,
    )
