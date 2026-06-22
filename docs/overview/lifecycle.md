# Жизненный цикл задачи

Два обязательных управляющих слоя: **Risk & Plan Gate** до кодинга и **Red Team Gate**
для задач повышенного риска.

```
Битрикс24 задача
  → Intake + валидация            (main, webhooks, intake)
  → Брифинг / уточняющие вопросы   (briefing, answer_extractor)
  → Definition of Ready
  → /go + авторизация              (go_authorizer)
  → Risk scoring                   (risk)
  → Explore & Plan                 (context_engine, planning)
  → Plan Gate
  → Кодинг с прогоном проверок репо (coding: цикл до verified)
  → Бюджет scope                   (scope: малый дифф → Ready, крупный → Draft)
  → Commit + Draft MR              (gitlab_client, orchestrator)
  → CI/CD checks                   (ci)
  → Независимый AI-review          (reviewer)
  → Red Team Gate (если нужно)     (redteam, gates)
  → Preview / smoke (если нужно)   (preview)
  → Human review
  → Merge by Maintainer            (человек)
  → Post-merge мониторинг + rollback note
```

## Этапы и кто блокирует переход

| Этап | Исполнитель | Выход | Блокирует |
|---|---|---|---|
| Intake | FastAPI-агент | валидированная карточка | да |
| Briefing | Briefing + постановщик | ответы, `/go` | да |
| DoR | оркестратор | задача готова к плану | да |
| Risk scoring | классификатор | `risk_level`, `red_team_required` | да для high/blocked |
| Explore & Plan | Coder | план, тест-план, doc impact | да |
| Plan Gate | политика / человек для high | разрешение на кодинг | да |
| Coding | Coder | код + docs, прогнанные проверки (`verified`) | да при ошибке |
| Scope budget | `scope` | малый дифф → авто Ready; крупный → Draft | да для авто-flip |
| CI/CD | GitLab CI | тесты, линт, security | да для обязательных |
| AI-review | Reviewer | line-комментарии / вердикт | да |
| Red Team | Red Team | PASS/FAIL/NEED_HUMAN | да |
| Human review | reviewer/maintainer | approve или правки | да |

## Ветвление

Ветка `auto-task-{task_id}` **отпочковывается от `main`** (`fork_base_branch`), а MR
нацелен в `dev` (`target_branch`). Повторный запуск переиспользует ветку и MR.
