"""Временный изолированный checkout репозитория с гарантированной очисткой.

Каталог создаётся под AGENT_TMP_DIR и удаляется в finally — даже при ошибке фазы.
"""

import contextlib
import os
import shutil
import tempfile
from collections.abc import AsyncIterator

from app.config import settings


@contextlib.asynccontextmanager
async def checkout_workspace(task_id: str, base_dir: str | None = None) -> AsyncIterator[str]:
    base = base_dir or settings.agent_tmp_dir
    os.makedirs(base, exist_ok=True)
    path = tempfile.mkdtemp(prefix=f"agent_{task_id}_", dir=base)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
