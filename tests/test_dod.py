from app.contracts import AIReviewVerdict, RedTeamResult
from app.dod import DoDInputs, definition_of_done

PASS_REVIEW = AIReviewVerdict(verdict="PASS", comments=[])
PASS_RT = RedTeamResult(verdict="PASS", max_severity="low", findings=[])


def _ok(**over):
    base = dict(
        acceptance_unmapped=[],
        ci_green=True,
        review=PASS_REVIEW,
        redteam=None,
        redteam_required=False,
        tests_present=True,
        doc_impact="yes",
        docs_updated=True,
        has_high_critical_vulns=False,
        secret_leaks=False,
        rollback_note="revert",
        human_approved=True,
    )
    base.update(over)
    return DoDInputs(**base)


def test_all_conditions_met():
    assert definition_of_done(_ok()).met


def test_ci_red_blocks():
    r = definition_of_done(_ok(ci_green=False))
    assert not r.met and any("CI" in u for u in r.unmet)


def test_review_blocking_blocks():
    r = definition_of_done(_ok(review=AIReviewVerdict(verdict="FAIL", comments=[])))
    assert not r.met


def test_redteam_required_but_missing_blocks():
    r = definition_of_done(_ok(redteam_required=True, redteam=None))
    assert not r.met and any("Red Team" in u for u in r.unmet)


def test_redteam_required_pass_ok():
    assert definition_of_done(_ok(redteam_required=True, redteam=PASS_RT)).met


def test_missing_tests_without_reason_blocks():
    r = definition_of_done(_ok(tests_present=False, tests_skip_reason=None))
    assert not r.met


def test_missing_tests_with_reason_ok():
    assert definition_of_done(_ok(tests_present=False, tests_skip_reason="чистый рефакторинг")).met


def test_docs_required_not_updated_blocks():
    r = definition_of_done(_ok(doc_impact="yes", docs_updated=False))
    assert not r.met


def test_no_rollback_blocks():
    assert not definition_of_done(_ok(rollback_note="")).met


def test_no_human_approve_blocks():
    assert not definition_of_done(_ok(human_approved=False)).met


def test_vulns_and_secrets_block():
    assert not definition_of_done(_ok(has_high_critical_vulns=True)).met
    assert not definition_of_done(_ok(secret_leaks=True)).met
