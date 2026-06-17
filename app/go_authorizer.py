"""Авторизация команды /go.

Проверка по Bitrix user_id автора, а не по тексту имени. Для high-risk задач
требуется /go от maintainer или reviewer, не только от постановщика. Решение
(rule, decision, evidence) сохраняется в go_authorization_event.
"""

from dataclasses import dataclass, field

# Приоритет правил: сильнейшее совпадение выигрывает.
_RULE_PRIORITY = ("maintainer", "reviewer", "responsible_user", "creator", "ai_go_approvers")
_HIGH_RISK_RULES = frozenset({"maintainer", "reviewer"})


@dataclass
class GoContext:
    user_id: str
    author_user_id: str = ""  # постановщик
    reviewer_user_id: str | None = None
    assignee_user_id: str | None = None  # ответственный
    ai_go_approvers: list[str] = field(default_factory=list)
    is_maintainer: bool = False  # роль в GitLab-проекте, резолвится клиентом


@dataclass
class GoDecision:
    authorized: bool
    rule: str | None
    decision: str  # authorized | rejected
    high_risk_rule_applied: bool
    evidence: dict


def _matched_rules(ctx: GoContext) -> set[str]:
    rules: set[str] = set()
    if not ctx.user_id:
        return rules  # пустой/неизвестный пользователь не совпадает ни с одним правилом
    if ctx.is_maintainer:
        rules.add("maintainer")
    if ctx.reviewer_user_id and ctx.user_id == ctx.reviewer_user_id:
        rules.add("reviewer")
    if ctx.assignee_user_id and ctx.user_id == ctx.assignee_user_id:
        rules.add("responsible_user")
    if ctx.author_user_id and ctx.user_id == ctx.author_user_id:
        rules.add("creator")
    if ctx.user_id and ctx.user_id in ctx.ai_go_approvers:
        rules.add("ai_go_approvers")
    return rules


def authorize(
    ctx: GoContext,
    risk_level: str,
    high_risk_requires_maintainer: bool = True,
) -> GoDecision:
    """Решение об авторизации /go. Чистая функция — побочных эффектов нет."""
    matched = _matched_rules(ctx)
    rule = next((r for r in _RULE_PRIORITY if r in matched), None)
    authorized = rule is not None

    high_risk_applied = risk_level == "high" and high_risk_requires_maintainer
    if high_risk_applied and not (matched & _HIGH_RISK_RULES):
        authorized = False  # для high-risk одного постановщика/ответственного мало

    evidence = {
        "user_id": ctx.user_id,
        "risk_level": risk_level,
        "matched_rules": sorted(matched),
        "is_maintainer": ctx.is_maintainer,
        "high_risk_rule_applied": high_risk_applied,
    }
    return GoDecision(
        authorized=authorized,
        rule=rule if authorized else (rule or "insufficient_rights"),
        decision="authorized" if authorized else "rejected",
        high_risk_rule_applied=high_risk_applied,
        evidence=evidence,
    )
