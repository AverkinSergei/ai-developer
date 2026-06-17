from app import briefing_state_machine as fsm
from app.briefing_store import BriefingStore
from app.clients.fakes import FakeLLM
from app.contracts import BriefingCommand
from app.db.models import TaskState
from app.orchestrator import handle_answers, handle_go


async def _maintainer(repo, user_id):
    return True


async def _seed(db, task_id="B24-1", risk="low", author="u-a", reviewer="u-rev"):
    db.add(
        TaskState(
            task_id=task_id,
            repo="grp/repo",
            target_branch="dev",
            task_type="feature",
            author_user_id=author,
            reviewer_user_id=reviewer,
            risk_level=risk,
        )
    )
    await db.flush()


async def _session_at(store, db, state, session_id="brf_1", task_id="B24-1"):
    session = await store.create_session(
        session_id=session_id,
        task_id=task_id,
        repo="grp/repo",
        target_branch="dev",
        author_user_id="u-a",
        allowed_go_users=[],
        required_fields_snapshot={},
    )
    chain = {
        fsm.READY_FOR_GO: [
            fsm.QUESTIONS_GENERATED,
            fsm.WAITING_ANSWERS,
            fsm.ANSWERS_RECEIVED,
            fsm.COMPLETENESS_CHECK,
            fsm.READY_FOR_GO,
        ],
        fsm.WAITING_ANSWERS: [fsm.QUESTIONS_GENERATED, fsm.WAITING_ANSWERS],
    }[state]
    for st in chain:
        await store.transition(session, st)
    return session


async def test_go_authorized_creator_low_risk(db_session):
    store = BriefingStore(db_session)
    await _seed(db_session)
    session = await _session_at(store, db_session, fsm.READY_FOR_GO)

    decision = await handle_go(db_session, task_id="B24-1", user_id="u-a", event_id="e1")
    assert decision.authorized
    assert decision.rule == "creator"
    assert session.state == fsm.APPROVED


async def test_go_authorized_writes_outbox(db_session):
    store = BriefingStore(db_session)
    await _seed(db_session)
    await _session_at(store, db_session, fsm.READY_FOR_GO)

    decision = await handle_go(db_session, task_id="B24-1", user_id="u-a", event_id="e1")
    assert decision.authorized
    pending = await store.list_pending_outbox()
    assert any(p.job == "run_task_phase" and p.args == ["B24-1", "plan"] for p in pending)


async def test_go_rejected_unknown_user(db_session):
    store = BriefingStore(db_session)
    await _seed(db_session)
    session = await _session_at(store, db_session, fsm.READY_FOR_GO)

    decision = await handle_go(db_session, task_id="B24-1", user_id="stranger", event_id="e1")
    assert not decision.authorized
    assert session.state == fsm.READY_FOR_GO  # не продвинулись


async def test_go_high_risk_author_rejected_maintainer_ok(db_session):
    store = BriefingStore(db_session)
    await _seed(db_session, risk="high")
    await _session_at(store, db_session, fsm.READY_FOR_GO)

    rejected = await handle_go(db_session, task_id="B24-1", user_id="u-a", event_id="e1")
    assert not rejected.authorized
    assert rejected.high_risk_rule_applied is True

    ok = await handle_go(
        db_session, task_id="B24-1", user_id="u-m", event_id="e2", resolve_maintainer=_maintainer
    )
    assert ok.authorized and ok.rule == "maintainer"


async def test_go_duplicate_ignored(db_session):
    store = BriefingStore(db_session)
    await _seed(db_session)
    await _session_at(store, db_session, fsm.READY_FOR_GO)

    first = await handle_go(db_session, task_id="B24-1", user_id="u-a", event_id="e1")
    second = await handle_go(db_session, task_id="B24-1", user_id="u-rev", event_id="e2")
    assert first.authorized
    assert second.decision == "ignored_duplicate"


async def test_go_event_replay_ignored(db_session):
    store = BriefingStore(db_session)
    await _seed(db_session)
    await _session_at(store, db_session, fsm.READY_FOR_GO)

    first = await handle_go(db_session, task_id="B24-1", user_id="u-a", event_id="same")
    replay = await handle_go(db_session, task_id="B24-1", user_id="u-a", event_id="same")
    assert first.authorized
    assert replay.decision == "ignored_duplicate"


async def test_handle_answers_structured(db_session):
    store = BriefingStore(db_session)
    await _seed(db_session)
    session = await _session_at(store, db_session, fsm.WAITING_ANSWERS)
    rnd = await store.add_round(session, "brf_1:r1", "c1", "bot")
    await store.add_question(rnd, "brf_1:r1:q1", 1, "Критерий?")
    await store.add_question(rnd, "brf_1:r1:q2", 2, "Роли?")

    cmd = BriefingCommand(
        kind="briefing_answer",
        round_id="r1",
        raw="/briefing answer r1\nA1: без перезагрузки\nA2: менеджер и админ",
    )
    res = await handle_answers(
        db_session, task_id="B24-1", command=cmd, author_user_id="u-a", source_comment_id="c2"
    )
    assert res["accepted"] == 2
    assert session.state == fsm.ANSWERS_RECEIVED


async def test_handle_answers_low_confidence_rejected(db_session):
    store = BriefingStore(db_session)
    await _seed(db_session)
    session = await _session_at(store, db_session, fsm.WAITING_ANSWERS)
    rnd = await store.add_round(session, "brf_1:r1", "c1", "bot")
    await store.add_question(rnd, "brf_1:r1:q1", 1, "Критерий?")

    # Нет структурированных A-строк -> модель, но с низким confidence.
    llm = FakeLLM(responses=['[{"ordinal": 1, "answer": "возможно так", "confidence": 0.4}]'])
    cmd = BriefingCommand(kind="briefing_answer", round_id="r1", raw="свободный ответ")
    res = await handle_answers(
        db_session,
        task_id="B24-1",
        command=cmd,
        author_user_id="u-a",
        source_comment_id="c2",
        llm=llm,
        confidence_min=0.7,
    )
    assert res["accepted"] == 0
    assert res["low_confidence"] == 1
    assert session.state == fsm.WAITING_ANSWERS  # остаёмся ждать корректный ответ
