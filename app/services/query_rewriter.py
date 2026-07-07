import logging

from app.security.resilience import CircuitBreakerOpenException, llm_breaker

logger = logging.getLogger("app.services.query_rewriter")


class QueryRewriter:
    async def _execute_rewrite(self, query: str, history: str) -> str:
        # Simple simulated rewrite:
        # In production, this calls a cheap LLM model (e.g. gpt-4o-mini) with a system prompt
        # that incorporates previous conversation history to rephrase the question.
        rewritten = query.strip()
        if "what is this" in rewritten.lower() and history:
            rewritten = f"Explanation of {history} based on RAG documentation"
        return rewritten

    async def rewrite(self, query: str, history: str = "") -> str:
        logger.info(f"Rewriting query: '{query}'")
        try:
            # Wrap LLM call in circuit breaker to protect application thread pool
            return await llm_breaker.call(self._execute_rewrite, query, history)
        except CircuitBreakerOpenException:
            logger.warning("LLM Circuit Breaker is OPEN. Falling back to original query.")
            return query


query_rewriter = QueryRewriter()
