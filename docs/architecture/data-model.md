# Модель данных

PostgreSQL хранит каноническое состояние. Модели — в `app/db/models.py`, миграции — Alembic.

## Таблицы

| Таблица | Назначение | Особенности |
|---|---|---|
| `task_state` | состояние задачи целиком | optimistic lock (`version_id_col`); `card_snapshot` (JSONB) — полная карточка |
| `briefing_session` | каноническое хранилище брифинга | optimistic lock; partial-unique: один активный сеанс на задачу |
| `briefing_round` | неизменяемый набор вопросов | unique `(session_id, round_number)` |
| `briefing_question` | вопрос раунда | `dor_dimension` — какой пробел DoR закрывает |
| `briefing_answer` | версионируемый ответ | правка → новая строка, прежняя `superseded`; partial-unique активного |
| `go_authorization_event` | каждая попытка `/go` | `event_id` unique; partial-unique: один `authorized` на сессию |
| `outbox_event` | транзакционный outbox | намерение enqueue в одной транзакции с переходом |
| `audit_event` | append-only audit trail | редакция секретов до вставки |

## Ключевые инварианты на уровне БД

- **Один активный брифинг на задачу** — partial unique index по `task_id` (вне терминальных
  состояний).
- **Один авторизованный `/go` на сессию** — partial unique index по `session_id WHERE
  authorized = true` (гарантия single-start независимо от лока).
- **Версионирование ответов** — активный ответ один (`superseded = false`), история сохраняется.

## Общие поля сущностей брифинга

`task_id`, `repo`, `target_branch`, `author_user_id`, `created_at`, `updated_at`, `status`,
`version`, `bitrix_comment_id`.

## Redis-карта (volatile)

| Назначение | Ключ | Механизм |
|---|---|---|
| Лок задачи | `lock:task:{id}` | SET NX EX + token, compare-and-del |
| Лок брифинга | `lock:briefing:{task_id}` | SET NX EX (гонка `/go`) |
| Идемпотентность | `seen:event:{id}` | SET NX EX |
| Счётчик правок | `fixes:mr:{iid}` | INCR + label `ai-iterations::N` |
| Бюджет токенов | `tokens:task:{id}` | INCRBY vs лимит |
| Снапшоты | `risk:task:{id}`, `plan:task:{id}`, `redteam:mr:{iid}` | JSON |
