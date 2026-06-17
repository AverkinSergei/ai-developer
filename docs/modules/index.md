# Обзор модулей

Модули сгруппированы по подсистемам — от приёма событий к частным фазам.

| Подсистема | Модули | Глава |
|---|---|---|
| API и оркестрация | `main`, `webhooks`, `worker`, `orchestrator` | [API и оркестрация](api-orchestration.md) |
| Брифинг и авторизация | `briefing`, `briefing_store`, `briefing_state_machine`, `answer_extractor`, `go_authorizer`, `commands`, `intake` | [Брифинг](briefing.md) |
| Риск, план, код | `risk`, `context_engine`, `planning`, `coding` | [Риск, план, код](coding.md) |
| Гейты | `reviewer`, `redteam`, `gates`, `ci`, `dod`, `preview` | [Гейты](gates.md) |
| Research | `research` | [Research](research.md) |
| Инфраструктура | `config`, `state`, `db`, `audit`, `metrics`, `workspace`, `contracts`, `clients/*` | [Инфраструктура](infrastructure.md) |

## Поток данных между подсистемами

```
webhooks ──► worker ──► orchestrator ──┬──► briefing/* (intake, брифинг, /go)
                                       └──► planning ─► coding ─► gitlab_client (Draft MR)
                                                          │
                                        reviewer / redteam / gates / ci / dod / preview
```
