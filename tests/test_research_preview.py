from app.clients.fakes import FakeBitrix, FakeGitLab, FakeLLM
from app.config import Settings
from app.contracts import RiskPlanGate, TaskCard
from app.dod import DoDResult
from app.orchestrator import finalize_mr
from app.preview import preview_required
from app.research import run_research


def _card(**over):
    base = dict(task_id="B24-1", task_type="research", target_repo="grp/repo")
    base.update(over)
    return TaskCard(**base)


def _gate(risk="medium"):
    return RiskPlanGate(risk_level=risk, doc_impact="yes")


async def test_research_posts_report():
    bitrix = FakeBitrix()
    llm = FakeLLM(responses=["# Отчёт\nВыводы и рекомендация."])
    report = await run_research(_card(business_goal="сравнить очереди"), llm, bitrix)
    assert "Отчёт" in report
    assert bitrix.comments
    assert "[AI_RESEARCH]" in bitrix.comments[0]["text"]


def test_preview_required_explicit_flag():
    assert preview_required(_card(preview=True), _gate(), Settings())


def test_preview_not_required_when_disabled():
    assert not preview_required(_card(affected_area=["frontend"]), _gate("high"), Settings())


def test_preview_required_high_risk_frontend_when_enabled():
    s = Settings(preview_enabled=True)
    assert preview_required(_card(affected_area=["frontend"]), _gate("high"), s)
    # medium frontend не требует
    assert not preview_required(_card(affected_area=["frontend"]), _gate("medium"), s)


async def test_finalize_mr_ready_when_dod_met():
    gl = FakeGitLab()
    mr = await gl.create_draft_mr("grp/repo", "auto-task-1", "dev", "t", "d")
    card = _card(task_type="feature", reviewer="u-rev")
    res = await finalize_mr(card, mr, DoDResult(met=True, unmet=[]), gl)
    assert res["status"] == "ready_for_human"
    assert gl.mrs[0]["draft"] is False
    assert gl.mrs[0]["reviewer_id"] == "u-rev"


async def test_finalize_mr_stays_draft_when_unmet():
    gl = FakeGitLab()
    mr = await gl.create_draft_mr("grp/repo", "auto-task-1", "dev", "t", "d")
    res = await finalize_mr(
        _card(task_type="feature"), mr, DoDResult(met=False, unmet=["нет approve"]), gl
    )
    assert res["status"] == "draft"
    assert gl.mrs[0]["draft"] is True
