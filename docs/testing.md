# Тестирование

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres redis
poetry install
poetry run pytest          # тесты (стор/оркестратор — на реальном Postgres)
poetry run ruff check .    # линт
poetry run ruff format --check .
poetry run mypy app        # типы
```

## Подход

- **Fakes как фундамент** — `FakeBitrix`/`FakeGitLab`/`FakeLLM`/`FakeGraph` за `Protocol`-
  интерфейсами делают тесты детерминированными, без внешних трат и флака.
- **Стор и оркестратор** тестируются на **реальном Postgres** (фикстура `db_session` —
  транзакция с откатом, схему не трогает); если БД недоступна — тесты пропускаются.
- **Блокирующие пути** — тесты проверяют именно отказ/блокировку (битый токен → 403, oversized
  → 413, недопустимый переход FSM, fail-closed вердикты), а не только happy path.

## Что покрыто

Конфиг и редакция логов; контракты и валидаторы; FSM брифинга (легальные/нелегальные
переходы); стор и версионирование ответов; авторизация `/go` (включая high-risk и анти-спуфинг
автора); песочница (traversal/symlink/.env/`O_NOFOLLOW`); risk scoring (EN+RU триггеры);
E2E-срез до Draft MR (ветка от `main`); петля self-fix (лимиты, авторизация); review/redteam
(fail-closed, блокировка); DoD; research/preview/cancel; outbox; сквозная обвязка
intake → брифинг → `/go` → план → Draft MR.

CI (`.gitlab-ci.yml`) поднимает postgres+redis и гоняет lint + tests.
