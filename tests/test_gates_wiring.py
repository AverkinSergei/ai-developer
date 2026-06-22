import json

import pytest

from app.clients.fakes import FakeGitLab, FakeLLM
from app.config import Settings, settings
from app.contracts import TaskCard
from app.orchestrator import _plan_one_repo

# .ai-agent.yml с всегда-зелёным тестом -> verified=True.
_AGENT_YML = "commands:\n  test: 'python3 -c \"import sys; sys.exit(0)\"'\n"


@pytest.fixture(autouse=True)
def _isolation(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "sandbox_isolation_confirmed", True)
    monkeypatch.setattr(settings, "agent_tmp_dir", str(tmp_path / "tmp"))


def _card():
    return TaskCard(
        task_id="B24-1",
        task_type="feature",
        target_repo="grp/a",
        target_branch="dev",
        affected_area=["backend"],
        business_goal="endpoint",
        acceptance_criteria="works",
        reviewer="u-rev",
    )


def _llm(review_verdict: str):
    plan = json.dumps(
        {
            "changes": [{"path": "app/feature.py", "action": "create", "rationale": "x"}],
            "doc_impact": "no",
            "doc_skip_reason": "internal",
        }
    )
    code = json.dumps({"app/feature.py": "def f():\n    return 1\n"})
    review = json.dumps({"verdict": review_verdict, "comments": []})
    return FakeLLM(responses=[plan, code, review])


def _gitlab():
    return FakeGitLab(files={"grp/a": {"app/main.py": "# a\n", ".ai-agent.yml": _AGENT_YML}})


async def test_gates_pass_flips_to_ready():
    gl = _gitlab()
    res = await _plan_one_repo(
        "B24-1",
        "grp/a",
        _card(),
        gitlab=gl,
        llm=_llm("PASS"),
        settings=Settings(),
        context_graphs=[],
    )
    assert res["status"] == "mr_ready"
    assert res["verified"] is True  # тест репо зелёный
    assert res["review_verdict"] == "PASS"
    assert res["ready_for_review"] is True
    assert gl.mrs[0]["draft"] is False  # Draft -> Ready
    assert gl.mrs[0]["reviewer_id"] == "u-rev"


async def test_review_block_keeps_draft():
    gl = _gitlab()
    res = await _plan_one_repo(
        "B24-1",
        "grp/a",
        _card(),
        gitlab=gl,
        llm=_llm("FAIL"),
        settings=Settings(),
        context_graphs=[],
    )
    assert res["gates_blocked"] is True
    assert res["ready_for_review"] is False
    assert gl.mrs[0]["draft"] is True  # блокирующий review -> остаётся Draft
