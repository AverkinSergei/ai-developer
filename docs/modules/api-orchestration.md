# API и оркестрация

## `main`

FastAPI-приложение: lifespan (инициализация БД и Redis), эндпоинты `/healthz`, `/readyz`,
`/metrics` (gated `METRICS_ENABLED`); подключает роутер вебхуков. Тяжёлая работа в
request-потоке не выполняется — только быстрый ack.

## `webhooks`

Роутер приёма событий.

- `POST /bitrix-webhook` — проверка `auth[application_token]` (constant-time), лимит размера
  тела, идемпотентность (`seen:event`), маршрутизация: события задач → intake; комментарии →
  команды. **Автор команды перепроверяется через Bitrix API** (`get_comment_author`),
  а не берётся из payload (анти-спуфинг).
- `POST /gitlab-webhook` — проверка `X-Gitlab-Token`, идемпотентность по `X-Gitlab-Event-UUID`;
  Pipeline Hook (failed на `auto-task-*`) → петля self-fix; Note Hook (`@ai fix`/`@ai resolve`,
  только maintainer/owner).
- `POST /internal/tasks/{id}/cancel` — internal-token, снятие лока, перевод задачи в `CANCELLED`.

`/go` авторизуется **синхронно** под `lock:briefing` до постановки фоновой задачи.

## `worker`

Фоновый worker на **Arq**. `enqueue_task` — единая точка постановки (движок очереди
заменяем). Функции: `run_task_phase` (диспетчер `intake`/`plan`), `run_command` (ответы
брифинга + `finalize_round`), `run_fix`/`run_resolve` (петля self-fix), `drain_outbox`
(relay транзакционного outbox, cron каждые 15 с).

## `orchestrator`

Бизнес-оркестрация поверх стора, клиентов и FSM:

- `intake_task` — карточка из полей Битрикс + теги → брифинг или `READY_FOR_GO`; при
  нескольких репозиториях запускает классификацию (`repo_planner`) и постит advisory
  `[AI_REPO_CHECK]` при несоответствиях;
- `handle_answers` + `finalize_round` — приём ответов и completeness-проверка;
- `handle_go` — авторизация `/go`, запись события, переход в `APPROVED`, запись намерения в outbox;
- `run_coding_slice` — план → код → ветка `auto-task-*` (от main) → Draft MR для одного репо;
- `execute_plan` — проходит по всем change-репозиториям задачи (`all_repos`), делает **по
  Draft MR на каждый**, строит общие контекстные графы (`context_only_repos`) и публикует
  **сводный комментарий `[AI_MR_SUMMARY]`** по всем MR в Б24;
- `finalize_mr` — снятие Draft и назначение reviewer (merge — за человеком).
