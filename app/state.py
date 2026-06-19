"""Volatile-состояние в Redis: locks, идемпотентность, счётчики, бюджеты, снапшоты.

Redis не является источником истины. Авторитетные лимиты дублируются в БД,
чтобы сброс Redis не обходил гейты.
"""

import json
import secrets
from typing import Any

import redis.asyncio as aioredis
from redis.commands.core import AsyncScript

from app.config import settings

# Атомарное снятие лока только владельцем (token совпал).
_UNLOCK_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


class StateStore:
    def __init__(self, url: str | None = None) -> None:
        self._url = url or settings.redis_url
        self._redis: aioredis.Redis | None = None
        self._unlock: AsyncScript | None = None

    def init(self) -> None:
        self._redis = aioredis.from_url(self._url, decode_responses=True)
        self._unlock = self._redis.register_script(_UNLOCK_LUA)

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    @property
    def redis(self) -> aioredis.Redis:
        if self._redis is None:
            raise RuntimeError("StateStore is not initialized")
        return self._redis

    async def ping(self) -> bool:
        return bool(await self.redis.ping())

    # --- Локи ---
    async def acquire_lock(self, key: str, ttl_sec: int | None = None) -> str | None:
        """SET NX EX. Возвращает token владельца или None, если занято."""
        token = secrets.token_hex(16)
        ok = await self.redis.set(key, token, nx=True, ex=ttl_sec or settings.phase_timeout_sec)
        return token if ok else None

    async def release_lock(self, key: str, token: str) -> bool:
        if self._unlock is None:
            raise RuntimeError("StateStore is not initialized")
        return bool(await self._unlock(keys=[key], args=[token]))

    async def force_release(self, key: str) -> None:
        """Безусловное снятие лока — только для административной отмены задачи."""
        await self.redis.delete(key)

    # --- Идемпотентность ---
    async def mark_seen(self, event_id: str) -> bool:
        """True, если событие новое; False, если уже обработано."""
        ok = await self.redis.set(
            f"seen:event:{event_id}", "1", nx=True, ex=settings.idempotency_ttl_sec
        )
        return bool(ok)

    # --- Счётчики / бюджеты ---
    async def incr_fixes(self, mr_iid: str) -> int:
        return int(await self.redis.incr(f"fixes:mr:{mr_iid}"))

    async def add_tokens(self, task_id: str, n: int) -> int:
        return int(await self.redis.incrby(f"tokens:task:{task_id}", n))

    async def tokens_used(self, task_id: str) -> int:
        return int(await self.redis.get(f"tokens:task:{task_id}") or 0)

    # --- JSON-снапшоты ---
    async def set_snapshot(self, key: str, value: dict[str, Any]) -> None:
        await self.redis.set(key, json.dumps(value, ensure_ascii=False))

    async def get_snapshot(self, key: str) -> dict[str, Any] | None:
        raw = await self.redis.get(key)
        return json.loads(raw) if raw else None


store = StateStore()


# Хелперы имён ключей.
def lock_task(task_id: str) -> str:
    return f"lock:task:{task_id}"


def lock_briefing(task_id: str) -> str:
    return f"lock:briefing:{task_id}"


def risk_key(task_id: str) -> str:
    return f"risk:task:{task_id}"


def plan_key(task_id: str) -> str:
    return f"plan:task:{task_id}"


def redteam_key(mr_iid: str) -> str:
    return f"redteam:mr:{mr_iid}"
