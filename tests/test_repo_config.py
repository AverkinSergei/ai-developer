import textwrap

from app.repo_config import load_repo_config


def test_loads_full_config(tmp_path):
    (tmp_path / ".ai-agent.yml").write_text(
        textwrap.dedent("""
        version: 1
        repo_type: python
        base_branch: dev
        commands:
          test: "pytest"
          lint: "ruff check ."
          typecheck: "mypy ."
        security:
          secret_scan: true
          dependency_scan: true
          red_team_paths:
            - "**/auth/**"
            - "**/payments/**"
        docs:
          require_for_public_api: true
        preview:
          enabled: false
        """),
        encoding="utf-8",
    )
    cfg = load_repo_config(str(tmp_path))
    assert cfg.is_default is False
    assert cfg.repo_type == "python"
    assert cfg.commands.test == "pytest"
    assert cfg.commands.typecheck == "mypy ."
    assert "**/auth/**" in cfg.security.red_team_paths


def test_missing_file_safe_default(tmp_path):
    cfg = load_repo_config(str(tmp_path))
    assert cfg.is_default is True
    assert cfg.base_branch == "dev"
    assert cfg.commands.test is None  # неизвестно — исполняемые проверки пропускаются
    assert cfg.security.secret_scan is True
    assert cfg.mandatory_baseline == ("tests", "lint", "secret_scan", "ai_review")


def test_malformed_yaml_falls_back(tmp_path):
    (tmp_path / ".ai-agent.yml").write_text("commands: [this: is, : broken", encoding="utf-8")
    cfg = load_repo_config(str(tmp_path))
    assert cfg.is_default is True  # битый файл не роняет задачу


def test_non_mapping_root_falls_back(tmp_path):
    (tmp_path / ".ai-agent.yml").write_text("- just\n- a\n- list\n", encoding="utf-8")
    cfg = load_repo_config(str(tmp_path))
    assert cfg.is_default is True


def test_partial_config_uses_defaults(tmp_path):
    (tmp_path / ".ai-agent.yml").write_text("repo_type: node\n", encoding="utf-8")
    cfg = load_repo_config(str(tmp_path))
    assert cfg.is_default is False
    assert cfg.repo_type == "node"
    assert cfg.security.secret_scan is True  # секция отсутствует -> дефолт
    assert cfg.preview.enabled is False
