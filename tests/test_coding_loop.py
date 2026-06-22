import json

import pytest

from app.clients.fakes import FakeLLM
from app.coding import generate_changes, run_fix_loop
from app.config import settings
from app.contracts import Change, RiskPlanGate, TaskCard
from app.repo_config import RepoCommands, RepoConfig


@pytest.fixture(autouse=True)
def _confirm_isolation(monkeypatch):
    monkeypatch.setattr(settings, "sandbox_isolation_confirmed", True)


def _card():
    return TaskCard(task_id="B24-1", task_type="feature", target_repo="grp/repo")


def _gate():
    return RiskPlanGate(
        risk_level="low",
        doc_impact="yes",
        changes=[Change(path="app/feature.py", action="create", rationale="r")],
    )


# Проверка: тест репо зелёный, только если в файле есть маркер OK.
_TEST_CMD = "python3 -c \"import sys; sys.exit(0 if 'OK' in open('app/feature.py').read() else 1)\""


async def test_iterates_until_checks_pass(tmp_path):
    cfg = RepoConfig(commands=RepoCommands(test=_TEST_CMD))
    llm = FakeLLM(
        responses=[
            json.dumps({"app/feature.py": "x = 1\n"}),  # без OK -> тест упадёт
            json.dumps({"app/feature.py": "x = 1  # OK\n"}),  # с OK -> пройдёт
        ]
    )
    res = await generate_changes(
        _card(), _gate(), llm, checkout_root=str(tmp_path), repo_config=cfg
    )
    assert res.verified is True
    assert res.iterations == 2
    assert res.checks["test"] == "passed"
    assert res.issues == []


async def test_exhausts_iterations_when_checks_keep_failing(tmp_path):
    cfg = RepoConfig(commands=RepoCommands(test=_TEST_CMD))
    llm = FakeLLM(responses=[json.dumps({"app/feature.py": "x = 1\n"})] * 5)
    res = await generate_changes(
        _card(), _gate(), llm, checkout_root=str(tmp_path), repo_config=cfg, max_iterations=2
    )
    assert res.verified is False
    assert res.iterations == 2
    assert res.issues  # fail-closed: непройденные проверки -> нужен человек


async def test_no_commands_means_unverified_but_not_failed(tmp_path):
    cfg = RepoConfig()  # дефолт: команд нет
    llm = FakeLLM(responses=[json.dumps({"app/feature.py": "def f():\n    return 1\n"})])
    res = await generate_changes(
        _card(), _gate(), llm, checkout_root=str(tmp_path), repo_config=cfg
    )
    assert res.verified is False  # проверять нечем
    assert res.issues == []  # но это не провал — MR откроется (его смотрит человек)
    assert res.iterations == 1


async def test_unverified_when_isolation_not_confirmed(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sandbox_isolation_confirmed", False)
    cfg = RepoConfig(commands=RepoCommands(test=_TEST_CMD))
    llm = FakeLLM(responses=[json.dumps({"app/feature.py": "x = 1  # OK\n"})])
    res = await generate_changes(
        _card(), _gate(), llm, checkout_root=str(tmp_path), repo_config=cfg
    )
    # проверки refused -> не runnable -> unverified, но не провал
    assert res.verified is False
    assert res.issues == []
    assert res.checks["test"] == "refused"


# --- run_fix_loop (самоисправление) ---
_OK_CHECK = "python3 -c \"import sys; sys.exit(0 if 'OK' in open('app/feature.py').read() else 1)\""


async def test_fix_loop_nothing_to_fix(tmp_path):
    cfg = RepoConfig(commands=RepoCommands(test='python3 -c "import sys; sys.exit(0)"'))
    llm = FakeLLM(responses=[])  # не должен вызываться — чинить нечего
    res = await run_fix_loop(_card(), checkout_root=str(tmp_path), repo_config=cfg, llm=llm)
    assert res.verified is True
    assert res.files == {}
    assert res.iterations == 0
    assert llm.calls == []


async def test_fix_loop_repairs_failing_check(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "feature.py").write_text("x = 1\n")  # без OK -> тест падает
    cfg = RepoConfig(commands=RepoCommands(test=_OK_CHECK))
    llm = FakeLLM(responses=[json.dumps({"app/feature.py": "x = 1  # OK\n"})])
    res = await run_fix_loop(_card(), checkout_root=str(tmp_path), repo_config=cfg, llm=llm)
    assert res.verified is True
    assert res.iterations == 1
    assert "app/feature.py" in res.files


async def test_fix_loop_gives_up_after_limit(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "feature.py").write_text("x = 1\n")
    cfg = RepoConfig(commands=RepoCommands(test=_OK_CHECK))
    llm = FakeLLM(responses=[json.dumps({"app/feature.py": "x = 2\n"})] * 5)  # без OK
    res = await run_fix_loop(
        _card(), checkout_root=str(tmp_path), repo_config=cfg, llm=llm, max_iterations=2
    )
    assert res.verified is False
    assert res.issues  # fail-closed -> нужен человек
