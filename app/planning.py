"""Explore & Plan: разведка по песочнице, план изменений, риск-профиль.

Модель предлагает план через безопасные инструменты; результат фиксируется как
RiskPlanGate. Уровень риска пересчитывается классификатором, а не берётся у модели.
"""

import json

from app.clients.protocols import GraphIndex, LLMClient
from app.config import Settings
from app.context_engine import ContextEngine, is_safe_repo_path
from app.contracts import Change, RiskPlanGate, TaskCard
from app.risk import classify_risk

_PLAN_SYSTEM = (
    "Ты планируешь изменения по задаче разработки. На входе постановка и дерево "
    "репозитория. Верни JSON с полями: context_files[], changes[{path,action,rationale}] "
    "(action: create|update|delete), test_plan[], doc_impact(yes|no), doc_skip_reason, "
    "rollback_note, out_of_scope[]. Не выходи за рамки задачи."
)


class PlanError(Exception):
    """Модель вернула некорректный план."""


async def explore_and_plan(
    card: TaskCard,
    engine: ContextEngine,
    llm: LLMClient,
    settings: Settings,
    graph: GraphIndex | None = None,
) -> RiskPlanGate:
    tree = engine.list_dir(".")

    # Граф кода — навигационная подсказка (untrusted), не источник истины.
    graph_hint = ""
    if graph is not None:
        question = card.business_goal or card.acceptance_criteria or "architecture overview"
        try:
            graph_hint = await graph.query(question)
        except Exception:  # noqa: BLE001 — подсказка опциональна, не должна ронять план
            graph_hint = ""

    prompt_payload = {
        "task_type": card.task_type,
        "business_goal": card.business_goal,
        "acceptance_criteria": card.acceptance_criteria,
        "affected_area": card.affected_area,
        "repo_tree": tree,
    }
    if graph_hint:
        prompt_payload["graph_hint_untrusted"] = graph_hint
    prompt = json.dumps(prompt_payload, ensure_ascii=False)
    resp = await llm.complete(system=_PLAN_SYSTEM, messages=[{"role": "user", "content": prompt}])
    try:
        payload = json.loads(resp.text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise PlanError("plan is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise PlanError("plan must be an object")

    changes = [Change(**c) for c in payload.get("changes", [])]
    unsafe = [c.path for c in changes if not is_safe_repo_path(c.path)]
    if unsafe:
        raise PlanError(f"unsafe change paths: {unsafe}")
    risk = classify_risk(card, [c.path for c in changes], settings)

    doc_impact = payload.get("doc_impact", "yes")
    doc_skip_reason = payload.get("doc_skip_reason")
    # Без явного обоснования пропуска документации считаем, что доки нужны (fail-closed).
    if doc_impact == "no" and not (doc_skip_reason or "").strip():
        doc_impact = "yes"
        doc_skip_reason = None

    return RiskPlanGate(
        risk_level=risk.risk_level,
        risk_reasons=risk.risk_reasons,
        red_team_required=risk.red_team_required,
        human_preapproval_required=risk.human_preapproval_required,
        context_files=list(payload.get("context_files", [])),
        changes=changes,
        test_plan=list(payload.get("test_plan", [])),
        doc_impact=doc_impact,
        doc_skip_reason=doc_skip_reason,
        rollback_note=payload.get("rollback_note", ""),
        out_of_scope=list(payload.get("out_of_scope", [])),
    )
