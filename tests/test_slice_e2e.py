import json

from app.clients.fakes import FakeGitLab, FakeLLM
from app.config import Settings
from app.context_engine import ContextEngine
from app.contracts import TaskCard
from app.orchestrator import run_coding_slice

REPO = "grp/repo"
S = Settings()


def _plan(**over):
    payload = {
        "context_files": ["app/main.py"],
        "changes": [{"path": "app/feature.py", "action": "create", "rationale": "new endpoint"}],
        "test_plan": ["проверить feature()"],
        "doc_impact": "no",
        "doc_skip_reason": "internal helper",
        "rollback_note": "revert the commit",
        "out_of_scope": [],
    }
    payload.update(over)
    return json.dumps(payload, ensure_ascii=False)


def _code(files=None):
    return json.dumps(files or {"app/feature.py": "def feature():\n    return 1\n"})


async def _engine(tmp_path, gl):
    root = await gl.fetch_archive(REPO, "dev", str(tmp_path))
    return ContextEngine(root)


def _card(**over):
    base = dict(
        task_id="B24-1",
        task_type="feature",
        target_repo=REPO,
        target_branch="dev",
        affected_area=["backend"],
        business_goal="добавить endpoint",
        acceptance_criteria="feature работает",
    )
    base.update(over)
    return TaskCard(**base)


async def test_slice_reaches_draft_mr(tmp_path):
    gl = FakeGitLab(files={REPO: {"app/main.py": "# app\n", "README.md": "# r\n"}})
    engine = await _engine(tmp_path, gl)
    llm = FakeLLM(responses=[_plan(), _code()])

    res = await run_coding_slice(_card(), engine=engine, llm=llm, gitlab=gl, settings=S)

    assert res["status"] == "mr_ready"
    assert res["mr"]["draft"] is True
    assert res["mr"]["target_branch"] == "dev"  # MR нацелен в dev
    assert res["gate"].risk_level == "medium"
    assert "medium" in res["mr"]["description"]
    assert gl.branches[REPO] == {"auto-task-B24-1"}
    # ветка отпочкована от main, а не от dev
    assert gl.branch_refs[(REPO, "auto-task-B24-1")] == "main"
    assert any(c["branch"] == "auto-task-B24-1" for c in gl.commits)


async def test_slice_blocked_stops(tmp_path):
    gl = FakeGitLab(files={REPO: {"app/main.py": "# app\n"}})
    engine = await _engine(tmp_path, gl)
    llm = FakeLLM(responses=[_plan(), _code()])

    card = _card(business_goal="rotate production secret in IAM")
    res = await run_coding_slice(card, engine=engine, llm=llm, gitlab=gl, settings=S)
    assert res["status"] == "blocked"
    assert gl.commits == []
    assert gl.mrs == []


async def test_slice_high_risk_needs_human(tmp_path):
    gl = FakeGitLab(files={REPO: {"app/main.py": "# app\n"}})
    engine = await _engine(tmp_path, gl)
    llm = FakeLLM(responses=[_plan(), _code()])

    card = _card(affected_area=["auth"])
    res = await run_coding_slice(card, engine=engine, llm=llm, gitlab=gl, settings=S)
    assert res["status"] == "needs_human"
    assert gl.commits == []


async def test_slice_self_check_failure(tmp_path):
    gl = FakeGitLab(files={REPO: {"app/main.py": "# app\n"}})
    engine = await _engine(tmp_path, gl)
    # план просит app/feature.py, а код вернул другой файл -> self-check ловит
    llm = FakeLLM(responses=[_plan(), _code({"app/other.py": "x=1\n"})])

    res = await run_coding_slice(_card(), engine=engine, llm=llm, gitlab=gl, settings=S)
    assert res["status"] == "self_check_failed"
    assert gl.mrs == []


async def test_slice_reuses_branch_and_mr(tmp_path):
    gl = FakeGitLab(files={REPO: {"app/main.py": "# app\n"}})
    engine = await _engine(tmp_path, gl)
    llm = FakeLLM(responses=[_plan(), _code(), _plan(), _code()])

    first = await run_coding_slice(_card(), engine=engine, llm=llm, gitlab=gl, settings=S)
    second = await run_coding_slice(_card(), engine=engine, llm=llm, gitlab=gl, settings=S)
    assert first["mr"]["iid"] == second["mr"]["iid"]
    assert len(gl.mrs) == 1  # новый MR не создаётся при открытом
    assert len(gl.commits) == 2  # но новый коммит добавляется
