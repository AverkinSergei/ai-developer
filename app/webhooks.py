"""Приём вебхуков. Подпись проверяется до любой работы; ack быстрый, тяжёлое — в очередь."""

import hashlib
import hmac
import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app import briefing_state_machine as fsm
from app.audit import log_event
from app.briefing_store import BriefingStore
from app.ci import (
    is_actionable_comment,
    is_auto_task_branch,
    next_fix_action,
    parse_note,
    parse_pipeline,
    pipeline_is_blocking,
)
from app.clients.bitrix import Bitrix
from app.clients.gitlab_client import GitLab
from app.commands import parse_command
from app.config import settings
from app.contracts import BriefingCommand
from app.db.base import sessionmanager
from app.db.models import TaskState
from app.gitlab_roles import make_maintainer_resolver
from app.metrics import go_decisions_total, webhooks_total
from app.orchestrator import handle_go
from app.state import lock_briefing, lock_task, store
from app.worker import enqueue_task

router = APIRouter()

# Клиенты для перепроверки автора, ролей и публикации ответов (seam для тестов).
bitrix_client = Bitrix()
gitlab_client = GitLab()

_MANUAL_INTERVENTION_MSG = (
    "Достигнут лимит автоправок (MAX_AI_FIXES). Требуется ручное вмешательство."
)
_FIX_AUTHZ_ROLES = {"maintainer", "owner"}

_TASK_ADD_EVENTS = {"ONTASKADD", "ONTASKUPDATE"}
_COMMENT_EVENTS = {"ONTASKCOMMENTADD"}

_GO_REJECTED_MSG = (
    "Команда /go отклонена: недостаточно прав. Требуется /go от: постановщик, "
    "ответственный, reviewer или maintainer."
)


async def _route_command(
    task_id: str,
    user_id: str,
    comment_id: str | None,
    event_id: str,
    command: BriefingCommand,
) -> None:
    """Маршрутизация команды из комментария. /go авторизуется синхронно под локом."""
    if command.kind == "go":
        token = await store.acquire_lock(lock_briefing(task_id))
        if token is None:
            log_event("go_lock_busy", task_id=task_id)
            return
        try:
            async with sessionmanager.session() as db:
                decision = await handle_go(
                    db,
                    task_id=task_id,
                    user_id=user_id,
                    event_id=event_id,
                    resolve_maintainer=make_maintainer_resolver(gitlab_client),
                    source_comment_id=comment_id,
                )
                await db.commit()
            go_decisions_total.labels(decision=decision.decision).inc()
            if decision.authorized:
                # Кодинг ставит relay из outbox (запись сделана в той же транзакции).
                log_event("go_authorized", task_id=task_id, user_id=user_id, rule=decision.rule)
            elif decision.decision == "rejected" and decision.rule == "insufficient_rights":
                await _post_comment(task_id, _GO_REJECTED_MSG)
                log_event("go_rejected", task_id=task_id, user_id=user_id)
            else:
                log_event("go_noop", task_id=task_id, decision=decision.decision)
        finally:
            await store.release_lock(lock_briefing(task_id), token)
        return

    # Ответы и прочие команды обрабатываются в фоне.
    await enqueue_task("run_command", task_id, command.kind, user_id, comment_id, command.raw)
    log_event("command_enqueued", task_id=task_id, kind=command.kind)


async def _post_comment(task_id: str, text: str) -> None:
    await bitrix_client.add_comment(task_id, text)
    log_event("bitrix_comment_out", task_id=task_id)


def _body_limit_bytes() -> int:
    return settings.webhook_max_body_mb * 1024 * 1024


def _valid_token(provided: str) -> bool:
    expected = settings.bitrix_app_token
    if not expected or not provided:
        return False
    return hmac.compare_digest(provided, expected)


@router.post("/bitrix-webhook")
async def bitrix_webhook(request: Request) -> JSONResponse:
    # Лимит размера тела (до парсинга).
    limit = _body_limit_bytes()
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        return JSONResponse(status_code=413, content={"error": "payload too large"})

    body = await request.body()
    if len(body) > limit:
        return JSONResponse(status_code=413, content={"error": "payload too large"})

    form = await request.form()

    if not _valid_token(str(form.get("auth[application_token]", ""))):
        log_event("bitrix_webhook_rejected", reason="bad_token")
        webhooks_total.labels(source="bitrix", outcome="rejected").inc()
        return JSONResponse(status_code=403, content={"error": "invalid token"})

    event = str(form.get("event", "")).upper()
    task_id = str(form.get("data[FIELDS][ID]", "")) or None

    # Идемпотентность: ts от Битрикс, иначе хэш тела.
    ts = str(form.get("ts", ""))
    if ts and task_id:
        event_id = f"{event}:{task_id}:{ts}"
    else:
        event_id = hashlib.sha256(body).hexdigest()

    if not await store.mark_seen(event_id):
        return JSONResponse(status_code=200, content={"status": "duplicate"})

    if event in _TASK_ADD_EVENTS and task_id:
        await enqueue_task("run_task_phase", task_id, "intake")
        log_event("bitrix_webhook_accepted", task_id=task_id, event=event)
    elif event in _COMMENT_EVENTS:
        # У comment-события [ID] — id комментария, id задачи в [TASK_ID].
        comment_task_id = str(form.get("data[FIELDS][TASK_ID]", "")) or None
        text = str(form.get("data[FIELDS][POST_MESSAGE]", ""))
        comment_id = str(form.get("data[FIELDS][ID]", "")) or None
        command = parse_command(text)
        if command is not None and comment_task_id and comment_id:
            # AUTHOR_ID из payload не доверяем — берём достоверного автора из Битрикс24.
            author = await bitrix_client.get_comment_author(comment_task_id, comment_id)
            if author:
                # event_id из стабильного comment_id, а не из подменяемого ts.
                cmd_event_id = f"cmd:{comment_task_id}:{comment_id}"
                await _route_command(comment_task_id, author, comment_id, cmd_event_id, command)
            else:
                log_event("comment_author_unverified", task_id=comment_task_id)

    return JSONResponse(status_code=200, content={"status": "ok"})


def _valid_gitlab_token(provided: str) -> bool:
    expected = settings.gitlab_webhook_secret
    if not expected or not provided:
        return False
    return hmac.compare_digest(provided, expected)


async def _post_mr_note(repo: str, mr_iid: str, body: str) -> None:
    await gitlab_client.add_mr_note(repo, mr_iid, body)
    log_event("gitlab_mr_note_out", repo=repo, mr_iid=mr_iid)


async def _trigger_self_fix(repo: str, mr_iid: str, trigger: str) -> None:
    """Счётчик правок + постановка фикса или остановка с просьбой о вмешательстве."""
    count = await store.incr_fixes(mr_iid)
    if next_fix_action(count - 1, settings.max_ai_fixes) == "stop":
        await _post_mr_note(repo, mr_iid, _MANUAL_INTERVENTION_MSG)
        log_event("self_fix_limit_reached", repo=repo, mr_iid=mr_iid, trigger=trigger)
        return
    await enqueue_task("run_fix", repo, mr_iid, trigger)
    log_event("self_fix_enqueued", repo=repo, mr_iid=mr_iid, trigger=trigger)


async def _handle_pipeline(payload: dict) -> None:
    pe = parse_pipeline(payload)
    if not pipeline_is_blocking(pe.status) or not is_auto_task_branch(pe.ref):
        return
    if not pe.mr_iid:
        log_event("pipeline_failed_no_mr", repo=pe.project, ref=pe.ref)
        return
    await _trigger_self_fix(pe.project, pe.mr_iid, trigger="ci_failed")


async def _handle_gitlab_note(payload: dict) -> None:
    ne = parse_note(payload)
    if not ne.mr_iid or not is_actionable_comment(ne.note):
        return
    command = parse_command(ne.note)
    if command is None or command.kind not in ("ai_fix", "ai_resolve"):
        return
    # @ai fix/resolve — только от maintainer/owner проекта.
    role = await gitlab_client.get_project_member_role(ne.project, ne.author_id)
    if role not in _FIX_AUTHZ_ROLES:
        log_event("ai_command_unauthorized", repo=ne.project, user_id=ne.author_id)
        return
    if command.kind == "ai_fix":
        await _trigger_self_fix(ne.project, ne.mr_iid, trigger="ai_fix")
    else:
        await enqueue_task("run_resolve", ne.project, ne.mr_iid)
        log_event("resolve_enqueued", repo=ne.project, mr_iid=ne.mr_iid)


@router.post("/gitlab-webhook")
async def gitlab_webhook(request: Request) -> JSONResponse:
    limit = _body_limit_bytes()
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        return JSONResponse(status_code=413, content={"error": "payload too large"})
    body = await request.body()
    if len(body) > limit:
        return JSONResponse(status_code=413, content={"error": "payload too large"})

    if not _valid_gitlab_token(request.headers.get("X-Gitlab-Token", "")):
        log_event("gitlab_webhook_rejected", reason="bad_token")
        webhooks_total.labels(source="gitlab", outcome="rejected").inc()
        return JSONResponse(status_code=403, content={"error": "invalid token"})

    event = request.headers.get("X-Gitlab-Event", "")
    uuid = request.headers.get("X-Gitlab-Event-UUID", "") or hashlib.sha256(body).hexdigest()
    if not await store.mark_seen(f"gl:{uuid}"):
        return JSONResponse(status_code=200, content={"status": "duplicate"})

    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return JSONResponse(status_code=200, content={"status": "ignored"})

    if event == "Pipeline Hook":
        await _handle_pipeline(payload)
    elif event == "Note Hook":
        await _handle_gitlab_note(payload)

    return JSONResponse(status_code=200, content={"status": "ok"})


def _valid_internal_token(provided: str) -> bool:
    expected = settings.internal_api_token
    if not expected or not provided:
        return False
    return hmac.compare_digest(provided, expected)


@router.post("/internal/tasks/{task_id}/cancel")
async def cancel_task(task_id: str, request: Request) -> JSONResponse:
    """Служебная отмена in-flight задачи: снимает lock и переводит в CANCELLED."""
    if not _valid_internal_token(request.headers.get("X-Internal-Token", "")):
        return JSONResponse(status_code=403, content={"error": "forbidden"})

    cancelled = False
    async with sessionmanager.session() as db:
        bstore = BriefingStore(db)
        session = await bstore.get_active_session_by_task(task_id)
        if session is not None:
            await bstore.transition(session, fsm.CANCELLED)
            cancelled = True
        task = await db.get(TaskState, task_id)
        if task is not None:
            task.status = "cancelled"
            cancelled = True
        await db.commit()

    await store.force_release(lock_task(task_id))
    log_event("task_cancelled", task_id=task_id, cancelled=cancelled)
    status = 200 if cancelled else 404
    return JSONResponse(status_code=status, content={"cancelled": cancelled})
