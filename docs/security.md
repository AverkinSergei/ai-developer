# Безопасность

Система проходила два Red Team-ревью (контур брифинга/`/go` и песочница); все
CRITICAL/HIGH-находки закрыты.

## Подпись и идемпотентность вебхуков

- Битрикс24: `auth[application_token]` сверяется constant-time (`hmac.compare_digest`),
  пустой токен → отказ (fail-closed).
- GitLab: `X-Gitlab-Token`; идемпотентность по `X-Gitlab-Event-UUID`.
- Лимит размера тела до парсинга (`WEBHOOK_MAX_BODY_MB`).

## Авторизация действий

- `/go` авторизуется синхронно по Bitrix `user_id` (не по имени), под `lock:briefing`.
  Автор команды **перепроверяется через Bitrix API**, а не берётся из payload (анти-спуфинг).
- High-risk `/go` требует maintainer/reviewer.
- `@ai fix`/`@ai resolve` — только maintainer/owner проекта.
- `/internal/*` — отдельный `INTERNAL_API_TOKEN`.

## Песочница Explore & Plan

`context_engine` запрещает абсолютные пути, path traversal, symlink-escape (файл и каталог),
чтение `.env`/секретов/`.git`. Чтение — `O_NOFOLLOW` + `fstat` (TOCTOU-safe). Содержимое
репозитория и комментариев считается **недоверенными данными**; системные инструкции агента
не переопределяются текстом из файлов (prompt injection). Уровень риска и пути изменений
валидируются сервером, а не берутся у модели.

## Fail-closed гейты

Вердикты `reviewer`/`redteam` при нераспознанном выводе модели → `NEED_HUMAN_*` (блокируют
merge). DB-инварианты гарантируют один авторизованный `/go` на сессию и один активный брифинг
на задачу. Транзакционный outbox исключает lost-start.

## Секреты и логи

Секреты — через Docker secrets / Vault, не в git и не в docker-compose. Логи проходят
редакцию (`LOG_REDACTION_ENABLED`): маскируются токены, cookies, заголовки Authorization и PII.
Агент не получает production-секреты и не подключается к production-БД.
