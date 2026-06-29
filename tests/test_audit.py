import io
import json
import sys

from loguru import logger

import app.audit as audit
from app.audit import configure_logging, log_event, redact


def _capture_logs(monkeypatch, *, debug: bool) -> io.StringIO:
    """Сбрасывает sink, направляет loguru в буфер и настраивает логирование."""
    audit._logging_configured = False
    monkeypatch.setattr(audit.settings, "debug", debug)
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    configure_logging()
    return buf


def test_json_sink_emits_redacted_fields(monkeypatch):
    buf = _capture_logs(monkeypatch, debug=False)
    try:
        log_event("intake_done", task_id="T-1", gitlab_token="glpat-ABCDEFGH")
    finally:
        logger.remove()
        audit._logging_configured = False
    extra = json.loads(buf.getvalue().strip().splitlines()[-1])["record"]["extra"]
    assert extra["event_type"] == "intake_done"
    assert extra["task_id"] == "T-1"
    assert extra["gitlab_token"] == "***"


def test_configure_logging_idempotent(monkeypatch):
    buf = _capture_logs(monkeypatch, debug=False)
    try:
        configure_logging()  # повторный вызов не добавляет второй sink
        log_event("go_authorized", task_id="T-2")
    finally:
        logger.remove()
        audit._logging_configured = False
    lines = [ln for ln in buf.getvalue().strip().splitlines() if ln]
    assert len(lines) == 1  # одно событие -> одна строка (sink один)


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
