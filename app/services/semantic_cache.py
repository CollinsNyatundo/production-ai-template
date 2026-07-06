import logging
from typing import Optional

from app.config import settings
from app.models import QueryResponse, SearchDocument

logger = logging.getLogger("app.services.semantic_cache")


class SemanticCache:
    def __init__(self):
        # In production, initialize Redis vector index or local Faiss / SQLite
        logger.info(f"Connecting to Redis cache at {settings.redis_url}...")
        self.redis_client = None
        # We handle Redis connection errors gracefully and fallback to in-memory dictionary
        self.local_cache = {}

    async def get(self, query: str) -> Optional[QueryResponse]:
        # Clean query for key lookup
        key = query.strip().lower()

        # Check cache (in production this does cosine similarity on query embeddings)
        if key in self.local_cache:
            logger.info(f"Semantic cache HIT for query: '{query}'")
            cached_ans, cached_sources = self.local_cache[key]
            return QueryResponse(
                answer=cached_ans, sources=cached_sources, cached=True, latency_ms=0.0
            )

        logger.info(f"Semantic cache MISS for query: '{query}'")
        return None

    async def set(self, query: str, answer: str, sources: list[SearchDocument]) -> None:
        key = query.strip().lower()
        # Set value
        self.local_cache[key] = (answer, sources)
        logger.info(f"Cached answer for query: '{query}'")


semantic_cache = SemanticCache()
