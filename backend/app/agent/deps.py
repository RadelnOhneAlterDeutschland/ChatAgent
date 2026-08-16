"""Wires the real `LLMProvider` for FastAPI request handling.

Tests override `get_llm_provider` with `tests/fakes/llm_provider.py::FakeLLMProvider` via
`app.dependency_overrides` — see `tests/conftest.py::client`. The per-request tool list
(bound to the caller's `db`/`owner_id`) is assembled in `api/chat.py`, not here — a tool
can't be a cacheable singleton the way the provider can.
"""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.agent.providers.base import LLMProvider
from app.agent.providers.openai_provider import OpenAIProvider
from app.core.config import get_settings


@lru_cache
def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    return OpenAIProvider(api_key=settings.openai_api_key, model=settings.openai_chat_model)


LLMProviderDep = Annotated[LLMProvider, Depends(get_llm_provider)]
