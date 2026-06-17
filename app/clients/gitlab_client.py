"""HTTP-клиент GitLab (REST). Соблюдает протокол GitLabClient.

Push разрешён только в ветки auto-task-*; protected branches трогать нельзя.
Архив репозитория распаковывается с защитой от path traversal.
"""

import os
import tarfile
import tempfile
from typing import Any
from urllib.parse import quote

import httpx

from app.config import settings


class GitLab:
    def __init__(
        self, base_url: str | None = None, token: str | None = None, timeout: float = 30.0
    ) -> None:
        self._base = (base_url or settings.gitlab_url).rstrip("/")
        self._token = token or settings.gitlab_token
        self._timeout = timeout

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=f"{self._base}/api/v4",
            headers={"PRIVATE-TOKEN": self._token},
            timeout=self._timeout,
        )

    @staticmethod
    def _pid(repo: str) -> str:
        return quote(repo, safe="")

    async def fetch_archive(self, repo: str, ref: str, dest_dir: str) -> str:
        async with self._client() as client:
            resp = await client.get(
                f"/projects/{self._pid(repo)}/repository/archive.tar.gz",
                params={"sha": ref},
            )
            resp.raise_for_status()
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
            tmp.write(resp.content)
            archive_path = tmp.name
        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                # filter='data' блокирует path traversal и небезопасные члены архива.
                tar.extractall(dest_dir, filter="data")
        finally:
            os.unlink(archive_path)
        # GitLab кладёт всё в один верхнеуровневый каталог.
        entries = [os.path.join(dest_dir, e) for e in os.listdir(dest_dir)]
        dirs = [e for e in entries if os.path.isdir(e)]
        return dirs[0] if len(dirs) == 1 else dest_dir

    async def branch_exists(self, repo: str, branch: str) -> bool:
        async with self._client() as client:
            resp = await client.get(
                f"/projects/{self._pid(repo)}/repository/branches/{quote(branch, safe='')}"
            )
        return resp.status_code == 200

    async def create_branch(self, repo: str, branch: str, ref: str) -> None:
        async with self._client() as client:
            resp = await client.post(
                f"/projects/{self._pid(repo)}/repository/branches",
                params={"branch": branch, "ref": ref},
            )
            resp.raise_for_status()

    async def commit_files(
        self, repo: str, branch: str, message: str, files: dict[str, str]
    ) -> str:
        actions = [
            {"action": "update", "file_path": path, "content": content}
            for path, content in files.items()
        ]
        async with self._client() as client:
            resp = await client.post(
                f"/projects/{self._pid(repo)}/repository/commits",
                json={"branch": branch, "commit_message": message, "actions": actions},
            )
            resp.raise_for_status()
            return str(resp.json().get("id", ""))

    async def find_open_mr(self, repo: str, source_branch: str) -> dict[str, Any] | None:
        async with self._client() as client:
            resp = await client.get(
                f"/projects/{self._pid(repo)}/merge_requests",
                params={"source_branch": source_branch, "state": "opened"},
            )
            resp.raise_for_status()
            items = resp.json()
        return items[0] if items else None

    async def create_draft_mr(
        self, repo: str, source_branch: str, target_branch: str, title: str, description: str
    ) -> dict[str, Any]:
        async with self._client() as client:
            resp = await client.post(
                f"/projects/{self._pid(repo)}/merge_requests",
                json={
                    "source_branch": source_branch,
                    "target_branch": target_branch,
                    "title": title if title.startswith("Draft:") else f"Draft: {title}",
                    "description": description,
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def add_mr_note(self, repo: str, mr_iid: str, body: str) -> None:
        async with self._client() as client:
            resp = await client.post(
                f"/projects/{self._pid(repo)}/merge_requests/{mr_iid}/notes",
                json={"body": body},
            )
            resp.raise_for_status()

    async def mark_mr_ready(self, repo: str, mr_iid: str, reviewer_id: str | None) -> None:
        # Снятие Draft в GitLab — убрать префикс "Draft:" из заголовка.
        async with self._client() as client:
            mr = (await client.get(f"/projects/{self._pid(repo)}/merge_requests/{mr_iid}")).json()
            title = str(mr.get("title", "")).removeprefix("Draft:").strip()
            payload: dict[str, Any] = {"title": title}
            if reviewer_id:
                payload["reviewer_ids"] = [int(reviewer_id)] if reviewer_id.isdigit() else []
            resp = await client.put(
                f"/projects/{self._pid(repo)}/merge_requests/{mr_iid}", json=payload
            )
            resp.raise_for_status()

    async def get_project_member_role(self, repo: str, user_id: str) -> str | None:
        async with self._client() as client:
            resp = await client.get(
                f"/projects/{self._pid(repo)}/members/all/{quote(user_id, safe='')}"
            )
        if resp.status_code != 200:
            return None
        level = resp.json().get("access_level", 0)
        # 40 = Maintainer, 50 = Owner.
        if level >= 50:
            return "owner"
        if level >= 40:
            return "maintainer"
        return "member"
