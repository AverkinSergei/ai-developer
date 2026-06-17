from app.audit import redact


def test_redact_sensitive_keys():
    out = redact({"authorization": "Bearer abc", "task_id": "B24-1"})
    assert out["authorization"] == "***"
    assert out["task_id"] == "B24-1"


def test_redact_nested():
    out = redact({"headers": {"X-Gitlab-Token": "s3cret", "ok": "v"}})
    assert out["headers"]["X-Gitlab-Token"] == "***"
    assert out["headers"]["ok"] == "v"


def test_redact_token_patterns_in_text():
    out = redact("token is glpat-ABCDEFGHIJKLMNOP and sk-1234567890abcd")
    assert "glpat-ABCDEFGHIJKLMNOP" not in out
    assert "glpat-***" in out
    assert "sk-***" in out


def test_redact_list():
    out = redact([{"password": "x"}, "Bearer tok12345678"])
    assert out[0]["password"] == "***"
    assert "Bearer ***" in out[1]
