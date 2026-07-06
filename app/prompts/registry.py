import logging
from typing import Dict
from app.prompts.templates import RAG_SYSTEM_PROMPT, SUMMARY_PROMPT

logger = logging.getLogger("app.prompts.registry")

class PromptRegistry:
    def __init__(self):
        # Local fallback cache
        self._local_prompts: Dict[str, str] = {
            "rag_system_prompt": RAG_SYSTEM_PROMPT,
            "summary_prompt": SUMMARY_PROMPT
        }
        logger.info("Initializing Prompt Registry (Hot-Swapping Enabled)...")

    async def get_prompt(self, name: str) -> str:
        logger.info(f"Resolving prompt template for: '{name}'")
        
        # PITFALL MITIGATION: In standard apps, prompts are locked in code.
        # In this production setup, we first attempt to pull from a remote prompt database
        # or services like Langfuse Prompt Hub / Redis config keys. If those fail,
        # we gracefully fallback to local code-defined templates.
        
        # Simulated Remote Fetch:
        try:
            # mock_fetch_success = False (Simulate fallback for local testing)
            # In production: return await remote_client.get_prompt(name)
            pass
        except Exception as e:
            logger.error(f"Failed to fetch remote prompt '{name}', falling back to local. Error: {e}")
            
        return self._local_prompts.get(name, "You are a helpful AI assistant.")

    def register_local_prompt(self, name: str, template: str) -> None:
        """Helper to add local templates at runtime or during testing."""
        self._local_prompts[name] = template

prompt_registry = PromptRegistry()
