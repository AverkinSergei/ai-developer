"""Сопоставление ответов постановщика с вопросами раунда.

Сначала пытаемся структурированный разбор (A1/A2 -> вопрос по порядковому номеру);
если не вышло и доступна модель — извлечение моделью с оценкой confidence.
Ответы ниже порога confidence не принимаются: агент просит структурированный формат.
"""

import json
import re
from dataclasses import dataclass

from app.clients.protocols import LLMClient

_ANSWER_LINE = re.compile(r"^\s*A(\d+)\s*[:.)]\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)

_EXTRACT_SYSTEM = (
    "Ты сопоставляешь ответы постановщика с вопросами брифинга. "
    "Верни JSON-массив объектов {ordinal, answer, confidence}. "
    "confidence в [0,1] — насколько уверенно ответ относится к вопросу. "
    "Не выдумывай ответы; если сопоставить нельзя, не включай вопрос."
)


@dataclass
class ExtractedAnswer:
    question_id: str
    raw_text: str
    normalized_answer: str
    confidence: float
    accepted_by_rule: str


def extract_structured(raw_text: str, question_by_ordinal: dict[int, str]) -> list[ExtractedAnswer]:
    """Разбирает строки вида 'A1: ...' и привязывает к вопросу по порядковому номеру."""
    out: list[ExtractedAnswer] = []
    for num, body in _ANSWER_LINE.findall(raw_text or ""):
        qid = question_by_ordinal.get(int(num))
        if not qid:
            continue  # ответ без соответствующего вопроса игнорируем
        text = body.strip()
        out.append(
            ExtractedAnswer(
                question_id=qid,
                raw_text=text,
                normalized_answer=text,
                confidence=1.0,
                accepted_by_rule="structured_command",
            )
        )
    return out


async def extract_with_model(
    raw_text: str,
    question_by_ordinal: dict[int, str],
    llm: LLMClient,
) -> list[ExtractedAnswer]:
    """Извлечение ответов моделью с самостоятельной оценкой confidence."""
    questions_repr = "\n".join(
        f"Q{ordn}: (question_id={qid})" for ordn, qid in question_by_ordinal.items()
    )
    resp = await llm.complete(
        system=_EXTRACT_SYSTEM,
        messages=[{"role": "user", "content": f"Вопросы:\n{questions_repr}\n\nОтвет:\n{raw_text}"}],
    )
    try:
        items = json.loads(resp.text)
    except (json.JSONDecodeError, TypeError):
        return []
    out: list[ExtractedAnswer] = []
    for it in items if isinstance(items, list) else []:
        qid = question_by_ordinal.get(int(it.get("ordinal", -1)))
        if not qid:
            continue
        text = str(it.get("answer", "")).strip()
        if not text:
            continue
        # confidence сообщает модель по недоверенному тексту — клампим в [0,1],
        # чтобы инъекция не могла выдать значение выше порога обходным путём.
        try:
            conf = max(0.0, min(1.0, float(it.get("confidence", 0.0))))
        except (TypeError, ValueError):
            conf = 0.0
        out.append(
            ExtractedAnswer(
                question_id=qid,
                raw_text=text,
                normalized_answer=text,
                confidence=conf,
                accepted_by_rule="model_extracted",
            )
        )
    return out


def accepted(answers: list[ExtractedAnswer], confidence_min: float) -> list[ExtractedAnswer]:
    """Оставляет только ответы с confidence не ниже порога."""
    return [a for a in answers if a.confidence >= confidence_min]
