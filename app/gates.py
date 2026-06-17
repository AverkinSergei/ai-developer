"""Сведение вердиктов AI-review и Red Team в решение о блокировке merge."""

from dataclasses import dataclass

from app.clients.protocols import LLMClient
from app.contracts import AIReviewVerdict, RedTeamResult, RiskPlanGate, TaskCard
from app.redteam import red_team_review, redteam_required
from app.reviewer import review_diff


@dataclass
class GateResult:
    blocked: bool
    reasons: list[str]
    review: AIReviewVerdict
    redteam: RedTeamResult | None


def merge_decision(review: AIReviewVerdict, redteam: RedTeamResult | None) -> GateResult:
    reasons: list[str] = []
    if review.merge_blocked:
        reasons.append(f"ai_review:{review.verdict}")
    if redteam is not None and redteam.merge_blocked:
        reasons.append(f"red_team:{redteam.verdict}")
    return GateResult(blocked=bool(reasons), reasons=reasons, review=review, redteam=redteam)


async def run_review_gates(
    card: TaskCard,
    gate: RiskPlanGate,
    diff: str,
    test_results: str,
    docs: str,
    llm: LLMClient,
    *,
    forced_redteam: bool = False,
) -> GateResult:
    """AI-review всегда; Red Team — по триггерам/риску/ручному запуску."""
    review = await review_diff(card, diff, test_results, docs, llm)
    changed_paths = [c.path for c in gate.changes]
    redteam = None
    if redteam_required(card, gate, changed_paths, forced=forced_redteam):
        redteam = await red_team_review(card, gate, diff, llm)
    return merge_decision(review, redteam)
