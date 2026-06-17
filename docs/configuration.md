# Конфигурация

Все настройки — в `app/config.py` (`Settings`). Источники по приоритету: переменные
окружения → `.env` → Docker secrets (`/run/secrets/<имя_поля>`). Секреты в логи,
docker-compose и MR не попадают.

## Хранилища

| Переменная | Назначение | Дефолт |
|---|---|---|
| `BRIEFING_DB_URL` | PostgreSQL (asyncpg) | `postgresql+asyncpg://...@postgres:5432/ai_developer` |
| `REDIS_URL` | Redis (volatile state) | `redis://redis:6379/0` |

## Интеграции / секреты

| Переменная | Назначение |
|---|---|
| `OPENAI_API_KEY` | ключ LLM-провайдера |
| `OPENAI_BASE_URL` | базовый URL LLM (по умолчанию OpenAI; можно совместимый) |
| `LLM_MODEL` | модель (например `gpt-4o-mini`) |
| `GITLAB_URL` / `GITLAB_TOKEN` | API GitLab; токен роли Developer |
| `GITLAB_WEBHOOK_SECRET` | проверка `X-Gitlab-Token` |
| `GITLAB_GROUP` | namespace репозиториев |
| `BITRIX_URL` | базовый REST URL Битрикс24 (входящий вебхук) |
| `BITRIX_APP_TOKEN` | проверка вебхуков Битрикс24 |
| `BITRIX_FIELD_MAP` | маппинг нормализованный_ключ → поле задачи (UF_*) |
| `INTERNAL_API_TOKEN` | для `/internal/*` |

## Брифинг

| Переменная | Дефолт |
|---|---|
| `MAX_BRIEFING_ROUNDS` | 3 |
| `MAX_QUESTIONS_PER_ROUND` | 4 |
| `BRIEFING_IDLE_TIMEOUT_HOURS` | 72 |
| `ANSWER_EXTRACTION_CONFIDENCE_MIN` | 0.7 |
| `AI_GO_APPROVERS` | `[]` |
| `HIGH_RISK_GO_REQUIRES_MAINTAINER` | true |

## Ветвление, лимиты, контуры

| Переменная | Дефолт | Смысл |
|---|---|---|
| `DEFAULT_BASE_BRANCH` | `dev` | цель MR |
| `FORK_BASE_BRANCH` | `main` | от какой ветки форкается `auto-task-*` |
| `MAX_TOKENS_PER_TASK` | 200000 | бюджет токенов |
| `PHASE_TIMEOUT_SEC` | 600 | тайм-аут фазы |
| `MAX_AI_FIXES` | 3 | лимит автоправок |
| `MAX_CHANGED_FILES_LOW` / `_MEDIUM` | 5 / 15 | повышение риска / pre-approval |
| `MAX_DIFF_LINES_AUTO` | 500 | разбивка/approval |
| `RED_TEAM_ENABLED` | true | |
| `PREVIEW_ENABLED` | false | per-repo |

## Инфраструктура

| Переменная | Дефолт |
|---|---|
| `WORKER_CONCURRENCY` | 1 |
| `MAX_REPO_ARCHIVE_MB` / `MAX_REPO_UNPACKED_MB` | 500 / 2000 |
| `AGENT_TMP_DIR` | `/worktmp` |
| `WEBHOOK_MAX_BODY_MB` | 5 |
| `METRICS_ENABLED` | true |
| `LOG_REDACTION_ENABLED` | true |

Per-repo настройки (`.ai-agent.yml` в целевом репозитории) уточняют test-команды, protected
paths, security-sensitive globs, preview и doc-политику.
