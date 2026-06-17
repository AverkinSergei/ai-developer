import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


class _RecStore:
    """In-memory замена StateStore для проверки идемпотентности."""

    def __init__(self) -> None:
        self.seen: set[str] = set()

    async def mark_seen(self, event_id: str) -> bool:
        if event_id in self.seen:
            return False
        self.seen.add(event_id)
        return True


@pytest.fixture
def wired(monkeypatch):
    calls: list[tuple] = []

    async def fake_enqueue(*args, **kwargs):
        calls.append((args, kwargs))
        return "job-1"

    monkeypatch.setattr(settings, "bitrix_app_token", "secret")
    monkeypatch.setattr("app.webhooks.store", _RecStore())
    monkeypatch.setattr("app.webhooks.enqueue_task", fake_enqueue)
    return calls


def _payload(token="secret", event="ONTASKADD", task_id="42", ts="1700000000"):
    return {
        "auth[application_token]": token,
        "event": event,
        "data[FIELDS][ID]": task_id,
        "ts": ts,
    }


def test_bad_token_rejected(wired):
    with TestClient(app) as client:
        resp = client.post("/bitrix-webhook", data=_payload(token="wrong"))
    assert resp.status_code == 403
    assert wired == []


def test_accepts_and_enqueues(wired):
    with TestClient(app) as client:
        resp = client.post("/bitrix-webhook", data=_payload())
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert len(wired) == 1
    assert wired[0][0] == ("run_task_phase", "42", "intake")


def test_idempotent_duplicate(wired):
    with TestClient(app) as client:
        first = client.post("/bitrix-webhook", data=_payload())
        second = client.post("/bitrix-webhook", data=_payload())
    assert first.json()["status"] == "ok"
    assert second.json()["status"] == "duplicate"
    assert len(wired) == 1  # второй раз в очередь не ставим


def test_oversized_body(wired, monkeypatch):
    monkeypatch.setattr(settings, "webhook_max_body_mb", 0)
    with TestClient(app) as client:
        resp = client.post("/bitrix-webhook", data=_payload())
    assert resp.status_code == 413


def test_non_task_event_no_enqueue(wired):
    with TestClient(app) as client:
        resp = client.post("/bitrix-webhook", data=_payload(event="ONSOMETHINGELSE"))
    assert resp.status_code == 200
    assert wired == []
