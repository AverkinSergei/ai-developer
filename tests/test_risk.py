from app.config import Settings
from app.contracts import TaskCard
from app.risk import classify_risk

S = Settings()


def _card(**kw):
    base = dict(task_id="B24-1", task_type="feature", target_repo="grp/repo")
    base.update(kw)
    return TaskCard(**base)


def test_docs_only_is_low():
    a = classify_risk(_card(affected_area=["docs"]), [], S)
    assert a.risk_level == "low"
    assert not a.red_team_required


def test_plain_business_logic_is_medium():
    a = classify_risk(_card(affected_area=["backend"], business_goal="список заказов"), [], S)
    assert a.risk_level == "medium"


def test_auth_is_high_with_redteam():
    a = classify_risk(_card(affected_area=["auth"]), ["app/auth/login.py"], S)
    assert a.risk_level == "high"
    assert a.red_team_required
    assert a.human_preapproval_required


def test_payment_trigger_high():
    a = classify_risk(_card(business_goal="расчёт payment баланса"), [], S)
    assert a.risk_level == "high"


def test_blocked_trigger():
    a = classify_risk(_card(business_goal="rotate production secret in IAM"), [], S)
    assert a.risk_level == "blocked"


def test_security_flag_forces_high():
    a = classify_risk(_card(affected_area=["frontend"], security=True), [], S)
    assert a.risk_level == "high"


def test_risk_hint_only_raises():
    a = classify_risk(_card(affected_area=["docs"], risk_hint="high"), [], S)
    assert a.risk_level == "high"


def test_file_count_bumps_to_medium():
    paths = [f"f{i}.txt" for i in range(S.max_changed_files_low + 1)]
    a = classify_risk(_card(affected_area=["docs"]), paths, S)
    assert a.risk_level == "medium"


def test_russian_auth_trigger_high():
    a = classify_risk(_card(business_goal="добавить авторизацию и роли пользователей"), [], S)
    assert a.risk_level == "high"


def test_russian_payment_trigger_high():
    a = classify_risk(_card(acceptance_criteria="корректный расчёт платежей и баланса"), [], S)
    assert a.risk_level == "high"


def test_russian_blocked_trigger():
    a = classify_risk(_card(business_goal="ротация боевых секретов в IAM"), [], S)
    assert a.risk_level == "blocked"


def test_many_files_require_preapproval():
    paths = [f"f{i}.py" for i in range(S.max_changed_files_medium + 1)]
    a = classify_risk(_card(affected_area=["backend"]), paths, S)
    assert a.human_preapproval_required
    assert a.risk_level == "high"
