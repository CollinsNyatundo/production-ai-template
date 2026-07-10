import logging
from typing import Optional

from app.models import QueryResponse, SearchDocument

logger = logging.getLogger("app.services.semantic_cache")


class SemanticCache:
    def __init__(self):
        # HONEST LABEL: despite the class name (kept for interface compatibility
        # with the rest of the pipeline), this is an exact-match cache keyed on
        # the normalized query string, not embedding-based semantic similarity.
        # NVIDIA's catalog includes embedding models (e.g. nv-embedqa) that could
        # back real cosine-similarity matching here - that's the natural next
        # step, not implemented in this pass. This also does not use Redis: it's
        # process-local memory, which means cache state is lost on restart and
        # NOT shared across replicas if this app is ever horizontally scaled.
        # REDIS_URL is configured but genuinely unused until that's built.
        logger.info("Initializing in-process exact-match query cache (local memory, not Redis-backed yet)...")
        self.local_cache = {}

    async def get(self, query: str) -> Optional[QueryResponse]:
        # Clean query for key lookup
        key = query.strip().lower()

        # Exact-match lookup - see the honest-label note in __init__.
        if key in self.local_cache:
            logger.info(f"Semantic cache HIT for query: '{query}'")
            cached_ans, cached_sources = self.local_cache[key]
            return QueryResponse(answer=cached_ans, sources=cached_sources, cached=True, latency_ms=0.0)

        logger.info(f"Semantic cache MISS for query: '{query}'")
        return None

    async def set(self, query: str, answer: str, sources: list[SearchDocument]) -> None:
        key = query.strip().lower()
        # Set value
        self.local_cache[key] = (answer, sources)
        logger.info(f"Cached answer for query: '{query}'")


semantic_cache = SemanticCache()
