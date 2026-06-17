import contextlib

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.go_authorizer import GoDecision
from app.main import app


class _Store:
    async def mark_seen(self, event_id: str) -> bool:
        return True

    async def acquire_lock(self, key: str, ttl_sec=None) -> str | None:
        return "tok"

    async def release_lock(self, key: str, token: str) -> bool:
        return True


class _DummyDB:
    async def commit(self) -> None:
        pass


class _SessionManager:
    @contextlib.asynccontextmanager
    async def session(self):
        yield _DummyDB()


class _Bitrix:
    """Достоверный автор приходит отсюда, а не из payload вебхука."""

    def __init__(self, author: str | None = "u-real") -> None:
        self.author = author
        self.posted: list[tuple] = []

    async def get_comment_author(self, task_id: str, comment_id: str) -> str | None:
        return self.author

    async def add_comment(self, task_id: str, text: str) -> str:
        self.posted.append((task_id, text))
        return "c-out"


def _comment_payload(message, token="secret", task_id="42", author="u-spoof", comment_id="c9"):
    return {
        "auth[application_token]": token,
        "event": "ONTASKCOMMENTADD",
        "data[FIELDS][TASK_ID]": task_id,
        "data[FIELDS][AUTHOR_ID]": author,  # подменяемое поле — должно игнорироваться
        "data[FIELDS][ID]": comment_id,
        "data[FIELDS][POST_MESSAGE]": message,
    }


@pytest.fixture
def wired(monkeypatch):
    enq: list[tuple] = []
    seen_user: list[str] = []
    bx = _Bitrix()

    async def fake_enqueue(*args, **kwargs):
        enq.append(args)
        return "job"

    monkeypatch.setattr(settings, "bitrix_app_token", "secret")
    monkeypatch.setattr("app.webhooks.store", _Store())
    monkeypatch.setattr("app.webhooks.sessionmanager", _SessionManager())
    monkeypatch.setattr("app.webhooks.enqueue_task", fake_enqueue)
    monkeypatch.setattr("app.webhooks.bitrix_client", bx)
    return enq, seen_user, bx


def _patch_go(monkeypatch, decision, seen_user):
    async def fake_handle_go(
        db, *, task_id, user_id, event_id, resolve_maintainer=None, source_comment_id=None
    ):
        seen_user.append(user_id)
        return decision

    monkeypatch.setattr("app.webhooks.handle_go", fake_handle_go)


def test_go_authorized_no_direct_enqueue(wired, monkeypatch):
    # Кодинг ставит relay из outbox, а не вебхук напрямую.
    enq, seen_user, bx = wired
    _patch_go(monkeypatch, GoDecision(True, "creator", "authorized", False, {}), seen_user)
    with TestClient(app) as client:
        resp = client.post("/bitrix-webhook", data=_comment_payload("/go"))
    assert resp.status_code == 200
    assert seen_user == ["u-real"]
    assert enq == []
    assert bx.posted == []


def test_author_comes_from_bitrix_not_payload(wired, monkeypatch):
    enq, seen_user, bx = wired
    bx.author = "u-real"
    _patch_go(monkeypatch, GoDecision(True, "creator", "authorized", False, {}), seen_user)
    with TestClient(app) as client:
        client.post("/bitrix-webhook", data=_comment_payload("/go", author="u-spoof"))
    # handle_go получил достоверного автора, а не подменённый AUTHOR_ID из payload.
    assert seen_user == ["u-real"]


def test_unverified_author_no_action(wired, monkeypatch):
    enq, seen_user, bx = wired
    bx.author = None  # Битрикс не подтвердил автора
    _patch_go(monkeypatch, GoDecision(True, "creator", "authorized", False, {}), seen_user)
    with TestClient(app) as client:
        client.post("/bitrix-webhook", data=_comment_payload("/go"))
    assert seen_user == []
    assert enq == []


def test_go_rejected_posts_comment(wired, monkeypatch):
    enq, seen_user, bx = wired
    _patch_go(
        monkeypatch, GoDecision(False, "insufficient_rights", "rejected", False, {}), seen_user
    )
    with TestClient(app) as client:
        resp = client.post("/bitrix-webhook", data=_comment_payload("/go"))
    assert resp.status_code == 200
    assert enq == []
    assert len(bx.posted) == 1
    assert "отклонена" in bx.posted[0][1]


def test_plain_comment_no_action(wired, monkeypatch):
    enq, seen_user, bx = wired
    _patch_go(monkeypatch, GoDecision(True, "creator", "authorized", False, {}), seen_user)
    with TestClient(app) as client:
        resp = client.post("/bitrix-webhook", data=_comment_payload("просто текст"))
    assert resp.status_code == 200
    assert enq == [] and bx.posted == []


def test_briefing_answer_enqueued(wired, monkeypatch):
    enq, seen_user, bx = wired
    _patch_go(monkeypatch, GoDecision(True, "creator", "authorized", False, {}), seen_user)
    with TestClient(app) as client:
        resp = client.post(
            "/bitrix-webhook", data=_comment_payload("/briefing answer r1\nA1: ответ")
        )
    assert resp.status_code == 200
    assert any(e[0] == "run_command" for e in enq)
