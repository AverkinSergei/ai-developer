import json

import pytest

from app.clients.fakes import FakeLLM
from app.coding import self_check
from app.config import Settings
from app.context_engine import ContextEngine
from app.contracts import Change, RiskPlanGate, TaskCard
from app.planning import PlanError, explore_and_plan

S = Settings()


def _card(**over):
    base = dict(
        task_id="B24-1", task_type="feature", target_repo="grp/repo", affected_area=["backend"]
    )
    base.update(over)
    return TaskCard(**base)


async def test_plan_rejects_unsafe_change_path(tmp_path):
    (tmp_path / "a.py").write_text("x")
    eng = ContextEngine(str(tmp_path))
    llm = FakeLLM(
        responses=[
            json.dumps(
                {
                    "changes": [{"path": "../evil.py", "action": "create", "rationale": "x"}],
                    "doc_impact": "no",
                    "doc_skip_reason": "r",
                }
            )
        ]
    )
    with pytest.raises(PlanError):
        await explore_and_plan(_card(), eng, llm, S)


async def test_plan_doc_impact_flips_to_yes_without_reason(tmp_path):
    eng = ContextEngine(str(tmp_path))
    llm = FakeLLM(
        responses=[
            json.dumps(
                {
                    "changes": [{"path": "a.py", "action": "create", "rationale": "x"}],
                    "doc_impact": "no",
                }
            )
        ]
    )
    gate = await explore_and_plan(_card(), eng, llm, S)
    assert gate.doc_impact == "yes"


async def test_plan_bad_json_raises(tmp_path):
    eng = ContextEngine(str(tmp_path))
    with pytest.raises(PlanError):
        await explore_and_plan(_card(), eng, FakeLLM(responses=["не json"]), S)


def test_self_check_flags_unsafe_path():
    gate = RiskPlanGate(
        risk_level="low",
        doc_impact="yes",
        changes=[Change(path="../x.py", action="create", rationale="r")],
    )
    issues = self_check({"../x.py": "code"}, gate)
    assert any("unsafe" in i for i in issues)


def test_self_check_flags_missing_and_extra():
    gate = RiskPlanGate(
        risk_level="low",
        doc_impact="yes",
        changes=[Change(path="a.py", action="create", rationale="r")],
    )
    issues = self_check({"b.py": "code"}, gate)
    assert any("missing" in i for i in issues)
    assert any("unplanned" in i for i in issues)
