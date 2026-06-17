import json

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


class _Store:
    def __init__(self):
        self.fixes = {}

    async def mark_seen(self, event_id: str) -> bool:
        return True

    async def incr_fixes(self, mr_iid: str) -> int:
        self.fixes[mr_iid] = self.fixes.get(mr_iid, 0) + 1
        return self.fixes[mr_iid]


class _GitLab:
    def __init__(self, role="maintainer"):
        self.role = role
        self.notes = []

    async def get_project_member_role(self, repo, user_id):
        return self.role

    async def add_mr_note(self, repo, mr_iid, body):
        self.notes.append((repo, mr_iid, body))


@pytest.fixture
def wired(monkeypatch):
    enq = []
    store = _Store()
    gl = _GitLab()

    async def fake_enqueue(*args, **kwargs):
        enq.append(args)
        return "job"

    monkeypatch.setattr(settings, "gitlab_webhook_secret", "glsecret")
    monkeypatch.setattr(settings, "max_ai_fixes", 3)
    monkeypatch.setattr("app.webhooks.store", store)
    monkeypatch.setattr("app.webhooks.gitlab_client", gl)
    monkeypatch.setattr("app.webhooks.enqueue_task", fake_enqueue)
    return enq, store, gl


def _post(client, payload, event, token="glsecret"):
    return client.post(
        "/gitlab-webhook",
        content=json.dumps(payload),
        headers={
            "X-Gitlab-Token": token,
            "X-Gitlab-Event": event,
            "X-Gitlab-Event-UUID": payload.get("_uuid", "u1"),
            "Content-Type": "application/json",
        },
    )


def _pipeline(status="failed", ref="auto-task-B24-1", iid=7, uuid="u1"):
    return {
        "_uuid": uuid,
        "object_attributes": {"status": status, "ref": ref},
        "merge_request": {"iid": iid},
        "project": {"path_with_namespace": "grp/repo"},
    }


def _note(text="@ai fix", uid=9, iid=7, uuid="u1"):
    return {
        "_uuid": uuid,
        "object_attributes": {"note": text},
        "user": {"id": uid, "username": "rev"},
        "merge_request": {"iid": iid, "source_branch": "auto-task-B24-1"},
        "project": {"path_with_namespace": "grp/repo"},
    }


def test_bad_token_rejected(wired):
    enq, store, gl = wired
    with TestClient(app) as client:
        resp = _post(client, _pipeline(), "Pipeline Hook", token="wrong")
    assert resp.status_code == 403
    assert enq == []


def test_pipeline_failed_triggers_fix(wired):
    enq, store, gl = wired
    with TestClient(app) as client:
        resp = _post(client, _pipeline(), "Pipeline Hook")
    assert resp.status_code == 200
    assert ("run_fix", "grp/repo", "7", "ci_failed") in enq


def test_pipeline_success_no_fix(wired):
    enq, store, gl = wired
    with TestClient(app) as client:
        _post(client, _pipeline(status="success"), "Pipeline Hook")
    assert enq == []


def test_pipeline_non_auto_branch_ignored(wired):
    enq, store, gl = wired
    with TestClient(app) as client:
        _post(client, _pipeline(ref="dev"), "Pipeline Hook")
    assert enq == []


def test_fix_limit_posts_manual_intervention(wired):
    enq, store, gl = wired
    store.fixes["7"] = 3  # лимит уже достигнут
    with TestClient(app) as client:
        _post(client, _pipeline(), "Pipeline Hook")
    assert enq == []
    assert gl.notes and "лимит" in gl.notes[0][2].lower()


def test_ai_fix_authorized(wired):
    enq, store, gl = wired
    with TestClient(app) as client:
        _post(client, _note("@ai fix"), "Note Hook")
    assert ("run_fix", "grp/repo", "7", "ai_fix") in enq


def test_ai_fix_unauthorized(wired):
    enq, store, gl = wired
    gl.role = "developer"  # не maintainer/owner
    with TestClient(app) as client:
        _post(client, _note("@ai fix"), "Note Hook")
    assert enq == []


def test_ai_resolve_enqueued(wired):
    enq, store, gl = wired
    with TestClient(app) as client:
        _post(client, _note("@ai resolve"), "Note Hook")
    assert ("run_resolve", "grp/repo", "7") in enq


def test_non_actionable_note_ignored(wired):
    enq, store, gl = wired
    with TestClient(app) as client:
        _post(client, _note("lgtm"), "Note Hook")
    assert enq == []
