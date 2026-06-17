from app.ci import (
    is_actionable_comment,
    is_auto_task_branch,
    next_fix_action,
    parse_note,
    parse_pipeline,
    pipeline_is_blocking,
)


def test_auto_task_branch():
    assert is_auto_task_branch("auto-task-B24-1")
    assert not is_auto_task_branch("dev")


def test_pipeline_blocking():
    assert pipeline_is_blocking("failed")
    assert pipeline_is_blocking("canceled")
    assert not pipeline_is_blocking("success")


def test_actionable_comment():
    assert is_actionable_comment("@ai fix")
    assert not is_actionable_comment("lgtm")
    assert not is_actionable_comment("  ")
    assert not is_actionable_comment("👍")


def test_next_fix_action():
    assert next_fix_action(0, 3) == "fix"
    assert next_fix_action(2, 3) == "fix"
    assert next_fix_action(3, 3) == "stop"


def test_parse_pipeline():
    pe = parse_pipeline(
        {
            "object_attributes": {"status": "failed", "ref": "auto-task-B24-1"},
            "merge_request": {"iid": 7},
            "project": {"path_with_namespace": "grp/repo"},
        }
    )
    assert pe.status == "failed"
    assert pe.ref == "auto-task-B24-1"
    assert pe.mr_iid == "7"
    assert pe.project == "grp/repo"


def test_parse_note():
    ne = parse_note(
        {
            "object_attributes": {"note": "@ai fix"},
            "user": {"id": 9, "username": "rev"},
            "merge_request": {"iid": 7, "source_branch": "auto-task-B24-1"},
            "project": {"path_with_namespace": "grp/repo"},
        }
    )
    assert ne.note == "@ai fix"
    assert ne.author_id == "9"
    assert ne.mr_iid == "7"
    assert ne.source_branch == "auto-task-B24-1"
