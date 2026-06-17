# Конечный автомат брифинга

Модуль `app/briefing_state_machine.py`. Переходы **валидирует только сервер** — модель
лишь предлагает действие. Недопустимый переход бросает `InvalidTransition`.

## Состояния

`NEW`, `QUESTIONS_GENERATED`, `WAITING_ANSWERS`, `ANSWERS_RECEIVED`, `COMPLETENESS_CHECK`,
`NEEDS_MORE_INFO`, `READY_FOR_GO`, `GO_AUTH_CHECK`, `APPROVED`, `PLAN_GATE`
и аварийные/терминальные: `EXPIRED_WAITING_ANSWERS`, `BLOCKED_MANUAL`, `CANCELLED`, `ERROR`.

## Переходы

```
NEW → QUESTIONS_GENERATED → WAITING_ANSWERS → ANSWERS_RECEIVED → COMPLETENESS_CHECK
NEW → COMPLETENESS_CHECK                         (DoR выполнен уже на intake)
COMPLETENESS_CHECK → NEEDS_MORE_INFO → WAITING_ANSWERS
COMPLETENESS_CHECK → READY_FOR_GO → GO_AUTH_CHECK → APPROVED → PLAN_GATE
GO_AUTH_CHECK → READY_FOR_GO                     (неавторизованный /go отклонён)
WAITING_ANSWERS → EXPIRED_WAITING_ANSWERS → WAITING_ANSWERS   (reopen)
READY_FOR_GO → WAITING_ANSWERS                   (/briefing reopen)
* → BLOCKED_MANUAL | CANCELLED | ERROR           (из любого нетерминального)
```

## Заметки

- Терминальные состояния (`APPROVED`, `PLAN_GATE`, `BLOCKED_MANUAL`, `CANCELLED`, `ERROR`)
  переходов не имеют и не учитываются в уникальности активного сеанса.
- `EXPIRED_WAITING_ANSWERS` намеренно **не** терминальный: он возобновляем (`/briefing reopen`)
  и продолжает блокировать создание второго сеанса.
- Сериализация переходов: Redis `lock:briefing:{task_id}` + optimistic `version` в БД.
- Каждый переход пишет `audit_event(state_transition)`.
