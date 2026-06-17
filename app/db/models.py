"""ORM-модели: состояние задач, брифинг, авторизация /go, audit trail.

БД — источник истины для брифинга. Redis хранит только volatile-состояние.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.briefing_state_machine import ALL_STATES, TERMINAL
from app.db.base import Base

_STATE_LIST = ", ".join(f"'{s}'" for s in sorted(ALL_STATES))
_TERMINAL_LIST = ", ".join(f"'{s}'" for s in sorted(TERMINAL))


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def _updated() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class TaskState(Base):
    """Состояние задачи целиком. Optimistic lock через version_id_col."""

    __tablename__ = "task_state"

    task_id: Mapped[str] = mapped_column(String, primary_key=True)
    repo: Mapped[str] = mapped_column(String, nullable=False)
    target_branch: Mapped[str] = mapped_column(String, nullable=False)
    task_type: Mapped[str] = mapped_column(String, nullable=False)
    phase: Mapped[str] = mapped_column(String, nullable=False, default="intake")
    risk_level: Mapped[str | None] = mapped_column(String, nullable=True)
    red_team_required: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    reviewer_user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    mr_iid: Mapped[str | None] = mapped_column(String, nullable=True)
    source_branch: Mapped[str | None] = mapped_column(String, nullable=True)
    author_user_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    # Полный снимок карточки задачи (TaskCard) — обновляется ответами брифинга.
    card_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()

    __mapper_args__ = {"version_id_col": version}


class BriefingSession(Base):
    """Каноническое хранилище брифинга. Один активный сеанс на задачу."""

    __tablename__ = "briefing_session"
    __table_args__ = (
        CheckConstraint(f"state IN ({_STATE_LIST})", name="ck_session_state"),
        # Один активный сеанс на task_id (терминальные состояния не учитываются).
        Index(
            "uq_session_active_task",
            "task_id",
            unique=True,
            postgresql_where=text(f"state NOT IN ({_TERMINAL_LIST})"),
        ),
    )

    session_id: Mapped[str] = mapped_column(String, primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("task_state.task_id"), nullable=False)
    repo: Mapped[str] = mapped_column(String, nullable=False)
    target_branch: Mapped[str] = mapped_column(String, nullable=False)
    state: Mapped[str] = mapped_column(String, nullable=False)
    rounds_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active_round_id: Mapped[str | None] = mapped_column(String, nullable=True)
    allowed_go_users: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    required_fields_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    author_user_id: Mapped[str] = mapped_column(String, nullable=False)
    bitrix_comment_id: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="open")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()

    __mapper_args__ = {"version_id_col": version}


class BriefingRound(Base):
    """Неизменяемый набор вопросов, опубликованный одним комментарием бота."""

    __tablename__ = "briefing_round"
    __table_args__ = (
        UniqueConstraint("session_id", "round_number", name="uq_round_session_number"),
    )

    round_id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("briefing_session.session_id"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(String, nullable=False)
    repo: Mapped[str] = mapped_column(String, nullable=False)
    target_branch: Mapped[str] = mapped_column(String, nullable=False)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String, nullable=False, default="WAITING_ANSWERS")
    author_user_id: Mapped[str] = mapped_column(String, nullable=False)
    bitrix_comment_id: Mapped[str] = mapped_column(String, nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="open")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class BriefingQuestion(Base):
    __tablename__ = "briefing_question"

    question_id: Mapped[str] = mapped_column(String, primary_key=True)
    round_id: Mapped[str] = mapped_column(ForeignKey("briefing_round.round_id"), nullable=False)
    session_id: Mapped[str] = mapped_column(String, nullable=False)
    task_id: Mapped[str] = mapped_column(String, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    dor_dimension: Mapped[str | None] = mapped_column(String, nullable=True)
    is_blocking: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    skipped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    skip_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="open")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class BriefingAnswer(Base):
    """Версионируемый ответ: правка создаёт новую строку, прежняя superseded=true."""

    __tablename__ = "briefing_answer"
    __table_args__ = (
        Index(
            "uq_answer_active_question",
            "question_id",
            unique=True,
            postgresql_where=text("superseded = false"),
        ),
        Index("ix_answer_question_version", "question_id", "answer_version"),
    )

    answer_id: Mapped[str] = mapped_column(String, primary_key=True)
    question_id: Mapped[str] = mapped_column(
        ForeignKey("briefing_question.question_id"), nullable=False
    )
    round_id: Mapped[str] = mapped_column(String, nullable=False)
    session_id: Mapped[str] = mapped_column(String, nullable=False)
    task_id: Mapped[str] = mapped_column(String, nullable=False)
    answer_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    superseded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_answer: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    source_comment_id: Mapped[str] = mapped_column(String, nullable=False)
    accepted_by_rule: Mapped[str] = mapped_column(String, nullable=False)
    author_user_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="accepted")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class GoAuthorizationEvent(Base):
    """Каждая попытка /go: authorized / rejected / ignored_duplicate. Append-only."""

    __tablename__ = "go_authorization_event"
    __table_args__ = (
        # Не более одного авторизованного /go на сессию (single-start независимо от лока).
        Index(
            "uq_go_authorized_per_session",
            "session_id",
            unique=True,
            postgresql_where=text("authorized = true"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("briefing_session.session_id"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(String, nullable=False)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    rule: Mapped[str] = mapped_column(String, nullable=False)
    decision: Mapped[str] = mapped_column(String, nullable=False)
    authorized: Mapped[bool] = mapped_column(Boolean, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    high_risk_rule_applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_comment_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = _created()


class OutboxEvent(Base):
    """Транзакционный outbox: намерение поставить фоновую задачу пишется в одной
    транзакции с переходом состояния. Relay читает pending и ставит в очередь —
    это исключает lost-start при сбое enqueue после commit."""

    __tablename__ = "outbox_event"
    __table_args__ = (Index("ix_outbox_status_created", "status", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String, nullable=False)
    job: Mapped[str] = mapped_column(String, nullable=False)
    args: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    created_at: Mapped[datetime] = _created()
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditEvent(Base):
    """Append-only audit trail. Редакция секретов выполняется до вставки."""

    __tablename__ = "audit_event"
    __table_args__ = (
        Index("ix_audit_task_created", "task_id", "created_at"),
        Index("ix_audit_event_type", "event_type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String, nullable=False)
    repo: Mapped[str | None] = mapped_column(String, nullable=True)
    branch: Mapped[str | None] = mapped_column(String, nullable=True)
    phase: Mapped[str] = mapped_column(String, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    outcome: Mapped[str | None] = mapped_column(String, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    actor: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = _created()
