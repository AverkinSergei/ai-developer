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
- `graph` — `GraphifyGraph` (реализует `GraphIndex`): читает персистентный `graph.json`
  graphify и даёт `query`/`path`/`explain` без внешних процессов. Путь к графу резолвится
  через `resolve_graph_path` (кэш `GRAPH_CACHE_DIR` по repo → `<checkout>/graphify-out/`).
  Если графа нет — объект «недоступен», и Explore & Plan опирается только на safe-tools.

## `gitlab_roles`

`make_maintainer_resolver` — резолвер maintainer/owner-роли для авторизации high-risk `/go`.

## `repo_config`

`load_repo_config(checkout_root)` — читает `.ai-agent.yml` из корня репо (команды
`test/lint/typecheck`, `security`, `docs`, `preview`); fail-safe (нет файла/битый YAML →
безопасный дефолт). Команды из конфига — **недоверенный ввод** (файл в репо), исполняются
только через `sandbox_exec`.

## `sandbox_exec`

`run_check`/`run_checks` — запуск проверок репо в изоляции: `shell=False`, минимальное
окружение без секретов сервиса, своя группа процессов (`killpg` по тайм-ауту), потоковое
чтение вывода с лимитом памяти, allowlist бинарей (guardrail). Fail-closed: без
`SANDBOX_ISOLATION_CONFIRMED` ничего не запускает. Запуск тестов репо = исполнение
произвольного кода, поэтому реальная изоляция (контейнер без сети) — обязательна в production.

## `graph_build`

Построение/обновление графа кода: `build_repo_graph` (checkout → `GRAPH_BUILD_CMD` → копия в
`GRAPH_CACHE_DIR`) и `sync_repo_graph` (на задаче: refresh при `GRAPH_REFRESH_ON_TASK`,
build при `GRAPH_AUTO_BUILD`; best-effort — сбой не роняет задачу).

## `cli`

CLI `ai-developer` (argparse). Команда `build-graph <repo...> [--ref]` строит графы целевых
репозиториев в `GRAPH_CACHE_DIR` офлайн. Entrypoint — `[tool.poetry.scripts]`.

## `contracts`

Pydantic-контракты межмодульного обмена (см. [Контракты](../architecture/contracts.md)).
