import pytest
from sqlalchemy.exc import IntegrityError

from app import briefing_state_machine as fsm
from app.briefing_store import BriefingStore
from app.db.models import BriefingSession, TaskState


async def _seed_task(db, task_id="B24-1"):
    db.add(
        TaskState(
            task_id=task_id,
            repo="grp/repo",
            target_branch="dev",
            task_type="feature",
            author_user_id="u-author",
        )
    )
    await db.flush()


async def _new_session(store, db, session_id="brf_1", task_id="B24-1"):
    return await store.create_session(
        session_id=session_id,
        task_id=task_id,
        repo="grp/repo",
        target_branch="dev",
        author_user_id="u-author",
        allowed_go_users=["u-author", "u-rev"],
        required_fields_snapshot={"task_type": "feature", "target_branch": "dev"},
    )


async def test_create_and_contract(db_session):
    store = BriefingStore(db_session)
    await _seed_task(db_session)
    session = await _new_session(store, db_session)

    contract = await store.to_contract(session)
    assert contract.state == fsm.NEW
    assert contract.allowed_go_users == ["u-author", "u-rev"]
    assert contract.accepted_answers == []
    assert contract.open_questions == []
    assert contract.go_event is None


async def test_round_question_answer_flow(db_session):
    store = BriefingStore(db_session)
    await _seed_task(db_session)
    session = await _new_session(store, db_session)

    rnd = await store.add_round(session, "brf_1:r1", bitrix_comment_id="c1", author_user_id="bot")
    q1 = await store.add_question(rnd, "brf_1:r1:q1", 1, "Критерий приёмки?")
    await store.add_question(rnd, "brf_1:r1:q2", 2, "Кто имеет доступ?")

    # До ответа оба вопроса открыты.
    contract = await store.to_contract(session)
    assert set(contract.open_questions) == {"brf_1:r1:q1", "brf_1:r1:q2"}

    await store.record_answer(
        question_id=q1.question_id,
        answer_id="a1",
        raw_text="статус без перезагрузки",
        normalized_answer="status without reload",
        confidence=0.9,
        source_comment_id="c2",
        accepted_by_rule="structured_command",
        author_user_id="u-author",
    )

    contract = await store.to_contract(session)
    assert contract.open_questions == ["brf_1:r1:q2"]
    assert len(contract.accepted_answers) == 1
    assert contract.accepted_answers[0].question_id == "brf_1:r1:q1"


async def test_answer_versioning_supersedes(db_session):
    store = BriefingStore(db_session)
    await _seed_task(db_session)
    session = await _new_session(store, db_session)
    rnd = await store.add_round(session, "brf_1:r1", "c1", "bot")
    q = await store.add_question(rnd, "brf_1:r1:q1", 1, "?")

    a1 = await store.record_answer(
        q.question_id, "a1", "v1", "v1", 0.8, "c2", "structured_command", "u-author"
    )
    a2 = await store.record_answer(
        q.question_id, "a2", "v2", "v2", 0.95, "c3", "structured_command", "u-author"
    )
    assert a1.answer_version == 1
    assert a2.answer_version == 2

    active = await store._active_answer(q.question_id)
    assert active is not None and active.answer_id == "a2"
    assert active.answer_version == 2

    contract = await store.to_contract(session)
    assert len(contract.accepted_answers) == 1
    assert contract.accepted_answers[0].answer_id == "a2"


async def test_transition_valid_and_invalid(db_session):
    store = BriefingStore(db_session)
    await _seed_task(db_session)
    session = await _new_session(store, db_session)

    await store.transition(session, fsm.QUESTIONS_GENERATED)
    assert session.state == fsm.QUESTIONS_GENERATED

    with pytest.raises(fsm.InvalidTransition):
        await store.transition(session, fsm.APPROVED)


async def test_transition_clears_active_round(db_session):
    store = BriefingStore(db_session)
    await _seed_task(db_session)
    session = await _new_session(store, db_session)
    await store.transition(session, fsm.QUESTIONS_GENERATED)
    await store.add_round(session, "brf_1:r1", "c1", "bot")
    assert session.active_round_id == "brf_1:r1"

    await store.transition(session, fsm.WAITING_ANSWERS)
    assert session.active_round_id == "brf_1:r1"  # WAITING_ANSWERS сохраняет активный раунд

    await store.transition(session, fsm.ANSWERS_RECEIVED)
    assert session.active_round_id is None


async def test_active_session_uniqueness(db_session):
    store = BriefingStore(db_session)
    await _seed_task(db_session)
    await _new_session(store, db_session, session_id="brf_1")

    db_session.add(
        BriefingSession(
            session_id="brf_2",
            task_id="B24-1",
            repo="grp/repo",
            target_branch="dev",
            state=fsm.NEW,
            allowed_go_users=[],
            required_fields_snapshot={},
            author_user_id="u-author",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
