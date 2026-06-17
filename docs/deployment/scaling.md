# Масштабирование

Основной параметр масштабирования — число параллельных активных задач.

## Оценка ресурсов

```
required_tmp_disk    ≈ concurrent_tasks × max_repo_unpacked_size × 2
required_worker_ram  ≈ concurrent_tasks × ram_per_task + base_worker_ram
recommended_workers  ≈ min(concurrent_tasks, безопасный_параллелизм_по_rate_limit_API)
```

## Стратегия

- На старте — `WORKER_CONCURRENCY=1..3`, собрать метрики duration/tokens/tmp_disk/memory,
  затем повышать параллелизм.
- При росте нагрузки масштабируются **worker**-контейнеры (горизонтально); `api` обычно
  остаётся лёгким и масштабируется позже.
- Отдельные PostgreSQL, Redis и observability; per-worker tmp volumes.

## Kubernetes

Имеет смысл после пилота и стабилизации нагрузки: autoscaling воркеров, централизованные
secrets, rolling updates, сетевые политики. Требует зрелой DevOps-практики.

## Конкуренция и идемпотентность

Горизонтальное масштабирование безопасно: per-task локи, идемпотентность вебхуков,
DB-инвариант «один авторизованный `/go` на сессию» и транзакционный outbox исключают
двойной старт и lost-start даже при нескольких воркерах.
