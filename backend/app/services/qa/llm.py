"""Single isolation point for the QA pipeline's LLM vendor.

Every stage goes through this client so model versions are recorded on
responses and swapping vendors touches one file.
"""

import json
import logging
from typing import Any

from openai import OpenAI

from app.core.config import Settings

logger = logging.getLogger(__name__)

ANSWER_MODEL = "gpt-4.1"
FAST_MODEL = "gpt-4.1-mini"


class LLMClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = (
            OpenAI(api_key=settings.openai_api_key)
            if settings.is_openai_configured
            else None
        )
        self.models_used: set[str] = set()

    @property
    def is_configured(self) -> bool:
        return self.client is not None

    def chat_text(
        self,
        messages: list[dict[str, str]],
        model: str = ANSWER_MODEL,
        temperature: float = 0.2,
        max_tokens: int = 900,
    ) -> str | None:
        if not self.client:
            return None
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            self.models_used.add(model)
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"LLM call failed ({model}): {e}")
            return None

    def chat_json(
        self,
        messages: list[dict[str, str]],
        model: str = FAST_MODEL,
        temperature: float = 0.0,
    ) -> dict[str, Any] | None:
        if not self.client:
            return None
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                response_format={"type": "json_object"},
            )
            self.models_used.add(model)
            return json.loads(response.choices[0].message.content or "{}")
        except Exception as e:
            logger.error(f"LLM JSON call failed ({model}): {e}")
            return None
