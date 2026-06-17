import contextlib

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


class _Result:
    def scalar_one_or_none(self):
        return None


class _DB:
    async def execute(self, *a, **k):
        return _Result()

    async def get(self, *a, **k):
        return None

    async def commit(self):
        pass

    async def flush(self):
        pass


class _SessionManager:
    @contextlib.asynccontextmanager
    async def session(self):
        yield _DB()


class _Store:
    def __init__(self):
        self.released = []

    async def force_release(self, key):
        self.released.append(key)


@pytest.fixture
def wired(monkeypatch):
    store = _Store()
    monkeypatch.setattr(settings, "internal_api_token", "internal-secret")
    monkeypatch.setattr("app.webhooks.sessionmanager", _SessionManager())
    monkeypatch.setattr("app.webhooks.store", store)
    return store


def test_cancel_bad_token(wired):
    with TestClient(app) as client:
        resp = client.post("/internal/tasks/B24-1/cancel", headers={"X-Internal-Token": "wrong"})
    assert resp.status_code == 403
    assert wired.released == []


def test_cancel_no_token(wired):
    with TestClient(app) as client:
        resp = client.post("/internal/tasks/B24-1/cancel")
    assert resp.status_code == 403


def test_cancel_nothing_to_cancel_releases_lock(wired):
    with TestClient(app) as client:
        resp = client.post(
            "/internal/tasks/B24-1/cancel", headers={"X-Internal-Token": "internal-secret"}
        )
    # задачи/сессии нет -> 404, но лок всё равно снят
    assert resp.status_code == 404
    assert wired.released == ["lock:task:B24-1"]
