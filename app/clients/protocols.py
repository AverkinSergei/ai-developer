"""Контракты внешних зависимостей.

Реальные клиенты и Fake-реализации соблюдают эти Protocol'ы; бизнес-логика
зависит только от интерфейсов, что делает тесты детерминированными.
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class BitrixClient(Protocol):
    async def add_comment(self, task_id: str, text: str) -> str:
        """Публикует комментарий, возвращает comment_id."""
        ...

    async def get_task(self, task_id: str) -> dict[str, Any]: ...

    async def get_comment_author(self, task_id: str, comment_id: str) -> str | None:
        """Достоверный автор комментария по данным Битрикс24 (не из payload вебхука)."""
        ...

    async def set_status_note(self, task_id: str, note: str) -> None:
        """Дублирует человекочитаемый статус в задачу."""
        ...


@runtime_checkable
class GitLabClient(Protocol):
    async def fetch_archive(self, repo: str, ref: str, dest_dir: str) -> str:
        """Скачивает и распаковывает архив репо, возвращает путь к корню."""
        ...

    async def branch_exists(self, repo: str, branch: str) -> bool: ...

    async def create_branch(self, repo: str, branch: str, ref: str) -> None: ...

    async def commit_files(
        self, repo: str, branch: str, message: str, files: dict[str, str]
    ) -> str:
        """Коммитит набор файлов, возвращает sha."""
        ...

    async def find_open_mr(self, repo: str, source_branch: str) -> dict[str, Any] | None: ...

    async def create_draft_mr(
        self, repo: str, source_branch: str, target_branch: str, title: str, description: str
    ) -> dict[str, Any]: ...

    async def get_project_member_role(self, repo: str, user_id: str) -> str | None:
        """Роль пользователя в проекте (для авторизации /go)."""
        ...

    async def mark_mr_ready(self, repo: str, mr_iid: str, reviewer_id: str | None) -> None:
        """Снимает Draft и назначает reviewer. Merge остаётся за человеком."""
        ...


@runtime_checkable
class LLMClient(Protocol):
    async def complete(
        self, system: str, messages: list[dict[str, str]], **kwargs: Any
    ) -> "LLMResponse": ...


@runtime_checkable
class GraphIndex(Protocol):
    """Навигация по персистентному графу кода (graphify)."""

    async def query(self, question: str, budget: int = 1500) -> str: ...

    async def path(self, src: str, dst: str) -> list[str]: ...

    async def explain(self, node: str) -> str: ...


class LLMResponse:
    """Унифицированный ответ модели."""

    def __init__(self, text: str, tokens_used: int = 0) -> None:
        self.text = text
        self.tokens_used = tokens_used
