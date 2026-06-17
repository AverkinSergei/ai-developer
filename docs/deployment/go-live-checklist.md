# Чек-лист go-live

## Инфраструктура

- [ ] Выделенный сервер/VM; ресурсы по профилю (см. [Требования](requirements.md)).
- [ ] `docker-compose.prod.yml` поднят; `api`/`worker`/`postgres`/`redis`/`proxy` healthy.
- [ ] Caddy с реальным доменом и TLS; наружу открыты только вебхуки и health.
- [ ] Автоматический daily backup PostgreSQL + retention.
- [ ] Prometheus скрейпит `/metrics`; алерты настроены.

## Секреты и доступы

- [ ] Все файлы `./secrets/*` заполнены и вне VCS.
- [ ] `GITLAB_TOKEN` — роль Developer, least privilege; push только в `auto-task-*`.
- [ ] `main`/`dev`/`release` — protected; merge только Maintainers.
- [ ] `INTERNAL_API_TOKEN` задан; `/internal/*` недоступен снаружи.
- [ ] `LOG_REDACTION_ENABLED=true`.

## Интеграции

- [ ] Вебхук GitLab → `/gitlab-webhook` (secret token, Comments + Pipeline events).
- [ ] Исходящий вебхук Битрикс24 → `/bitrix-webhook` (`ONTASKADD`/`ONTASKUPDATE`/`ONTASKCOMMENTADD`, `application_token`).
- [ ] `BITRIX_URL` (входящий вебхук) с правами на задачи/комментарии.
- [ ] `BITRIX_FIELD_MAP` сопоставлен с UF_*-полями портала.
- [ ] Тестовая задача проходит путь intake → брифинг → `/go` → Draft MR.

## Эксплуатационный долг (доделать перед полной автономностью)

- [ ] Реальная логика `run_fix` (по MR-diff + findings reviewer) и `run_resolve` (conflict
      resolution) — сейчас стабы.
- [ ] Нагрузочный замер на целевом `WORKER_CONCURRENCY`.
- [ ] Дашборды Grafana/Loki поверх `/metrics` и логов.
