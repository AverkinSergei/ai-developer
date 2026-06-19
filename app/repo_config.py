"""Загрузка per-repo конфигурации `.ai-agent.yml` из корня checkout.

Уточняет команды проверок, security-sensitive пути, doc- и preview-политику. При
отсутствии файла используется безопасный дефолт. Парсинг — fail-safe: битый файл не
роняет задачу, а откатывается к дефолту.

ВНИМАНИЕ: `.ai-agent.yml` лежит в самом (недоверенном) репозитории, поэтому его
`commands` — недоверенный ввод. Их исполнение допустимо только в изолированной песочнице
(sandbox executor), а не напрямую.
"""

import os

import yaml
from loguru import logger
from pydantic import BaseModel, Field

REPO_CONFIG_FILENAME = ".ai-agent.yml"
# Безопасный baseline, если конфигурации нет (см. также §11 спеки).
_DEFAULT_MANDATORY = ("tests", "lint", "secret_scan", "ai_review")


class RepoCommands(BaseModel):
    test: str | None = None
    lint: str | None = None
    typecheck: str | None = None


class RepoSecurity(BaseModel):
    secret_scan: bool = True
    dependency_scan: bool = True
    red_team_paths: list[str] = Field(default_factory=list)


class RepoDocs(BaseModel):
    require_for_public_api: bool = True


class RepoPreview(BaseModel):
    enabled: bool = False


class RepoConfig(BaseModel):
    version: int = 1
    repo_type: str = "unknown"
    base_branch: str = "dev"
    commands: RepoCommands = Field(default_factory=RepoCommands)
    security: RepoSecurity = Field(default_factory=RepoSecurity)
    docs: RepoDocs = Field(default_factory=RepoDocs)
    preview: RepoPreview = Field(default_factory=RepoPreview)
    # True, если конфиг не найден и применён дефолт.
    is_default: bool = False

    @property
    def mandatory_baseline(self) -> tuple[str, ...]:
        return _DEFAULT_MANDATORY


def load_repo_config(checkout_root: str) -> RepoConfig:
    """Читает `.ai-agent.yml` из корня checkout. Нет файла/битый — безопасный дефолт."""
    path = os.path.join(checkout_root, REPO_CONFIG_FILENAME)
    if not os.path.isfile(path):
        logger.warning("repo_config: {} отсутствует, безопасный дефолт", REPO_CONFIG_FILENAME)
        return RepoConfig(is_default=True)
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if not isinstance(data, dict):
            raise ValueError("корень .ai-agent.yml должен быть объектом")
        return RepoConfig(**data)
    except (OSError, yaml.YAMLError, ValueError, TypeError) as exc:
        logger.warning("repo_config: не удалось разобрать {} ({}), дефолт", path, exc)
        return RepoConfig(is_default=True)
