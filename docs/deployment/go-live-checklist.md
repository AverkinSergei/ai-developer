# Чек-лист go-live

## Инфраструктура

- [ ] Выделенный сервер/VM; ресурсы по профилю (см. [Требования](requirements.md)).
- [ ] `docker-compose.prod.yml` поднят; `api`/`worker`/`postgres`/`redis`/`proxy` healthy.
- [ ] Caddy: TLS (домен через ACME либо self-signed по IP) или HTTP в изолированной внутренней сети — см. [Выделенный сервер по IP](dedicated-ip.md); наружу открыты только вебхуки и health.
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

- [ ] Полное разрешение конфликтов MR: `run_resolve` сейчас ограниченный хендлер —
      маршрутизирует к человеку, 3-way слияние не выполняется (нужен git-checkout вместо
      архива). `run_fix` уже реализован (агентный цикл правок ветки).
- [ ] Живой пилот на 10–20 реальных тикетах + go/no-go-метрики.
- [ ] Нагрузочный замер на целевом `WORKER_CONCURRENCY`.
- [ ] Дашборды Grafana/Loki поверх `/metrics` и логов.
