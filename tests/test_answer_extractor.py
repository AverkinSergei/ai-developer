from app.answer_extractor import accepted, extract_structured, extract_with_model
from app.clients.fakes import FakeLLM

QBO = {1: "brf_1:r1:q1", 2: "brf_1:r1:q2"}


def test_extract_structured_maps_by_ordinal():
    text = "/briefing answer r1\nA1: критерий приёмки\nA2: только менеджер"
    out = extract_structured(text, QBO)
    assert {a.question_id for a in out} == {"brf_1:r1:q1", "brf_1:r1:q2"}
    assert all(a.confidence == 1.0 for a in out)
    assert all(a.accepted_by_rule == "structured_command" for a in out)


def test_extract_structured_ignores_unmapped():
    out = extract_structured("A3: ответ без вопроса", QBO)
    assert out == []


def test_accepted_threshold_filters_low_confidence():
    out = extract_structured("A1: x", QBO)
    assert accepted(out, 0.7) == out
    # искусственно занизим
    out[0].confidence = 0.5
    assert accepted(out, 0.7) == []


async def test_extract_with_model_parses_json():
    llm = FakeLLM(responses=['[{"ordinal": 1, "answer": "через таблицу", "confidence": 0.92}]'])
    out = await extract_with_model("свободный текст", QBO, llm)
    assert len(out) == 1
    assert out[0].question_id == "brf_1:r1:q1"
    assert out[0].confidence == 0.92
    assert out[0].accepted_by_rule == "model_extracted"


async def test_extract_with_model_bad_json_returns_empty():
    llm = FakeLLM(responses=["не json"])
    out = await extract_with_model("текст", QBO, llm)
    assert out == []
