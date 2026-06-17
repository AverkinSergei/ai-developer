"""Red Team контур: поиск способов эксплуатации изменения и решение о блокировке.

Подключается по триггерам повышенного риска или вручную (@ai redteam). Задача —
не улучшать стиль, а найти эксплойт. Нераспознанный вывод модели трактуется
fail-closed как NEED_HUMAN_SECURITY_REVIEW.
"""

import json

from app.clients.protocols import LLMClient
from app.contracts import RedTeamResult, RiskPlanGate, TaskCard

# Триггеры обязательного Red Team (EN + RU), сверяются с областями/путями/текстом.
_TRIGGERS = (
    "auth",
    "login",
    "session",
    "registration",
    "permission",
    "rbac",
    "acl",
    "role",
    "payment",
    "balance",
    "discount",
    "invoice",
    "pii",
    "personal data",
    "email",
    "phone",
    "external api",
    "webhook",
    "callback",
    "public endpoint",
    "upload",
    "html",
    "markdown",
    "sql",
    "migration",
    "schema",
    "dependency",
    "lockfile",
    "secret",
    "deploy",
    "docker",
    "kubernetes",
    "prompt",
    # RU
    "авториз",
    "аутентиф",
    "сесси",
    "регистрац",
    "права",
    "роль",
    "платёж",
    "платеж",
    "оплат",
    "баланс",
    "скидк",
    "счёт",
    "счет",
    "персональн",
    "почт",
    "телефон",
    "вебхук",
    "загрузка файл",
    "миграц",
    "схема данных",
    "зависимост",
    "секрет",
    "деплой",
)

_REDTEAM_SYSTEM = (
    "Ты Red Team reviewer. Твоя задача — найти способы эксплуатации изменения, а не "
    "улучшать стиль кода. Проверь: auth bypass, privilege escalation, IDOR/BOLA, "
    "injections (SQL/NoSQL/command/template), XSS/HTML/Markdown, SSRF, path traversal, "
    "unsafe upload, утечки secrets/PII, unsafe deps, race conditions, webhook validation, "
    "prompt injection/tool abuse. Верни JSON {verdict, max_severity, findings:[{title,"
    "severity,affected_files,exploit_scenario,recommended_fix,merge_blocking}]}. "
    "verdict: PASS|PASS_WITH_NOTES|FAIL|NEED_HUMAN_SECURITY_REVIEW. "
    "severity: low|medium|high|critical."
)

_FAIL_CLOSED = RedTeamResult(verdict="NEED_HUMAN_SECURITY_REVIEW", max_severity="high", findings=[])


def redteam_required(
    card: TaskCard,
    gate: RiskPlanGate,
    changed_paths: list[str],
    forced: bool = False,
) -> bool:
    """Нужен ли Red Team: ручной запуск, high/blocked риск или совпадение триггера."""
    if forced or gate.red_team_required or gate.risk_level in ("high", "blocked"):
        return True
    haystack = " ".join(
        [
            card.business_goal,
            card.acceptance_criteria,
            " ".join(card.affected_area),
            " ".join(card.context_keywords),
            " ".join(changed_paths),
        ]
    ).lower()
    return any(t in haystack for t in _TRIGGERS)


async def red_team_review(
    card: TaskCard,
    gate: RiskPlanGate,
    diff: str,
    llm: LLMClient,
) -> RedTeamResult:
    payload = json.dumps(
        {
            "task_type": card.task_type,
            "acceptance_criteria": card.acceptance_criteria,
            "risk_level": gate.risk_level,
            "diff": diff,
        },
        ensure_ascii=False,
    )
    resp = await llm.complete(
        system=_REDTEAM_SYSTEM, messages=[{"role": "user", "content": payload}]
    )
    try:
        data = json.loads(resp.text)
        return RedTeamResult(**data)
    except (json.JSONDecodeError, TypeError, ValueError):
        return _FAIL_CLOSED
