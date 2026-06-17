import json

from app.clients.fakes import FakeLLM
from app.contracts import AIReviewVerdict, Change, RedTeamResult, RiskPlanGate, TaskCard
from app.gates import merge_decision, run_review_gates
from app.redteam import red_team_review, redteam_required
from app.reviewer import autofixable, review_diff


def _card(**over):
    base = dict(task_id="B24-1", task_type="feature", target_repo="grp/repo")
    base.update(over)
    return TaskCard(**base)


def _gate(risk="medium", **over):
    base = dict(
        risk_level=risk,
        doc_impact="yes",
        changes=[Change(path="app/x.py", action="create", rationale="r")],
    )
    base.update(over)
    return RiskPlanGate(**base)


# --- reviewer ---
async def test_review_pass_parsed():
    llm = FakeLLM(responses=['{"verdict": "PASS", "comments": []}'])
    v = await review_diff(_card(), "diff", "ok", "docs", llm)
    assert v.verdict == "PASS"
    assert not v.merge_blocked


async def test_review_bad_json_fail_closed():
    llm = FakeLLM(responses=["не json"])
    v = await review_diff(_card(), "diff", "ok", "docs", llm)
    assert v.verdict == "NEED_HUMAN_REVIEW"
    assert v.merge_blocked


async def test_review_blocker_comment_blocks():
    llm = FakeLLM(
        responses=[
            '{"verdict": "PASS_WITH_NOTES", "comments": '
            '[{"file": "a.py", "line": 1, "severity": "blocker", "body": "fix"}]}'
        ]
    )
    v = await review_diff(_card(), "diff", "ok", "docs", llm)
    assert v.merge_blocked
    assert len(autofixable(v)) == 1


# --- redteam triggers ---
def test_redteam_required_forced():
    assert redteam_required(_card(), _gate(risk="low"), [], forced=True)


def test_redteam_required_high_risk():
    assert redteam_required(_card(), _gate(risk="high", red_team_required=True), [])


def test_redteam_required_trigger_match():
    assert redteam_required(_card(business_goal="добавить вебхук"), _gate(risk="medium"), [])


def test_redteam_not_required_plain():
    assert not redteam_required(
        _card(business_goal="поправить текст в футере"), _gate(risk="low"), ["app/ui.py"]
    )


# --- redteam review ---
async def test_redteam_high_finding_blocks():
    payload = {
        "verdict": "PASS_WITH_NOTES",
        "max_severity": "high",
        "findings": [
            {
                "title": "IDOR",
                "severity": "high",
                "affected_files": ["a.py"],
                "exploit_scenario": "x",
                "recommended_fix": "y",
                "merge_blocking": True,
            }
        ],
    }
    llm = FakeLLM(responses=[json.dumps(payload)])
    r = await red_team_review(_card(), _gate(risk="high"), "diff", llm)
    assert r.merge_blocked


async def test_redteam_bad_json_fail_closed():
    llm = FakeLLM(responses=["мусор"])
    r = await red_team_review(_card(), _gate(risk="high"), "diff", llm)
    assert r.verdict == "NEED_HUMAN_SECURITY_REVIEW"
    assert r.merge_blocked


# --- gate wiring ---
async def test_gates_pass_low_risk_no_redteam():
    llm = FakeLLM(responses=['{"verdict": "PASS", "comments": []}'])
    res = await run_review_gates(
        _card(business_goal="footer text"), _gate(risk="low"), "diff", "ok", "docs", llm
    )
    assert not res.blocked
    assert res.redteam is None


async def test_gates_block_on_redteam_high_risk():
    review_ok = '{"verdict": "PASS", "comments": []}'
    rt = json.dumps(
        {
            "verdict": "FAIL",
            "max_severity": "critical",
            "findings": [],
        }
    )
    llm = FakeLLM(responses=[review_ok, rt])
    res = await run_review_gates(
        _card(affected_area=["auth"]),
        _gate(risk="high", red_team_required=True),
        "diff",
        "ok",
        "docs",
        llm,
    )
    assert res.blocked
    assert res.redteam is not None
    assert any("red_team" in r for r in res.reasons)


def test_merge_decision_combines():
    rev = AIReviewVerdict(verdict="PASS", comments=[])
    rt = RedTeamResult(verdict="FAIL", max_severity="high", findings=[])
    assert merge_decision(rev, None).blocked is False
    assert merge_decision(rev, rt).blocked is True
