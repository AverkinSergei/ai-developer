"""OpenAI-совместимый LLM-клиент (chat completions). Соблюдает протокол LLMClient.

base_url настраивается, поэтому подходит для OpenAI и совместимых провайдеров.
Ключи только через secrets; лимиты токенов контролирует вызывающий код.
"""

from typing import Any

import httpx

from app.clients.protocols import LLMResponse
from app.config import settings


class OpenAILLM:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self._key = api_key or settings.openai_api_key
        self._base = (base_url or settings.openai_base_url).rstrip("/")
        self._model = model or settings.llm_model
        self._timeout = timeout

    async def complete(
        self, system: str, messages: list[dict[str, str]], **kwargs: Any
    ) -> LLMResponse:
        payload = {
            "model": kwargs.get("model", self._model),
            "messages": [{"role": "system", "content": system}, *messages],
            "temperature": kwargs.get("temperature", 0.2),
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base}/chat/completions",
                headers={"Authorization": f"Bearer {self._key}"},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        text = data["choices"][0]["message"]["content"]
        tokens = int((data.get("usage") or {}).get("total_tokens", 0))
        return LLMResponse(text=text, tokens_used=tokens)
