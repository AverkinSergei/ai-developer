"""Структурные логи и редакция чувствительных данных.

Из логов вырезаются токены, секреты, cookies, заголовки Authorization и PII.
Запись в таблицу audit_event добавляется на фазе 1 (после появления моделей).
"""

import re
import sys
from typing import Any

from loguru import logger

from app.config import settings

# Ключи, значения которых маскируются целиком.
_SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "set-cookie",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "openai_api_key",
    "gitlab_token",
    "gitlab_webhook_secret",
    "bitrix_app_token",
    "password",
    "secret",
    "x-gitlab-token",
    "application_token",
}

# Грубые паттерны секретов в свободном тексте.
_TOKEN_PATTERNS = [
    re.compile(r"(glpat-)[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(gh[ps]_)[A-Za-z0-9]{8,}"),
    re.compile(r"\b(sk-)[A-Za-z0-9]{8,}\b"),
    re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]{8,}", re.IGNORECASE),
]

_MASK = "***"


def redact(value: Any) -> Any:
    """Рекурсивно маскирует секреты в dict/list/str."""
    if not settings.log_redaction_enabled:
        return value
    if isinstance(value, dict):
        return {k: (_MASK if k.lower() in _SENSITIVE_KEYS else redact(v)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [redact(v) for v in value]
    if isinstance(value, str):
        out = value
        for pat in _TOKEN_PATTERNS:
            out = pat.sub(r"\1" + _MASK, out)
        return out
    return value


def log_event(event_type: str, **fields: Any) -> None:
    """Структурная запись события агентного цикла."""
    logger.bind(event_type=event_type, **redact(fields)).info(event_type)


_logging_configured = False


def configure_logging() -> None:
    """Настраивает sink loguru: JSON в проде, читаемый формат с extra в debug.

    Вызывается на старте api (lifespan) и worker (on_startup). Идемпотентна.
    В проде (serialize=True) поля, добавленные через bind в log_event, попадают
    в JSON и доступны сборщикам (Loki/ELK) и фильтрации по task_id/event_type.
    Редакция секретов уже выполнена на уровне полей в log_event.
    """
    global _logging_configured
    if _logging_configured:
        return
    logger.remove()
    level = "DEBUG" if settings.debug else "INFO"
    if settings.debug:
        logger.add(
            sys.stdout,
            level=level,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                "<level>{level: <7}</level> | {message} | {extra}"
            ),
        )
    else:
        # Структурный JSON: одна строка на событие, со всеми extra-полями.
        logger.add(sys.stdout, level=level, serialize=True)
    _logging_configured = True
