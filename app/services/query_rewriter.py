import logging

logger = logging.getLogger("app.services.query_rewriter")


class QueryRewriter:
    async def rewrite(self, query: str, history: str = "") -> str:
        logger.info(f"Rewriting query: '{query}'")

        # Simple simulated rewrite: trim whitespace and ensure it ends cleanly
        # In production, this calls a cheap LLM model (e.g. gpt-3.5-turbo) with a system prompt
        # that incorporates previous conversation history to rephrase the question.
        rewritten = query.strip()

        # Example rephrase simulation:
        if "what is this" in rewritten.lower() and history:
            rewritten = f"Explanation of {history} based on RAG documentation"

        logger.info(f"Rewritten query output: '{rewritten}'")
        return rewritten


query_rewriter = QueryRewriter()
