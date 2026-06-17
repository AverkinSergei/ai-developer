"""Конфигурация сервиса: env / secrets и значения по умолчанию.

Секреты приходят через env (Docker secrets / Vault) и не попадают в логи,
docker-compose.yml, MR или Битрикс24.
"""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        # Docker secrets: файлы в /run/secrets/<имя_поля> переопределяют env.
        secrets_dir="/run/secrets",
    )

    app_name: str = "ai-developer"
    app_env: str = "prod"  # test / dev / prod
    debug: bool = False

    default_base_branch: str = "dev"  # цель MR по умолчанию
    fork_base_branch: str = "main"  # от какой ветки отпочковывается auto-task-* (исходник MR)

    # --- Хранилища ---
    # Каноническое хранилище брифинга, аудита и состояния задач.
    briefing_db_url: str = Field(
        default="postgresql+asyncpg://ai_developer:ai_developer@postgres:5432/ai_developer"
    )
    # Redis — только volatile state: locks, idempotency, counters, budgets, snapshots.
    redis_url: str = Field(default="redis://redis:6379/0")

    # --- Брифинг ---
    max_briefing_rounds: int = 3
    max_questions_per_round: int = 4
    min_questions_per_round: int = 2
    briefing_idle_timeout_hours: int = 72
    answer_extraction_confidence_min: float = 0.7
    ai_go_approvers: list[str] = Field(default_factory=list)  # allowlist user/group id
    high_risk_go_requires_maintainer: bool = True

    # --- Интеграции / секреты ---
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    # Маппинг нормализованный_ключ -> поле задачи Битрикс24 (UF_* специфичны для портала).
    bitrix_field_map: dict[str, str] = Field(default_factory=dict)
    gitlab_url: str = ""
    gitlab_token: str = ""  # least privilege, роль Developer
    gitlab_webhook_secret: str = ""
    gitlab_group: str = ""
    bitrix_url: str = ""
    bitrix_app_token: str = ""
    ci_bot_username: str = "ai-developer-bot"
    internal_api_token: str = ""  # для /internal/* endpoint'ов

    # --- Лимиты ---
    max_tokens_per_task: int = 200_000
    phase_timeout_sec: int = 600
    max_ai_fixes: int = 3
    max_changed_files_low: int = 5  # выше -> risk_level=medium
    max_changed_files_medium: int = 15  # выше -> human pre-approval
    max_diff_lines_auto: int = 500  # выше -> разбивка/approval

    # --- Контуры ---
    red_team_enabled: bool = True
    preview_enabled: bool = False  # per-repo

    # --- Инфраструктура ---
    worker_concurrency: int = 1
    max_repo_archive_mb: int = 500
    max_repo_unpacked_mb: int = 2000
    agent_tmp_dir: str = "/worktmp"
    # Кэш персистентных графов кода (graphify). Пусто = только локальный graphify-out/.
    graph_cache_dir: str = ""
    # Команда построения графа; {path} подставляется корнем чекаута репозитория.
    graph_build_cmd: str = "graphify {path} --update --no-viz"
    agent_tmp_cleanup_ttl_hours: int = 24
    webhook_max_body_mb: int = 5
    webhook_allowed_ips: list[str] = Field(default_factory=list)
    healthcheck_timeout_sec: int = 5
    metrics_enabled: bool = True
    log_redaction_enabled: bool = True

    @field_validator("ai_go_approvers", mode="after")
    @classmethod
    def _drop_empty_approvers(cls, v: list[str]) -> list[str]:
        # Пустая запись в allowlist не должна авторизовать пользователя с пустым id.
        return [x.strip() for x in v if x and x.strip()]

    @property
    def idempotency_ttl_sec(self) -> int:
        """TTL для ключей идемпотентности вебхуков."""
        return self.briefing_idle_timeout_hours * 3600


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
