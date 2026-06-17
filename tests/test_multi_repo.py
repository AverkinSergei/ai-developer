import json

from app.clients.fakes import FakeBitrix, FakeGitLab, FakeLLM
from app.config import settings
from app.contracts import TaskCard
from app.db.models import TaskState
from app.orchestrator import execute_plan


def test_card_repo_properties():
    card = TaskCard(
        task_id="B24-1",
        task_type="feature",
        target_repo="grp/a",
        target_repos=["grp/b", "grp/a"],  # дубль основного схлопывается
        context_repos=["grp/lib", "grp/b"],  # grp/b уже change -> не контекст
    )
    assert card.all_repos == ["grp/a", "grp/b"]
    assert card.context_only_repos == ["grp/lib"]


def _card_snapshot(**over):
    base = {
        "task_id": "B24-1",
        "task_type": "feature",
        "target_repo": "grp/a",
        "target_branch": "dev",
        "business_goal": "добавить endpoint",
        "acceptance_criteria": "работает",
        "affected_area": ["backend"],
        "author_user_id": "u-a",
    }
    base.update(over)
    return base


def _plan_code():
    plan = json.dumps(
        {
            "changes": [{"path": "app/feature.py", "action": "create", "rationale": "x"}],
            "test_plan": ["t"],
            "doc_impact": "no",
            "doc_skip_reason": "internal",
            "rollback_note": "revert",
        }
    )
    code = json.dumps({"app/feature.py": "def f():\n    return 1\n"})
    return [plan, code]


async def test_multi_repo_creates_mr_per_repo(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "agent_tmp_dir", str(tmp_path))
    db_session.add(
        TaskState(
            task_id="B24-1",
            repo="grp/a",
            target_branch="dev",
            task_type="feature",
            author_user_id="u-a",
            card_snapshot=_card_snapshot(target_repos=["grp/b"]),
        )
    )
    await db_session.flush()

    gl = FakeGitLab(files={"grp/a": {"app/m.py": "# a\n"}, "grp/b": {"app/m.py": "# b\n"}})
    llm = FakeLLM(responses=[*_plan_code(), *_plan_code()])  # по паре на каждый репо

    res = await execute_plan(db_session, task_id="B24-1", gitlab=gl, llm=llm, bitrix=FakeBitrix())
    assert res["status"] == "multi"
    assert len(res["results"]) == 2
    assert {r["repo"] for r in res["results"]} == {"grp/a", "grp/b"}
    assert {mr["repo"] for mr in gl.mrs} == {"grp/a", "grp/b"}  # по MR на каждый репо
    assert gl.branch_refs[("grp/a", "auto-task-B24-1")] == "main"
    assert gl.branch_refs[("grp/b", "auto-task-B24-1")] == "main"


async def test_context_repo_gets_no_mr(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "agent_tmp_dir", str(tmp_path))
    db_session.add(
        TaskState(
            task_id="B24-1",
            repo="grp/a",
            target_branch="dev",
            task_type="feature",
            author_user_id="u-a",
            card_snapshot=_card_snapshot(context_repos=["grp/lib"]),
        )
    )
    await db_session.flush()

    gl = FakeGitLab(files={"grp/a": {"app/m.py": "# a\n"}, "grp/lib": {"lib.py": "# lib\n"}})
    llm = FakeLLM(responses=_plan_code())  # только для grp/a

    res = await execute_plan(db_session, task_id="B24-1", gitlab=gl, llm=llm, bitrix=FakeBitrix())
    assert res["status"] == "mr_ready"  # один change-репо -> совместимый формат
    assert {mr["repo"] for mr in gl.mrs} == {"grp/a"}  # в context-репо MR нет
    assert "grp/lib" not in gl.branches  # ветка в контекстном репо не создаётся
