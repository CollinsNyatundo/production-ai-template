import logging
from typing import Dict, Optional

from langsmith import Client

from app.config import settings
from app.prompts.templates import (
    AGENT_SYSTEM_PROMPT,
    QUERY_REWRITE_PROMPT,
    RAG_SYSTEM_PROMPT,
    RERANK_PROMPT,
    SUMMARY_PROMPT,
)

logger = logging.getLogger("app.prompts.registry")


class PromptRegistry:
    def __init__(self) -> None:
        # Local fallback cache - always available even with zero external config.
        self._local_prompts: Dict[str, str] = {
            "rag_system_prompt": RAG_SYSTEM_PROMPT,
            "summary_prompt": SUMMARY_PROMPT,
            "agent_system_prompt": AGENT_SYSTEM_PROMPT,
            "query_rewrite_prompt": QUERY_REWRITE_PROMPT,
            "rerank_prompt": RERANK_PROMPT,
        }
        self._langsmith_client: Optional[Client] = None
        if settings.langsmith_api_key:
            try:
                self._langsmith_client = Client(
                    api_key=settings.langsmith_api_key, api_url=settings.langsmith_endpoint
                )
            except Exception as e:  # pragma: no cover - defensive, SDK/network issues
                logger.warning(f"Could not initialize LangSmith client for prompt hub: {e}")
        logger.info("Initializing Prompt Registry (LangSmith Prompt Hub, local fallback)...")

    async def get_prompt(self, name: str) -> str:
        logger.info(f"Resolving prompt template for: '{name}'")

        # Hot-swap path: if a prompt with this name has been pushed to the LangSmith
        # Prompt Hub, prefer it over the code-defined default so prompts can be
        # iterated on without a deploy. Any failure (no client, prompt doesn't
        # exist yet, network unreachable) falls back to the local template - this
        # is a real network call, not a simulation, so the except branch is a
        # normal, expected code path, not just a comment.
        if self._langsmith_client is not None:
            try:
                remote_prompt = self._langsmith_client.pull_prompt(name)
                template = self._extract_template_text(remote_prompt)
                if template:
                    logger.info(f"Resolved '{name}' from LangSmith Prompt Hub.")
                    return template
            except Exception as e:
                logger.info(f"No remote prompt for '{name}' (or fetch failed), using local default. Detail: {e}")

        return self._local_prompts.get(name, "You are a helpful AI assistant.")

    @staticmethod
    def _extract_template_text(remote_prompt: object) -> Optional[str]:
        """LangChain prompt objects vary in shape; pull out the raw template text defensively."""
        template = getattr(remote_prompt, "template", None)
        if isinstance(template, str):
            return template
        messages = getattr(remote_prompt, "messages", None)
        if messages:
            try:
                return "\n".join(getattr(m, "content", "") or "" for m in messages)
            except Exception:
                return None
        return None

    def register_local_prompt(self, name: str, template: str) -> None:
        """Helper to add local templates at runtime or during testing."""
        self._local_prompts[name] = template


prompt_registry = PromptRegistry()
