"""Бюджет диффа: калибрует автономный scope под малые изменения.

Файловые лимиты учитываются на этапе плана (risk.py), но фактический размер диффа по
сгенерированному коду — отдельный сигнал. Здесь считаем реальный дифф (added+removed по
difflib) против оригинала из чекаута. Превышение MAX_DIFF_LINES_AUTO не отменяет MR (работа
полезна человеку), но снимает авто-flip Draft→Ready: большие изменения смотрит человек.
"""

import difflib
from dataclasses import dataclass, field

from app.config import Settings, settings


@dataclass
class ScopeVerdict:
    diff_lines: int
    changed_files: int
    within_budget: bool
    reasons: list[str] = field(default_factory=list)


def changed_line_count(old: str, new: str) -> int:
    """Число изменённых строк (added+removed) в unified-диффе old→new."""
    n = 0
    for line in difflib.unified_diff(old.splitlines(), new.splitlines(), n=0):
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
            n += 1
    return n


def assess_scope(
    originals: dict[str, str],
    files: dict[str, str],
    deletions: list[str],
    *,
    settings: Settings = settings,
) -> ScopeVerdict:
    """Оценивает размер фактического диффа против бюджета автономного scope."""
    total = sum(changed_line_count(originals.get(p, ""), c) for p, c in files.items())
    total += sum(len(originals.get(p, "").splitlines()) for p in deletions)
    changed_files = len(files) + len(deletions)

    reasons: list[str] = []
    within = True
    if total > settings.max_diff_lines_auto:
        within = False
        reasons.append(f"diff {total} lines > {settings.max_diff_lines_auto}")
    if changed_files > settings.max_changed_files_medium:
        within = False
        reasons.append(f"changed files {changed_files} > {settings.max_changed_files_medium}")
    return ScopeVerdict(
        diff_lines=total, changed_files=changed_files, within_budget=within, reasons=reasons
    )
