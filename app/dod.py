"""Definition of Done: проверка готовности MR к приёмке человеком.

Все условия должны выполняться; иначе merge не предлагается. Решение о merge
всегда остаётся за человеком-Maintainer.
"""

from dataclasses import dataclass, field

from app.contracts import AIReviewVerdict, RedTeamResult


@dataclass
class DoDInputs:
    acceptance_unmapped: list[str] = field(default_factory=list)  # несопоставленные критерии
    ci_green: bool = False
    review: AIReviewVerdict | None = None
    redteam: RedTeamResult | None = None
    redteam_required: bool = False
    tests_present: bool = False
    tests_skip_reason: str | None = None
    doc_impact: str = "yes"
    docs_updated: bool = False
    has_high_critical_vulns: bool = False
    secret_leaks: bool = False
    rollback_note: str = ""
    human_approved: bool = False


@dataclass
class DoDResult:
    met: bool
    unmet: list[str]


def definition_of_done(inp: DoDInputs) -> DoDResult:
    unmet: list[str] = []

    if inp.acceptance_unmapped:
        unmet.append(f"acceptance criteria не сопоставлены: {inp.acceptance_unmapped}")
    if not inp.ci_green:
        unmet.append("обязательные CI checks не зелёные")

    if inp.review is None or inp.review.merge_blocked:
        unmet.append("AI-review не PASS/PASS_WITH_NOTES без блокеров")
    if inp.redteam_required:
        if inp.redteam is None or inp.redteam.merge_blocked:
            unmet.append("Red Team не пройден")

    if not inp.tests_present and not (inp.tests_skip_reason or "").strip():
        unmet.append("нет тестов и нет approved-причины их отсутствия")
    if inp.doc_impact == "yes" and not inp.docs_updated:
        unmet.append("документация не обновлена при doc_impact=yes")

    if inp.has_high_critical_vulns:
        unmet.append("есть high/critical уязвимости")
    if inp.secret_leaks:
        unmet.append("обнаружены утечки секретов")
    if not inp.rollback_note.strip():
        unmet.append("отсутствует rollback_note")
    if not inp.human_approved:
        unmet.append("нет approve от назначенного human reviewer")

    return DoDResult(met=not unmet, unmet=unmet)
