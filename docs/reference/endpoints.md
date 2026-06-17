# Эндпоинты

| Метод | Путь | Назначение | Доступ |
|---|---|---|---|
| POST | `/bitrix-webhook` | события задач Б24: создание/обновление, `/go`, команды | подпись `application_token` |
| POST | `/gitlab-webhook` | MR comments, pipeline status, `@ai fix`/`@ai resolve` | подпись `X-Gitlab-Token` |
| GET | `/healthz` | liveness probe | публичный |
| GET | `/readyz` | readiness: связность Redis/PostgreSQL | публичный |
| GET | `/metrics` | Prometheus-метрики | только внутренняя сеть |
| POST | `/internal/tasks/{id}/cancel` | служебная отмена in-flight задачи | `INTERNAL_API_TOKEN` |

Все write-эндпоинты проверяют подпись/токен, работают асинхронно и возвращают быстрый
acknowledgement; тяжёлая работа уходит в фон с блокировкой задачи в Redis.

В production через reverse proxy наружу публикуются только `/bitrix-webhook`,
`/gitlab-webhook`, `/healthz`, `/readyz`. `/metrics` и `/internal/*` остаются внутренними.
