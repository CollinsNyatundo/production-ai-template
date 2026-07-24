import asyncio
import logging

from app.services.llm_client import llm_client
from app.services.memory.mem0_client import mem0_client
from app.services.memory.memory_guard import memory_guard

logger = logging.getLogger("app.services.memory.memory_manager")


class MemoryManager:
    """Out-of-band async worker that extracts facts and resolves memory contradictions."""

    async def extract_and_store_memories_async(
        self,
        tenant_id: str,
        user_id: str,
        user_query: str,
        assistant_response: str,
    ) -> None:
        """Asynchronously extracts long-term facts/preferences and stores them in Mem0 store."""
        try:
            prompt = (
                f"You are a Memory Extraction Engine.\n"
                f"Analyze this interaction to extract long-term user preferences, coding standards, or domain facts.\n\n"
                f'USER QUERY: "{user_query}"\n'
                f'ASSISTANT RESPONSE: "{assistant_response[:400]}"\n\n'
                f"Extract 0 to 2 concise facts/preferences in 1 line each. If none exist, output 'NONE'."
            )

            resp = await llm_client.chat(
                messages=[
                    {"role": "system", "content": "Extract core user facts and preferences."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=150,
            )

            content = (resp.choices[0].message.content or "").strip()
            if "NONE" in content or not content:
                return

            candidate_lines = [line.strip("- 123456789. ") for line in content.split("\n") if line.strip()]

            for line in candidate_lines:
                is_safe, reason = memory_guard.validate_memory_candidate(line)
                if is_safe:
                    await mem0_client.add_memory(
                        tenant_id=tenant_id,
                        user_id=user_id,
                        text=line,
                        category="preference",
                        confidence=0.85,
                    )
                else:
                    logger.warning(f"Memory candidate rejected by MemoryGuard: {reason}")

        except Exception as err:
            logger.error(f"Error in async memory extraction for user '{user_id}': {err}")

    def trigger_async_extraction(
        self,
        tenant_id: str,
        user_id: str,
        user_query: str,
        assistant_response: str,
    ) -> None:
        """Fires memory extraction in an un-blocked background task."""
        try:
            asyncio.create_task(
                self.extract_and_store_memories_async(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    user_query=user_query,
                    assistant_response=assistant_response,
                )
            )
        except Exception as err:
            logger.warning(f"Failed to create background memory extraction task: {err}")


memory_manager = MemoryManager()
