import logging
from typing import Optional

from app.cloud.queue_store import dynamodb_state_repo
from app.config import settings
from app.models import QueryResponse, SearchDocument

logger = logging.getLogger("app.services.semantic_cache")


class SemanticCache:
    def __init__(self) -> None:
        # HONEST LABEL: despite the class name (kept for interface compatibility
        # with the rest of the pipeline), this is an exact-match cache keyed on
        # the normalized query string, not embedding-based semantic similarity.
        # In AWS backend mode, tenant cache invalidation generations are persisted
        # in DynamoDB so ingestion or deletion on one replica invalidates cached
        # answers on every replica.
        logger.info("Initializing exact-match query cache (with shared DynamoDB invalidation in AWS mode)...")
        self.local_cache: dict[tuple[str, str], tuple[str, list[SearchDocument], int]] = {}
        self._tenant_generations: dict[str, int] = {}

    def _evict_local_tenant(self, tenant_id: str) -> int:
        keys_to_remove = [k for k in self.local_cache if k[0] == tenant_id]
        for k in keys_to_remove:
            del self.local_cache[k]
        return len(keys_to_remove)

    def get_tenant_generation(self, tenant_id: str) -> int:
        """Return the last known local cache invalidation generation for a tenant.

        Args:
            tenant_id: Tenant identifier whose cache generation counter is queried.

        Returns:
            Monotonically increasing integer starting at ``0`` and incremented on
            every ``invalidate_tenant(tenant_id)`` call.
        """
        return self._tenant_generations.get(tenant_id, 0)

    async def get_tenant_generation_async(self, tenant_id: str) -> int:
        """Return the authoritative tenant cache generation (shared via DynamoDB in AWS mode).

        Args:
            tenant_id: Tenant identifier whose cache generation counter is queried.

        Returns:
            Current monotonic tenant generation; evicts stale local entries if a
            peer replica advanced the shared DynamoDB generation.
        """
        local_gen = self._tenant_generations.get(tenant_id, 0)
        if settings.aws_backend_enabled and settings.aws_dynamodb_table:
            shared_gen = await dynamodb_state_repo.get_cache_generation(tenant_id)
            if shared_gen > local_gen:
                self._tenant_generations[tenant_id] = shared_gen
                self._evict_local_tenant(tenant_id)
                return shared_gen
        return local_gen

    async def get(self, tenant_id: str, query: str) -> Optional[QueryResponse]:
        # Consult shared tenant generation first so cross-replica invalidations take effect immediately.
        current_gen = await self.get_tenant_generation_async(tenant_id)
        key = (tenant_id, query.strip().lower())

        if key in self.local_cache:
            cached_ans, cached_sources, entry_gen = self.local_cache[key]
            if entry_gen != current_gen:
                del self.local_cache[key]
                logger.info(f"Semantic cache STALE eviction for query: '{query}'")
                return None
            logger.info(f"Semantic cache HIT for query: '{query}'")
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
        current_gen = await self.get_tenant_generation_async(tenant_id)
        if expected_generation is not None and current_gen != expected_generation:
            logger.info(f"Skipping stale cache write for tenant '{tenant_id}' (generation changed during query)")
            return
        key = (tenant_id, query.strip().lower())
        self.local_cache[key] = (answer, sources, current_gen)
        logger.info(f"Cached answer for query: '{query}'")

    async def invalidate_tenant(self, tenant_id: str) -> int:
        next_local = self._tenant_generations.get(tenant_id, 0) + 1
        if settings.aws_backend_enabled and settings.aws_dynamodb_table:
            shared_gen = await dynamodb_state_repo.increment_cache_generation(tenant_id)
            self._tenant_generations[tenant_id] = max(next_local, shared_gen)
        else:
            self._tenant_generations[tenant_id] = next_local
        removed = self._evict_local_tenant(tenant_id)
        if removed:
            logger.info(f"Invalidated {removed} cached entries for tenant '{tenant_id}'")
        return removed


semantic_cache = SemanticCache()
