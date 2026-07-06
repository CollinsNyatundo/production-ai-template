import logging

logger = logging.getLogger("app.services.query_router")


class QueryRouter:
    async def route(self, query: str) -> str:
        logger.info(f"Routing query: '{query}'")

        # Simple heuristic routing. In production, this can be handled by an LLM-driven selector
        # or semantic classifiers that direct the query to different execution paths.
        query_lower = query.lower()
        if "web" in query_lower or "internet" in query_lower or "news" in query_lower:
            route_path = "web_search"
        elif (
            "code" in query_lower
            or "file" in query_lower
            or "repository" in query_lower
        ):
            route_path = "code_search"
        else:
            route_path = "vector_search"

        logger.info(f"Query routed to: '{route_path}'")
        return route_path


query_router = QueryRouter()
