import logging
from typing import Dict, List

logger = logging.getLogger("app.services.conversation")

class ConversationService:
    def __init__(self):
        # In-memory dictionary representing session history database
        self.sessions: Dict[str, List[Dict[str, str]]] = {}

    async def get_history(self, session_id: str) -> List[Dict[str, str]]:
        logger.info(f"Retrieving history for session: {session_id}")
        return self.sessions.get(session_id, [])

    async def add_message(self, session_id: str, role: str, content: str) -> None:
        logger.info(f"Adding {role} message to session: {session_id}")
        if session_id not in self.sessions:
            self.sessions[session_id] = []
        self.sessions[session_id].append({"role": role, "content": content})

    async def clear_history(self, session_id: str) -> None:
        logger.info(f"Clearing history for session: {session_id}")
        if session_id in self.sessions:
            del self.sessions[session_id]

conversation_service = ConversationService()
