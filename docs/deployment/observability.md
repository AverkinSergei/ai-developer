# Наблюдаемость

## Метрики

Эндпоинт `/metrics` (Prometheus, gated `METRICS_ENABLED`). Базовые серии:

- `ai_developer_webhooks_total{source,outcome}` — принятые/отклонённые вебхуки;
- `ai_developer_go_decisions_total{decision}` — решения по `/go`;
- `ai_developer_phase_errors_total{phase,error_type}` — ошибки фаз;
- `ai_developer_phase_duration_seconds{phase}` — длительность фаз.

`/metrics` наружу не публикуется — скрейпится во внутренней сети.

### Сбор через Prometheus

`/metrics` отдаёт `api` на порту `8080` и через Caddy не публикуется, поэтому Prometheus
скрейпит его изнутри внутренней сети docker по имени сервиса `api:8080` (пока
`METRICS_ENABLED=true`).

В репозитории есть готовые `prometheus.yml` (конфиг скрейпа, target `api:8080`),
`docker-compose.monitoring.yml` (Prometheus + Grafana в той же сети `net_internal`, UI на
localhost сервера) и каталог `grafana/` с provisioning — источник данных Prometheus и
дашборд «AI-developer — обзор» подключаются автоматически. Мониторинг поднимается одной
командой поверх prod-оверлея:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  -f docker-compose.monitoring.yml up -d prometheus grafana
```

UI наружу не публикуются — доступ с рабочей машины по SSH-туннелю (задайте
`GRAFANA_ADMIN_PASSWORD` в `.env`):

```bash
ssh -L 9090:127.0.0.1:9090 -L 3000:127.0.0.1:3000 <сервер>
# Prometheus: http://localhost:9090  (Status -> Targets: ai-developer = UP)
# Grafana:    http://localhost:3000  (admin / GRAFANA_ADMIN_PASSWORD)
#   датасорс и дашборд уже provisioned: Dashboards -> ai-developer -> «AI-developer — обзор»
```

Дашборд `grafana/dashboards/ai-developer.json` (панели: p95 длительности фаз, rate ошибок
фаз, вебхуки, решения `/go`, суммарный rate ошибок) редактируемый — дополняйте под себя.

Быстрая проверка эндпоинта без Prometheus (изнутри сети `api`):

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec api \
  python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8080/metrics').read().decode()[:600])"
```

Примеры PromQL:

```promql
# частота ошибок по фазам
sum by (phase) (rate(ai_developer_phase_errors_total[5m]))
# p95 длительности фазы
histogram_quantile(0.95, sum by (le, phase) (rate(ai_developer_phase_duration_seconds_bucket[5m])))
# приём/отклонение вебхуков
sum by (source, outcome) (rate(ai_developer_webhooks_total[5m]))
# решения по /go за час
sum by (decision) (rate(ai_developer_go_decisions_total[1h]))
```

## Логи

Логирование настраивается `audit.configure_logging()` на старте `api` (lifespan) и `worker`
(`on_startup`). В production (`DEBUG=false`) — структурные JSON-логи loguru (`serialize=True`)
в stdout: одна строка на событие со всеми полями в `record.extra`. В `DEBUG=true` — читаемый
текстовый формат с теми же полями. Секреты вырезаются на уровне полей в `log_event`
(управляется `LOG_REDACTION_ENABLED`); запрещено логировать токены, cookies, заголовки
Authorization и сырые PII.

Ключевые события: `intake_done`, `go_authorized`/`go_rejected`,
`self_fix_enqueued`/`self_fix_limit_reached`, `plan_done`, `outbox_drained`,
`graph_built`/`graph_sync_failed`/`graph_autobuild_failed`, переходы FSM (`audit_event`).

Фильтрация по полю (JSON-формат):

```bash
docker compose ... logs --no-color worker \
  | jq -c 'select(.record.extra.task_id == "<TASK_ID>")'
```

## Health

- `/healthz` — liveness.
- `/readyz` — readiness: проверяет связность с Redis и PostgreSQL.

## Минимальный набор алертов

Зависшие задачи (рост длительности фаз), рост очереди воркеров, error rate внешних API,
превышение лимитов (токены/фазы), достижение `MAX_AI_FIXES`. Рекомендуемый стек — Prometheus +
Grafana + Loki/ELK; минимум — structured logs + healthcheck + алерты по ошибкам фаз.
