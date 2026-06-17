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

Замените `example.com` на реальный домен — Caddy получит TLS автоматически. Наружу открыты
только вебхуки и health-пробы; остальное — 404.

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
