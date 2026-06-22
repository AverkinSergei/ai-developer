# Гейты качества и безопасности

## `reviewer`

Независимый AI-review диффа. На входе только задача, acceptance criteria, diff, результаты
тестов и docs — **без хода рассуждений Coder**. Нераспознанный вывод модели → fail-closed
`NEED_HUMAN_REVIEW`. `autofixable` отбирает замечания high/blocker для self-fix.

## `redteam`

Red Team-контур: поиск способов эксплуатации, а не улучшение стиля. `redteam_required` —
матрица триггеров (EN + RU: auth, payments, PII, webhook, upload, migration, deps, secrets,
prompt и т.д.) плюс риск high/blocked и ручной запуск. Нераспознанный вывод → fail-closed
`NEED_HUMAN_SECURITY_REVIEW`.

## `gates`

Сведение вердиктов: `merge_decision` (объединяет `merge_blocked` review и Red Team) и
`run_review_gates` (review всегда; Red Team — по триггерам/риску/ручному запуску).

## `scope`

Бюджет автономного scope по **фактическому** диффу. `changed_line_count` считает реальный
дифф (added+removed по `difflib`) против оригинала из чекаута, поэтому правка двух строк в
большом файле остаётся малой. `assess_scope` сверяет суммарный дифф с `MAX_DIFF_LINES_AUTO`
и число файлов с `MAX_CHANGED_FILES_MEDIUM`. Превышение **не отменяет MR** (работа полезна
человеку), но снимает авто-flip Draft→Ready: `ready = verified AND not blocked AND
within_scope`. Причина превышения попадает в сводный `[AI_MR_SUMMARY]`. Так агент берёт на
себя только малые механические диффы, крупные изменения уходят на ревью человеку.

## `ci`

Разбор событий GitLab CI: `parse_pipeline`/`parse_note`, блокирующие статусы,
actionable-фильтр (игнор `lgtm`/пустых), `next_fix_action` (fix/stop по `MAX_AI_FIXES`).

## `dod`

Definition of Done — чек-лист готовности MR к приёмке: acceptance сопоставлены, CI зелёный,
AI-review без блокеров, Red Team пройден (если требуется), тесты/approved-причина, docs по
`doc_impact`, нет high/critical уязвимостей и утечек секретов, есть `rollback_note`, есть
approve человека. Возвращает `{met, unmet[]}`.

## `preview`

`preview_required` — нужен ли preview/smoke (флаг `preview=yes` или high-risk
frontend/api/integration при `PREVIEW_ENABLED`); `run_smoke` — точка для реальных проверок.
