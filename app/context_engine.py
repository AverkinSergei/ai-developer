"""Безопасные инструменты обхода распакованного репозитория: list_dir, grep, read_file.

Все пути нормализуются и проверяются на принадлежность корню checkout. Запрещены
абсолютные пути, path traversal, symlink-escape, чтение .env/секретов и служебных
каталогов. Содержимое репозитория считается недоверенными данными.
"""

import fnmatch
import os
import re
import stat
from dataclasses import dataclass

# Имена/глобы, чтение которых запрещено.
_DENIED_NAMES = {".env", ".git", ".hg", ".svn", "id_rsa", "id_dsa", ".netrc", ".pgpass"}
_DENIED_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".secret")
_DENIED_PREFIXES = (".env.",)

_DEFAULT_MAX_READ_BYTES = 1_000_000
_DEFAULT_GREP_LIMIT = 200


class SandboxError(Exception):
    """Нарушение границ песочницы."""


@dataclass
class GrepHit:
    path: str  # относительный путь от корня
    line_no: int
    line: str


def _is_denied(name: str) -> bool:
    low = name.lower()
    if low in _DENIED_NAMES:
        return True
    if low.endswith(_DENIED_SUFFIXES):
        return True
    return low.startswith(_DENIED_PREFIXES)


def is_safe_repo_path(path: str) -> bool:
    """Путь репо-относительный, без абсолюта/`..`/denied-сегментов. Для проверки путей,
    предложенных моделью (план/код), до записи в коммит."""
    if not path or os.path.isabs(path):
        return False
    norm = os.path.normpath(path)
    parts = norm.split(os.sep)
    if norm.startswith("..") or ".." in parts:
        return False
    return not any(_is_denied(p) for p in parts)


class ContextEngine:
    def __init__(self, root: str, max_read_bytes: int = _DEFAULT_MAX_READ_BYTES) -> None:
        self._root = os.path.realpath(root)
        self._max_read_bytes = max_read_bytes

    def _resolve(self, path: str) -> str:
        """Возвращает абсолютный realpath внутри корня или бросает SandboxError."""
        if os.path.isabs(path):
            raise SandboxError("absolute path is not allowed")
        candidate = os.path.realpath(os.path.join(self._root, path))
        # realpath раскрывает symlink — выход за корень (в т.ч. через symlink) отсекается.
        if candidate != self._root and not candidate.startswith(self._root + os.sep):
            raise SandboxError("path escapes repository root")
        # Запрет на denied-компоненты в любом сегменте пути.
        rel = os.path.relpath(candidate, self._root)
        if rel != ".":
            for part in rel.split(os.sep):
                if _is_denied(part):
                    raise SandboxError(f"access to '{part}' is denied")
        return candidate

    def _relpath(self, abspath: str) -> str:
        return os.path.relpath(abspath, self._root)

    def list_dir(self, path: str = ".") -> list[str]:
        target = self._resolve(path)
        if not os.path.isdir(target):
            raise SandboxError("not a directory")
        out = []
        for name in sorted(os.listdir(target)):
            if _is_denied(name):
                continue
            full = os.path.join(target, name)
            out.append(name + ("/" if os.path.isdir(full) else ""))
        return out

    def _open_regular(self, target: str) -> int:
        """Открывает обычный файл без следования по symlink, проверяя тип/размер по fd."""
        try:
            fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW)
        except OSError as exc:
            raise SandboxError("cannot open (symlink or missing)") from exc
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                raise SandboxError("not a file")
            if st.st_size > self._max_read_bytes:
                raise SandboxError("file too large")
        except BaseException:
            os.close(fd)
            raise
        return fd

    def read_file(self, path: str) -> str:
        target = self._resolve(path)
        fd = self._open_regular(target)
        with os.fdopen(fd, encoding="utf-8", errors="replace") as fh:
            return fh.read()

    def grep(
        self, pattern: str, glob: str | None = None, limit: int = _DEFAULT_GREP_LIMIT
    ) -> list[GrepHit]:
        rx = re.compile(pattern)
        hits: list[GrepHit] = []
        for dirpath, dirnames, filenames in os.walk(self._root):
            # Не заходим в denied-каталоги.
            dirnames[:] = [d for d in dirnames if not _is_denied(d)]
            for fname in filenames:
                if _is_denied(fname):
                    continue
                if glob and not fnmatch.fnmatch(fname, glob):
                    continue
                full = os.path.join(dirpath, fname)
                if os.path.islink(full):
                    continue
                rel = self._relpath(full)
                try:
                    fd = self._open_regular(full)
                except SandboxError:
                    continue
                read_bytes = 0
                with os.fdopen(fd, encoding="utf-8", errors="replace") as fh:
                    for i, line in enumerate(fh, start=1):
                        read_bytes += len(line)
                        if read_bytes > self._max_read_bytes:
                            break  # файл вырос во время обхода — обрезаем
                        if rx.search(line):
                            hits.append(GrepHit(rel, i, line.rstrip("\n")))
                            if len(hits) >= limit:
                                return hits
        return hits
