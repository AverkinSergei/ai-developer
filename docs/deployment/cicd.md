# CI/CD: сборка образа и деплой

Пайплайн (`.gitlab-ci.yml`) следует конвенции соседних сервисов (`crm-lead-intake`):
качество → сборка образа в GitLab Container Registry → ручной деплой на сервер через
runner, зарегистрированный на самом сервере.

```
push/MR ─► lint + typecheck + docs + test        (shared/docker runner, python-образ)
push main ─► build_image → registry               (runner ai-developer, хостовый docker)
            └► deploy_prod (manual) → 10.0.0.111   (тот же runner: pull + up -d)
```

| Стадия | Где исполняется | Когда |
|---|---|---|
| `lint`/`typecheck`/`docs`/`test` | python-образ (docker executor) | MR и `main` |
| `build_image` | runner `ai-developer` (хостовый docker) | только `main` |
| `deploy_prod` | runner `ai-developer` | только `main`, **вручную** |

## Разовая подготовка сервера

**1. Клон репозитория с секретами** (deploy работает в этом каталоге, не в чекауте CI):

```bash
sudo mkdir -p /var/www/ai-developer && sudo chown "$USER" /var/www/ai-developer
git clone git@gitlab.bpg.team:developer/microservices/ai-developer.git /var/www/ai-developer
cd /var/www/ai-developer
# заполнить secrets/* и .env (см. «Выделенный сервер по IP»); они в .gitignore и git reset их не трогает
```

**2. GitLab Runner на сервере** (docker-исполнитель с доступом к хостовому docker), тег
`ai-developer`:

```bash
# на сервере установлен gitlab-runner + docker
sudo gitlab-runner register \
  --url https://gitlab.bpg.team/ \
  --registration-token <PROJECT_TOKEN> \
  --executor docker \
  --docker-image docker:27 \
  --docker-volumes /var/run/docker.sock:/var/run/docker.sock \
  --docker-volumes /var/www/ai-developer:/var/www/ai-developer \
  --tag-list ai-developer \
  --description "ai-developer prod"
```

Монтирование сокета даёт джобам `build_image`/`deploy_prod` доступ к docker хоста;
монтирование `/var/www/ai-developer` — к каталогу с `secrets/*` и `.env`.

**3. Container Registry** включён в проекте (Deploy → Container Registry). Логин в CI —
по предопределённым `$CI_REGISTRY_USER`/`$CI_REGISTRY_PASSWORD` (job token), пуш в
`$CI_REGISTRY_IMAGE`.

## Как работает деплой

`deploy_prod` (вручную из пайплайна `main`):

1. `docker login` в registry.
2. `cd /var/www/ai-developer`, `git reset --hard $CI_COMMIT_SHA` — обновляет `docker-compose*`,
   `Caddyfile` до коммита; `secrets/*` и `.env` (в `.gitignore`) сохраняются.
3. `AI_IMAGE=$CI_REGISTRY_IMAGE`, `AI_TAG=$CI_COMMIT_SHA` — compose подставляет образ
   (`image: ${AI_IMAGE:-ai-developer}:${AI_TAG:-latest}` в `docker-compose.prod.yml`).
4. `docker compose pull api worker` → поднять `postgres`/`redis` → `alembic upgrade head`
   (миграции до приложения) → `up -d --remove-orphans` → `docker image prune -f`.

## Откат

Запустить `deploy_prod` вручную на старом коммите (Pipelines → нужный коммит → `deploy_prod`),
либо на сервере: `AI_TAG=<старый_sha> docker compose -f docker-compose.yml -f
docker-compose.prod.yml up -d`. Образы прошлых SHA лежат в registry.

## Замечания

- Локальная сборка (без CI) работает по-прежнему: `AI_IMAGE`/`AI_TAG` не заданы → дефолт
  `ai-developer:latest`, `docker compose ... up -d --build` собирает образ на месте.
- `lint`/`test` идут на docker-executor runner (python-образ + сервисы `postgres`/`redis`).
  Если в проекте только runner `ai-developer`, добавьте ему возможность брать эти джобы
  (docker executor) или вынесите на shared runners.
