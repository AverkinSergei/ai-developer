import pytest
from pydantic import ValidationError

from app.contracts import AIReviewVerdict, RedTeamResult, RiskPlanGate, TaskCard


def test_task_id_pattern_rejects_path_chars():
    with pytest.raises(ValidationError):
        TaskCard(task_id="x/../main", task_type="feature", target_repo="grp/repo")


def test_task_id_pattern_accepts_normal():
    card = TaskCard(task_id="B24-456", task_type="feature", target_repo="grp/repo")
    assert card.task_id == "B24-456"


def test_doc_skip_reason_required_when_no_doc_impact():
    with pytest.raises(ValidationError):
        RiskPlanGate(risk_level="low", doc_impact="no")


def test_high_risk_forces_redteam_and_preapproval():
    g = RiskPlanGate(risk_level="high", doc_impact="yes")
    assert g.red_team_required is True
    assert g.human_preapproval_required is True


def test_redteam_merge_blocked_on_high_finding():
    r = RedTeamResult(
        verdict="PASS_WITH_NOTES",
        max_severity="high",
        findings=[
            {
                "title": "IDOR",
                "severity": "high",
                "affected_files": ["a.py"],
                "exploit_scenario": "x",
                "recommended_fix": "y",
                "merge_blocking": True,
            }
        ],
    )
    assert r.merge_blocked is True


def test_redteam_pass_not_blocked():
    r = RedTeamResult(verdict="PASS", max_severity="low", findings=[])
    assert r.merge_blocked is False


def test_ai_review_blocked_on_blocker_comment():
    v = AIReviewVerdict(
        verdict="PASS_WITH_NOTES",
        comments=[{"file": "a.py", "line": 1, "severity": "blocker", "body": "fix"}],
    )
    assert v.merge_blocked is True


def test_ai_review_pass_with_low_notes_not_blocked():
    v = AIReviewVerdict(
        verdict="PASS_WITH_NOTES",
        comments=[{"file": "a.py", "severity": "low", "body": "nit"}],
    )
    assert v.merge_blocked is False
