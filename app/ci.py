"""Чтение статусов GitLab CI и решения петли самоисправления.

Реагируем только на ветки auto-task-* и на actionable-сигналы (упавший pipeline,
команды @ai fix/@ai resolve). Лимит правок — MAX_AI_FIXES.
"""

from dataclasses import dataclass
from typing import Any

# Стадии, падение которых блокирует merge (безопасный baseline без .ai-agent.yml).
DEFAULT_MANDATORY_STAGES = ("tests", "lint", "secret_scan", "ai_review")

_BLOCKING_PIPELINE_STATUS = {"failed", "canceled"}
AUTO_TASK_PREFIX = "auto-task-"

# Комментарии, на которые агент не реагирует.
_NON_ACTIONABLE = ("lgtm", "looks good", "ok", "ок", "+1", "👍")


@dataclass
class PipelineEvent:
    status: str
    ref: str
    project: str
    mr_iid: str | None = None


@dataclass
class NoteEvent:
    note: str
    author_id: str
    author_username: str
    project: str
    mr_iid: str | None = None
    source_branch: str | None = None


def is_auto_task_branch(ref: str) -> bool:
    return ref.startswith(AUTO_TASK_PREFIX)


def pipeline_is_blocking(status: str) -> bool:
    return status in _BLOCKING_PIPELINE_STATUS


def is_actionable_comment(note: str) -> bool:
    """Отсекает пустое и lgtm/looks good — на такое агент не реагирует."""
    low = (note or "").strip().lower()
    if not low:
        return False
    return low not in _NON_ACTIONABLE


def parse_pipeline(payload: dict[str, Any]) -> PipelineEvent:
    attrs = payload.get("object_attributes", {})
    mr = payload.get("merge_request") or {}
    return PipelineEvent(
        status=str(attrs.get("status", "")),
        ref=str(attrs.get("ref", "")),
        project=str((payload.get("project") or {}).get("path_with_namespace", "")),
        mr_iid=str(mr["iid"]) if mr.get("iid") is not None else None,
    )


def parse_note(payload: dict[str, Any]) -> NoteEvent:
    attrs = payload.get("object_attributes", {})
    user = payload.get("user") or {}
    mr = payload.get("merge_request") or {}
    return NoteEvent(
        note=str(attrs.get("note", "")),
        author_id=str(user.get("id", "")),
        author_username=str(user.get("username", "")),
        project=str((payload.get("project") or {}).get("path_with_namespace", "")),
        mr_iid=str(mr["iid"]) if mr.get("iid") is not None else None,
        source_branch=str(mr.get("source_branch")) if mr.get("source_branch") else None,
    )


def next_fix_action(fixes_done: int, max_fixes: int) -> str:
    """fix — ещё можно править; stop — лимит исчерпан, нужен человек."""
    return "fix" if fixes_done < max_fixes else "stop"
