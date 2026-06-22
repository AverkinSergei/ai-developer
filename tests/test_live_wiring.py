import json

from app import briefing_state_machine as fsm
from app.briefing_store import BriefingStore
from app.clients.fakes import FakeBitrix, FakeGitLab, FakeLLM
from app.config import Settings, settings
from app.contracts import BriefingCommand
from app.db.models import TaskState
from app.orchestrator import execute_plan, finalize_round, handle_answers, intake_task

FIELD_MAP = {
    "task_type": "ufType",
    "target_repo": "ufRepo",
    "business_goal": "ufGoal",
    "acceptance_criteria": "ufAcc",
    "affected_area": "ufArea",
    "reviewer": "ufReviewer",
}
S = Settings(bitrix_field_map=FIELD_MAP)


def _full_card_dict():
    return {
        "task_id": "B24-1",
        "task_type": "feature",
        "target_repo": "grp/repo",
        "target_branch": "dev",
        "business_goal": "добавить endpoint",
        "acceptance_criteria": "работает",
        "affected_area": ["backend"],
        "reviewer": "u-rev",
        "author_user_id": "u-a",
    }


# --- intake ---
async def test_intake_incomplete_opens_briefing(db_session):
    bitrix = FakeBitrix(
        tasks={"B24-1": {"ufType": "feature", "ufRepo": "grp/repo", "createdBy": "u-a"}}
    )
    raw = await bitrix.get_task("B24-1")
    res = await intake_task(
        db_session, task_id="B24-1", raw_fields=raw, text="нужен API", bitrix=bitrix, settings=S
    )
    assert res["status"] == "briefing"
    store = BriefingStore(db_session)
    session = await store.get_active_session_by_task("B24-1")
    assert session.state == fsm.WAITING_ANSWERS
    assert any("[AI_BRIEFING]" in c["text"] for c in bitrix.comments)


async def test_intake_complete_ready_for_go(db_session):
    raw = {
        "ufType": "feature",
        "ufRepo": "grp/repo",
        "ufGoal": "g",
        "ufAcc": "ac",
        "ufArea": ["backend"],
        "ufReviewer": "u-rev",
        "createdBy": "u-a",
    }
    bitrix = FakeBitrix(tasks={"B24-1": raw})
    res = await intake_task(
        db_session, task_id="B24-1", raw_fields=raw, text="", bitrix=bitrix, settings=S
    )
    assert res["status"] == "ready_for_go"
    store = BriefingStore(db_session)
    session = await store.get_active_session_by_task("B24-1")
    assert session.state == fsm.READY_FOR_GO


async def test_intake_invalid_missing_type(db_session):
    raw = {"ufRepo": "grp/repo", "createdBy": "u-a"}
    bitrix = FakeBitrix(tasks={"B24-1": raw})
    res = await intake_task(
        db_session, task_id="B24-1", raw_fields=raw, text="", bitrix=bitrix, settings=S
    )
    assert res["status"] == "invalid"
    assert "B24-1" in bitrix.status_notes


# --- finalize_round (completeness) ---
async def test_finalize_round_reaches_ready(db_session):
    store = BriefingStore(db_session)
    snapshot = _full_card_dict()
    snapshot.pop("business_goal")  # единственный пробел
    db_session.add(
        TaskState(
            task_id="B24-1",
            repo="grp/repo",
            target_branch="dev",
            task_type="feature",
            author_user_id="u-a",
            reviewer_user_id="u-rev",
            card_snapshot=snapshot,
        )
    )
    await db_session.flush()
    session = await store.create_session(
        session_id="brf_B24-1",
        task_id="B24-1",
        repo="grp/repo",
        target_branch="dev",
        author_user_id="u-a",
        allowed_go_users=["u-a"],
        required_fields_snapshot={},
    )
    await store.transition(session, fsm.QUESTIONS_GENERATED)
    rnd = await store.add_round(session, "brf_B24-1:r1", "c1", "ai-bot")
    await store.add_question(rnd, "brf_B24-1:r1:q1", 1, "Цель?", dor_dimension="business_goal")
    await store.transition(session, fsm.WAITING_ANSWERS)
    await store.record_answer(
        "brf_B24-1:r1:q1", "a1", "цель X", "цель X", 1.0, "c2", "structured_command", "u-a"
    )
    await store.transition(session, fsm.ANSWERS_RECEIVED)

    res = await finalize_round(db_session, task_id="B24-1", bitrix=FakeBitrix())
    assert res["status"] == "ready_for_go"
    assert session.state == fsm.READY_FOR_GO
    task = await db_session.get(TaskState, "B24-1")
    assert task.card_snapshot["business_goal"] == "цель X"


# --- execute_plan (капстоун: до Draft MR) ---
async def test_execute_plan_creates_draft_mr(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "agent_tmp_dir", str(tmp_path))
    db_session.add(
        TaskState(
            task_id="B24-1",
            repo="grp/repo",
            target_branch="dev",
            task_type="feature",
            author_user_id="u-a",
            card_snapshot=_full_card_dict(),
        )
    )
    await db_session.flush()

    gl = FakeGitLab(files={"grp/repo": {"app/main.py": "# app\n"}})
    plan = json.dumps(
        {
            "changes": [{"path": "app/feature.py", "action": "create", "rationale": "x"}],
            "test_plan": ["t"],
            "doc_impact": "no",
            "doc_skip_reason": "internal",
            "rollback_note": "revert",
        }
    )
    code = json.dumps({"app/feature.py": "def feature():\n    return 1\n"})
    review = json.dumps({"verdict": "PASS", "comments": []})
    llm = FakeLLM(responses=[plan, code, review])  # plan -> code -> AI-review
    bitrix = FakeBitrix()

    res = await execute_plan(db_session, task_id="B24-1", gitlab=gl, llm=llm, bitrix=bitrix)
    assert res["status"] == "mr_ready"
    # без .ai-agent.yml проверок нет -> unverified -> MR остаётся Draft (смотрит человек)
    assert res["mr"]["draft"] is True
    assert res["review_verdict"] == "PASS"
    assert res["ready_for_review"] is False
    assert gl.branch_refs[("grp/repo", "auto-task-B24-1")] == "main"
    task = await db_session.get(TaskState, "B24-1")
    assert task.mr_iid == res["mr"]["iid"]
    assert any("[AI_MR_SUMMARY]" in c["text"] for c in bitrix.comments)


async def test_briefing_answer_advances_via_worker_path(db_session):
    # handle_answers + finalize_round вместе доводят до READY_FOR_GO.
    store = BriefingStore(db_session)
    snapshot = _full_card_dict()
    snapshot.pop("business_goal")
    db_session.add(
        TaskState(
            task_id="B24-1",
            repo="grp/repo",
            target_branch="dev",
            task_type="feature",
            author_user_id="u-a",
            reviewer_user_id="u-rev",
            card_snapshot=snapshot,
        )
    )
    await db_session.flush()
    session = await store.create_session(
        session_id="brf_B24-1",
        task_id="B24-1",
        repo="grp/repo",
        target_branch="dev",
        author_user_id="u-a",
        allowed_go_users=["u-a"],
        required_fields_snapshot={},
    )
    await store.transition(session, fsm.QUESTIONS_GENERATED)
    rnd = await store.add_round(session, "brf_B24-1:r1", "c1", "ai-bot")
    await store.add_question(rnd, "brf_B24-1:r1:q1", 1, "Цель?", dor_dimension="business_goal")
    await store.transition(session, fsm.WAITING_ANSWERS)

    cmd = BriefingCommand(
        kind="briefing_answer", round_id="r1", raw="/briefing answer r1\nA1: цель Y"
    )
    await handle_answers(
        db_session, task_id="B24-1", command=cmd, author_user_id="u-a", source_comment_id="c2"
    )
    res = await finalize_round(db_session, task_id="B24-1", bitrix=FakeBitrix())
    assert res["status"] == "ready_for_go"
