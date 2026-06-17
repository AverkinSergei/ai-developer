# Брифинг и авторизация

## `intake`

Разбор постановки: `parse_text_tags` (теги `[tests/docs/preview/security/context]`),
`missing_required_fields` (обязательные поля по типу задачи), `build_task_card`. Маппинг
полей Битрикс24 (UF_*) задаётся конфигом `bitrix_field_map`.

## `briefing`

Генерация вопросов (LLM + шаблонный fallback по незаполненным полям), `completeness_ready`,
рендер комментария раунда `[AI_BRIEFING]`. Модуль **не** принимает решений о переходах и
правах — только готовит вопросы и текст.

## `briefing_store`

Каноническое хранилище: CRUD сеанса/раундов/вопросов, **версионирование ответов** (правка →
новая строка, прежняя `superseded`), переходы через FSM, `to_contract()`, транзакционный
outbox (`add_outbox`/`list_pending_outbox`/`mark_outbox_sent`).

## `briefing_state_machine`

Конечный автомат (см. [Архитектуру](../architecture/state-machine.md)). Серверная валидация
переходов; `assert_transition` бросает `InvalidTransition` на недопустимый переход.

## `answer_extractor`

Сопоставление ответов с вопросами: структурированный разбор `A1/A2 → вопрос по порядковому
номеру` (confidence 1.0) и fallback на модель. confidence модели клампится в `[0,1]`; ответы
ниже порога `ANSWER_EXTRACTION_CONFIDENCE_MIN` не принимаются.

## `go_authorizer`

Чистая авторизация `/go`. Совпадение по Bitrix `user_id` (не по имени). Приоритет ролей:
`maintainer > reviewer > responsible_user > creator > ai_go_approvers`. Для high-risk задач
(`HIGH_RISK_GO_REQUIRES_MAINTAINER`) требуется maintainer или reviewer. Пустой `user_id` не
совпадает ни с одним правилом.

## `repo_planner`

`classify_repos` — бот сам определяет, в каких репозиториях задачи нужны изменения (MR), а
какие нужны только для контекста, и сверяет это со списками постановщика. При несоответствиях
(`mismatches`) intake публикует advisory-комментарий `[AI_REPO_CHECK]` в задачу. Это
**подсказка, а не смена scope**: бот не меняет молча, в каких репозиториях делать MR — это
решение человека; работает по указанным спискам.

## `commands`

Парсер команд из комментариев: `/go`, `/briefing answer|status|reopen|cancel|skip`,
`@ai status|stop|retry|resolve|fix|redteam`. Распознаются только в начале комментария;
обычный текст командой не считается.
