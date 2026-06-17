"""Канонические контракты между модулями."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

RiskLevel = Literal["low", "medium", "high", "blocked"]
Severity = Literal["low", "medium", "high", "critical"]
ReviewSeverity = Literal["low", "medium", "high", "blocker"]


class Change(BaseModel):
    path: str
    action: Literal["create", "update", "delete"]
    rationale: str


class RiskPlanGate(BaseModel):
    risk_level: RiskLevel
    risk_reasons: list[str] = Field(default_factory=list)
    red_team_required: bool = False
    human_preapproval_required: bool = False
    context_files: list[str] = Field(default_factory=list)
    changes: list[Change] = Field(default_factory=list)
    test_plan: list[str] = Field(default_factory=list)
    doc_impact: Literal["yes", "no"]
    doc_skip_reason: str | None = None
    rollback_note: str = ""
    out_of_scope: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> "RiskPlanGate":
        if self.doc_impact == "no" and not (self.doc_skip_reason or "").strip():
            raise ValueError("doc_skip_reason required when doc_impact='no'")
        if self.risk_level == "high":
            self.red_team_required = True
            self.human_preapproval_required = True
        return self


class RedTeamFinding(BaseModel):
    title: str
    severity: Severity
    affected_files: list[str] = Field(default_factory=list)
    exploit_scenario: str
    recommended_fix: str
    merge_blocking: bool


class RedTeamResult(BaseModel):
    verdict: Literal["PASS", "PASS_WITH_NOTES", "FAIL", "NEED_HUMAN_SECURITY_REVIEW"]
    max_severity: Severity
    findings: list[RedTeamFinding] = Field(default_factory=list)

    @property
    def merge_blocked(self) -> bool:
        if self.verdict in ("FAIL", "NEED_HUMAN_SECURITY_REVIEW"):
            return True
        return any(f.severity in ("high", "critical") for f in self.findings)


class ReviewComment(BaseModel):
    file: str
    line: int | None = None
    severity: ReviewSeverity
    body: str


class AIReviewVerdict(BaseModel):
    verdict: Literal["PASS", "PASS_WITH_NOTES", "FAIL", "NEED_HUMAN_REVIEW"]
    comments: list[ReviewComment] = Field(default_factory=list)

    @property
    def merge_blocked(self) -> bool:
        if self.verdict in ("FAIL", "NEED_HUMAN_REVIEW"):
            return True
        return any(c.severity in ("high", "blocker") for c in self.comments)


CommandKind = Literal[
    "go",  # закрыть брифинг и разрешить агенту работать (после авторизации)
    "briefing_answer",  # ответы на вопросы раунда: /briefing answer <round_id>
    "briefing_status",  # показать текущее состояние брифинга
    "briefing_reopen",  # открыть новый раунд после READY_FOR_GO: /briefing reopen <reason>
    "briefing_cancel",  # остановить брифинг: /briefing cancel <reason>
    "briefing_skip",  # явно отказать в ответе на вопрос: /briefing skip <question_id> <reason>
    "ai_status",  # @ai status — краткий статус фазы и блокеров
    "ai_stop",  # @ai stop — остановить агента и снять lock
    "ai_retry",  # @ai retry — перезапустить последнюю упавшую фазу
    "ai_resolve",  # @ai resolve — попытаться разрешить конфликт MR
    "ai_fix",  # @ai fix — исправить замечания в MR в рамках лимитов
    "ai_redteam",  # @ai redteam — принудительно запустить Red Team review
]


class BriefingCommand(BaseModel):
    """Разобранная управляющая команда из комментария Битрикс24."""

    kind: CommandKind
    round_id: str | None = None
    question_id: str | None = None
    args: str = ""  # reason / прочий хвост
    raw: str = ""  # полный текст комментария (для экстрактора ответов)


class AcceptedAnswer(BaseModel):
    question_id: str
    answer_id: str
    source_comment_id: str


class GoEvent(BaseModel):
    user_id: str
    authorized: bool
    rule: str


class BriefingSessionContract(BaseModel):
    """Сериализация сеанса брифинга для внешнего обмена."""

    session_id: str
    task_id: str
    state: str
    rounds_count: int
    active_round_id: str | None = None
    allowed_go_users: list[str] = Field(default_factory=list)
    required_fields_snapshot: dict = Field(default_factory=dict)
    accepted_answers: list[AcceptedAnswer] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    go_event: GoEvent | None = None


class TaskCard(BaseModel):
    """Карточка задачи из нативных полей Битрикс24 + теги из текста."""

    # Ограниченный набор символов: task_id попадает в имя ветки auto-task-{id}.
    task_id: str = Field(pattern=r"^[A-Za-z0-9_:.\-]+$")
    task_type: Literal["feature", "bugfix", "refactor", "research", "review", "security_review"]
    target_repo: str  # основной репозиторий (где делается MR)
    target_repos: list[str] = Field(default_factory=list)  # доп. репозитории для изменений (MR)
    context_repos: list[str] = Field(default_factory=list)  # read-only: только контекст, без MR
    target_branch: str = "dev"
    business_goal: str = ""
    acceptance_criteria: str = ""
    affected_area: list[str] = Field(default_factory=list)
    risk_hint: RiskLevel = "low"
    reviewer: str | None = None
    author_user_id: str = ""
    # Теги-модификаторы из текста.
    tests: Literal["required", "optional", "skip"] | None = None
    docs: Literal["required", "auto", "skip"] | None = None
    preview: bool | None = None
    security: bool = False
    context_keywords: list[str] = Field(default_factory=list)

    @property
    def all_repos(self) -> list[str]:
        """Репозитории, где делаются изменения/MR (основной + дополнительные), без дублей."""
        ordered = dict.fromkeys([self.target_repo, *self.target_repos])
        return [r for r in ordered if r]

    @property
    def context_only_repos(self) -> list[str]:
        """Read-only репозитории для контекста, исключая те, где делается MR."""
        change_repos = set(self.all_repos)
        return [r for r in dict.fromkeys(self.context_repos) if r and r not in change_repos]
