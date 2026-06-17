# Развёртывание — обзор

Глава описывает разворачивание от локального ноутбука до production.

| Сценарий | Когда | Глава |
|---|---|---|
| Локально с внешними системами | разработка, проверка гипотезы | [Локально](local-external.md) |
| Production | боевая эксплуатация | [Production](production.md) |

Сопутствующее: [Требования к окружению](requirements.md), [Наблюдаемость](observability.md),
[Масштабирование](scaling.md), [Чек-лист go-live](go-live-checklist.md).

## Файлы развёртывания

| Файл | Назначение |
|---|---|
| `docker-compose.yml` | базовый стек: api / worker / postgres / redis |
| `docker-compose.dev.yml` | dev-оверлей: публикует порты БД на localhost (подключать явно) |
| `docker-compose.prod.yml` | prod-оверлей: secrets, internal-сеть, Caddy, лимиты, hardening |
| `Caddyfile` | reverse proxy: TLS, лимит тела, маршруты вебхуков |
| `secrets/` | Docker secrets (вне VCS, см. `secrets/README.md`) |

## Принцип

GitLab CI/CD — отдельный контур. ai-developer готовит MR и реагирует на результаты CI; он
**не должен** зависеть от локального GitLab Runner как обязательного компонента.
