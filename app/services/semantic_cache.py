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
        self.local_cache: dict[tuple[str, str], tuple[str, list[SearchDocument]]] = {}
        self._tenant_generations: dict[str, int] = {}

    def get_tenant_generation(self, tenant_id: str) -> int:
        """Return the current cache invalidation generation for a tenant.

        Args:
            tenant_id: Tenant identifier whose cache generation counter is queried.

        Returns:
            Monotonically increasing integer starting at ``0`` and incremented on
            every ``invalidate_tenant(tenant_id)`` call.
        """
        return self._tenant_generations.get(tenant_id, 0)

    async def get(self, tenant_id: str, query: str) -> Optional[QueryResponse]:
        # Clean query for key lookup
        key = (tenant_id, query.strip().lower())

        # Exact-match lookup - see the honest-label note in __init__.
        if key in self.local_cache:
            logger.info(f"Semantic cache HIT for query: '{query}'")
            cached_ans, cached_sources = self.local_cache[key]
            return QueryResponse(answer=cached_ans, sources=cached_sources, cached=True, latency_ms=0.0)

        logger.info(f"Semantic cache MISS for query: '{query}'")
        return None

    async def set(
        self,
        tenant_id: str,
        query: str,
        answer: str,
        sources: list[SearchDocument],
        expected_generation: Optional[int] = None,
    ) -> None:
        if expected_generation is not None and self.get_tenant_generation(tenant_id) != expected_generation:
            logger.info(f"Skipping stale cache write for tenant '{tenant_id}' (generation changed during query)")
            return
        key = (tenant_id, query.strip().lower())
        # Set value
        self.local_cache[key] = (answer, sources)
        logger.info(f"Cached answer for query: '{query}'")

    async def invalidate_tenant(self, tenant_id: str) -> int:
        self._tenant_generations[tenant_id] = self.get_tenant_generation(tenant_id) + 1
        keys_to_remove = [k for k in self.local_cache if k[0] == tenant_id]
        for k in keys_to_remove:
            del self.local_cache[k]
        if keys_to_remove:
            logger.info(f"Invalidated {len(keys_to_remove)} cached entries for tenant '{tenant_id}'")
        return len(keys_to_remove)


semantic_cache = SemanticCache()
