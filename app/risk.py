"""Классификация риска задачи перед кодингом.

Оценка по полям задачи, изменяемым областям, планируемым путям и словам-триггерам.
blocked => агент не кодит. high => нужен Red Team и human pre-approval.
"""

from dataclasses import dataclass, field
from typing import cast

from app.config import Settings
from app.contracts import RiskLevel, TaskCard

_RANK = {"low": 0, "medium": 1, "high": 2, "blocked": 3}

# Задачу нельзя выполнять автономно.
_BLOCKED_TRIGGERS = (
    "production secret",
    "prod secret",
    "protected branch",
    "disable ci",
    "ci disable",
    "iam",
    "prod data",
    "production data",
    "rotate secret",
    # русские формулировки
    "прод секрет",
    "продакшен секрет",
    "боевые секрет",
    "боевые данные",
    "защищённую ветку",
    "защищенную ветку",
    "отключить ci",
    "ротац",
)

# Требуют Red Team и pre-approval.
_HIGH_TRIGGERS = (
    "auth",
    "login",
    "session",
    "password",
    "permission",
    "rbac",
    "acl",
    "role",
    "payment",
    "balance",
    "invoice",
    "billing",
    "pii",
    "personal data",
    "migration",
    "webhook",
    "callback",
    "external api",
    "upload",
    "dependency",
    "lockfile",
    "secret",
    "token",
    # русские формулировки
    "авториз",
    "аутентиф",
    "пароль",
    "сесси",
    "права доступа",
    "роль",
    "платёж",
    "платеж",
    "оплат",
    "баланс",
    "счёт",
    "счет",
    "биллинг",
    "персональн",
    "перс данны",
    "миграц",
    "вебхук",
    "webhook",
    "загрузка файл",
    "зависимост",
    "секрет",
    "токен",
)

_HIGH_AREAS = {"auth", "payments", "db", "infra"}
_LOW_ONLY_AREAS = {"docs"}


@dataclass
class RiskAssessment:
    risk_level: RiskLevel
    risk_reasons: list[str] = field(default_factory=list)
    red_team_required: bool = False
    human_preapproval_required: bool = False


def _haystack(card: TaskCard, changed_paths: list[str]) -> str:
    parts = [
        card.business_goal,
        card.acceptance_criteria,
        " ".join(card.affected_area),
        " ".join(card.context_keywords),
        " ".join(changed_paths),
    ]
    return " ".join(parts).lower()


def classify_risk(
    card: TaskCard,
    changed_paths: list[str],
    settings: Settings,
) -> RiskAssessment:
    text = _haystack(card, changed_paths)
    reasons: list[str] = []
    level = "low"

    # Базовый уровень по типу задачи: код — минимум medium, кроме чистых docs/ui.
    areas = {a.lower() for a in card.affected_area}
    if card.task_type in ("feature", "bugfix", "refactor"):
        if areas and areas <= _LOW_ONLY_AREAS:
            level = "low"
        else:
            level = "medium"

    if card.security:  # постановщик явно потребовал security review
        level = _max(level, "high")
        reasons.append("security flag from requester")

    for trig in _HIGH_TRIGGERS:
        if trig in text:
            level = _max(level, "high")
            reasons.append(f"high trigger: {trig}")
    if areas & _HIGH_AREAS:
        level = _max(level, "high")
        reasons.append(f"sensitive area: {sorted(areas & _HIGH_AREAS)}")

    for trig in _BLOCKED_TRIGGERS:
        if trig in text:
            level = _max(level, "blocked")
            reasons.append(f"blocked trigger: {trig}")

    # Подсказка постановщика учитывается, но только повышает.
    level = _max(level, card.risk_hint)

    # Лимиты по числу файлов.
    human_preapproval = level in ("high", "blocked")
    n = len(changed_paths)
    if n > settings.max_changed_files_medium:
        human_preapproval = True
        level = _max(level, "high")
        reasons.append(f"changed files {n} > {settings.max_changed_files_medium}")
    elif n > settings.max_changed_files_low:
        level = _max(level, "medium")
        reasons.append(f"changed files {n} > {settings.max_changed_files_low}")

    red_team = level in ("high", "blocked")
    return RiskAssessment(
        risk_level=cast(RiskLevel, level),
        risk_reasons=reasons,
        red_team_required=red_team,
        human_preapproval_required=human_preapproval or level == "high",
    )


def _max(a: str, b: str) -> str:
    return a if _RANK[a] >= _RANK[b] else b
