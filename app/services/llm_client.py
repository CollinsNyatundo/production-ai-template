"""
Real LLM client. Replaces the hardcoded canned-response branches that used to
live inline in rag_pipeline.py, executor.py, and query_rewriter.py.

Talks to NVIDIA's OpenAI-compatible endpoint (any model in the NVIDIA API
catalog can be swapped in via NVIDIA_MODEL without code changes). If
LANGSMITH_TRACING_ENABLED is set and an API key is present, every call is
automatically traced to LangSmith via wrap_openai - no manual span code needed.

Errors are allowed to propagate. Callers (executor.py, rag_pipeline.py,
query_rewriter.py) wrap calls in the existing AsyncCircuitBreaker
(app/security/resilience.py), which is where failure handling and fallback
behavior belongs - this module does not swallow errors or return fake data.
"""

import logging
import os
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion

from app.config import settings

logger = logging.getLogger("app.services.llm_client")


class LLMNotConfiguredError(RuntimeError):
    """Raised when a chat call is attempted without an NVIDIA_API_KEY configured."""


def _maybe_enable_langsmith_tracing() -> bool:
    """
    The langsmith SDK reads its config from process env vars, not from an
    object we control, so we propagate the pydantic Settings values into
    os.environ once at import time. Only does anything if the user actually
    configured a LangSmith key - otherwise tracing is a harmless no-op and
    the template works with zero LangSmith setup.
    """
    if not settings.langsmith_tracing_enabled or not settings.langsmith_api_key:
        return False
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    os.environ.setdefault("LANGSMITH_API_KEY", settings.langsmith_api_key)
    os.environ.setdefault("LANGSMITH_ENDPOINT", settings.langsmith_endpoint)
    os.environ.setdefault("LANGSMITH_PROJECT", settings.langsmith_project)
    return True


_TRACING_ENABLED = _maybe_enable_langsmith_tracing()


class LLMClient:
    def __init__(self) -> None:
        self._client: Optional[AsyncOpenAI] = None
        self._configured = bool(settings.nvidia_api_key)
        if self._configured:
            raw_client = AsyncOpenAI(
                api_key=settings.nvidia_api_key,
                base_url=settings.nvidia_base_url,
                timeout=settings.llm_request_timeout_s,
            )
            if _TRACING_ENABLED:
                # Deferred import: langsmith is only needed when tracing is on.
                from langsmith.wrappers import wrap_openai

                raw_client = wrap_openai(raw_client)
                logger.info(
                    f"LangSmith tracing enabled for LLM calls (project='{settings.langsmith_project}')"
                )
            self._client = raw_client
            logger.info(
                f"LLM client initialized: NVIDIA NIM, model='{settings.nvidia_model}', "
                f"base_url='{settings.nvidia_base_url}'"
            )
        else:
            logger.warning(
                "NVIDIA_API_KEY not set - LLM client is unconfigured. Calls will raise "
                "LLMNotConfiguredError, which the circuit breaker in each caller will "
                "catch and route to its existing fallback path."
            )

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> ChatCompletion:
        if not self._configured or self._client is None:
            raise LLMNotConfiguredError(
                "NVIDIA_API_KEY is not configured. Set it in .env to enable real LLM calls."
            )

        kwargs: Dict[str, Any] = {
            "model": settings.nvidia_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice or "auto"

        return await self._client.chat.completions.create(**kwargs)

    @staticmethod
    def tool_registry_schemas_to_openai_tools(schemas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Adapts ToolRegistry.get_tool_schemas() output to the OpenAI/NVIDIA `tools` format."""
        return [{"type": "function", "function": schema} for schema in schemas]


llm_client = LLMClient()
