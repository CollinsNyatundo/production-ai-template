import pytest

from app.services.query_router import query_router


@pytest.mark.asyncio
async def test_router_heuristics():
    # Assert code query routes to code_search
    code_route = await query_router.route("Show me the config file schema")
    assert code_route == "code_search"

    # Assert web query routes to web_search
    web_route = await query_router.route("What are the latest news on AI regulations?")
    assert web_route == "web_search"

    # Assert standard query routes to vector_search
    vector_route = await query_router.route("Explain hybrid retrieval mechanisms")
    assert vector_route == "vector_search"
