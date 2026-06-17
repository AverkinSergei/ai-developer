# Локально с внешними Битрикс24 и GitLab

Главная сложность локального ноутбука — у него нет публичного адреса, а внешним системам
нужно достучаться вебхуками. Решается туннелем (cloudflared/ngrok). Исходящие REST-вызовы
(к GitLab/Bitrix/LLM) идут с ноутбука напрямую — туннель нужен только для входящих вебхуков.

```
Bitrix24 / GitLab  ──webhooks──►  туннель (https)  ──►  ноутбук: api:8080 → worker + pg + redis
                                                              └──REST──► GitLab / Bitrix / LLM
```

## Шаги

**1. Поднять стек + БД**
```bash
cp .env.example .env          # заполнить (см. ниже)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
docker compose exec api alembic upgrade head
```

**2. Заполнить `.env`**

- `OPENAI_API_KEY`, при необходимости `OPENAI_BASE_URL`, `LLM_MODEL`.
- GitLab (us→GitLab): `GITLAB_URL`, `GITLAB_TOKEN` (роль Developer), `GITLAB_GROUP`,
  `GITLAB_WEBHOOK_SECRET`.
- Bitrix (us→Bitrix): `BITRIX_URL` — **входящий** вебхук Битрикс
  (`https://<портал>.bitrix24.ru/rest/<user_id>/<code>/`, права на задачи и комментарии),
  `BITRIX_APP_TOKEN`.
- `BITRIX_FIELD_MAP` — соответствие нормализованных ключей вашим UF_*-полям задач, например:
  `{"task_type":"UF_AUTO_123","target_repo":"UF_AUTO_124","business_goal":"UF_AUTO_125","acceptance_criteria":"UF_AUTO_126","affected_area":"UF_AUTO_127","reviewer":"UF_AUTO_128"}`.

**3. Туннель** (даёт публичный HTTPS):
```bash
cloudflared tunnel --url http://localhost:8080      # → https://<random>.trycloudflare.com = BASE
```

**4. Зарегистрировать вебхуки (внешние → нам)**

- GitLab (Settings → Webhooks): URL `BASE/gitlab-webhook`, Secret token = `GITLAB_WEBHOOK_SECRET`,
  триггеры **Comments** и **Pipeline events**.
- Битрикс24 (Разработчикам → Исходящий вебхук): обработчик `BASE/bitrix-webhook`, события
  `ONTASKADD`, `ONTASKUPDATE`, `ONTASKCOMMENTADD`; `application_token` = `BITRIX_APP_TOKEN`.

**5. Проверить**
```bash
curl https://<tunnel>/healthz     # {"status":"ok"}
curl https://<tunnel>/readyz      # Redis + Postgres
docker compose logs -f api worker
```
Создайте тестовую задачу → в логах: `intake_done`, раунд брифинга, на `/go` — `go_authorized`
и запись в outbox; relay поставит фазу `plan` → Draft MR в вашем GitLab, ссылка вернётся в Б24.

!!! warning "Безопасность туннеля"
    Туннель на `:8080` откроет наружу **все** маршруты, включая `/metrics` и `/internal/*`.
    Направляйте туннель на **Caddy** из `docker-compose.prod.yml` (он публикует только вебхуки и
    health) либо ограничьте доступ. Обязательно задайте `INTERNAL_API_TOKEN`.
