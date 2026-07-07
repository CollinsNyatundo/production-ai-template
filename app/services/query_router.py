import logging

from app.security.resilience import CircuitBreakerOpenException, llm_breaker

logger = logging.getLogger("app.services.query_router")


class QueryRouter:
    async def _execute_route(self, query: str) -> str:
        # Simple heuristic routing. In production, this can be handled by an LLM-driven selector
        # or semantic classifiers that direct the query to different execution paths.
        query_lower = query.lower()
        if "web" in query_lower or "internet" in query_lower or "news" in query_lower:
            return "web_search"
        elif "code" in query_lower or "file" in query_lower or "repository" in query_lower:
            return "code_search"
        else:
            return "vector_search"

    async def route(self, query: str) -> str:
        logger.info(f"Routing query: '{query}'")
        try:
            # Wrap router LLM call in circuit breaker
            route_path = await llm_breaker.call(self._execute_route, query)
            logger.info(f"Query routed to: '{route_path}'")
            return route_path
        except CircuitBreakerOpenException:
            logger.warning("LLM Circuit Breaker is OPEN. Falling back to default route 'vector_search'.")
            return "vector_search"


query_router = QueryRouter()
