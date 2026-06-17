"""Разбор и валидация постановки задачи из Битрикс24.

Обязательные данные берутся из нормализованных полей задачи; текст задачи даёт
опциональные теги-модификаторы. Маппинг Bitrix UF_* -> нормализованные ключи —
ответственность config/клиента (подключается позже).
"""

import re

from app.contracts import TaskCard

CODE_TYPES = frozenset({"feature", "bugfix", "refactor"})
VALID_TASK_TYPES = frozenset(
    {"feature", "bugfix", "refactor", "research", "review", "security_review"}
)

# Теги в тексте: [tests: required], [docs: auto], [preview: yes], [security: yes], [context: a, b]
_TAG_RE = re.compile(r"\[(tests|docs|preview|security|context)\s*:\s*([^\]]*)\]", re.IGNORECASE)


def parse_text_tags(text: str) -> dict:
    """Извлекает теги-модификаторы из текста задачи."""
    out: dict = {}
    for key, raw in _TAG_RE.findall(text or ""):
        key = key.lower()
        val = raw.strip()
        if key == "tests":
            out["tests"] = val.split("-")[0].strip().lower() or None
        elif key == "docs":
            out["docs"] = val.split("-")[0].strip().lower() or None
        elif key == "preview":
            out["preview"] = val.lower() == "yes"
        elif key == "security":
            out["security"] = val.lower() == "yes"
        elif key == "context":
            out["context_keywords"] = [k.strip() for k in val.split(",") if k.strip()]
    return out


def required_fields_for(task_type: str) -> list[str]:
    """Обязательные нативные поля по типу задачи."""
    base = ["task_type", "target_repo", "target_branch", "affected_area"]
    if task_type in CODE_TYPES:
        base += ["business_goal", "reviewer"]
    if task_type in ("feature", "bugfix"):
        base += ["acceptance_criteria"]
    return base


def missing_required_fields(raw: dict) -> list[str]:
    """Список незаполненных обязательных полей. Пустые строки/списки считаются отсутствующими."""
    task_type = (raw.get("task_type") or "").strip()
    if task_type not in VALID_TASK_TYPES:
        return ["task_type"]
    missing = []
    for field in required_fields_for(task_type):
        val = raw.get(field)
        if val is None or (isinstance(val, str) and not val.strip()) or val == []:
            missing.append(field)
    return missing


def build_task_card(raw: dict, text: str = "") -> TaskCard:
    """Собирает TaskCard из нормализованных полей и тегов текста.

    Вызывать только когда missing_required_fields пуст.
    """
    data = {
        "task_id": raw["task_id"],
        "task_type": raw["task_type"],
        "target_repo": raw["target_repo"],
        "target_branch": raw.get("target_branch") or "dev",
        "business_goal": raw.get("business_goal", ""),
        "acceptance_criteria": raw.get("acceptance_criteria", ""),
        "affected_area": raw.get("affected_area") or [],
        "risk_hint": raw.get("risk_hint") or "low",
        "reviewer": raw.get("reviewer"),
        "author_user_id": raw.get("author_user_id", ""),
    }
    data.update(parse_text_tags(text))
    return TaskCard(**data)
