# Production

Для боевой эксплуатации — отдельный сервер/VM, изоляция БД, reverse proxy с TLS и Docker secrets.

## Запуск

```bash
# 1) заполнить ./secrets/* (вне VCS, см. secrets/README.md)
# 2) поднять hardened-стек:
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
# 3) применить миграции:
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec api alembic upgrade head
```

## Что делает prod-оверлей

- **Секреты** — Docker secrets, читаются приложением из `/run/secrets` (переопределяют env).
  Файлы: `postgres_password`, `briefing_db_url`, `redis_url`, `gitlab_token`,
  `gitlab_webhook_secret`, `bitrix_app_token`, `openai_api_key`, `internal_api_token`.
- **Сети** — `postgres`/`redis` в `net_internal` (`internal: true`, без внешнего доступа);
  `api`/`worker` дополнительно в `net_egress` для исходящих REST.
- **Reverse proxy (Caddy)** — TLS, лимит размера тела, наружу только `/bitrix-webhook`,
  `/gitlab-webhook`, `/healthz`, `/readyz`. `/metrics` и `/internal/*` не публикуются.
- **Hardening контейнеров** — `read_only` rootfs, `tmpfs` для `/tmp`, `no-new-privileges`,
  `pids_limit`, лимиты CPU/RAM.

## Caddyfile

По умолчанию `Caddyfile` настроен на **self-signed TLS по IP** (`https://10.0.0.111`,
`tls internal`, `bind 0.0.0.0`) — для развёртывания без домена, см. [Выделенный сервер по
IP](dedicated-ip.md). Для домена замените адрес сайта на реальный домен и уберите
`bind`/`tls internal` — Caddy получит доверенный сертификат автоматически (ACME). Наружу
открыты только вебхуки и health-пробы; остальное — 404.

## Миграции и backup

- Миграции применяются командой `alembic upgrade head` (в контейнере `api`).
- Обязателен автоматический backup PostgreSQL с retention — потеря БД ломает историю
  брифингов, audit trail и состояние задач.

## Права бота в GitLab

Токен уровня Developer; push разрешён только в `auto-task-*`; `main`/`dev`/`release` —
protected, merge только Maintainers; бот не аппрувит собственный MR и не снимает обязательные
checks.

## Запуск воркеров

`worker` запускается как `arq app.worker.WorkerSettings` (включает cron `drain_outbox`).
Масштабируется горизонтально — см. [Масштабирование](scaling.md).

## Онбординг графов кода (опционально)

Графы кода для Explore & Plan строятся **офлайн** и кладутся в `GRAPH_CACHE_DIR` командой:

```bash
# в контейнере/CI — портативная форма (пакет не установлен при --no-root):
docker compose run --rm worker python -m app.cli build-graph namespace/project-a [--ref main]
# локально, где пакет установлен, доступен короткий алиас:
ai-developer build-graph namespace/project-a namespace/project-b
```

Команда скачивает архив репозитория (от `FORK_BASE_BRANCH`), запускает `GRAPH_BUILD_CMD`
(по умолчанию `graphify {path} --update --no-viz`) и кладёт `graph.json` в
`GRAPH_CACHE_DIR/<namespace_project>/graph.json`. Требуется доступ к GitLab и установленный
`graphify`.

Помимо ручного запуска, ai-developer **синхронизирует граф сам**: при выполнении задачи
граф репозитория обновляется (`GRAPH_REFRESH_ON_TASK`) или строится при отсутствии
(`GRAPH_AUTO_BUILD`). Это best-effort: при сбое сборки задача не падает — используется ранее
закэшированный граф или только safe-tools. Ручная команда полезна для предварительного
прогрева кэша и периодического обновления по cron.
