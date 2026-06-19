# ai-developer

Автономная AI-система разработки: задача в Битрикс24 → FastAPI-агент (брифинг, авторизация `/go`) → risk scoring + Plan Gate → Explore & Plan → кодинг → Draft MR в GitLab → CI/CD → независимый AI-review → Red Team → merge человеком-Maintainer.

Агент не мержит, не трогает protected branches и не получает production-секреты. При неопределённости процесс блокируется и передаётся человеку (fail closed).

## Стек

Python 3.14 · FastAPI · Arq (фоновые задачи) · PostgreSQL 15 (каноническое состояние) · Redis 7 (locks/idempotency/counters) · SQLAlchemy 2.0 async + Alembic · Pydantic v2 · Docker Compose.

## Локальный запуск

```bash
cp .env.example .env          # заполнить секреты
docker compose up --build     # api :8080 + worker + postgres + redis
```

Миграции: `alembic upgrade head`. Метрики Prometheus: `GET /metrics`.

Граф кода целевого репозитория (для Explore & Plan) строится офлайн:

```bash
python -m app.cli build-graph namespace/project   # → GRAPH_CACHE_DIR/<repo>/graph.json
```

(`ai-developer build-graph ...` — короткий алиас там, где пакет установлен; `python -m app.cli`
работает везде, включая контейнер с `--no-root`.)

## Production

```bash
# заполнить ./secrets/* (см. secrets/README.md), затем:
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

Секреты — через Docker secrets (читаются из `/run/secrets`), postgres/redis закрыты
в internal-сети, ingress только через reverse proxy (Caddy) с TLS и лимитом тела.

## Разработка

Тесты стора и приложение можно гонять на хосте против контейнерных БД. Dev-оверлей
публикует порты postgres/redis на localhost (подключается явно, в production не идёт):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres redis
poetry install
poetry run pytest          # тесты (стор — на реальном Postgres)
poetry run ruff check .    # линт
poetry run mypy app        # типы
```

## Структура

- `app/main.py` — FastAPI: вебхуки, `/healthz`, `/readyz`.
- `app/worker.py` — Arq worker, `enqueue_task`.
- `app/config.py` — конфигурация (env/secrets).
- `app/state.py` — Redis: locks, идемпотентность, счётчики, бюджеты, снапшоты.
- `app/db/` — async-движок и ORM-модели.
- `app/contracts.py` — контракты между модулями (risk/redteam/review/task).
- `app/audit.py` — структурные логи и редакция секретов.
- `app/clients/` — интерфейсы Bitrix/GitLab/LLM/Graph + Fake-реализации для тестов.

Модули брифинга, risk, planning, coding, reviewer, redteam, ci, preview добавляются по фазам.
