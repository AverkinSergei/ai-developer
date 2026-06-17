# Контракты

Канонические Pydantic-модели межмодульного обмена — `app/contracts.py`.

## RiskPlanGate

Выход `planning`. Поля: `risk_level (low|medium|high|blocked)`, `risk_reasons[]`,
`red_team_required`, `human_preapproval_required`, `context_files[]`,
`changes[]{path, action(create|update|delete), rationale}`, `test_plan[]`,
`doc_impact(yes|no)`, `doc_skip_reason`, `rollback_note`, `out_of_scope[]`.

Валидаторы: `doc_skip_reason` обязателен при `doc_impact=no`; `risk_level=high` принудительно
включает `red_team_required` и `human_preapproval_required`.

## RedTeamResult

Выход `redteam`. `verdict (PASS|PASS_WITH_NOTES|FAIL|NEED_HUMAN_SECURITY_REVIEW)`,
`max_severity`, `findings[]{title, severity, affected_files[], exploit_scenario,
recommended_fix, merge_blocking}`. Свойство `merge_blocked`: FAIL /
NEED_HUMAN_SECURITY_REVIEW / любой high|critical → блокирует.

## AIReviewVerdict

Выход `reviewer`. `verdict (PASS|PASS_WITH_NOTES|FAIL|NEED_HUMAN_REVIEW)`,
`comments[]{file, line, severity(low|medium|high|blocker), body}`. Свойство `merge_blocked`:
FAIL / NEED_HUMAN_REVIEW / любой high|blocker.

## TaskCard

Карточка задачи: `task_id` (ограниченный charset — попадает в имя ветки), `task_type`,
`target_repo`, `target_branch`, `business_goal`, `acceptance_criteria`, `affected_area[]`,
`risk_hint`, `reviewer`, `author_user_id`, теги `tests`/`docs`/`preview`/`security`,
`context_keywords[]`.

**Несколько репозиториев:** `target_repos[]` — дополнительные репозитории **для изменений**
(по одному Draft MR на каждый); `context_repos[]` — **read-only** репозитории только для
контекста (участвуют в Explore & Plan через граф, но MR в них не делается). Свойства:
`all_repos` (где делаются MR: основной + дополнительные, без дублей) и `context_only_repos`
(контекст за вычетом change-репозиториев).

## BriefingCommand / BriefingSessionContract

`BriefingCommand` — разобранная команда (`go`, `briefing_answer`, `briefing_status`,
`briefing_reopen`, `briefing_cancel`, `briefing_skip`, `ai_*`).
`BriefingSessionContract` — сериализация сеанса (`session_id`, `state`, `rounds_count`,
`allowed_go_users`, `accepted_answers`, `open_questions`, `go_event`).
