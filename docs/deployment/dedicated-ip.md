# Выделенный сервер по IP (без домена)

Развёртывание на отдельном сервере, доступном только по приватному IP (например
`10.0.0.111`), без доменного имени. Подходит, когда GitLab и Bitrix24 **self-hosted в той
же корпоративной сети** и могут слать вебхуки прямо на этот IP.

```
GitLab (self-hosted) ─webhooks─┐
Bitrix24 (self-hosted) ─webhooks┼─► https://10.0.0.111  (Caddy, self-signed TLS)
                                │        └─► api:8080 → worker + postgres + redis
сервер ─REST(outbound)──────────┴─► GitLab / Bitrix / LLM
```

!!! warning "Приватный IP требует достижимости из той же сети"
    `10.0.0.111` — адрес RFC1918, он **не маршрутизируется** из интернета. Облачный
    Bitrix24 (`*.bitrix24.ru`) до него не достучится — для облака нужен публичный ingress
    или VPN. Эта инструкция рассчитана на self-hosted GitLab/Bitrix во внутренней сети.

## 1. Секреты

Production-оверлей читает секреты из файлов `./secrets/*` (вне VCS, см. `secrets/README.md`).
Создайте на сервере по одному значению в файле:

```bash
cd ai-developer
umask 077
printf '%s' 'СИЛЬНЫЙ_ПАРОЛЬ'                       > secrets/postgres_password
printf '%s' 'postgresql+asyncpg://ai_developer:СИЛЬНЫЙ_ПАРОЛЬ@postgres:5432/ai_developer' > secrets/briefing_db_url
printf '%s' 'redis://redis:6379/0'                  > secrets/redis_url
printf '%s' 'glpat-…'                               > secrets/gitlab_token
printf '%s' 'СЛУЧАЙНЫЙ_СЕКРЕТ_ВЕБХУКА'              > secrets/gitlab_webhook_secret
printf '%s' 'APP_TOKEN_ИЗ_БИТРИКС'                  > secrets/bitrix_app_token
printf '%s' 'sk-…'                                  > secrets/openai_api_key
printf '%s' "$(openssl rand -hex 32)"               > secrets/internal_api_token
```

Пароль в `postgres_password` и в `briefing_db_url` должен совпадать.

**Права на файлы секретов.** Приложение работает в контейнере под `appuser` (uid `10001`),
а compose монтирует файлы секретов с их хостовыми правами (опции `uid/gid/mode` у `secrets:`
в не-swarm режиме игнорируются). Файлы `0600`, созданные вашим пользователем, контейнер не
прочитает (`Permission denied: /run/secrets/...`). Отдайте их uid контейнера:

```bash
sudo chown 10001:10001 secrets/*
sudo chmod 0400 secrets/*
```

Так секреты читает только контейнер; обычные хост-пользователи — нет.

## 2. Несекретный конфиг — `.env`

Секреты идут через `secrets/` (они переопределяют env), остальное — в `.env`:

```bash
cp .env.example .env
```

Заполнить в `.env`: `GITLAB_URL`, `GITLAB_GROUP`, `BITRIX_URL` (URL входящего вебхука
self-hosted портала), `CI_BOT_USERNAME`, при необходимости `OPENAI_BASE_URL`/`LLM_MODEL`.
**Обязательно** `BITRIX_FIELD_MAP` под UF_*-поля задач. `SANDBOX_ISOLATION_CONFIRMED`
оставьте `false` на первом прогоне (MR выйдут unverified, но безопасно).

## 3. TLS под IP

`Caddyfile` уже настроен на `https://10.0.0.111` с `tls internal` (self-signed) и
`bind 0.0.0.0`. Если IP другой — поправьте адрес сайта в `Caddyfile`. Caddy сам выпустит
сертификат с этим IP в SAN при старте.

## 4. Поднять стек

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec api alembic upgrade head
```

`postgres`/`redis` закрыты в internal-сети; наружу смотрит только Caddy (`443`/`80`).

## 5. Зарегистрировать вебхуки

- **GitLab** (Settings → Webhooks): URL `https://10.0.0.111/gitlab-webhook`, Secret token =
  значение `secrets/gitlab_webhook_secret`, триггеры **Comments** и **Pipeline events**.
  Снимите галку **Enable SSL verification** (сертификат self-signed).
- **Bitrix24** (Разработчикам → Исходящий вебхук): обработчик
  `https://10.0.0.111/bitrix-webhook`, события `ONTASKADD`, `ONTASKUPDATE`,
  `ONTASKCOMMENTADD`; `application_token` = значение `secrets/bitrix_app_token`.

!!! note "Self-signed и проверка SSL на стороне Bitrix"
    Self-hosted Bitrix шлёт вебхук через curl и может проверять сертификат. Если запрос
    отклоняется по SSL — добавьте корневой CA Caddy в доверенные на сервере Bitrix:
    ```bash
    docker compose -f docker-compose.yml -f docker-compose.prod.yml \
      exec proxy cat /data/caddy/pki/authorities/local/root.crt
    ```
    Скопируйте этот корень в trust store сервера Bitrix (для облака этот вариант не подходит).

## 6. Проверка

```bash
curl -k https://10.0.0.111/healthz     # {"status":"ok"}
curl -k https://10.0.0.111/readyz      # ready: true (Redis + Postgres)
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f api worker
```

Создайте тестовую задачу в Б24 → в логах: `intake_done`, раунд брифинга; на `/go` —
`go_authorized` + запись в outbox; relay поставит фазу `plan` → Draft MR в GitLab.

## 7. Ограничить доступ по сети

`/metrics` и `/internal/*` Caddy наружу не публикует (открыты только вебхуки и health).
Поле `WEBHOOK_ALLOWED_IPS` приложением **не enforce-ится**, поэтому ограничивайте источники
на уровне фаервола: разрешите вход на `443` только с адресов GitLab и сервера Bitrix.

```bash
# пример (ufw): только эти источники к 443
ufw allow from <GITLAB_IP> to any port 443 proto tcp
ufw allow from <BITRIX_IP> to any port 443 proto tcp
ufw deny 443/tcp
```

Обязательно задайте `internal_api_token` (шаг 1) — он защищает `/internal/*`.
