import pytest

from app.services.semantic_cache import semantic_cache


@pytest.mark.asyncio
async def test_cache_miss_and_hit():
    query = "Unique cache test query"

    # Assert cache miss initially
    miss_res = await semantic_cache.get(query)
    assert miss_res is None

    # Seed cache
    await semantic_cache.set(query, "Cached response", [])

    # Assert cache hit
    hit_res = await semantic_cache.get(query)
    assert hit_res is not None
    assert hit_res.answer == "Cached response"
    assert hit_res.cached is True
