"""Оркестрация брифинга: обработка /go и приём ответов.

Переходы состояния идут через стор/FSM, права — через go_authorizer. /go
авторизуется синхронно до постановки кодинга в очередь.
"""

from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app import briefing_state_machine as fsm
from app.answer_extractor import accepted, extract_structured, extract_with_model
from app.briefing import render_round_comment, template_questions
from app.briefing_store import BriefingStore
from app.clients.graph import GraphifyGraph
from app.clients.protocols import BitrixClient, GitLabClient, GraphIndex, LLMClient
from app.coding import generate_changes
from app.config import Settings, settings
from app.context_engine import ContextEngine
from app.contracts import BriefingCommand, RiskPlanGate, TaskCard
from app.db.models import TaskState
from app.dod import DoDResult
from app.go_authorizer import GoContext, GoDecision, authorize
from app.graph_build import sync_repo_graph
from app.intake import VALID_TASK_TYPES, build_task_card, missing_required_fields
from app.planning import explore_and_plan
from app.workspace import checkout_workspace

# Без этих полей задачу нельзя даже завести; остальное добирает брифинг.
_INTAKE_REQUIRED = ("task_type", "target_repo")

# repo, user_id -> является ли пользователь maintainer проекта.
MaintainerResolver = Callable[[str, str], Awaitable[bool]]


async def _no_maintainer(repo: str, user_id: str) -> bool:
    return False


async def handle_go(
    db: AsyncSession,
    *,
    task_id: str,
    user_id: str,
    event_id: str,
    resolve_maintainer: MaintainerResolver = _no_maintainer,
    source_comment_id: str | None = None,
) -> GoDecision:
    """Авторизует /go, фиксирует событие, при успехе переводит сеанс в APPROVED."""
    store = BriefingStore(db)
    session = await store.get_session_by_task(task_id)
    if session is None:
        return GoDecision(
            authorized=False,
            rule="not_ready",
            decision="rejected",
            high_risk_rule_applied=False,
            evidence={"reason": "no_session", "user_id": user_id},
        )

    # Точный повтор того же события (ретрай доставки вебхука) — идемпотентно дубль.
    if await store.go_event_exists(event_id):
        return GoDecision(
            authorized=False,
            rule="duplicate",
            decision="ignored_duplicate",
            high_risk_rule_applied=False,
            evidence={"reason": "event_replay"},
        )

    # Уже был авторизованный /go — любой следующий это дубль (в т.ч. после APPROVED).
    existing = await store.latest_authorized_go(session.session_id)
    if existing is not None:
        await store.add_go_event(
            event_id=event_id,
            session_id=session.session_id,
            task_id=task_id,
            user_id=user_id,
            rule="duplicate",
            decision="ignored_duplicate",
            authorized=False,
            evidence={"reason": "already_authorized", "user_id": user_id},
            high_risk_rule_applied=False,
            source_comment_id=source_comment_id,
        )
        return GoDecision(
            authorized=False,
            rule="duplicate",
            decision="ignored_duplicate",
            high_risk_rule_applied=False,
            evidence={"reason": "already_authorized"},
        )

    if session.state not in (fsm.READY_FOR_GO, fsm.GO_AUTH_CHECK):
        return GoDecision(
            authorized=False,
            rule="not_ready",
            decision="rejected",
            high_risk_rule_applied=False,
            evidence={"reason": "not_ready", "state": session.state, "user_id": user_id},
        )

    task = await db.get(TaskState, task_id)
    if task is None:
        return GoDecision(
            authorized=False,
            rule="not_ready",
            decision="rejected",
            high_risk_rule_applied=False,
            evidence={"reason": "no_task_state", "user_id": user_id},
        )
    is_maintainer = await resolve_maintainer(task.repo, user_id)
    ctx = GoContext(
        user_id=user_id,
        author_user_id=task.author_user_id,
        reviewer_user_id=task.reviewer_user_id,
        assignee_user_id=None,  # ответственный появится, когда intake начнёт его заполнять
        ai_go_approvers=settings.ai_go_approvers,
        is_maintainer=is_maintainer,
    )
    decision = authorize(
        ctx,
        risk_level=task.risk_level or "low",
        high_risk_requires_maintainer=settings.high_risk_go_requires_maintainer,
    )

    await store.add_go_event(
        event_id=event_id,
        session_id=session.session_id,
        task_id=task_id,
        user_id=user_id,
        rule=decision.rule,
        decision=decision.decision,
        authorized=decision.authorized,
        evidence=decision.evidence,
        high_risk_rule_applied=decision.high_risk_rule_applied,
        source_comment_id=source_comment_id,
    )

    if decision.authorized:
        if session.state == fsm.READY_FOR_GO:
            await store.transition(session, fsm.GO_AUTH_CHECK)
        await store.transition(session, fsm.APPROVED)
        # Намерение запустить кодинг — в той же транзакции (без lost-start).
        await store.add_outbox(task_id, "run_task_phase", [task_id, "plan"])

    return decision


async def handle_answers(
    db: AsyncSession,
    *,
    task_id: str,
    command: BriefingCommand,
    author_user_id: str,
    source_comment_id: str,
    llm: LLMClient | None = None,
    confidence_min: float | None = None,
) -> dict:
    """Сопоставляет ответы с вопросами активного раунда и сохраняет принятые."""
    threshold = (
        settings.answer_extraction_confidence_min if confidence_min is None else confidence_min
    )
    store = BriefingStore(db)
    session = await store.get_active_session_by_task(task_id)
    if session is None or session.state != fsm.WAITING_ANSWERS:
        return {"accepted": 0, "reason": "not_waiting"}

    label = (command.round_id or "").lower().lstrip("r")
    if not label.isdigit():
        return {"accepted": 0, "reason": "bad_round"}
    rnd = await store.get_round_by_number(session.session_id, int(label))
    if rnd is None or session.active_round_id != rnd.round_id:
        return {"accepted": 0, "reason": "round_mismatch"}

    qbo = await store.questions_by_ordinal(rnd.round_id)
    extracted = extract_structured(command.raw, qbo)
    if not extracted and llm is not None:
        extracted = await extract_with_model(command.raw, qbo, llm)
    good = accepted(extracted, threshold)

    for ans in good:
        await store.record_answer(
            question_id=ans.question_id,
            answer_id=f"{ans.question_id}#{source_comment_id}",
            raw_text=ans.raw_text,
            normalized_answer=ans.normalized_answer,
            confidence=ans.confidence,
            source_comment_id=source_comment_id,
            accepted_by_rule=ans.accepted_by_rule,
            author_user_id=author_user_id,
        )

    if good:
        await store.transition(session, fsm.ANSWERS_RECEIVED)

    return {"accepted": len(good), "low_confidence": len(extracted) - len(good)}


def _clean(s: str) -> str:
    """Схлопывает переводы строк/пробелы — не даёт недоверенному тексту ломать разметку MR."""
    return " ".join(str(s).split())


def _mr_description(card: TaskCard, gate: RiskPlanGate) -> str:
    """Описание MR: summary, acceptance, risk, тест-план, doc_impact, rollback, audit."""
    doc_line = f"**Doc impact:** {gate.doc_impact}"
    if gate.doc_impact == "no":
        doc_line += f" ({_clean(gate.doc_skip_reason or '')})"
    test_lines = [f"- {_clean(t)}" for t in gate.test_plan] or ["- (none)"]
    lines = [
        f"## {card.task_type}: {card.task_id}",
        "",
        f"**Business goal:** {_clean(card.business_goal) or '-'}",
        f"**Acceptance criteria:** {_clean(card.acceptance_criteria) or '-'}",
        f"**Risk level:** {gate.risk_level}",
        doc_line,
        "",
        "### Test plan",
        *test_lines,
        "",
        "### Rollback",
        _clean(gate.rollback_note) or "-",
        "",
        "### Audit",
        f"- changes: {len(gate.changes)} files",
        f"- red_team_required: {gate.red_team_required}",
    ]
    return "\n".join(lines)


async def run_coding_slice(
    card: TaskCard,
    *,
    engine: ContextEngine,
    llm: LLMClient,
    gitlab: GitLabClient,
    settings: Settings = settings,
    graph: GraphIndex | None = None,
    context_graphs: list[GraphIndex] | None = None,
) -> dict:
    """Тонкий срез: план -> гейты -> код -> ветка auto-task-* -> Draft MR."""
    gate = await explore_and_plan(
        card, engine, llm, settings, graph=graph, context_graphs=context_graphs
    )

    if gate.risk_level == "blocked":
        return {"status": "blocked", "gate": gate}
    # high / требующие предодобрения не выполняются автономно — передаём человеку.
    if gate.human_preapproval_required or gate.red_team_required:
        return {"status": "needs_human", "gate": gate}

    coding = await generate_changes(card, gate, llm)
    if coding.issues:
        return {"status": "self_check_failed", "issues": coding.issues, "gate": gate}

    branch = f"auto-task-{card.task_id}"
    # Ветка отпочковывается от fork_base_branch (main), а MR нацелен в target_branch (dev).
    if not await gitlab.branch_exists(card.target_repo, branch):
        await gitlab.create_branch(card.target_repo, branch, settings.fork_base_branch)
    await gitlab.commit_files(
        card.target_repo, branch, f"{card.task_type}: {card.task_id}", coding.files
    )

    mr = await gitlab.find_open_mr(card.target_repo, branch)
    if mr is None:
        mr = await gitlab.create_draft_mr(
            card.target_repo,
            branch,
            card.target_branch,
            f"Draft: {card.task_type} {card.task_id}",
            _mr_description(card, gate),
        )
    return {"status": "mr_ready", "mr": mr, "gate": gate, "branch": branch}


async def finalize_mr(
    card: TaskCard,
    mr: dict,
    dod: DoDResult,
    gitlab: GitLabClient,
) -> dict:
    """При выполнении DoD снимает Draft и назначает reviewer; merge — за человеком."""
    if dod.met:
        await gitlab.mark_mr_ready(card.target_repo, mr["iid"], card.reviewer)
        return {"status": "ready_for_human", "mr": mr}
    return {"status": "draft", "unmet": dod.unmet}


def _normalize_bitrix(raw: dict, field_map: dict[str, str]) -> dict:
    """Bitrix-поля -> нормализованные ключи карточки по конфиг-маппингу."""
    out: dict = {}
    for norm_key, bx_key in field_map.items():
        val = raw.get(bx_key)
        if val not in (None, "", []):
            out[norm_key] = val
    out.setdefault("author_user_id", str(raw.get("createdBy") or raw.get("CREATED_BY") or ""))
    return out


def _allowed_go_users(card: TaskCard, settings: Settings) -> list[str]:
    users = [card.author_user_id, *(settings.ai_go_approvers or [])]
    if card.reviewer:
        users.append(card.reviewer)
    return [u for u in dict.fromkeys(users) if u]


async def intake_task(
    db: AsyncSession,
    *,
    task_id: str,
    raw_fields: dict,
    text: str,
    bitrix: BitrixClient,
    settings: Settings = settings,
) -> dict:
    """Валидирует постановку, сохраняет карточку и открывает брифинг или READY_FOR_GO."""
    store = BriefingStore(db)
    normalized = _normalize_bitrix(raw_fields, settings.bitrix_field_map)
    normalized["task_id"] = task_id
    normalized.setdefault("target_branch", settings.default_base_branch)

    bad_type = str(normalized.get("task_type") or "") not in VALID_TASK_TYPES
    missing_intake = [f for f in _INTAKE_REQUIRED if not str(normalized.get(f) or "").strip()]
    if bad_type or missing_intake:
        await bitrix.set_status_note(
            task_id, "Заполните обязательные поля: task_type, target_repo."
        )
        return {"status": "invalid", "missing": missing_intake or ["task_type"]}

    card = build_task_card(normalized, text)
    task = await db.get(TaskState, task_id)
    if task is None:
        task = TaskState(
            task_id=task_id,
            repo=card.target_repo,
            target_branch=card.target_branch,
            task_type=card.task_type,
            author_user_id=card.author_user_id or "unknown",
        )
        db.add(task)
    task.repo = card.target_repo
    task.target_branch = card.target_branch
    task.task_type = card.task_type
    task.reviewer_user_id = card.reviewer
    task.card_snapshot = card.model_dump()
    await db.flush()

    session = await store.get_active_session_by_task(task_id)
    if session is None:
        session = await store.create_session(
            session_id=f"brf_{task_id}",
            task_id=task_id,
            repo=card.target_repo,
            target_branch=card.target_branch,
            author_user_id=card.author_user_id or "unknown",
            allowed_go_users=_allowed_go_users(card, settings),
            required_fields_snapshot={
                "task_type": card.task_type,
                "target_repo": card.target_repo,
                "target_branch": card.target_branch,
            },
        )
    if session.state != fsm.NEW:
        return {"status": "already_started", "state": session.state}

    gaps = [g for g in missing_required_fields(normalized) if g not in _INTAKE_REQUIRED]
    if not gaps:
        await store.transition(session, fsm.COMPLETENESS_CHECK)
        await store.transition(session, fsm.READY_FOR_GO)
        await bitrix.set_status_note(task_id, "Брифинг: готов к /go.")
        return {"status": "ready_for_go"}

    await _open_round(store, session, card, gaps, bitrix)
    return {"status": "briefing", "questions": len(gaps)}


async def _open_round(
    store: BriefingStore,
    session,
    card: TaskCard,
    gaps: list[str],
    bitrix: BitrixClient,
) -> None:
    """Создаёт раунд вопросов по пробелам и публикует его в Битрикс24."""
    if session.state == fsm.NEW:
        await store.transition(session, fsm.QUESTIONS_GENERATED)
    elif session.state == fsm.NEEDS_MORE_INFO:
        pass
    round_number = session.rounds_count + 1
    label = f"r{round_number}"
    questions = template_questions(gaps)
    body = render_round_comment(session.session_id, label, questions)
    comment_id = await bitrix.add_comment(session.task_id, body)
    rnd = await store.add_round(session, f"{session.session_id}:{label}", comment_id, "ai-bot")
    for i, (field, q) in enumerate(zip(gaps, questions, strict=False), start=1):
        await store.add_question(rnd, f"{rnd.round_id}:q{i}", i, q, dor_dimension=field)
    await store.transition(session, fsm.WAITING_ANSWERS)


async def finalize_round(
    db: AsyncSession,
    *,
    task_id: str,
    bitrix: BitrixClient,
    settings: Settings = settings,
) -> dict:
    """После приёма ответов: completeness -> READY_FOR_GO, новый раунд или BLOCKED."""
    store = BriefingStore(db)
    session = await store.get_active_session_by_task(task_id)
    if session is None or session.state != fsm.ANSWERS_RECEIVED:
        return {"status": "noop"}

    await store.transition(session, fsm.COMPLETENESS_CHECK)

    task = await db.get(TaskState, task_id)
    card_data = dict(task.card_snapshot or {})
    for dimension, answer in await store.accepted_answers_with_dimension(session.session_id):
        if dimension:
            card_data[dimension] = answer
    task.card_snapshot = card_data
    await db.flush()

    gaps = [g for g in missing_required_fields(card_data) if g not in _INTAKE_REQUIRED]
    if not gaps:
        await store.transition(session, fsm.READY_FOR_GO)
        await bitrix.set_status_note(task_id, "Брифинг: готов к /go.")
        return {"status": "ready_for_go"}

    if session.rounds_count >= settings.max_briefing_rounds:
        await store.transition(session, fsm.BLOCKED_MANUAL)
        await bitrix.set_status_note(task_id, "Брифинг исчерпал лимит раундов — нужен человек.")
        return {"status": "blocked_manual"}

    await store.transition(session, fsm.NEEDS_MORE_INFO)
    card = TaskCard(**card_data)
    await _open_round(store, session, card, gaps, bitrix)
    return {"status": "more_info", "questions": len(gaps)}


async def _build_context_graphs(
    repos: list[str], *, gitlab: GitLabClient, settings: Settings
) -> list[GraphIndex]:
    """Графы read-only репозиториев-контекста (без MR). Best-effort, недоступные пропускаем."""
    graphs: list[GraphIndex] = []
    for repo in repos:
        path = await sync_repo_graph(repo, gitlab=gitlab, settings=settings)
        if path:
            graphs.append(GraphifyGraph(path))
    return graphs


async def _plan_one_repo(
    task_id: str,
    repo: str,
    card: TaskCard,
    *,
    gitlab: GitLabClient,
    llm: LLMClient,
    settings: Settings,
    context_graphs: list[GraphIndex],
) -> dict:
    """План/код/Draft MR для одного репозитория задачи (с учётом контекстных графов)."""
    repo_card = card.model_copy(update={"target_repo": repo})
    ws_id = f"{task_id}-{repo.replace('/', '_')}"
    async with checkout_workspace(ws_id) as ws:
        root = await gitlab.fetch_archive(repo, settings.fork_base_branch, ws)
        engine = ContextEngine(root)
        graph_path = await sync_repo_graph(repo, gitlab=gitlab, settings=settings)
        graph = GraphifyGraph(graph_path) if graph_path else None
        result = await run_coding_slice(
            repo_card,
            engine=engine,
            llm=llm,
            gitlab=gitlab,
            settings=settings,
            graph=graph,
            context_graphs=context_graphs,
        )
    result["repo"] = repo
    return result


def _plan_status_note(results: list[dict]) -> str:
    lines: list[str] = []
    for r in results:
        repo = r.get("repo", "?")
        status = r["status"]
        if status == "mr_ready":
            mr = r["mr"]
            link = mr.get("web_url") or f"MR !{mr['iid']}"
            lines.append(f"{repo}: Draft MR {link}")
        elif status == "blocked":
            lines.append(f"{repo}: risk=blocked — нужен человек")
        elif status == "needs_human":
            lines.append(f"{repo}: high-risk — нужен human pre-approval / Red Team")
        elif status == "self_check_failed":
            lines.append(f"{repo}: self-check не пройден")
        else:
            lines.append(f"{repo}: {status}")
    return "\n".join(lines)


async def execute_plan(
    db: AsyncSession,
    *,
    task_id: str,
    gitlab: GitLabClient,
    llm: LLMClient,
    bitrix: BitrixClient,
    settings: Settings = settings,
) -> dict:
    """План/код/Draft MR по каждому репозиторию задачи (по одному MR на репозиторий)."""
    task = await db.get(TaskState, task_id)
    if task is None or not task.card_snapshot:
        return {"status": "no_task"}
    card = TaskCard(**task.card_snapshot)

    # Контекстные репозитории (read-only) строим один раз — общий контекст для всех целей.
    context_graphs = await _build_context_graphs(
        card.context_only_repos, gitlab=gitlab, settings=settings
    )

    results: list[dict] = []
    for repo in card.all_repos:
        results.append(
            await _plan_one_repo(
                task_id,
                repo,
                card,
                gitlab=gitlab,
                llm=llm,
                settings=settings,
                context_graphs=context_graphs,
            )
        )

    mr_ready = [r for r in results if r["status"] == "mr_ready"]
    if mr_ready:
        task.mr_iid = str(mr_ready[0]["mr"]["iid"])
        task.source_branch = mr_ready[0]["branch"]
        task.phase = "ci"
    elif any(r["status"] == "blocked" for r in results):
        task.phase = "blocked"
    elif any(r["status"] == "needs_human" for r in results):
        task.phase = "needs_human"
    await db.flush()
    await bitrix.set_status_note(task_id, _plan_status_note(results))

    if len(results) == 1:
        return results[0]  # обратная совместимость с одним репозиторием
    return {"status": "multi", "results": results}
