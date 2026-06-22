"""Запуск проверок репозитория (test/lint/typecheck/secret_scan).

Модель угроз. `.ai-agent.yml` лежит в НЕДОВЕРЕННОМ репозитории, а запуск его тестов —
это по определению исполнение произвольного кода репозитория; это нельзя «отсанитайзить»
разбором строки команды. Поэтому сдерживаем ИЗОЛЯЦИЕЙ окружения, а не фильтрацией:

- shell=False (execve) — оболочка не интерпретирует `;|&$`, цепочки невозможны;
- минимальное окружение БЕЗ секретов сервиса (нет утечки токенов, даже если код враждебный);
- запуск в эфемерном checkout-каталоге (cwd), тайм-аут и обрезка вывода;
- белый список бинарей — лёгкий guardrail против явных footgun'ов (rm/curl/bash как точка
  входа), НЕ основная защита (python3/node всё равно исполняют произвольный код).

REAL containment в production: контейнер/namespace без сети + эфемерный checkout +
unprivileged user. Этот модуль — in-process слой; см. деплой-главу.
"""

import asyncio
import os
import shlex
import signal
from dataclasses import dataclass

from app.config import settings

# Лёгкий guardrail: явные не-инструменты не запускаем. НЕ основная защита (см. докстринг).
_BUILTIN_ALLOWED = frozenset(
    {
        "python",
        "python3",
        "pytest",
        "tox",
        "nox",
        "coverage",
        "ruff",
        "flake8",
        "black",
        "isort",
        "mypy",
        "pyright",
        "bandit",
        "pip-audit",
        "safety",
        "semgrep",
        "gitleaks",
        "trufflehog",
        "node",
        "npm",
        "npx",
        "pnpm",
        "yarn",
        "eslint",
        "tsc",
        "jest",
        "vitest",
        "go",
        "gofmt",
        "golangci-lint",
        "cargo",
        "make",
    }
)

_STATUS_PASSED = "passed"
_STATUS_FAILED = "failed"
_STATUS_REFUSED = "refused"
_STATUS_SKIPPED = "skipped"
_STATUS_TIMEOUT = "timeout"


@dataclass
class CheckResult:
    name: str
    status: str  # passed | failed | refused | skipped | timeout
    returncode: int | None = None
    output: str = ""

    @property
    def ok(self) -> bool:
        return self.status == _STATUS_PASSED


def _allowed_binaries() -> frozenset[str]:
    return _BUILTIN_ALLOWED | {b.strip() for b in settings.sandbox_allowed_binaries if b.strip()}


def _safe_env(cwd: str) -> dict[str, str]:
    """Минимальное окружение без секретов сервиса; PATH можно закрепить через конфиг."""
    return {
        "PATH": settings.sandbox_path or os.environ.get("PATH", ""),
        "HOME": cwd,
        "LANG": "C.UTF-8",
    }


def _terminate_group(proc: asyncio.subprocess.Process) -> None:
    """Убивает всю группу процессов (включая потомков), а не только прямой child."""
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except ProcessLookupError:
            pass


async def _read_capped(stream: asyncio.StreamReader, limit: int) -> tuple[bytes, bool]:
    """Читает поток с жёстким лимитом по памяти. Возвращает (данные, превышен_ли_лимит)."""
    buf = bytearray()
    over = False
    while True:
        chunk = await stream.read(65536)
        if not chunk:
            break
        room = limit - len(buf)
        if room > 0:
            buf.extend(chunk[:room])
        if len(buf) >= limit:
            over = True  # дальше не буферизуем — память ограничена
            break
    return bytes(buf), over


async def run_check(
    name: str, command: str | None, cwd: str, timeout_sec: int | None = None
) -> CheckResult:
    """Запускает одну проверку безопасно. Пустая команда — skipped, нарушение политики — refused."""
    if not settings.sandbox_isolation_confirmed:
        # Fail-closed: без подтверждённой изоляции окружения проверки не запускаем.
        return CheckResult(name, _STATUS_REFUSED, output="sandbox isolation not confirmed")
    if not command or not command.strip():
        return CheckResult(name, _STATUS_SKIPPED)
    argv = shlex.split(command)
    if not argv:
        return CheckResult(name, _STATUS_SKIPPED)
    if os.path.basename(argv[0]) not in _allowed_binaries():
        return CheckResult(name, _STATUS_REFUSED, output=f"binary '{argv[0]}' is not allowlisted")

    limit = settings.sandbox_max_output_kb * 1024
    timeout_sec = timeout_sec or settings.phase_timeout_sec
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=cwd,
            env=_safe_env(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,  # своя группа процессов -> убиваем всё дерево
        )
    except (FileNotFoundError, OSError) as exc:
        return CheckResult(name, _STATUS_REFUSED, output=f"cannot exec: {exc}")

    assert proc.stdout is not None
    try:
        output_bytes, over = await asyncio.wait_for(
            _read_capped(proc.stdout, limit), timeout=timeout_sec
        )
    except TimeoutError:
        _terminate_group(proc)
        await proc.wait()
        return CheckResult(name, _STATUS_TIMEOUT, output=f"timeout after {timeout_sec}s")

    output = output_bytes.decode("utf-8", errors="replace")
    if over:
        # Вывод превысил лимит — глушим дерево, считаем проверку проваленной.
        _terminate_group(proc)
        await proc.wait()
        return CheckResult(
            name, _STATUS_FAILED, output=output + "\n[output truncated: limit exceeded]"
        )

    returncode = await proc.wait()
    status = _STATUS_PASSED if returncode == 0 else _STATUS_FAILED
    return CheckResult(name, status, returncode=returncode, output=output)


async def run_checks(commands: dict[str, str | None], cwd: str) -> dict[str, CheckResult]:
    """Прогон набора проверок {name: command} в checkout-каталоге."""
    results: dict[str, CheckResult] = {}
    for name, command in commands.items():
        results[name] = await run_check(name, command, cwd)
    return results
