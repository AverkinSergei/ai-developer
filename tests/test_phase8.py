import os

from fastapi.testclient import TestClient

from app.briefing_store import BriefingStore
from app.clients.fakes import FakeGitLab
from app.config import settings
from app.gitlab_roles import make_maintainer_resolver
from app.main import app
from app.workspace import checkout_workspace


async def test_workspace_cleanup(tmp_path):
    captured = {}
    async with checkout_workspace("B24-1", base_dir=str(tmp_path)) as ws:
        assert os.path.isdir(ws)
        os.mkdir(os.path.join(ws, "sub"))  # делаем каталог непустым
        captured["ws"] = ws
    assert not os.path.exists(captured["ws"])  # удалён даже непустым


async def test_maintainer_resolver():
    gl = FakeGitLab()
    gl.roles[("grp/repo", "u1")] = "maintainer"
    gl.roles[("grp/repo", "u2")] = "developer"
    resolve = make_maintainer_resolver(gl)
    assert await resolve("grp/repo", "u1") is True
    assert await resolve("grp/repo", "u2") is False
    assert await resolve("grp/repo", "u3") is False


def test_metrics_endpoint_enabled():
    with TestClient(app) as client:
        resp = client.get("/metrics")
    assert resp.status_code == 200
    assert b"ai_developer" in resp.content


def test_metrics_endpoint_disabled(monkeypatch):
    monkeypatch.setattr(settings, "metrics_enabled", False)
    with TestClient(app) as client:
        resp = client.get("/metrics")
    assert resp.status_code == 404


async def test_outbox_roundtrip(db_session):
    store = BriefingStore(db_session)
    ev = await store.add_outbox("B24-1", "run_task_phase", ["B24-1", "plan"])
    pending = await store.list_pending_outbox()
    assert any(p.id == ev.id for p in pending)

    await store.mark_outbox_sent(ev.id)
    pending2 = await store.list_pending_outbox()
    assert all(p.id != ev.id for p in pending2)
