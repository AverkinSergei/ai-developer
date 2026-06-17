from app.commands import parse_command


def test_go():
    assert parse_command("/go").kind == "go"
    assert parse_command("/go now").kind == "go"


def test_briefing_answer_round_id():
    cmd = parse_command("/briefing answer r2\nA1: текст")
    assert cmd.kind == "briefing_answer"
    assert cmd.round_id == "r2"
    assert "A1: текст" in cmd.raw


def test_briefing_answer_without_round_id_is_none():
    assert parse_command("/briefing answer") is None


def test_briefing_status_reopen_cancel():
    assert parse_command("/briefing status").kind == "briefing_status"
    reopen = parse_command("/briefing reopen уточнили роли")
    assert reopen.kind == "briefing_reopen"
    assert reopen.args == "уточнили роли"
    cancel = parse_command("/briefing cancel снято")
    assert cancel.kind == "briefing_cancel" and cancel.args == "снято"


def test_briefing_skip():
    cmd = parse_command("/briefing skip brf_1:r1:q3 вне scope")
    assert cmd.kind == "briefing_skip"
    assert cmd.question_id == "brf_1:r1:q3"
    assert cmd.args == "вне scope"


def test_ai_commands():
    assert parse_command("@ai status").kind == "ai_status"
    assert parse_command("@ai fix").kind == "ai_fix"
    assert parse_command("@ai redteam").kind == "ai_redteam"


def test_plain_text_and_unknown_are_none():
    assert parse_command("просто комментарий") is None
    assert parse_command("@ai bogus") is None
    assert parse_command("") is None
    assert parse_command("/unknown cmd") is None
