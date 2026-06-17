# Инфраструктура

## `config`

`Settings` (pydantic-settings): env + `.env` + Docker secrets (`secrets_dir=/run/secrets`).
Полный инвентарь переменных — в главе [Конфигурация](../configuration.md).

## `state`

Redis: `acquire_lock`/`release_lock` (SET NX EX + compare-and-del), `force_release`,
`mark_seen` (идемпотентность), счётчики правок и токенов, JSON-снапшоты. Только volatile.

## `db`

`base` — async `DatabaseSessionManager` + `Base`; `models` — ORM-модели (см.
[Модель данных](../architecture/data-model.md)). Миграции — Alembic.

## `audit`

Структурные логи (loguru) + редакция секретов: маскирует ключи (`authorization`, `token`,
`*_secret`, ...) и паттерны (`glpat-`, `sk-`, `Bearer ...`) в dict/list/str. Управляется
`LOG_REDACTION_ENABLED`.

## `metrics`

Prometheus-метрики: `webhooks_total`, `go_decisions_total`, `phase_errors_total`,
`phase_duration_seconds`. Эндпоинт `/metrics` (gated `METRICS_ENABLED`).

## `workspace`

`checkout_workspace` — временный изолированный каталог под `AGENT_TMP_DIR` с гарантированной
очисткой в `finally` (даже при ошибке фазы).

## `clients`

Интеграции за `Protocol`-интерфейсами (`protocols.py`), что делает тесты детерминированными:

- `bitrix` — REST Битрикс24 (`add_comment`, `get_task`, `get_comment_author`, `set_status_note`);
- `gitlab_client` — GitLab REST (archive с безопасной распаковкой `filter='data'`, ветки,
  commits, MR, notes, роли, Draft→Ready); push только в `auto-task-*`;
- `llm` — `OpenAILLM`, OpenAI-совместимый (chat completions), `base_url` настраивается;
- `fakes` — in-memory `FakeBitrix`/`FakeGitLab`/`FakeLLM`/`FakeGraph` для тестов;
- `graph` (`GraphIndex`) — навигация по персистентному графу кода (graphify) для Explore & Plan.

## `gitlab_roles`

`make_maintainer_resolver` — резолвер maintainer/owner-роли для авторизации high-risk `/go`.

## `contracts`

Pydantic-контракты межмодульного обмена (см. [Контракты](../architecture/contracts.md)).
