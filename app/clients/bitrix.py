"""HTTP-клиент Битрикс24 (REST). Соблюдает протокол BitrixClient."""

from typing import Any

import httpx

from app.config import settings


class Bitrix:
    def __init__(self, base_url: str | None = None, timeout: float = 15.0) -> None:
        self._base = (base_url or settings.bitrix_url).rstrip("/")
        self._timeout = timeout

    async def _call(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base}/{method}.json"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()

    async def add_comment(self, task_id: str, text: str) -> str:
        data = await self._call(
            "task.commentitem.add",
            {"taskId": task_id, "fields": {"POST_MESSAGE": text}},
        )
        return str(data.get("result", ""))

    async def get_task(self, task_id: str) -> dict[str, Any]:
        data = await self._call("tasks.task.get", {"taskId": task_id})
        return data.get("result", {})

    async def get_comment_author(self, task_id: str, comment_id: str) -> str | None:
        data = await self._call("task.commentitem.get", {"taskId": task_id, "itemId": comment_id})
        result = data.get("result") or {}
        author = result.get("AUTHOR_ID") or (result.get("AUTHOR") or {}).get("ID")
        return str(author) if author else None

    async def set_status_note(self, task_id: str, note: str) -> None:
        # Человекочитаемый статус дублируется отдельным комментарием.
        await self.add_comment(task_id, note)
