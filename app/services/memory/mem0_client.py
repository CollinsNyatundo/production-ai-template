import datetime
import logging
import uuid
from dataclasses import dataclass, field
from typing import Dict, List

logger = logging.getLogger("app.services.memory.mem0_client")


@dataclass
class MemoryItem:
    """Represents a single persistent memory entry."""

    text: str
    tenant_id: str = "default-tenant"
    user_id: str = "default-user"
    category: str = "preference"  # preference, technical, business, domain
    confidence: float = 0.9
    memory_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    created_at: str = field(default_factory=lambda: datetime.datetime.utcnow().isoformat())


class Mem0Client:
    """Hybrid Memory Store client with strict multi-tenant isolation."""

    def __init__(self) -> None:
        # In-memory store keyed by compound (tenant_id, user_id)
        self._store: Dict[str, List[MemoryItem]] = {}

    def _get_key(self, tenant_id: str, user_id: str) -> str:
        return f"{tenant_id}:{user_id}"

    async def add_memory(
        self,
        tenant_id: str,
        user_id: str,
        text: str,
        category: str = "preference",
        confidence: float = 0.9,
    ) -> MemoryItem:
        """Stores a new memory item for the specified tenant and user."""
        key = self._get_key(tenant_id, user_id)
        if key not in self._store:
            self._store[key] = []

        # Deduplicate exact text
        clean_text = text.strip()
        for item in self._store[key]:
            if item.text.lower() == clean_text.lower():
                item.confidence = max(item.confidence, confidence)
                return item

        memory_item = MemoryItem(
            text=clean_text,
            tenant_id=tenant_id,
            user_id=user_id,
            category=category,
            confidence=confidence,
        )
        self._store[key].append(memory_item)
        logger.info(f"Added memory '{memory_item.memory_id}' for scope '{key}'")
        return memory_item

    async def search_memories(
        self,
        tenant_id: str,
        user_id: str,
        query: str = "",
        limit: int = 5,
    ) -> List[MemoryItem]:
        """Searches persistent memories for a specific tenant and user."""
        key = self._get_key(tenant_id, user_id)
        memories = self._store.get(key, [])
        if not memories:
            return []

        if not query.strip():
            return memories[:limit]

        # Simple semantic keyword overlap scoring
        query_words = set(query.lower().split())
        scored: List[tuple[float, MemoryItem]] = []

        for item in memories:
            item_words = set(item.text.lower().split())
            overlap = len(query_words.intersection(item_words))
            score = (overlap / (len(query_words) or 1)) * item.confidence
            scored.append((score, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:limit]]

    async def get_all_memories(self, tenant_id: str, user_id: str) -> List[MemoryItem]:
        """Retrieves all active memories for a given tenant and user scope."""
        key = self._get_key(tenant_id, user_id)
        return list(self._store.get(key, []))

    async def delete_memory(self, tenant_id: str, user_id: str, memory_id: str) -> bool:
        """Deletes a specific memory item by memory_id within tenant isolation bounds."""
        key = self._get_key(tenant_id, user_id)
        memories = self._store.get(key, [])
        initial_len = len(memories)

        self._store[key] = [m for m in memories if m.memory_id != memory_id]
        deleted = len(self._store[key]) < initial_len
        if deleted:
            logger.info(f"Deleted memory '{memory_id}' from scope '{key}'")
        return deleted

    async def clear_scope(self, tenant_id: str, user_id: str) -> None:
        """Clears all memories for a specific tenant and user scope."""
        key = self._get_key(tenant_id, user_id)
        if key in self._store:
            del self._store[key]
            logger.info(f"Cleared memory scope '{key}'")


# Singleton instance
mem0_client = Mem0Client()
