"""Каноническое хранилище брифинга: CRUD, переходы состояния, сериализация.

Переходы проходят через FSM (assert_transition). Источник истины — БД;
из истории комментариев состояние не восстанавливается.
"""

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import briefing_state_machine as fsm
from app.contracts import AcceptedAnswer, BriefingSessionContract, GoEvent
from app.db.models import (
    BriefingAnswer,
    BriefingQuestion,
    BriefingRound,
    BriefingSession,
    GoAuthorizationEvent,
    OutboxEvent,
)


def _now() -> datetime:
    return datetime.now(UTC)


class BriefingStore:
    def __init__(self, session: AsyncSession) -> None:
        self.db = session

    # --- Сеанс ---
    async def create_session(
        self,
        session_id: str,
        task_id: str,
        repo: str,
        target_branch: str,
        author_user_id: str,
        allowed_go_users: list[str],
        required_fields_snapshot: dict,
    ) -> BriefingSession:
        obj = BriefingSession(
            session_id=session_id,
            task_id=task_id,
            repo=repo,
            target_branch=target_branch,
            state=fsm.NEW,
            allowed_go_users=allowed_go_users,
            required_fields_snapshot=required_fields_snapshot,
            author_user_id=author_user_id,
        )
        self.db.add(obj)
        await self.db.flush()
        return obj

    async def get_session(self, session_id: str) -> BriefingSession | None:
        return await self.db.get(BriefingSession, session_id)

    async def get_session_by_task(self, task_id: str) -> BriefingSession | None:
        """Последняя сессия задачи в любом состоянии (для обработки /go после APPROVED)."""
        stmt = (
            select(BriefingSession)
            .where(BriefingSession.task_id == task_id)
            .order_by(BriefingSession.created_at.desc())
            .limit(1)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_active_session_by_task(self, task_id: str) -> BriefingSession | None:
        stmt = (
            select(BriefingSession)
            .where(BriefingSession.task_id == task_id)
            .where(BriefingSession.state.notin_(tuple(fsm.TERMINAL)))
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def transition(self, session: BriefingSession, new_state: str) -> None:
        """Валидирует переход по FSM и применяет его."""
        fsm.assert_transition(session.state, new_state)
        session.state = new_state
        if new_state != fsm.WAITING_ANSWERS:
            session.active_round_id = None
        await self.db.flush()

    # --- Раунды и вопросы ---
    async def add_round(
        self,
        session: BriefingSession,
        round_id: str,
        bitrix_comment_id: str,
        author_user_id: str,
    ) -> BriefingRound:
        session.rounds_count += 1
        rnd = BriefingRound(
            round_id=round_id,
            session_id=session.session_id,
            task_id=session.task_id,
            repo=session.repo,
            target_branch=session.target_branch,
            round_number=session.rounds_count,
            author_user_id=author_user_id,
            bitrix_comment_id=bitrix_comment_id,
            published_at=_now(),
        )
        self.db.add(rnd)
        session.active_round_id = round_id
        await self.db.flush()
        return rnd

    async def add_question(
        self,
        rnd: BriefingRound,
        question_id: str,
        ordinal: int,
        text: str,
        dor_dimension: str | None = None,
        is_blocking: bool = True,
    ) -> BriefingQuestion:
        q = BriefingQuestion(
            question_id=question_id,
            round_id=rnd.round_id,
            session_id=rnd.session_id,
            task_id=rnd.task_id,
            ordinal=ordinal,
            text=text,
            dor_dimension=dor_dimension,
            is_blocking=is_blocking,
        )
        self.db.add(q)
        await self.db.flush()
        return q

    # --- Ответы (версионируемые) ---
    async def record_answer(
        self,
        question_id: str,
        answer_id: str,
        raw_text: str,
        normalized_answer: str,
        confidence: float,
        source_comment_id: str,
        accepted_by_rule: str,
        author_user_id: str,
    ) -> BriefingAnswer:
        """Новый ответ замещает предыдущий активный (тот помечается superseded)."""
        q = await self.db.get(BriefingQuestion, question_id)
        if q is None:
            raise ValueError(f"Неизвестный question_id: {question_id}")

        prev = await self._active_answer(question_id)
        next_version = (prev.answer_version + 1) if prev else 1
        if prev is not None:
            await self.db.execute(
                update(BriefingAnswer)
                .where(BriefingAnswer.answer_id == prev.answer_id)
                .values(superseded=True)
            )

        ans = BriefingAnswer(
            answer_id=answer_id,
            question_id=question_id,
            round_id=q.round_id,
            session_id=q.session_id,
            task_id=q.task_id,
            answer_version=next_version,
            superseded=False,
            raw_text=raw_text,
            normalized_answer=normalized_answer,
            confidence=confidence,
            source_comment_id=source_comment_id,
            accepted_by_rule=accepted_by_rule,
            author_user_id=author_user_id,
        )
        self.db.add(ans)
        await self.db.flush()
        return ans

    async def _active_answer(self, question_id: str) -> BriefingAnswer | None:
        stmt = (
            select(BriefingAnswer)
            .where(BriefingAnswer.question_id == question_id)
            .where(BriefingAnswer.superseded.is_(False))
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_round_by_number(self, session_id: str, number: int) -> BriefingRound | None:
        stmt = (
            select(BriefingRound)
            .where(BriefingRound.session_id == session_id)
            .where(BriefingRound.round_number == number)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def accepted_answers_with_dimension(
        self, session_id: str
    ) -> list[tuple[str | None, str]]:
        """Принятые ответы как (dor_dimension, normalized_answer) — для обновления карточки."""
        stmt = (
            select(BriefingQuestion.dor_dimension, BriefingAnswer.normalized_answer)
            .join(BriefingAnswer, BriefingAnswer.question_id == BriefingQuestion.question_id)
            .where(BriefingAnswer.session_id == session_id)
            .where(BriefingAnswer.superseded.is_(False))
        )
        return [(row[0], row[1]) for row in (await self.db.execute(stmt)).all()]

    async def questions_by_ordinal(self, round_id: str) -> dict[int, str]:
        stmt = select(BriefingQuestion).where(BriefingQuestion.round_id == round_id)
        rows = (await self.db.execute(stmt)).scalars().all()
        return {q.ordinal: q.question_id for q in rows}

    # --- Авторизация /go ---
    async def add_go_event(
        self,
        event_id: str,
        session_id: str,
        task_id: str,
        user_id: str,
        rule: str | None,
        decision: str,
        authorized: bool,
        evidence: dict,
        high_risk_rule_applied: bool,
        source_comment_id: str | None = None,
    ) -> GoAuthorizationEvent:
        ev = GoAuthorizationEvent(
            event_id=event_id,
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
            rule=rule or "insufficient_rights",
            decision=decision,
            authorized=authorized,
            evidence=evidence,
            high_risk_rule_applied=high_risk_rule_applied,
            checked_at=_now(),
            source_comment_id=source_comment_id,
        )
        self.db.add(ev)
        await self.db.flush()
        return ev

    async def go_event_exists(self, event_id: str) -> bool:
        stmt = select(GoAuthorizationEvent.id).where(GoAuthorizationEvent.event_id == event_id)
        return (await self.db.execute(stmt)).first() is not None

    # --- Транзакционный outbox ---
    async def add_outbox(self, task_id: str, job: str, args: list) -> OutboxEvent:
        ev = OutboxEvent(task_id=task_id, job=job, args=args, status="pending")
        self.db.add(ev)
        await self.db.flush()
        return ev

    async def list_pending_outbox(self, limit: int = 100) -> list[OutboxEvent]:
        stmt = (
            select(OutboxEvent)
            .where(OutboxEvent.status == "pending")
            .order_by(OutboxEvent.created_at)
            .limit(limit)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def mark_outbox_sent(self, outbox_id: int) -> None:
        await self.db.execute(
            update(OutboxEvent)
            .where(OutboxEvent.id == outbox_id)
            .values(status="sent", sent_at=_now())
        )
        await self.db.flush()

    async def latest_authorized_go(self, session_id: str) -> GoAuthorizationEvent | None:
        stmt = (
            select(GoAuthorizationEvent)
            .where(GoAuthorizationEvent.session_id == session_id)
            .where(GoAuthorizationEvent.authorized.is_(True))
            .order_by(GoAuthorizationEvent.id.desc())
            .limit(1)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    # --- Сериализация ---
    async def to_contract(self, session: BriefingSession) -> BriefingSessionContract:
        accepted_stmt = (
            select(BriefingAnswer)
            .where(BriefingAnswer.session_id == session.session_id)
            .where(BriefingAnswer.superseded.is_(False))
        )
        accepted = (await self.db.execute(accepted_stmt)).scalars().all()
        answered_qids = {a.question_id for a in accepted}

        questions_stmt = select(BriefingQuestion).where(
            BriefingQuestion.session_id == session.session_id
        )
        questions = (await self.db.execute(questions_stmt)).scalars().all()
        open_questions = [
            q.question_id
            for q in questions
            if q.question_id not in answered_qids and not q.skipped and q.is_blocking
        ]

        go = await self.latest_authorized_go(session.session_id)
        go_event = (
            GoEvent(user_id=go.user_id, authorized=go.authorized, rule=go.rule) if go else None
        )

        return BriefingSessionContract(
            session_id=session.session_id,
            task_id=session.task_id,
            state=session.state,
            rounds_count=session.rounds_count,
            active_round_id=session.active_round_id,
            allowed_go_users=list(session.allowed_go_users or []),
            required_fields_snapshot=dict(session.required_fields_snapshot or {}),
            accepted_answers=[
                AcceptedAnswer(
                    question_id=a.question_id,
                    answer_id=a.answer_id,
                    source_comment_id=a.source_comment_id,
                )
                for a in accepted
            ],
            open_questions=open_questions,
            go_event=go_event,
        )
