"""In-memory реализации клиентов для тестов и локального e2e без внешних систем."""

import os
from typing import Any

from app.clients.protocols import LLMResponse


class FakeBitrix:
    def __init__(self, tasks: dict[str, dict[str, Any]] | None = None) -> None:
        self.tasks = tasks or {}
        self.comments: list[dict[str, Any]] = []
        self.status_notes: dict[str, str] = {}
        self.comment_authors: dict[str, str] = {}  # comment_id -> author_user_id
        self._seq = 0

    async def add_comment(self, task_id: str, text: str) -> str:
        self._seq += 1
        comment_id = f"c{self._seq}"
        self.comments.append({"id": comment_id, "task_id": task_id, "text": text})
        return comment_id

    async def get_task(self, task_id: str) -> dict[str, Any]:
        return self.tasks.get(task_id, {})

    async def get_comment_author(self, task_id: str, comment_id: str) -> str | None:
        return self.comment_authors.get(comment_id)

    async def set_status_note(self, task_id: str, note: str) -> None:
        self.status_notes[task_id] = note


class FakeGitLab:
    def __init__(self, files: dict[str, dict[str, str]] | None = None) -> None:
        # files: {repo: {path: content}}
        self.files = files or {}
        self.branches: dict[str, set[str]] = {}
        self.branch_refs: dict[tuple[str, str], str] = {}  # (repo, branch) -> ref форка
        self.commits: list[dict[str, Any]] = []
        self.mrs: list[dict[str, Any]] = []
        self.roles: dict[tuple[str, str], str] = {}  # (repo, user_id) -> role
        self._mr_seq = 0

    async def fetch_archive(self, repo: str, ref: str, dest_dir: str) -> str:
        root = os.path.join(dest_dir, repo.replace("/", "_"))
        for path, content in self.files.get(repo, {}).items():
            full = os.path.join(root, path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as fh:  # noqa: ASYNC230  (in-memory fake)
                fh.write(content)
        return root

    async def branch_exists(self, repo: str, branch: str) -> bool:
        return branch in self.branches.get(repo, set())

    async def create_branch(self, repo: str, branch: str, ref: str) -> None:
        self.branches.setdefault(repo, set()).add(branch)
        self.branch_refs[(repo, branch)] = ref

    async def commit_files(
        self, repo: str, branch: str, message: str, files: dict[str, str]
    ) -> str:
        sha = f"sha{len(self.commits) + 1}"
        self.commits.append(
            {"repo": repo, "branch": branch, "message": message, "files": files, "sha": sha}
        )
        return sha

    async def find_open_mr(self, repo: str, source_branch: str) -> dict[str, Any] | None:
        for mr in self.mrs:
            if (
                mr["repo"] == repo
                and mr["source_branch"] == source_branch
                and mr["state"] == "opened"
            ):
                return mr
        return None

    async def create_draft_mr(
        self, repo: str, source_branch: str, target_branch: str, title: str, description: str
    ) -> dict[str, Any]:
        self._mr_seq += 1
        mr = {
            "iid": str(self._mr_seq),
            "repo": repo,
            "source_branch": source_branch,
            "target_branch": target_branch,
            "title": title,
            "description": description,
            "draft": True,
            "state": "opened",
        }
        self.mrs.append(mr)
        return mr

    async def get_project_member_role(self, repo: str, user_id: str) -> str | None:
        return self.roles.get((repo, user_id))

    async def mark_mr_ready(self, repo: str, mr_iid: str, reviewer_id: str | None) -> None:
        for mr in self.mrs:
            if mr["repo"] == repo and mr["iid"] == mr_iid:
                mr["draft"] = False
                mr["reviewer_id"] = reviewer_id


class FakeLLM:
    """Возвращает заранее заданные ответы по порядку обращений."""

    def __init__(self, responses: list[str] | None = None) -> None:
        self.responses = list(responses or [])
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self, system: str, messages: list[dict[str, str]], **kwargs: Any
    ) -> LLMResponse:
        self.calls.append({"system": system, "messages": messages, "kwargs": kwargs})
        text = self.responses.pop(0) if self.responses else "{}"
        return LLMResponse(text=text, tokens_used=len(text) // 4)


class FakeGraph:
    def __init__(self, answers: dict[str, str] | None = None) -> None:
        self.answers = answers or {}

    async def query(self, question: str, budget: int = 1500) -> str:
        return self.answers.get(question, "")

    async def path(self, src: str, dst: str) -> list[str]:
        return [src, dst]

    async def explain(self, node: str) -> str:
        return self.answers.get(node, "")
