"""Provider-agnostic LLM client helpers.

All chat and embedding traffic goes through OpenAI-compatible endpoints,
which lets the platform run on open-source models (Llama via Groq or
OpenRouter, local Ollama, Together, ...) by configuration alone. See
Settings.chat_llm / Settings.embedding_llm for the resolution rules.
"""

import logging
from typing import Optional, Tuple

from app.core.config import Settings

try:
    from openai import OpenAI

    OPENAI_SDK_AVAILABLE = True
except ImportError:  # pragma: no cover - the sdk is a hard dep in production
    OpenAI = None
    OPENAI_SDK_AVAILABLE = False

logger = logging.getLogger(__name__)


def get_chat_client(settings: Settings) -> Tuple[Optional["OpenAI"], Optional[str]]:
    """Return (client, model) for chat completions, or (None, None)."""
    config = settings.chat_llm
    if config is None or not OPENAI_SDK_AVAILABLE:
        return None, None
    client = OpenAI(api_key=config["api_key"], base_url=config["base_url"])
    return client, config["model"]


def get_embedding_client(
    settings: Settings,
) -> Tuple[Optional["OpenAI"], Optional[str], int]:
    """Return (client, model, dimensions) for embeddings, or (None, None, 0)."""
    config = settings.embedding_llm
    if config is None or not OPENAI_SDK_AVAILABLE:
        return None, None, 0
    client = OpenAI(api_key=config["api_key"], base_url=config["base_url"])
    return client, config["model"], config["dimensions"]
