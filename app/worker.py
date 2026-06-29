"""Фоновый worker на Arq.

enqueue_task — единая точка постановки задач; держит движок очереди заменяемым.
"""

from typing import Any

from arq import create_pool, cron
from arq.connections import RedisSettings

from app.audit import configure_logging, log_event
from app.briefing_store import BriefingStore
from app.clients.bitrix import Bitrix
from app.clients.gitlab_client import GitLab
from app.clients.llm import OpenAILLM
from app.commands import parse_command
from app.config import settings
from app.db.base import sessionmanager
from app.orchestrator import (
    execute_plan,
    finalize_round,
    handle_answers,
    intake_task,
    run_conflict_resolution,
    run_self_fix,
)


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(settings.redis_url)


async def enqueue_task(func_name: str, *args: Any, **kwargs: Any) -> str | None:
    """Ставит задачу в очередь. Возвращает job_id."""
    pool = await create_pool(_redis_settings())
    try:
        job = await pool.enqueue_job(func_name, *args, **kwargs)
        return job.job_id if job else None
    finally:
        await pool.aclose()


async def run_task_phase(ctx: dict[str, Any], task_id: str, phase: str) -> None:
    """Диспетчер фаз: intake (постановка/брифинг) и plan (план/код/Draft MR)."""
    if phase == "intake":
        bitrix = Bitrix()
        raw = await bitrix.get_task(task_id)
        text = str(raw.get("description") or raw.get("DESCRIPTION") or "")
        async with sessionmanager.session() as db:
            result = await intake_task(
                db, task_id=task_id, raw_fields=raw, text=text, bitrix=bitrix, llm=OpenAILLM()
            )
            await db.commit()
        log_event("intake_done", task_id=task_id, **result)
    elif phase == "plan":
        async with sessionmanager.session() as db:
            result = await execute_plan(
                db, task_id=task_id, gitlab=GitLab(), llm=OpenAILLM(), bitrix=Bitrix()
            )
            await db.commit()
        log_event("plan_done", task_id=task_id, status=result.get("status"))
    else:
        log_event("phase_unknown", task_id=task_id, phase=phase)


async def run_command(
    ctx: dict[str, Any],
    task_id: str,
    kind: str,
    user_id: str,
    comment_id: str | None,
    raw: str,
) -> None:
    """Фоновая обработка команд брифинга (ответы, reopen/cancel/skip, @ai)."""
    if kind == "briefing_answer":
        command = parse_command(raw)
        if command is None:
            return
        async with sessionmanager.session() as db:
            result = await handle_answers(
                db,
                task_id=task_id,
                command=command,
                author_user_id=user_id,
                source_comment_id=comment_id or "",
            )
            # После приёма ответов — completeness: READY_FOR_GO / новый раунд / BLOCKED.
            if result.get("accepted"):
                await finalize_round(db, task_id=task_id, bitrix=Bitrix())
            await db.commit()
        log_event("answers_processed", task_id=task_id, **result)
        return
    log_event("command_received_stub", task_id=task_id, kind=kind)


async def run_fix(ctx: dict[str, Any], repo: str, mr_iid: str, trigger: str) -> None:
    """Самоисправление по упавшему CI / @ai fix: чинит проверки в ветке auto-task-*."""
    async with sessionmanager.session() as db:
        result = await run_self_fix(
            db, repo=repo, mr_iid=mr_iid, gitlab=GitLab(), llm=OpenAILLM(), bitrix=Bitrix()
        )
        await db.commit()
    log_event(
        "run_fix_done", repo=repo, mr_iid=mr_iid, trigger=trigger, status=result.get("status")
    )


async def run_resolve(ctx: dict[str, Any], repo: str, mr_iid: str) -> None:
    """Реакция на @ai resolve (конфликт MR)."""
    async with sessionmanager.session() as db:
        result = await run_conflict_resolution(db, repo=repo, mr_iid=mr_iid, bitrix=Bitrix())
        await db.commit()
    log_event("run_resolve_done", repo=repo, mr_iid=mr_iid, status=result.get("status"))


async def drain_outbox(ctx: dict[str, Any]) -> int:
    """Relay: ставит в очередь pending-намерения из outbox и помечает их sent.

    Job'ы идемпотентны, поэтому повторная постановка безопасна.
    """
    sent = 0
    async with sessionmanager.session() as db:
        store = BriefingStore(db)
        pending = await store.list_pending_outbox()
        for ev in pending:
            await enqueue_task(ev.job, *ev.args)
            await store.mark_outbox_sent(ev.id)
            sent += 1
        await db.commit()
    if sent:
        log_event("outbox_drained", sent=sent)
    return sent


async def _on_startup(ctx: dict[str, Any]) -> None:
    configure_logging()


class WorkerSettings:
    functions = [run_task_phase, run_command, run_fix, run_resolve]
    cron_jobs = [cron(drain_outbox, second={0, 15, 30, 45})]
    redis_settings = _redis_settings()
    max_jobs = settings.worker_concurrency
    job_timeout = settings.phase_timeout_sec
    on_startup = _on_startup
