# Наблюдаемость

## Метрики

Эндпоинт `/metrics` (Prometheus, gated `METRICS_ENABLED`). Базовые серии:

- `ai_developer_webhooks_total{source,outcome}` — принятые/отклонённые вебхуки;
- `ai_developer_go_decisions_total{decision}` — решения по `/go`;
- `ai_developer_phase_errors_total{phase,error_type}` — ошибки фаз;
- `ai_developer_phase_duration_seconds{phase}` — длительность фаз.

`/metrics` наружу не публикуется — скрейпится во внутренней сети.

## Логи

Структурные JSON-логи (loguru) с редакцией секретов. Ключевые события: `intake_done`,
`go_authorized`/`go_rejected`, `self_fix_enqueued`/`self_fix_limit_reached`, `plan_done`,
`outbox_drained`, `graph_built`/`graph_sync_failed`/`graph_autobuild_failed`, переходы FSM
(`audit_event`). Запрещено логировать токены, cookies, заголовки Authorization и сырые PII.

## Health

- `/healthz` — liveness.
- `/readyz` — readiness: проверяет связность с Redis и PostgreSQL.

## Минимальный набор алертов

Зависшие задачи (рост длительности фаз), рост очереди воркеров, error rate внешних API,
превышение лимитов (токены/фазы), достижение `MAX_AI_FIXES`. Рекомендуемый стек — Prometheus +
Grafana + Loki/ELK; минимум — structured logs + healthcheck + алерты по ошибкам фаз.
