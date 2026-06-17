# secrets/

Docker secrets для production-оверлея (`docker-compose.prod.yml`). Каждый файл —
одна строка-значение, монтируется в `/run/secrets/<имя>` и читается приложением
через `secrets_dir` (переопределяет env). **В VCS не коммитить** (см. .gitignore).

Нужные файлы:

- `postgres_password` — пароль PostgreSQL
- `briefing_db_url` — `postgresql+asyncpg://ai_developer:<pwd>@postgres:5432/ai_developer`
- `redis_url` — `redis://redis:6379/0`
- `gitlab_token` — токен GitLab (Developer, least privilege)
- `gitlab_webhook_secret` — секрет проверки X-Gitlab-Token
- `bitrix_app_token` — секрет проверки вебхуков Битрикс24
- `openai_api_key` — ключ LLM-провайдера
- `internal_api_token` — токен для `/internal/*`

Для зрелого окружения вместо файлов — Vault/SOPS с инъекцией в `/run/secrets`.
