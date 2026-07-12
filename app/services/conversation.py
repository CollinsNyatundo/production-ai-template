import logging
from typing import Dict, List

from app.services.state_store import state_store

logger = logging.getLogger("app.services.conversation")


class ConversationService:
    async def get_history(self, session_id: str) -> List[Dict[str, str]]:
        logger.info(f"Retrieving history for session: {session_id}")
        return await state_store.get_history(session_id)

    async def add_message(self, session_id: str, role: str, content: str) -> None:
        logger.info(f"Saving message to state store for session: {session_id}")
        await state_store.save_message(session_id, role, content)

    async def clear_history(self, session_id: str) -> None:
        logger.info(f"Clearing history from state store for session: {session_id}")
        await state_store.clear_history(session_id)


conversation_service = ConversationService()
