from app.config import Settings


def test_defaults():
    s = Settings()
    assert s.default_base_branch == "dev"
    assert s.max_briefing_rounds == 3
    assert s.max_tokens_per_task == 200_000
    assert s.max_ai_fixes == 3
    assert s.red_team_enabled is True


def test_idempotency_ttl_from_idle_timeout():
    s = Settings(briefing_idle_timeout_hours=2)
    assert s.idempotency_ttl_sec == 7200


def test_env_override(monkeypatch):
    monkeypatch.setenv("MAX_AI_FIXES", "5")
    monkeypatch.setenv("PREVIEW_ENABLED", "true")
    s = Settings()
    assert s.max_ai_fixes == 5
    assert s.preview_enabled is True
