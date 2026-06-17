"""Офлайн-построение графа кода целевого репозитория в кэш GRAPH_CACHE_DIR.

Шаги: скачать архив репозитория (от fork_base) → запустить graphify → положить
graph.json в кэш по repo. Запускается онбордингом/по расписанию, не в рантайме задачи.
"""

import asyncio
import os
import shutil
from collections.abc import Awaitable, Callable

from app.audit import log_event
from app.clients.graph import resolve_graph_path
from app.clients.protocols import GitLabClient
from app.config import Settings, settings
from app.workspace import checkout_workspace

# runner(cmd, cwd) — выполняет команду сборки графа; бросает на ненулевом коде возврата.
Runner = Callable[[str, str], Awaitable[None]]


class GraphBuildError(Exception):
    pass


async def _default_runner(cmd: str, cwd: str) -> None:
    proc = await asyncio.create_subprocess_shell(
        cmd,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await proc.communicate()
    if proc.returncode != 0:
        tail = (out or b"").decode(errors="replace")[-500:]
        raise GraphBuildError(f"graph build failed ({proc.returncode}): {tail}")


def _cache_dest(cache_dir: str, repo: str) -> str:
    return os.path.join(cache_dir, repo.replace("/", "_"), "graph.json")


async def build_repo_graph(
    repo: str,
    *,
    gitlab: GitLabClient,
    cache_dir: str | None = None,
    ref: str | None = None,
    build_cmd: str | None = None,
    runner: Runner | None = None,
) -> str:
    """Строит граф репозитория и кладёт graph.json в кэш. Возвращает путь к графу."""
    cache_dir = cache_dir or settings.graph_cache_dir
    if not cache_dir:
        raise GraphBuildError("GRAPH_CACHE_DIR не задан")
    ref = ref or settings.fork_base_branch
    build_cmd = build_cmd or settings.graph_build_cmd
    runner = runner or _default_runner

    async with checkout_workspace(f"graph-{repo.replace('/', '_')}") as ws:
        root = await gitlab.fetch_archive(repo, ref, ws)
        await runner(build_cmd.format(path=root), root)
        produced = os.path.join(root, "graphify-out", "graph.json")
        if not os.path.isfile(produced):
            raise GraphBuildError("graphify не создал graphify-out/graph.json")
        dest = _cache_dest(cache_dir, repo)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(produced, dest)

    log_event("graph_built", repo=repo, ref=ref, dest=dest)
    return dest


async def sync_repo_graph(
    repo: str,
    *,
    gitlab: GitLabClient,
    settings: Settings = settings,
    runner: Runner | None = None,
) -> str | None:
    """Синхронизирует граф репозитория перед планированием и возвращает путь к нему.

    - `GRAPH_REFRESH_ON_TASK` — обновлять граф (graphify --update) на каждом запуске;
    - `GRAPH_AUTO_BUILD` — построить при отсутствии в кэше.

    Best-effort: любой сбой сборки (нет graphify, ошибка) не роняет задачу — возвращается
    ранее закэшированный граф (возможно устаревший) либо None (тогда только safe-tools).
    """
    cache = settings.graph_cache_dir
    if not cache:
        return None
    existing = resolve_graph_path(repo, None, cache)
    need_build = settings.graph_refresh_on_task or (existing is None and settings.graph_auto_build)
    if not need_build:
        return existing
    try:
        return await build_repo_graph(repo, gitlab=gitlab, cache_dir=cache, runner=runner)
    except GraphBuildError as exc:
        log_event("graph_sync_failed", repo=repo, error=str(exc))
        return existing  # фолбэк на возможно устаревший кэш
