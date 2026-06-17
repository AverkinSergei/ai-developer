from app.briefing import (
    completeness_ready,
    generate_questions,
    render_round_comment,
    template_questions,
)
from app.clients.fakes import FakeLLM
from app.contracts import TaskCard

CARD = TaskCard(task_id="B24-1", task_type="feature", target_repo="grp/repo")


def test_template_questions():
    qs = template_questions(["business_goal", "acceptance_criteria"])
    assert len(qs) == 2
    assert "бизнес-цель" in qs[0]


async def test_generate_questions_fallback_without_llm():
    qs = await generate_questions(CARD, ["acceptance_criteria"], llm=None, max_questions=4)
    assert qs == ["Какие критерии успешной приёмки?"]


async def test_generate_questions_with_llm():
    llm = FakeLLM(responses=['["Вопрос 1?", "Вопрос 2?"]'])
    qs = await generate_questions(CARD, ["business_goal"], llm=llm, max_questions=4)
    assert qs == ["Вопрос 1?", "Вопрос 2?"]


async def test_generate_questions_caps_max():
    llm = FakeLLM(responses=['["q1","q2","q3","q4","q5"]'])
    qs = await generate_questions(CARD, ["x"], llm=llm, max_questions=3)
    assert len(qs) == 3


async def test_generate_questions_bad_json_falls_back():
    llm = FakeLLM(responses=["не json"])
    qs = await generate_questions(CARD, ["reviewer"], llm=llm, max_questions=4)
    assert qs == ["Кто проводит ревью результата?"]


def test_completeness_ready():
    assert completeness_ready([], []) is True
    assert completeness_ready(["business_goal"], []) is False
    assert completeness_ready([], ["brf_1:r1:q1"]) is False


def test_render_round_comment():
    txt = render_round_comment("brf_1", "r1", ["Q про приёмку?", "Q про роли?"])
    assert "[AI_BRIEFING]" in txt
    assert "round_id: r1" in txt
    assert "/briefing answer r1" in txt
    assert "Q1: Q про приёмку?" in txt
    assert "Q2: Q про роли?" in txt
