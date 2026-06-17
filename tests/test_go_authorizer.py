from app.go_authorizer import GoContext, authorize


def test_maintainer_authorized():
    d = authorize(GoContext(user_id="u1", is_maintainer=True), risk_level="low")
    assert d.authorized and d.rule == "maintainer"


def test_reviewer_authorized():
    d = authorize(GoContext(user_id="u-rev", reviewer_user_id="u-rev"), risk_level="low")
    assert d.authorized and d.rule == "reviewer"


def test_author_authorized_low_risk():
    d = authorize(GoContext(user_id="u-a", author_user_id="u-a"), risk_level="low")
    assert d.authorized and d.rule == "creator"


def test_responsible_authorized_low_risk():
    d = authorize(GoContext(user_id="u-r", assignee_user_id="u-r"), risk_level="medium")
    assert d.authorized and d.rule == "responsible_user"


def test_approver_allowlist():
    d = authorize(GoContext(user_id="u-x", ai_go_approvers=["u-x"]), risk_level="low")
    assert d.authorized and d.rule == "ai_go_approvers"


def test_empty_user_rejected_even_with_empty_approver():
    d = authorize(GoContext(user_id="", ai_go_approvers=[""]), risk_level="low")
    assert not d.authorized
    assert d.rule == "insufficient_rights"


def test_unknown_user_rejected():
    d = authorize(GoContext(user_id="stranger"), risk_level="low")
    assert not d.authorized
    assert d.decision == "rejected"
    assert d.rule == "insufficient_rights"


def test_high_risk_author_rejected():
    d = authorize(GoContext(user_id="u-a", author_user_id="u-a"), risk_level="high")
    assert not d.authorized
    assert d.high_risk_rule_applied is True


def test_high_risk_reviewer_authorized():
    d = authorize(GoContext(user_id="u-rev", reviewer_user_id="u-rev"), risk_level="high")
    assert d.authorized and d.rule == "reviewer"


def test_high_risk_maintainer_authorized():
    d = authorize(GoContext(user_id="u-m", is_maintainer=True), risk_level="high")
    assert d.authorized and d.rule == "maintainer"


def test_high_risk_rule_disabled_allows_author():
    d = authorize(
        GoContext(user_id="u-a", author_user_id="u-a"),
        risk_level="high",
        high_risk_requires_maintainer=False,
    )
    assert d.authorized and d.rule == "creator"
