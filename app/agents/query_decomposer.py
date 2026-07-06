import logging
from typing import List

logger = logging.getLogger("app.agents.query_decomposer")


class QueryDecomposer:
    async def decompose(self, query: str) -> List[str]:
        logger.info(f"Decomposing query: '{query}'")

        # Simulated decomposition. In production, an LLM parses the user prompt
        # and outputs a list of discrete sub-questions for parallel execution.
        # E.g. "What is semantic caching and what is hybrid retrieval?" ->
        # ["What is semantic caching?", "What is hybrid retrieval?"]

        cleaned = query.strip()
        if " and " in cleaned.lower():
            parts = cleaned.lower().split(" and ")
            sub_queries = [p.strip().capitalize() for p in parts]
            logger.info(f"Decomposed into sub-queries: {sub_queries}")
            return sub_queries

        return [query]


query_decomposer = QueryDecomposer()
