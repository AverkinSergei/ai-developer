from app.intake import build_task_card, missing_required_fields, parse_text_tags


def test_parse_text_tags():
    text = (
        "Описание [tests: required] [docs: auto] [preview: yes] [security: yes] [context: auth, db]"
    )
    tags = parse_text_tags(text)
    assert tags["tests"] == "required"
    assert tags["docs"] == "auto"
    assert tags["preview"] is True
    assert tags["security"] is True
    assert tags["context_keywords"] == ["auth", "db"]


def test_parse_text_tags_skip_with_reason():
    tags = parse_text_tags("[tests: skip-нет смысла]")
    assert tags["tests"] == "skip"


def test_missing_required_invalid_task_type():
    assert missing_required_fields({"task_type": "nonsense"}) == ["task_type"]


def test_missing_required_feature():
    raw = {
        "task_type": "feature",
        "target_repo": "grp/repo",
        "target_branch": "dev",
        "affected_area": ["backend"],
        # business_goal, reviewer, acceptance_criteria отсутствуют
    }
    missing = missing_required_fields(raw)
    assert set(missing) == {"business_goal", "reviewer", "acceptance_criteria"}


def test_missing_required_full_feature_ok():
    raw = {
        "task_type": "feature",
        "target_repo": "grp/repo",
        "target_branch": "dev",
        "affected_area": ["backend"],
        "business_goal": "g",
        "reviewer": "u-rev",
        "acceptance_criteria": "ac",
    }
    assert missing_required_fields(raw) == []


def test_research_needs_no_acceptance_criteria():
    raw = {
        "task_type": "research",
        "target_repo": "grp/repo",
        "target_branch": "dev",
        "affected_area": ["docs"],
    }
    assert missing_required_fields(raw) == []


def test_build_task_card_with_tags():
    raw = {
        "task_id": "B24-1",
        "task_type": "feature",
        "target_repo": "grp/repo",
        "target_branch": "dev",
        "affected_area": ["backend"],
        "business_goal": "g",
        "reviewer": "u-rev",
        "acceptance_criteria": "ac",
    }
    card = build_task_card(raw, text="нужно [security: yes] [context: auth]")
    assert card.task_id == "B24-1"
    assert card.security is True
    assert card.context_keywords == ["auth"]
    assert card.target_branch == "dev"
